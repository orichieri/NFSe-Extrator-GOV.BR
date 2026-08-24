"""
Preenche a planilha ANALISE_NFS-E.xlsx com os dados consultados.

Regras de segurança adotadas aqui (para reduzir risco de estragar a planilha):
  - Nunca escreve por cima de uma célula que já contém FÓRMULA — se a
    posição mapeada tiver algo começando com "=", para tudo com erro claro
    em vez de sobrescrever silenciosamente.
  - Os rótulos das linhas (coluna A) são lidos DINAMICAMENTE da própria aba,
    não fixados por número de linha — se a estrutura mudar de um mês pro
    outro, o programa avisa em vez de escrever na linha errada.
  - Formas de pagamento vindas do banco que não têm linha correspondente na
    planilha são reportadas, nunca descartadas silenciosamente.
  - Antes de sobrescrever o arquivo original, salva um backup com timestamp.
  - Nunca mexe em fórmulas existentes — só nas células de valor.
"""

import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import openpyxl

import config


class PlanilhaError(Exception):
    """Erro de estrutura/validação da planilha — sinal para parar e checar na mão."""


@dataclass
class RelatorioPreenchimento:
    formas_nao_mapeadas: list = field(default_factory=list)   # [(loja, forma, valor)]
    lojas_sem_bloco_revenda: list = field(default_factory=list)
    celulas_escritas: int = 0


def _fazer_backup(caminho: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = caminho.with_name(f"{caminho.stem}_backup_{ts}{caminho.suffix}")
    shutil.copy2(caminho, destino)
    return destino


def _mapa_formas_pagamento(ws) -> dict:
    """Lê a coluna A do bloco 'FORMA DE PAGAMENTO' (linha 4 até o TOTAL) e
    devolve {RÓTULO_MAIÚSCULO: número_da_linha}."""
    mapa = {}
    linha = 4
    while True:
        valor = ws[f"A{linha}"].value
        if valor is None:
            linha += 1
            if linha > 4 + 40:  # trava de segurança, nunca deveria chegar aqui
                raise PlanilhaError("Não encontrei a linha 'TOTAL' do bloco de formas de "
                                     "pagamento — estrutura da aba parece diferente do esperado.")
            continue
        if str(valor).strip().upper() == "TOTAL":
            break
        mapa[str(valor).strip().upper()] = linha
        linha += 1
    return mapa


def _achar_linha_por_rotulo(ws, rotulo: str, coluna: str = "A", max_linha: int = 45) -> int:
    alvo = rotulo.strip().upper()
    for linha in range(1, max_linha + 1):
        valor = ws[f"{coluna}{linha}"].value
        if valor is not None and str(valor).strip().upper() == alvo:
            return linha
    raise PlanilhaError(f"Não encontrei a linha com rótulo '{rotulo}' na coluna {coluna}.")


def _checar_celula_livre(ws, coordenada: str):
    atual = ws[coordenada].value
    if isinstance(atual, str) and atual.startswith("="):
        raise PlanilhaError(
            f"A célula {coordenada} já contém uma fórmula ({atual}) — "
            "abortando para não sobrescrever. Confira o mapeamento de linhas."
        )


def criar_planilha_a_partir_do_modelo(caminho_destino: str) -> Path:
    """Copia o modelo (fórmulas/formatação prontas, valores zerados) para
    criar uma planilha nova do zero. Levanta PlanilhaError se o modelo não
    for encontrado (não deveria acontecer numa instalação normal)."""
    modelo = config.caminho_recurso(config.CAMINHO_MODELO)
    if not modelo.exists():
        raise PlanilhaError(
            f"Arquivo modelo '{modelo.name}' não encontrado na pasta do programa "
            f"({modelo.parent}). Reinstale o programa ou copie o modelo pra lá."
        )
    destino = Path(caminho_destino)
    if destino.exists():
        raise PlanilhaError(f"Já existe um arquivo em {destino} — não vou sobrescrever.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(modelo, destino)
    return destino


def preencher_mes(
    caminho_planilha: str,
    mes: int,
    pagamentos: dict,       # {loja: {forma: valor}}
    revendas: dict,         # {loja: {'fiscal': valor, 'comissao': valor}}
    nfse: dict,              # {loja: valor}
    fazer_backup: bool = True,
) -> RelatorioPreenchimento:
    caminho = Path(caminho_planilha)
    if not caminho.exists():
        raise PlanilhaError(
            f"Arquivo não encontrado: {caminho}\n"
            "Confira se o nome/caminho está certo e se o arquivo está na mesma pasta do script "
            "(ou use o caminho completo)."
        )

    nome_aba = config.MESES.get(mes)
    if nome_aba is None:
        raise PlanilhaError(f"Mês inválido: {mes}")

    if fazer_backup:
        backup = _fazer_backup(caminho)
        print(f"Backup criado em: {backup}")

    wb = openpyxl.load_workbook(caminho)  # mantém fórmulas como texto (não usar data_only aqui)
    if nome_aba not in wb.sheetnames:
        raise PlanilhaError(
            f"A aba '{nome_aba}' não existe na planilha. Abas encontradas: {wb.sheetnames}.\n"
            "Isso normalmente acontece quando o arquivo apontado não é a planilha real "
            "(ex: um Excel novo/vazio, que só tem a aba 'Sheet' por padrão) — confira o "
            "caminho do arquivo selecionado."
        )
    ws = wb[nome_aba]

    relatorio = RelatorioPreenchimento()
    colunas_loja = {loja["nome"]: loja["coluna_planilha"] for loja in config.LOJAS}

    # --- 1. formas de pagamento -------------------------------------------------
    mapa_formas = _mapa_formas_pagamento(ws)
    for loja_nome, formas in pagamentos.items():
        coluna = colunas_loja.get(loja_nome)
        if coluna is None:
            raise PlanilhaError(f"Loja '{loja_nome}' não está em config.LOJAS.")
        for forma, valor in formas.items():
            linha = mapa_formas.get(forma.strip().upper())
            if linha is None:
                relatorio.formas_nao_mapeadas.append((loja_nome, forma, valor))
                continue
            coord = f"{coluna}{linha}"
            _checar_celula_livre(ws, coord)
            ws[coord] = round(float(valor), 2)
            relatorio.celulas_escritas += 1

    # --- 2. revendas (linha "REVENDAS" no bloco de cima) ------------------------
    linha_revendas = _achar_linha_por_rotulo(ws, "REVENDAS")
    for loja_nome, dados in revendas.items():
        coluna = colunas_loja.get(loja_nome)
        if coluna is None:
            raise PlanilhaError(f"Loja '{loja_nome}' não está em config.LOJAS.")
        coord = f"{coluna}{linha_revendas}"
        _checar_celula_livre(ws, coord)
        ws[coord] = round(float(dados["fiscal"]), 2)
        relatorio.celulas_escritas += 1

    # --- 3. NFS-e ----------------------------------------------------------------
    linha_nfse = _achar_linha_por_rotulo(ws, "NFS-E")
    for loja_nome, valor in nfse.items():
        coluna = colunas_loja.get(loja_nome)
        if coluna is None:
            raise PlanilhaError(f"Loja '{loja_nome}' não está em config.LOJAS.")
        coord = f"{coluna}{linha_nfse}"
        _checar_celula_livre(ws, coord)
        ws[coord] = round(float(valor), 2)
        relatorio.celulas_escritas += 1

    # --- 4. bloco "ANALISE DE VENDAS DE REVENDAS" (FISCAL / COMISSAO) -----------
    # SEFAZ (coluna D deste bloco) fica de fora: não há query pra ela ainda.
    for loja_nome, dados in revendas.items():
        try:
            linha = _achar_linha_por_rotulo(ws, loja_nome, coluna="A")
        except PlanilhaError:
            relatorio.lojas_sem_bloco_revenda.append(loja_nome)
            continue
        for coluna_bloco, chave in (("B", "fiscal"), ("C", "comissao")):
            coord = f"{coluna_bloco}{linha}"
            _checar_celula_livre(ws, coord)
            ws[coord] = round(float(dados[chave]), 2)
            relatorio.celulas_escritas += 1

    wb.save(caminho)
    return relatorio


if __name__ == "__main__":
    # Teste manual rápido com dados fictícios — não roda automaticamente no app_gui.py
    if not Path("teste_planilha.xlsx").exists():
        print("Não encontrei 'teste_planilha.xlsx' nesta pasta.")
        print("Pra testar sem risco: copie o arquivo ANALISE_NFS-E.xlsx pra esta pasta,")
        print("faça uma cópia dele e renomeie a cópia para 'teste_planilha.xlsx', depois rode de novo.")
        raise SystemExit(1)

    exemplo_pagamentos = {
        "MATRIZ": {"DEPOSITO": 1000.0, "DINHEIRO": 200.5, "PIX POS": 50.25},
        "PRAIA DA COSTA": {"DEPOSITO": 500.0},
        "JARDIM DA PENHA": {},
        "JARDIM CAMBURI": {},
    }
    exemplo_revendas = {
        "MATRIZ": {"fiscal": 300.0, "comissao": 15.0},
        "PRAIA DA COSTA": {"fiscal": 0.0, "comissao": 0.0},
        "JARDIM DA PENHA": {"fiscal": 0.0, "comissao": 0.0},
        "JARDIM CAMBURI": {"fiscal": 0.0, "comissao": 0.0},
    }
    exemplo_nfse = {
        "MATRIZ": 400000.0, "PRAIA DA COSTA": 150000.0,
        "JARDIM DA PENHA": 90000.0, "JARDIM CAMBURI": 80000.0,
    }
    rel = preencher_mes("teste_planilha.xlsx", 8, exemplo_pagamentos, exemplo_revendas, exemplo_nfse)
    print("Células escritas:", rel.celulas_escritas)
    print("Formas não mapeadas:", rel.formas_nao_mapeadas)
    print("Lojas sem bloco revenda:", rel.lojas_sem_bloco_revenda)
