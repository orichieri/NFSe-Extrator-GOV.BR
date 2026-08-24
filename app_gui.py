"""
Tela única do sistema. Rode:

    python app_gui.py

Fluxo dentro da mesma janela:
  1. Escolha o mês de referência (ou datas customizadas) no topo.
  2. Aba "1. Pagamentos e Revendas" — consulta o SQL Server das 4 lojas.
  3. Aba "2. NFS-e" — guia a extração no Emissor Nacional, loja a loja.
  4. Aba "3. Preencher planilha" — escreve tudo na aba do mês certo.

Cada aba guarda seu resultado no estado da janela (self.pagamentos,
self.revendas, self.nfse); a aba 3 só precisa que pelo menos uma parte
tenha sido preenchida — não precisa rodar as 3 etapas toda vez.
"""

import calendar
import logging
import threading
import tkinter as tk
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

import config
import configuracao
import consulta_pagamentos
import consulta_revendas
import preencher_planilha
from extrator_nfse import ExtratorFrame

logging.basicConfig(
    filename="app_gui.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


class App:
    def __init__(self):
        self.pagamentos = {}
        self.revendas = {}
        self.nfse = {}

        self.root = tk.Tk()
        self.root.title("Sistema de Faturamento / NFS-e")
        self.root.geometry("620x620")
        self.root.protocol("WM_DELETE_WINDOW", self._ao_fechar)

        self._construir_filtro_periodo()
        self._construir_abas()

        self.root.mainloop()

    # -- filtro de período (topo, compartilhado por todas as abas) ----------

    def _construir_filtro_periodo(self):
        frame = ttk.LabelFrame(self.root, text="Período")
        frame.pack(fill="x", padx=10, pady=8)

        hoje = date.today()

        ttk.Label(frame, text="Mês de referência:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.var_mes = tk.StringVar(value=config.MESES[hoje.month])
        combo_mes = ttk.Combobox(frame, textvariable=self.var_mes, state="readonly",
                                  values=list(config.MESES.values()), width=14)
        combo_mes.grid(row=0, column=1, padx=5, pady=5)
        combo_mes.bind("<<ComboboxSelected>>", lambda e: self._atualizar_datas_pelo_mes())

        ttk.Label(frame, text="Ano:").grid(row=0, column=2, padx=5, pady=5, sticky="w")
        self.var_ano = tk.StringVar(value=str(hoje.year))
        entry_ano = ttk.Entry(frame, textvariable=self.var_ano, width=6)
        entry_ano.grid(row=0, column=3, padx=5, pady=5)
        entry_ano.bind("<FocusOut>", lambda e: self._atualizar_datas_pelo_mes())

        ttk.Button(frame, text="Usar mês inteiro",
                   command=self._atualizar_datas_pelo_mes).grid(row=0, column=4, padx=8)

        ttk.Label(frame, text="Data inicial:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.var_data_ini = tk.StringVar()
        ttk.Entry(frame, textvariable=self.var_data_ini, width=12).grid(row=1, column=1, padx=5, pady=5)

        ttk.Label(frame, text="Data final:").grid(row=1, column=2, padx=5, pady=5, sticky="w")
        self.var_data_fim = tk.StringVar()
        ttk.Entry(frame, textvariable=self.var_data_fim, width=12).grid(row=1, column=3, padx=5, pady=5)

        ttk.Label(frame, text="(formato DD/MM/AAAA — editável pra período customizado)",
                  font=("Arial", 8), foreground="#666").grid(row=2, column=0, columnspan=5,
                                                              padx=5, sticky="w")

        self._atualizar_datas_pelo_mes()

    def _mes_numero(self) -> int:
        nome = self.var_mes.get()
        for numero, nome_mes in config.MESES.items():
            if nome_mes == nome:
                return numero
        raise ValueError(f"Mês inválido: {nome}")

    def _atualizar_datas_pelo_mes(self):
        try:
            ano = int(self.var_ano.get())
            mes = self._mes_numero()
            primeiro, ultimo = config.primeiro_ultimo_dia_mes(ano, mes)
            self.var_data_ini.set(primeiro.strftime("%d/%m/%Y"))
            self.var_data_fim.set(ultimo.strftime("%d/%m/%Y"))
        except ValueError:
            pass  # ano ainda incompleto sendo digitado, ignora até o foco sair

    def _obter_periodo(self):
        """Lê e valida os campos de data, devolve (data_ini, data_fim) como date."""
        try:
            data_ini = datetime.strptime(self.var_data_ini.get().strip(), "%d/%m/%Y").date()
            data_fim = datetime.strptime(self.var_data_fim.get().strip(), "%d/%m/%Y").date()
        except ValueError:
            raise ValueError("Datas inválidas — use o formato DD/MM/AAAA.")
        if data_fim < data_ini:
            raise ValueError("A data final não pode ser anterior à data inicial.")
        return data_ini, data_fim

    # -- abas -----------------------------------------------------------

    def _construir_abas(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=8)

        self._construir_aba_sql()
        self._construir_aba_nfse()
        self._construir_aba_planilha()
        self._construir_aba_configuracoes()

    # -- aba 1: pagamentos e revendas ---------------------------------------

    def _construir_aba_sql(self):
        aba = ttk.Frame(self.notebook)
        self.notebook.add(aba, text="1. Pagamentos e Revendas")

        ttk.Button(aba, text="▶ Consultar SQL Server (4 lojas)",
                   command=self._consultar_sql_thread).pack(pady=8)

        self.log_sql = scrolledtext.ScrolledText(aba, height=22, state=tk.DISABLED, wrap="word")
        self.log_sql.pack(fill="both", expand=True, padx=8, pady=8)

    def _log(self, widget, texto):
        widget.config(state=tk.NORMAL)
        widget.insert(tk.END, texto + "\n")
        widget.see(tk.END)
        widget.config(state=tk.DISABLED)

    def _consultar_sql_thread(self):
        try:
            data_ini, data_fim = self._obter_periodo()
        except ValueError as e:
            messagebox.showerror("Período inválido", str(e))
            return
        threading.Thread(target=self._consultar_sql, args=(data_ini, data_fim), daemon=True).start()

    def _consultar_sql(self, data_ini, data_fim):
        self.root.after(0, lambda: self._log(
            self.log_sql, f"=== Consultando {data_ini.strftime('%d/%m/%Y')} a "
                           f"{data_fim.strftime('%d/%m/%Y')} ==="))
        try:
            self.root.after(0, lambda: self._log(self.log_sql, "\n-- Formas de pagamento --"))
            pagamentos = {}
            for loja in config.LOJAS:
                self.root.after(0, lambda n=loja["nome"]: self._log(self.log_sql, f"Consultando {n}..."))
                dados = consulta_pagamentos.consultar_formas_pagamento(loja["emp_id"], data_ini, data_fim)
                pagamentos[loja["nome"]] = dados
                total = sum(dados.values())
                self.root.after(0, lambda n=loja["nome"], t=total, c=len(dados): self._log(
                    self.log_sql, f"  {n}: {c} forma(s), total R$ {t:,.2f}"))
            self.pagamentos = pagamentos

            self.root.after(0, lambda: self._log(self.log_sql, "\n-- Revendas --"))
            revendas = {}
            for loja in config.LOJAS:
                dados = consulta_revendas.consultar_revenda(loja["emp_id"], data_ini, data_fim)
                revendas[loja["nome"]] = dados
                self.root.after(0, lambda n=loja["nome"], d=dados: self._log(
                    self.log_sql, f"  {n}: FISCAL R$ {d['fiscal']:,.2f} / COMISSAO R$ {d['comissao']:,.2f}"))
            self.revendas = revendas

            self.root.after(0, lambda: self._log(
                self.log_sql, "\nConcluído. Vá na aba 3 quando quiser preencher a planilha "
                               "(pode ir preenchendo antes de terminar a extração de NFS-e)."))
        except Exception as e:
            logging.exception("Erro ao consultar SQL")
            self.root.after(0, lambda: self._log(self.log_sql, f"\n[ERRO] {e}"))
            self.root.after(0, lambda: messagebox.showerror("Erro na consulta SQL", str(e)))

    # -- aba 2: NFS-e ------------------------------------------------------

    def _construir_aba_nfse(self):
        aba = ttk.Frame(self.notebook)
        self.notebook.add(aba, text="2. NFS-e")

        self.extrator_frame = ExtratorFrame(aba, config.LOJAS, on_progresso=self._on_progresso_nfse)
        self.extrator_frame.pack(fill="both", expand=True, padx=8, pady=8)

    def _on_progresso_nfse(self, resultados):
        self.nfse = resultados

    # -- aba 3: preencher planilha -------------------------------------------

    def _construir_aba_planilha(self):
        aba = ttk.Frame(self.notebook)
        self.notebook.add(aba, text="3. Preencher planilha")

        frame_arquivo = ttk.Frame(aba)
        frame_arquivo.pack(fill="x", padx=8, pady=8)
        ttk.Label(frame_arquivo, text="Arquivo da planilha:").pack(side="left")
        caminho_padrao = configuracao.carregar().get("planilha_padrao", "ANALISE_NFS-E.xlsx")
        self.var_caminho_planilha = tk.StringVar(value=caminho_padrao)
        ttk.Entry(frame_arquivo, textvariable=self.var_caminho_planilha, width=40).pack(
            side="left", padx=5)
        ttk.Button(frame_arquivo, text="Procurar...", command=self._escolher_arquivo).pack(side="left")

        ttk.Button(aba, text="✚ Criar planilha nova (a partir do modelo)",
                   command=self._criar_planilha_nova).pack(pady=4)
        ttk.Label(aba, text="Use isso na primeira vez, ou no início de um ano novo — "
                             "já vem com fórmulas, cores e os 12 meses prontos.",
                  font=("Arial", 8), foreground="#666").pack()

        ttk.Button(aba, text="▶ Preencher planilha com os dados coletados",
                   command=self._preencher_planilha_thread).pack(pady=10)

        self.log_planilha = scrolledtext.ScrolledText(aba, height=16, state=tk.DISABLED, wrap="word")
        self.log_planilha.pack(fill="both", expand=True, padx=8, pady=8)

    def _criar_planilha_nova(self):
        ano = self.var_ano.get().strip() or str(date.today().year)
        caminho = filedialog.asksaveasfilename(
            title="Criar planilha nova",
            initialfile=f"ANALISE_NFS-E_{ano}.xlsx",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")])
        if not caminho:
            return
        try:
            preencher_planilha.criar_planilha_a_partir_do_modelo(caminho)
        except preencher_planilha.PlanilhaError as e:
            messagebox.showerror("Erro ao criar planilha", str(e))
            return
        self.var_caminho_planilha.set(caminho)
        messagebox.showinfo("Planilha criada",
                             f"Planilha criada em:\n{caminho}\n\nJá selecionada no campo acima.")

    def _escolher_arquivo(self):
        caminho = filedialog.askopenfilename(
            title="Escolha a planilha", filetypes=[("Excel", "*.xlsx")])
        if caminho:
            self.var_caminho_planilha.set(caminho)

    def _preencher_planilha_thread(self):
        if not self.pagamentos and not self.revendas and not self.nfse:
            resposta = messagebox.askyesno(
                "Nada consultado ainda",
                "Você ainda não consultou pagamentos/revendas nem extraiu NFS-e nesta sessão.\n"
                "Quer continuar mesmo assim (nada será escrito)?")
            if not resposta:
                return
        threading.Thread(target=self._preencher_planilha, daemon=True).start()

    def _preencher_planilha(self):
        caminho = self.var_caminho_planilha.get().strip()
        if not Path(caminho).exists():
            self.root.after(0, lambda: messagebox.showerror(
                "Arquivo não encontrado",
                f"Não encontrei o arquivo:\n{caminho}\n\n"
                "Clique em 'Procurar...' se ele já existe em outro lugar, ou em "
                "'Criar planilha nova (a partir do modelo)' se for começar do zero."))
            return

        try:
            mes = self._mes_numero()
        except ValueError as e:
            self.root.after(0, lambda: messagebox.showerror("Mês inválido", str(e)))
            return

        self.root.after(0, lambda: self._log(
            self.log_planilha, f"=== Preenchendo aba {self.var_mes.get()} em {caminho} ==="))
        try:
            relatorio = preencher_planilha.preencher_mes(
                caminho, mes, self.pagamentos, self.revendas, self.nfse)
        except preencher_planilha.PlanilhaError as e:
            self.root.after(0, lambda: self._log(self.log_planilha, f"\n[ERRO] {e}"))
            self.root.after(0, lambda: messagebox.showerror("Erro ao preencher planilha", str(e)))
            return
        except Exception as e:
            logging.exception("Erro inesperado ao preencher planilha")
            self.root.after(0, lambda: self._log(self.log_planilha, f"\n[ERRO INESPERADO] {e}"))
            self.root.after(0, lambda: messagebox.showerror("Erro inesperado", str(e)))
            return

        self.root.after(0, lambda: self._log(
            self.log_planilha, f"\nCélulas escritas: {relatorio.celulas_escritas}"))
        if relatorio.formas_nao_mapeadas:
            self.root.after(0, lambda: self._log(self.log_planilha, "\n[ATENÇÃO] formas sem linha na planilha:"))
            for loja, forma, valor in relatorio.formas_nao_mapeadas:
                self.root.after(0, lambda l=loja, f=forma, v=valor: self._log(
                    self.log_planilha, f"  - {l}: '{f}' = R$ {v:,.2f}"))
        if relatorio.lojas_sem_bloco_revenda:
            self.root.after(0, lambda: self._log(
                self.log_planilha, "\n[ATENÇÃO] lojas sem linha no bloco de revendas: "
                                    + ", ".join(relatorio.lojas_sem_bloco_revenda)))
        self.root.after(0, lambda: self._log(self.log_planilha, "\nConcluído com sucesso."))
        self.root.after(0, lambda: messagebox.showinfo("Concluído", "Planilha atualizada com sucesso!"))

    # -- aba 4: configurações -------------------------------------------------

    def _construir_aba_configuracoes(self):
        aba = ttk.Frame(self.notebook)
        self.notebook.add(aba, text="Configurações")

        dados = configuracao.carregar()

        frame_bd = ttk.LabelFrame(aba, text="Conexão com o SQL Server")
        frame_bd.pack(fill="x", padx=10, pady=10)

        self.var_cfg_server = tk.StringVar(value=dados.get("server", ""))
        self.var_cfg_database = tk.StringVar(value=dados.get("database", ""))
        self.var_cfg_usuario = tk.StringVar(value=dados.get("usuario", ""))
        self.var_cfg_senha = tk.StringVar(value=dados.get("senha", ""))
        self.var_cfg_driver = tk.StringVar(value=dados.get("odbc_driver", ""))
        self.var_cfg_trusted = tk.BooleanVar(value=dados.get("trusted_connection", False))
        self.var_cfg_trust_cert = tk.BooleanVar(value=dados.get("trust_server_certificate", True))

        linhas = [
            ("Servidor (Server name no SSMS):", self.var_cfg_server),
            ("Banco de dados:", self.var_cfg_database),
            ("Usuário:", self.var_cfg_usuario),
        ]
        for i, (rotulo, var) in enumerate(linhas):
            ttk.Label(frame_bd, text=rotulo).grid(row=i, column=0, padx=6, pady=4, sticky="w")
            ttk.Entry(frame_bd, textvariable=var, width=35).grid(row=i, column=1, padx=6, pady=4, sticky="w")

        ttk.Label(frame_bd, text="Senha:").grid(row=3, column=0, padx=6, pady=4, sticky="w")
        ttk.Entry(frame_bd, textvariable=self.var_cfg_senha, width=35, show="*").grid(
            row=3, column=1, padx=6, pady=4, sticky="w")

        ttk.Checkbutton(frame_bd, text="Usar autenticação do Windows (em vez de usuário/senha)",
                         variable=self.var_cfg_trusted).grid(row=4, column=0, columnspan=2,
                                                              padx=6, pady=4, sticky="w")

        ttk.Label(frame_bd, text="Driver ODBC:").grid(row=5, column=0, padx=6, pady=4, sticky="w")
        ttk.Entry(frame_bd, textvariable=self.var_cfg_driver, width=35).grid(
            row=5, column=1, padx=6, pady=4, sticky="w")

        ttk.Checkbutton(frame_bd, text="Confiar no certificado do servidor "
                                        "(marque se o SSMS também usa essa opção)",
                         variable=self.var_cfg_trust_cert).grid(row=6, column=0, columnspan=2,
                                                                 padx=6, pady=4, sticky="w")

        frame_planilha = ttk.LabelFrame(aba, text="Planilha")
        frame_planilha.pack(fill="x", padx=10, pady=6)
        ttk.Label(frame_planilha, text="Caminho padrão sugerido:").grid(
            row=0, column=0, padx=6, pady=6, sticky="w")
        self.var_cfg_planilha = tk.StringVar(value=dados.get("planilha_padrao", "ANALISE_NFS-E.xlsx"))
        ttk.Entry(frame_planilha, textvariable=self.var_cfg_planilha, width=35).grid(
            row=0, column=1, padx=6, pady=6, sticky="w")

        frame_acoes = ttk.Frame(aba)
        frame_acoes.pack(pady=12)
        ttk.Button(frame_acoes, text="🔌 Testar conexão",
                   command=self._testar_conexao_thread).grid(row=0, column=0, padx=6)
        ttk.Button(frame_acoes, text="💾 Salvar configurações",
                   command=self._salvar_configuracoes).grid(row=0, column=1, padx=6)

        self.lbl_status_config = ttk.Label(aba, text="", wraplength=500, justify="center")
        self.lbl_status_config.pack(pady=6)

    def _coletar_config_tela(self) -> dict:
        return {
            "server": self.var_cfg_server.get().strip(),
            "database": self.var_cfg_database.get().strip(),
            "usuario": self.var_cfg_usuario.get().strip(),
            "senha": self.var_cfg_senha.get(),
            "odbc_driver": self.var_cfg_driver.get().strip(),
            "trusted_connection": self.var_cfg_trusted.get(),
            "trust_server_certificate": self.var_cfg_trust_cert.get(),
            "planilha_padrao": self.var_cfg_planilha.get().strip(),
        }

    def _salvar_configuracoes(self):
        dados = self._coletar_config_tela()
        problemas = configuracao.validar(dados)
        if problemas:
            resposta = messagebox.askyesno(
                "Configuração incompleta",
                "Encontrei o(s) seguinte(s) problema(s):\n- " + "\n- ".join(problemas) +
                "\n\nSalvar mesmo assim? (as consultas ao banco não vão funcionar até corrigir)")
            if not resposta:
                return
        configuracao.salvar(dados)
        self.var_caminho_planilha.set(dados["planilha_padrao"])
        self.lbl_status_config.config(text="Configurações salvas.", foreground="green")

    def _testar_conexao_thread(self):
        self.lbl_status_config.config(text="Testando conexão...", foreground="blue")
        threading.Thread(target=self._testar_conexao, daemon=True).start()

    def _testar_conexao(self):
        dados = self._coletar_config_tela()
        problemas = configuracao.validar(dados)
        if problemas:
            self.root.after(0, lambda: self.lbl_status_config.config(
                text="Não testei porque faltam campos: " + "; ".join(problemas), foreground="red"))
            return
        try:
            import pyodbc
            conn = pyodbc.connect(configuracao.get_connection_string(dados), timeout=10)
            conn.close()
            self.root.after(0, lambda: self.lbl_status_config.config(
                text="Conectou com sucesso!", foreground="green"))
        except Exception as e:
            self.root.after(0, lambda: self.lbl_status_config.config(
                text=f"Falha na conexão: {e}", foreground="red"))

    # -- fechamento -------------------------------------------------------

    def _ao_fechar(self):
        try:
            self.extrator_frame.encerrar()
        except Exception:
            pass
        self.root.destroy()


if __name__ == "__main__":
    App()
