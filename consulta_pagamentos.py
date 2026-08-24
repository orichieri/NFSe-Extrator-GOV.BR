"""
Consulta os valores por forma de pagamento, por loja, no período informado.

Baseado exatamente na query fornecida (WITH UltimoVendaItem ... GROUP BY GEN_DESC),
apenas parametrizando EMP_ID e o intervalo de datas em vez de valores fixos.
"""

from datetime import date
import db
import config

QUERY = """
WITH UltimoVendaItem AS (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY MOVI_MVCX_EMP_ID, MOVI_MVCX_ID, MOVI_MOVV_NR_LANC
               ORDER BY MOVI_SEQ DESC
           ) AS PrimeiroRegistro
    FROM MOV_VENDA_ITEM
)
SELECT SUM(MVPG_VALOR) AS VALOR,
       GEN_DESC        AS FORMA
FROM MOV_VENDA
INNER JOIN UltimoVendaItem AS ITEM ON
        ITEM.MOVI_MVCX_EMP_ID  = MOVV_MVCX_EMP_ID
    AND ITEM.MOVI_MVCX_ID      = MOVV_MVCX_ID
    AND ITEM.MOVI_MOVV_NR_LANC = MOVV_NR_LANC
    AND ITEM.PrimeiroRegistro  = 1
INNER JOIN CLIENTE ON
        CLI_ID     = MOVV_CLI_ID
    AND CLI_EMP_ID = MOVV_CLI_EMP_ID
INNER JOIN OPER_CAIXA ON
        OCX_ID = ITEM.MOVI_OCX_ID
INNER JOIN MOV_VENDA_PG ON
        MVPG_MVCX_EMP_ID  = MOVV_MVCX_EMP_ID
    AND MVPG_MVCX_ID      = MOVV_MVCX_ID
    AND MVPG_MOVV_NR_LANC = MOVV_NR_LANC
INNER JOIN GENER ON
        GEN_TID = 13
    AND GEN_ID  = MVPG_GEN_ID_COND_PG
LEFT JOIN USUARIO ON
        MOVV_USR_ID = USR_ID
WHERE OCX_TIPO = 'E'
  AND MOVV_FLG_CX <= 0
  AND MOVV_DTA_VENDA BETWEEN ? AND ?
  AND MOVV_MVCX_EMP_ID = ?
  AND (MOVV_FLG_SITUACAO <> 3 AND MOVV_FLG_SITUACAO <> 4)
GROUP BY GEN_DESC
ORDER BY GEN_DESC
"""


def consultar_formas_pagamento(emp_id: int, data_ini: date, data_fim: date) -> dict:
    """
    Retorna um dict {FORMA_PAGAMENTO: valor} para a loja/periodo informados.
    Formas descontinuadas (config.FORMAS_DESCONTINUADAS) são reportadas via
    print de aviso, mas não somadas (não existem linhas pra elas na planilha
    atual, mas se aparecerem no histórico não travam o processo).
    """
    conn = db.conectar()
    try:
        cur = conn.cursor()
        cur.execute(
            QUERY,
            data_ini.strftime("%Y/%m/%d"),
            data_fim.strftime("%Y/%m/%d"),
            emp_id,
        )
        resultado = {}
        for valor, forma in cur.fetchall():
            forma = (forma or "").strip().upper()
            if forma in config.FORMAS_DESCONTINUADAS:
                print(f"  [aviso] forma de pagamento descontinuada encontrada no período: "
                      f"{forma} = {valor} (EMP_ID={emp_id}) — não incluída no mapeamento automático")
                continue
            resultado[forma] = float(valor or 0)
        return resultado
    finally:
        conn.close()


def consultar_todas_lojas(data_ini: date, data_fim: date) -> dict:
    """Retorna {nome_loja: {forma: valor}} para todas as lojas em config.LOJAS."""
    dados = {}
    for loja in config.LOJAS:
        print(f"Consultando formas de pagamento — {loja['nome']} (EMP_ID={loja['emp_id']})...")
        dados[loja["nome"]] = consultar_formas_pagamento(loja["emp_id"], data_ini, data_fim)
    return dados


if __name__ == "__main__":
    from datetime import date
    di, df = date(2026, 8, 1), date(2026, 8, 5)
    import json
    print(json.dumps(consultar_todas_lojas(di, df), indent=2, ensure_ascii=False))
