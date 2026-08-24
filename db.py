"""Conexão com o SQL Server via pyodbc, usando configuracao.json."""

import pyodbc
import configuracao


def conectar():
    """Abre e retorna uma conexão pyodbc com o banco configurado em configuracao.json."""
    dados = configuracao.carregar()
    problemas = configuracao.validar(dados)
    if problemas:
        raise RuntimeError(
            "Configuração de conexão incompleta:\n  - " + "\n  - ".join(problemas) +
            "\n\nPreencha isso na aba 'Configurações' do programa."
        )

    conn_str = configuracao.get_connection_string(dados)
    try:
        return pyodbc.connect(conn_str, timeout=15)
    except pyodbc.Error as e:
        raise RuntimeError(
            "Não foi possível conectar ao SQL Server.\n"
            f"Servidor: {dados['server']} / Banco: {dados['database']}\n"
            f"Erro original: {e}\n\n"
            "Verifique:\n"
            f" 1. Se o driver ODBC está instalado (deve aparecer '{dados['odbc_driver']}' "
            "ao rodar: python -c \"import pyodbc; print(pyodbc.drivers())\")\n"
            " 2. Se servidor/banco/usuário/senha na aba 'Configurações' estão corretos\n"
            " 3. Se esta máquina tem acesso de rede ao servidor (VPN/rede interna)\n"
        ) from e
