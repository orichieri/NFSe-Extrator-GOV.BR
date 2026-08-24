"""
Frame (bloco) de extração de NFS-e — pensado para ser embutido dentro da
janela única (app_gui.py), não como janela separada.

Toda a navegação/soma real fica em scraper_nfse.py; este arquivo só cuida
da tela e da tomada de decisão (avançar / repetir / pular / corrigir).
"""

import json
import logging
import os
import threading
import time
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

import scraper_nfse as scraper

logger = logging.getLogger("extrator_nfse")

ARQUIVO_RESULTADO = "nfse_resultado.json"

# Pausa entre fechar o navegador de uma loja e abrir o da próxima. Ajuda a
# evitar o bloqueio por "volume incomum de requisições" do site do Emissor
# Nacional, que é sensível a várias sessões abertas em sequência rápida.
PAUSA_ENTRE_LOJAS_SEG = 15


def fmt_moeda(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


class ExtratorFrame(ttk.Frame):
    """
    Uso:
        frame = ExtratorFrame(parent, lojas=config.LOJAS, on_progresso=callback)
        frame.pack(fill="both", expand=True)
        frame.iniciar()   # abre o navegador da primeira loja

    on_progresso(resultados_parciais: dict) é chamado toda vez que uma loja
    é confirmada, e de novo (com o dict completo) quando termina tudo — isso
    permite que a tela principal mantenha o estado atualizado sem sondar o
    frame o tempo todo.
    """

    def __init__(self, parent, lojas, on_progresso=None):
        super().__init__(parent)
        self.lojas = lojas
        self.on_progresso = on_progresso
        self.indice_loja = 0
        self.driver = None
        self._valor_pendente = None
        self._alguma_loja_ja_aberta = False  # controla se aplica pausa entre lojas
        self.resultados = self._carregar_progresso_anterior()

        ttk.Label(self, text="Extração de NFS-e — Emissor Nacional",
                  font=("Arial", 12, "bold")).pack(pady=6)

        self.lbl_loja = ttk.Label(self, text="", font=("Arial", 11, "bold"), foreground="#1565C0")
        self.lbl_loja.pack(pady=2)

        self.lbl_status = ttk.Label(self, text="Clique em 'Iniciar' para começar.",
                                     wraplength=420, justify="center")
        self.lbl_status.pack(pady=6)

        self.frame_inicio = ttk.Frame(self)
        self.btn_iniciar_tudo = ttk.Button(self.frame_inicio, text="▶ Iniciar extração",
                                            command=self.iniciar)
        self.btn_iniciar_tudo.pack(pady=4)

        self.frame_extracao = ttk.Frame(self)
        self.btn_somar = ttk.Button(self.frame_extracao, text="▶ Somar notas desta loja",
                                     command=self._iniciar_extracao_thread, state=tk.DISABLED)
        self.btn_somar.pack(pady=4)

        self.frame_confirmacao = ttk.Frame(self)
        ttk.Button(self.frame_confirmacao, text="✔ Confirmar e ir p/ próxima loja",
                   command=self._confirmar_e_avancar).grid(row=0, column=0, padx=3, pady=2)
        ttk.Button(self.frame_confirmacao, text="↻ Repetir esta loja",
                   command=self._repetir_loja).grid(row=0, column=1, padx=3, pady=2)
        ttk.Button(self.frame_confirmacao, text="✎ Digitar valor manualmente",
                   command=self._corrigir_manual).grid(row=0, column=2, padx=3, pady=2)

        self.lbl_resultado = ttk.Label(self, text="", font=("Arial", 14, "bold"), foreground="#D32F2F")
        self.lbl_resultado.pack(pady=6)

        # -- resumo editável: lista com os valores já confirmados de cada loja,
        # com botões pra editar ou limpar tudo sem precisar mexer no navegador.
        frame_resumo = ttk.LabelFrame(self, text="Valores confirmados")
        frame_resumo.pack(fill="both", expand=True, padx=4, pady=8)

        self.tabela_resumo = ttk.Treeview(frame_resumo, columns=("loja", "valor"),
                                           show="headings", height=4)
        self.tabela_resumo.heading("loja", text="Loja")
        self.tabela_resumo.heading("valor", text="Valor")
        self.tabela_resumo.column("loja", width=180)
        self.tabela_resumo.column("valor", width=140, anchor="e")
        self.tabela_resumo.pack(fill="both", expand=True, padx=4, pady=4)
        self.tabela_resumo.bind("<Double-1>", lambda e: self._editar_valor_selecionado())

        frame_botoes_resumo = ttk.Frame(frame_resumo)
        frame_botoes_resumo.pack(pady=4)
        ttk.Button(frame_botoes_resumo, text="✎ Editar valor selecionado",
                   command=self._editar_valor_selecionado).grid(row=0, column=0, padx=3)
        ttk.Button(frame_botoes_resumo, text="🗑 Limpar tudo e recomeçar",
                   command=self._confirmar_limpar_tudo).grid(row=0, column=1, padx=3)

        self.frame_inicio.pack(pady=6)
        self._pular_lojas_ja_feitas()
        self._atualiza_resumo()

    # -- progresso persistido -------------------------------------------

    def _carregar_progresso_anterior(self) -> dict:
        if os.path.exists(ARQUIVO_RESULTADO):
            try:
                with open(ARQUIVO_RESULTADO, "r", encoding="utf-8") as f:
                    dados = json.load(f)
                logger.info("Progresso anterior carregado: %s", dados)
                return dados
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Não consegui ler progresso anterior (%s), começando do zero.", e)
        return {}

    def _salvar_progresso(self):
        try:
            with open(ARQUIVO_RESULTADO, "w", encoding="utf-8") as f:
                json.dump(self.resultados, f, indent=2, ensure_ascii=False)
        except OSError as e:
            logger.error("Falha ao salvar progresso: %s", e)
            messagebox.showwarning(
                "Aviso", f"Não consegui salvar o arquivo de progresso agora ({e}).")

    def _pular_lojas_ja_feitas(self):
        while (self.indice_loja < len(self.lojas)
               and self.lojas[self.indice_loja]["nome"] in self.resultados):
            self.indice_loja += 1

    def reiniciar_do_zero(self):
        """Descarta progresso salvo (nfse_resultado.json) e recomeça pela loja 1."""
        self.resultados = {}
        self.indice_loja = 0
        if os.path.exists(ARQUIVO_RESULTADO):
            os.remove(ARQUIVO_RESULTADO)
        self._atualiza_resumo()

    # -- fluxo público ------------------------------------------------------

    def iniciar(self):
        self.frame_inicio.pack_forget()
        threading.Thread(target=self._abrir_loja_atual, daemon=True).start()

    # -- fluxo por loja ---------------------------------------------------

    def _abrir_loja_atual(self):
        self._pular_lojas_ja_feitas()
        if self.indice_loja >= len(self.lojas):
            self.after(0, self._finalizar)
            return

        loja = self.lojas[self.indice_loja]

        if self._alguma_loja_ja_aberta:
            # não é a primeira abertura da sessão — espera um pouco antes de
            # abrir o próximo navegador, pra não bater requisição em cima de
            # requisição (inclusive numa repetição depois de bloqueio).
            scraper.fechar_navegador(self.driver)
            self.driver = None
            self._aguardar_com_contagem(PAUSA_ENTRE_LOJAS_SEG, loja)
        else:
            self.after(0, lambda: self._mostra_tela_extracao(loja))
            self._abrir_navegador_da_loja(loja)

    def _aguardar_com_contagem(self, segundos_restantes: int, loja: dict):
        if segundos_restantes <= 0:
            self.after(0, lambda: self._mostra_tela_extracao(loja))
            self._abrir_navegador_da_loja(loja)
            return
        self.after(0, lambda: self.lbl_status.config(
            text=f"Aguardando {segundos_restantes}s antes de abrir o navegador da próxima loja "
                 f"({loja['nome']}) — evita bloqueio por excesso de requisições no site.",
            foreground="#B26A00"))
        self.after(0, lambda: self.lbl_loja.config(text=""))
        time.sleep(1)
        self._aguardar_com_contagem(segundos_restantes - 1, loja)

    def _abrir_navegador_da_loja(self, loja: dict):
        self._alguma_loja_ja_aberta = True
        try:
            self.driver = scraper.abrir_navegador()
            self.after(0, lambda: self.btn_somar.config(state=tk.NORMAL))
        except scraper.NavegadorIndisponivel as e:
            logger.error("Erro ao abrir navegador para %s: %s", loja["nome"], e)
            self.after(0, lambda: self.lbl_status.config(
                text=f"Erro ao abrir navegador: {e}\nClique em 'Repetir esta loja'.", foreground="red"))
            self.after(0, self._mostra_tela_confirmacao)

    def _mostra_tela_extracao(self, loja):
        self.frame_confirmacao.pack_forget()
        self.frame_extracao.pack(pady=6)
        self.lbl_loja.config(text=f"Loja atual: {loja['nome']}")
        self.lbl_status.config(
            text="1. Selecione o certificado desta loja e faça login.\n"
                 "2. Vá até 'Notas > Emitidas' e filtre pelo período.\n"
                 "3. Clique em 'Somar notas desta loja'.",
            foreground="black")
        self.lbl_resultado.config(text="")
        self.btn_somar.config(state=tk.DISABLED)

    def _mostra_tela_confirmacao(self):
        self.frame_extracao.pack_forget()
        self.frame_confirmacao.pack(pady=6)

    def _iniciar_extracao_thread(self):
        self.btn_somar.config(state=tk.DISABLED)
        threading.Thread(target=self._extrair_dados, daemon=True).start()

    def _extrair_dados(self):
        loja = self.lojas[self.indice_loja]

        def progresso(pagina):
            self.after(0, lambda: self.lbl_status.config(
                text=f"[{loja['nome']}] Lendo página {pagina}...", foreground="blue"))

        try:
            resultado = scraper.somar_periodo_completo(self.driver, callback_progresso=progresso)
            self._valor_pendente = resultado.total
            logger.info("%s: total=%.2f paginas=%d", loja["nome"], resultado.total, resultado.paginas_lidas)

            self.after(0, lambda: self.lbl_status.config(
                text=f"[{loja['nome']}] Concluído — {resultado.paginas_lidas} página(s) lida(s).",
                foreground="green"))
            self.after(0, lambda: self.lbl_resultado.config(
                text=f"TOTAL {loja['nome']}: {fmt_moeda(resultado.total)}"))
            self.after(0, self._mostra_tela_confirmacao)

        except (scraper.TabelaNaoEncontrada, scraper.ErroPaginacao,
                scraper.NavegadorIndisponivel, scraper.AcessoBloqueado) as e:
            self._trata_erro_extracao(str(e))

    def _trata_erro_extracao(self, mensagem):
        logger.warning("Erro na extração: %s", mensagem)
        self._valor_pendente = None
        self.after(0, lambda: self.lbl_status.config(text=mensagem, foreground="red"))
        self.after(0, self._mostra_tela_confirmacao)

    # -- decisões do usuário -----------------------------------------------

    def _confirmar_e_avancar(self):
        if self._valor_pendente is None:
            messagebox.showinfo("Sem valor", "Ainda não há um valor somado para confirmar. "
                                              "Repita a loja ou digite manualmente.")
            return
        loja = self.lojas[self.indice_loja]
        self.resultados[loja["nome"]] = self._valor_pendente
        self._valor_pendente = None
        self._salvar_progresso()
        self._atualiza_resumo()
        if self.on_progresso:
            self.on_progresso(dict(self.resultados))
        self.indice_loja += 1
        threading.Thread(target=self._abrir_loja_atual, daemon=True).start()

    def _repetir_loja(self):
        threading.Thread(target=self._abrir_loja_atual, daemon=True).start()

    def _corrigir_manual(self):
        loja = self.lojas[self.indice_loja]
        valor = simpledialog.askfloat(
            "Valor manual",
            f"Digite o total de NFS-e da loja {loja['nome']} (use ponto para decimais, ex: 12345.67):",
            parent=self)
        if valor is None:
            return
        self.resultados[loja["nome"]] = float(valor)
        self._salvar_progresso()
        self._atualiza_resumo()
        if self.on_progresso:
            self.on_progresso(dict(self.resultados))
        self.indice_loja += 1
        threading.Thread(target=self._abrir_loja_atual, daemon=True).start()

    def _atualiza_resumo(self):
        self.tabela_resumo.delete(*self.tabela_resumo.get_children())
        for loja in self.lojas:
            nome = loja["nome"]
            if nome in self.resultados:
                self.tabela_resumo.insert("", "end", iid=nome, values=(nome, fmt_moeda(self.resultados[nome])))
            else:
                self.tabela_resumo.insert("", "end", iid=nome, values=(nome, "— (pendente)"))

    def _editar_valor_selecionado(self):
        selecionado = self.tabela_resumo.selection()
        if not selecionado:
            messagebox.showinfo("Nada selecionado", "Clique numa loja da lista antes de editar.")
            return
        nome_loja = selecionado[0]
        valor_atual = self.resultados.get(nome_loja, 0.0)
        novo_valor = simpledialog.askfloat(
            "Editar valor",
            f"Total de NFS-e para {nome_loja} (use ponto para decimais):",
            parent=self, initialvalue=valor_atual)
        if novo_valor is None:
            return
        self.resultados[nome_loja] = float(novo_valor)
        self._salvar_progresso()
        self._atualiza_resumo()
        if self.on_progresso:
            self.on_progresso(dict(self.resultados))

    def _confirmar_limpar_tudo(self):
        if not self.resultados and self.indice_loja == 0:
            return  # já está limpo, nada a fazer
        resposta = messagebox.askyesno(
            "Limpar tudo",
            "Isso apaga todos os valores de NFS-e já confirmados nesta sessão "
            "(inclusive o arquivo de progresso salvo) e recomeça da primeira loja.\n\n"
            "Tem certeza?")
        if not resposta:
            return
        scraper.fechar_navegador(self.driver)
        self.driver = None
        self.reiniciar_do_zero()
        self.frame_extracao.pack_forget()
        self.frame_confirmacao.pack_forget()
        self.frame_inicio.pack(pady=6)
        self.lbl_loja.config(text="")
        self.lbl_resultado.config(text="")
        self.lbl_status.config(text="Clique em 'Iniciar' para começar.", foreground="black")
        if self.on_progresso:
            self.on_progresso(dict(self.resultados))

    # -- finalização --------------------------------------------------------

    def _finalizar(self):
        scraper.fechar_navegador(self.driver)
        self.frame_extracao.pack_forget()
        self.frame_confirmacao.pack_forget()
        self.lbl_status.config(text="Todas as lojas foram somadas!", foreground="green")
        self._atualiza_resumo()
        if self.on_progresso:
            self.on_progresso(dict(self.resultados))

    def encerrar(self):
        """Chamar ao fechar a janela principal, pra não deixar Chrome órfão."""
        scraper.fechar_navegador(self.driver)
