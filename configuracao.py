"""
Configurações que podem mudar (conexão com o banco, caminho da planilha
padrão) ficam num arquivo configuracao.json ao lado do programa — não
dentro do código Python.

Isso é essencial pra quando isto virar um .exe (PyInstaller): um .exe
compilado não é editável como texto, então qualquer coisa que precise
mudar depois (senha do banco, endereço do servidor, etc.) TEM que estar
num arquivo externo. A aba "Configurações" do app_gui.py edita esse JSON.
"""

import json
import sys
from pathlib import Path

PADRAO = {
    "server": "10.236.1.3",
    "database": "",
    "usuario": "sa",
    "senha": "",
    "trusted_connection": False,
    "odbc_driver": "ODBC Driver 17 for SQL Server",
    "encrypt": "optional",              # "optional", "yes" ou "no"
    "trust_server_certificate": True,
    "planilha_padrao": "ANALISE_NFS-E.xlsx",
}


def pasta_base() -> Path:
    """Pasta onde ficam configuracao.json e os arquivos de trabalho.
    Se estiver rodando como .exe (PyInstaller), usa a pasta do .exe, não
    uma pasta temporária interna."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def caminho_json() -> Path:
    return pasta_base() / "configuracao.json"


def carregar() -> dict:
    """Lê configuracao.json, preenchendo com os valores padrão qualquer
    chave que não exista (ex: depois de uma atualização do programa que
    adicionou um campo novo)."""
    dados = dict(PADRAO)
    caminho = caminho_json()
    if caminho.exists():
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                salvos = json.load(f)
            dados.update(salvos)
        except (json.JSONDecodeError, OSError) as e:
            raise RuntimeError(
                f"O arquivo {caminho} existe mas não consegui ler ({e}). "
                "Se ele estiver corrompido, apague-o — o programa recria com "
                "valores em branco na próxima abertura."
            ) from e
    return dados


def salvar(dados: dict):
    caminho = caminho_json()
    atual = carregar()
    atual.update(dados)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(atual, f, indent=2, ensure_ascii=False)


def validar(dados: dict) -> list:
    """Retorna lista de problemas (vazia se estiver tudo certo)."""
    problemas = []
    if not dados.get("server"):
        problemas.append("Servidor (endereço do SQL Server) não preenchido.")
    if not dados.get("database"):
        problemas.append("Nome do banco de dados não preenchido.")
    if not dados.get("trusted_connection"):
        if not dados.get("usuario"):
            problemas.append("Usuário do banco não preenchido.")
        if not dados.get("senha"):
            problemas.append("Senha do banco não preenchida.")
    return problemas


def get_connection_string(dados: dict = None) -> str:
    dados = dados or carregar()
    partes = [
        f"DRIVER={{{dados['odbc_driver']}}}",
        f"SERVER={dados['server']}",
        f"DATABASE={dados['database']}",
    ]
    if dados.get("trusted_connection"):
        partes.append("Trusted_Connection=yes")
    else:
        partes.append(f"UID={dados['usuario']}")
        partes.append(f"PWD={dados['senha']}")

    if dados.get("encrypt") and dados["encrypt"] != "optional":
        partes.append(f"Encrypt={dados['encrypt']}")
    if dados.get("trust_server_certificate"):
        partes.append("TrustServerCertificate=yes")

    return ";".join(partes) + ";"
