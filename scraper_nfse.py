"""
Lógica de extração do Emissor Nacional, ISOLADA da interface gráfica.

Manter isso separado do tkinter tem um motivo prático: um erro de Selenium
(elemento não encontrado, timeout, site fora do ar) não deve nunca deixar a
janela travada ou o Chrome aberto sozinho. Cada função aqui lança uma
exceção específica e previsível; quem decide o que mostrar na tela é o
extrator_nfse.py.
"""

import logging
import random
import time
from dataclasses import dataclass
from typing import Optional

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

URL_EMITIDAS = "https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas"
TIMEOUT_PADRAO = 15

# Pausa entre uma página e outra, pra não parecer um volume anormal de
# requisições pro site (o que gera bloqueio temporário — "Conexão
# Temporariamente Restrita"). Varia um pouco (não sempre o mesmo número)
# porque um intervalo idêntico toda vez também é fácil de sinalizar como
# automação. Se ainda assim bloquear com frequência, aumente esses valores.
PAUSA_ENTRE_PAGINAS_SEG = (3.0, 6.0)  # (mínimo, máximo) em segundos

# A cada N páginas, faz uma pausa mais longa — imita alguém que parou pra
# ler a tela em vez de virar página o tempo todo no mesmo ritmo.
PAGINAS_ATE_PAUSA_LONGA = 5
PAUSA_LONGA_SEG = (10.0, 18.0)

TEXTOS_BLOQUEIO = (
    "conexão temporariamente restrita",
    "volume incomum de requisições",
    "acesso foi pausado preventivamente",
)

JS_SOMA_PAGINA = """
    let total = 0;
    let linhas = document.querySelectorAll('tr[data-situacao="P100_GERADA"]');
    for (let i = 0; i < linhas.length; i++) {
        let valorTexto = linhas[i].getAttribute('data-valor');
        if (valorTexto) {
            total += parseFloat(valorTexto.replace(/\\./g, '').replace(',', '.'));
        }
    }
    return total;
"""

logger = logging.getLogger("scraper_nfse")


# --- exceções específicas ---------------------------------------------------

class NavegadorIndisponivel(Exception):
    """O Chrome não abriu, travou, ou foi fechado pelo usuário."""


class TabelaNaoEncontrada(Exception):
    """Chegou na hora de somar mas não achou a tabela de notas na tela."""


class ErroPaginacao(Exception):
    """Achou a tabela, mas não conseguiu confirmar a virada de página."""


class AcessoBloqueado(Exception):
    """O site do Emissor Nacional bloqueou temporariamente por volume de requisições."""


# --- resultado tipado, evita depender de dict solto -------------------------

@dataclass
class ResultadoExtracao:
    total: float
    paginas_lidas: int


# --- funções ------------------------------------------------------------

def abrir_navegador() -> webdriver.Chrome:
    try:
        servico = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=servico)
        driver.get(URL_EMITIDAS)
        return driver
    except WebDriverException as e:
        raise NavegadorIndisponivel(f"Falha ao abrir o Chrome: {e}") from e


def navegador_esta_vivo(driver: webdriver.Chrome) -> bool:
    """Checa se a janela ainda existe (usuário pode ter fechado na mão)."""
    try:
        _ = driver.window_handles
        return True
    except WebDriverException:
        return False


def _checar_bloqueio(driver: webdriver.Chrome):
    """Detecta a página de 'Conexão Temporariamente Restrita' do site e
    levanta um erro específico, em vez de deixar cair no erro genérico de
    'tabela não encontrada' (que confundiria a causa real)."""
    try:
        texto_pagina = driver.page_source.lower()
    except WebDriverException:
        return
    if any(trecho in texto_pagina for trecho in TEXTOS_BLOQUEIO):
        raise AcessoBloqueado(
            "O site do Emissor Nacional bloqueou o acesso temporariamente por excesso de "
            "requisições ('Conexão Temporariamente Restrita'). Isso costuma durar de 10-30 "
            "minutos. Espere um pouco antes de clicar em 'Repetir esta loja' — tentar de novo "
            "na hora só prolonga o bloqueio."
        )


def _esperar_tabela(driver: webdriver.Chrome, timeout: int = TIMEOUT_PADRAO):
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, "table tbody tr")
        )
    except TimeoutException as e:
        _checar_bloqueio(driver)  # se foi bloqueio, isso levanta AcessoBloqueado (mais específico)
        raise TabelaNaoEncontrada(
            "Nenhuma nota apareceu na tela dentro do tempo esperado. "
            "Confira se o login foi feito e se o filtro de data foi aplicado."
        ) from e


def _somar_pagina_atual(driver: webdriver.Chrome) -> float:
    try:
        valor = driver.execute_script(JS_SOMA_PAGINA)
        return float(valor or 0)
    except WebDriverException as e:
        raise NavegadorIndisponivel(f"Perdi a conexão com o navegador ao somar a página: {e}") from e


def _ir_proxima_pagina(driver: webdriver.Chrome) -> bool:
    """Retorna True se avançou de página, False se já estava na última."""
    try:
        botao_proximo = driver.find_element(By.CSS_SELECTOR, "a[data-original-title='Próxima']")
    except NoSuchElementException:
        # Site sem paginação (poucas notas) — considera como última página.
        return False

    try:
        pai_botao = botao_proximo.find_element(By.XPATH, "..")
        classe_pai = pai_botao.get_attribute("class") or ""
        if "disabled" in classe_pai:
            return False

        primeira_linha_atual = driver.find_element(
            By.CSS_SELECTOR, "table tbody tr").get_attribute("data-chave")

        driver.execute_script("arguments[0].click();", botao_proximo)

        WebDriverWait(driver, TIMEOUT_PADRAO).until(
            lambda d: d.find_element(By.CSS_SELECTOR, "table tbody tr")
            .get_attribute("data-chave") != primeira_linha_atual
        )
        return True
    except TimeoutException as e:
        _checar_bloqueio(driver)
        raise ErroPaginacao(
            "Cliquei em 'Próxima' mas a tabela não mudou. O site pode ter ficado lento."
        ) from e
    except WebDriverException as e:
        raise NavegadorIndisponivel(f"Perdi a conexão com o navegador ao paginar: {e}") from e


def somar_periodo_completo(driver: webdriver.Chrome, callback_progresso=None) -> ResultadoExtracao:
    """
    Soma todas as páginas da listagem atual (já filtrada pelo usuário).

    callback_progresso, se passado, é chamado como callback_progresso(pagina_atual)
    a cada página lida — útil pra atualizar um label na tela sem acoplar Selenium ao tkinter.

    Faz uma pausa curta e variável entre páginas (PAUSA_ENTRE_PAGINAS_SEG), e
    uma pausa mais longa a cada PAGINAS_ATE_PAUSA_LONGA páginas, pra não gerar
    um volume de requisições que pareça automação agressiva e acabe disparando
    o bloqueio temporário do site.
    """
    if not navegador_esta_vivo(driver):
        raise NavegadorIndisponivel("O navegador foi fechado antes de iniciar a extração.")

    total = 0.0
    pagina_atual = 1

    while True:
        if callback_progresso:
            callback_progresso(pagina_atual)

        _esperar_tabela(driver)
        _checar_bloqueio(driver)
        total += _somar_pagina_atual(driver)

        avancou = _ir_proxima_pagina(driver)
        if not avancou:
            break

        if pagina_atual % PAGINAS_ATE_PAUSA_LONGA == 0:
            time.sleep(random.uniform(*PAUSA_LONGA_SEG))
        else:
            time.sleep(random.uniform(*PAUSA_ENTRE_PAGINAS_SEG))
        pagina_atual += 1

    return ResultadoExtracao(total=total, paginas_lidas=pagina_atual)


def fechar_navegador(driver: Optional[webdriver.Chrome]):
    if driver is None:
        return
    try:
        driver.quit()
    except WebDriverException:
        pass  # já estava fechado, sem problema
