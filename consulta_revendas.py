"""
Consulta o total de revendas (produtos não manipulados) por loja no período.

Usa exatamente a query fornecida (nível de item) como subconsulta, e só soma
VL_LIQUIDO (-> coluna FISCAL) e VL_COMISSAO (-> coluna COMISSAO) por fora,
para não alterar a lógica original.

A coluna SEFAZ do bloco "ANALISE DE VENDAS DE REVENDAS" não tem fonte nesta
query — continua manual (ver preencher_planilha.py).
"""

from datetime import date
import db
import config

QUERY_BASE = """
SELECT
       PEDV_EMP_ID
      ,PEDV_ID
      ,USR_NOME
      ,PEDVI_DESCR
      ,PEDVI_VL_UNITARIO
      ,PEDVI_QTDE AS QTDE
      ,(PEDVI_VL_UNITARIO * PEDVI_QTDE) AS VL_TOTAL
      ,((PEDVI_VL_DESC + PEDVI_VL_DESC_CONV) * PEDVI_QTDE) AS PEDVI_VL_DESC
      ,(PEDVI_VL_UNITARIO * PEDVI_QTDE) - ((PEDVI_VL_DESC + PEDVI_VL_DESC_CONV) * PEDVI_QTDE) AS VL_LIQUIDO
      ,CLI_RAZAO
      ,USR_ID
      ,PEDVI_PRO_ID
      ,PEDV_DTA_EMIS
      ,CLI_FONE1
      ,PEDVI_REC_ID
      ,CASE WHEN ISNULL(PRO_COMISSAO_VENDAS,0) <> 0 THEN
                    PRO_COMISSAO_VENDAS
               ELSE ISNULL(USR_COMISSAO_VENDAS,0) END AS COMISSAO
      ,CASE WHEN ISNULL(PRO_COMISSAO_VENDAS,0) <> 0 THEN
                    (PRO_COMISSAO_VENDAS * ((PEDVI_VL_UNITARIO * PEDVI_QTDE) - ((PEDVI_VL_DESC + PEDVI_VL_DESC_CONV) * PEDVI_QTDE))) / 100
               ELSE (ISNULL(USR_COMISSAO_VENDAS,0) * ((PEDVI_VL_UNITARIO * PEDVI_QTDE) - ((PEDVI_VL_DESC + PEDVI_VL_DESC_CONV) * PEDVI_QTDE))) / 100
       END AS VL_COMISSAO
  FROM
     PEDIDO_VENDA_ITEM
       LEFT JOIN PEDIDO_VENDA ON
                 PEDV_EMP_ID = PEDVI_PEDV_EMP_ID
             AND PEDV_ID     = PEDVI_PEDV_ID
       LEFT JOIN PEDIDO_VENDA_OCOR AS USRO ON
                 USRO.PEDVO_PEDV_EMP_ID = PEDV_EMP_ID
             AND USRO.PEDVO_PEDV_ID     = PEDV_ID
             AND USRO.PEDVO_FLG_TIPO    = 0
             AND USRO.PEDVO_DTA         = (SELECT MAX(PEDVO_DTA)
                                        FROM PEDIDO_VENDA_OCOR
                                       WHERE PEDVO_PEDV_EMP_ID = PEDV_EMP_ID
                                         AND PEDVO_PEDV_ID     = PEDV_ID
                                         AND PEDVO_FLG_TIPO    = 0)
     LEFT JOIN PEDIDO_VENDA_OCOR AS DTAO ON
               DTAO.PEDVO_PEDV_EMP_ID = PEDV_EMP_ID
           AND DTAO.PEDVO_PEDV_ID     = PEDV_ID
           AND DTAO.PEDVO_FLG_TIPO    = '3'
           AND DTAO.PEDVO_DTA         = (SELECT MAX(PEDVO_DTA)
                                           FROM PEDIDO_VENDA_OCOR
                                          WHERE PEDVO_PEDV_EMP_ID = PEDV_EMP_ID
                                            AND PEDVO_PEDV_ID     = PEDV_ID
                                            AND PEDVO_FLG_TIPO    = 3)
       LEFT JOIN USUARIO ON
                 USR_ID = USRO.PEDVO_USR_ID
       LEFT JOIN CLIENTE ON
                 CLI_EMP_ID = PEDV_CLI_EMP_ID
             AND CLI_ID = PEDV_CLI_ID
       LEFT JOIN PRODUTO ON
                 PRO_ID = PEDVI_PRO_ID
       LEFT JOIN CONVENIO ON
                 CONV_ID = PEDV_CONV_ID
 WHERE PEDVI_VL_UNITARIO  > 0
   AND (PEDVI_PRO_ID IS NULL OR PEDVI_PRO_ID > 99)
   AND PEDVI_FLG_CONF = 1
   AND PEDVI_FLG_SITUACAO <> 0
   AND PEDVI_FLG_SITUACAO <> 7
   AND PEDVI_FLG_SITUACAO <> 6
   AND DTAO.PEDVO_DTA BETWEEN ? AND ?
   AND PEDV_FLG_SITUACAO = 3
   AND PEDV_EMP_ID = ?
   AND PRO_FAM_ID = ?
   AND PEDVI_PRO_ID IS NOT NULL
   AND PEDVI_DESCR <> '*** TAXA DE ENTREGA ***'
"""

QUERY_SOMA = f"""
SELECT ISNULL(SUM(VL_LIQUIDO), 0)  AS FISCAL,
       ISNULL(SUM(VL_COMISSAO), 0) AS COMISSAO
FROM ({QUERY_BASE}) AS ITENS_REVENDA
"""


def consultar_revenda(emp_id: int, data_ini: date, data_fim: date) -> dict:
    """Retorna {'fiscal': valor, 'comissao': valor} para a loja/periodo informados."""
    conn = db.conectar()
    try:
        cur = conn.cursor()
        cur.execute(
            QUERY_SOMA,
            data_ini.strftime("%Y/%m/%d"),
            data_fim.strftime("%Y/%m/%d"),
            emp_id,
            config.FAM_ID_REVENDA,
        )
        fiscal, comissao = cur.fetchone()
        return {"fiscal": float(fiscal or 0), "comissao": float(comissao or 0)}
    finally:
        conn.close()


def consultar_todas_lojas(data_ini: date, data_fim: date) -> dict:
    """Retorna {nome_loja: {'fiscal':..., 'comissao':...}} para todas as lojas."""
    dados = {}
    for loja in config.LOJAS:
        print(f"Consultando revendas — {loja['nome']} (EMP_ID={loja['emp_id']})...")
        dados[loja["nome"]] = consultar_revenda(loja["emp_id"], data_ini, data_fim)
    return dados


if __name__ == "__main__":
    from datetime import date
    import json
    di, df = date(2026, 8, 1), date(2026, 8, 6)
    print(json.dumps(consultar_todas_lojas(di, df), indent=2, ensure_ascii=False))
