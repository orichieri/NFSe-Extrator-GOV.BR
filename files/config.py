"""
Configurações fixas do negócio — coisas que praticamente não mudam
(quais lojas existem, nomes dos meses).

A conexão com o banco (servidor/usuário/senha) e o caminho da planilha
padrão ficam em configuracao.py / configuracao.json, que são editáveis
pela aba "Configurações" do programa sem precisar mexer em código.
"""

# ---------------------------------------------------------------------------
# LOJAS (EMP_ID -> nome / coluna na planilha)
# ---------------------------------------------------------------------------
# A ordem das colunas na planilha é: MATRIZ, PRAIA DA COSTA, JARDIM DA PENHA, JARDIM CAMBURI

LOJAS = [
    {"emp_id": 1, "nome": "MATRIZ", "coluna_planilha": "B"},
    {"emp_id": 2, "nome": "PRAIA DA COSTA", "coluna_planilha": "C"},
    {"emp_id": 3, "nome": "JARDIM DA PENHA", "coluna_planilha": "D"},
    {"emp_id": 6, "nome": "JARDIM CAMBURI", "coluna_planilha": "E"},
]

# Formas de pagamento que não usamos mais — se aparecerem no resultado do
# banco (histórico antigo dentro do período consultado), são ignoradas e
# reportadas como aviso em vez de quebrar o preenchimento.
FORMAS_DESCONTINUADAS = {
    "ERRO TEF CARTAO",
    "FUNCIONAL CARD",
    "VIDA LINK",
    "CARTAO TEF",
}

# Família de produto usada na query de revendas (PRO_FAM_ID = 36 no script original)
FAM_ID_REVENDA = 36

# ---------------------------------------------------------------------------
# PLANILHA
# ---------------------------------------------------------------------------
MESES = {
    1: "JANEIRO", 2: "FEVEREIRO", 3: "MARÇO", 4: "ABRIL",
    5: "MAIO", 6: "JUNHO", 7: "JULHO", 8: "AGOSTO",
    9: "SETEMBRO", 10: "OUTUBRO", 11: "NOVEMBRO", 12: "DEZEMBRO",
}

# Arquivo "molde" (fórmulas, formatação e cores prontas, valores zerados)
# usado para criar uma planilha nova automaticamente quando o arquivo
# apontado ainda não existe (ex: começo de um ano novo).
CAMINHO_MODELO = "modelo_planilha.xlsx"


def caminho_recurso(nome_arquivo: str) -> "Path":
    """Resolve o caminho de um arquivo empacotado junto do programa.

    Funciona tanto rodando como script Python normal quanto como .exe
    compilado com PyInstaller (--onefile extrai os arquivos de --add-data
    numa pasta temporária apontada por sys._MEIPASS em tempo de execução —
    esse é o jeito documentado de achar esses arquivos de volta)."""
    import sys
    from pathlib import Path
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / nome_arquivo


def primeiro_ultimo_dia_mes(ano: int, mes: int):
    """Retorna (primeiro_dia, ultimo_dia) do mês/ano como objetos date."""
    import calendar
    from datetime import date
    primeiro = date(ano, mes, 1)
    ultimo_dia_num = calendar.monthrange(ano, mes)[1]
    ultimo = date(ano, mes, ultimo_dia_num)
    return primeiro, ultimo
