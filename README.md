# Sistema de análise de faturamento / NFS-e

Automatiza o preenchimento da planilha de faturamento: consulta as formas de
pagamento e as revendas direto no SQL Server, guia a extração das NFS-e no
Emissor Nacional, e escreve tudo na aba do mês certo — numa única tela.

## Arquivos

| Arquivo | O que faz |
|---|---|
| `app_gui.py` | **Tela única — é este que você roda.** |
| `configuracao.py` | Lê/grava `configuracao.json` (conexão com o banco, planilha padrão) |
| `config.py` | Coisas fixas do negócio: lojas, meses, caminho do modelo |
| `db.py` | Abre a conexão pyodbc usando `configuracao.json` |
| `consulta_pagamentos.py` | Query de formas de pagamento, por loja |
| `consulta_revendas.py` | Query de revendas (FISCAL/COMISSAO), por loja |
| `scraper_nfse.py` | Navegação/soma no site do Emissor Nacional (sem tela) |
| `extrator_nfse.py` | Bloco de tela da extração de NFS-e, encaixado em `app_gui.py` |
| `preencher_planilha.py` | Escreve os valores na aba do mês certo + cria planilha nova a partir do modelo |
| `modelo_planilha.xlsx` | Planilha "molde": fórmulas, cores e os 12 meses prontos, valores zerados |

## Instalação (uma vez só)

1. Instale o Python 3.10+ se ainda não tiver: https://www.python.org/downloads/
   (marque a opção "Add Python to PATH" no instalador)
2. Instale o **driver ODBC do SQL Server** (se o PC já roda o sistema de
   vendas, provavelmente já está instalado):
   https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server
3. Abra o terminal (cmd/PowerShell) nesta pasta e rode:
   ```
   pip install -r requirements.txt
   ```
4. Rode `python app_gui.py`, vá na aba **"Configurações"** e preencha:
   servidor, banco, usuário, senha (os mesmos dados da tela de conexão do
   SSMS) — clique em "Testar conexão" antes de salvar, pra confirmar que
   está tudo certo. Isso fica salvo em `configuracao.json`, você não
   precisa mexer em nenhum arquivo `.py`.

## Uso mensal

```
python app_gui.py
```

1. **Período** (topo): escolha o mês — as datas preenchem sozinhas com o mês
   inteiro, mas dá pra editar pra um período customizado.
2. **Aba "1. Pagamentos e Revendas"**: consulta as 4 lojas automaticamente.
3. **Aba "2. NFS-e"**: guia a extração loja a loja. Depois de confirmado,
   qualquer valor pode ser **editado** (clique duplo na lista) ou você pode
   digitar um valor na mão pra uma loja sem precisar abrir o navegador pra
   ela. O botão **"Limpar tudo e recomeçar"** apaga tudo e começa do zero.
4. **Aba "3. Preencher planilha"**: se ainda não existe uma planilha pro
   ano, clique em **"Criar planilha nova (a partir do modelo)"** — ela já
   nasce com fórmulas, os 12 meses e as cores (verde/vermelho no RESULTADO)
   prontos. Depois é só clicar em preencher — faz backup automático antes
   de salvar.

## O que NÃO é automatizado (por enquanto)

- **Coluna SEFAZ** do bloco "ANALISE DE VENDAS DE REVENDAS" — não existe
  query fornecida pra isso ainda, continua manual (edite direto no Excel).
- **Login/certificado no Emissor Nacional** — o site não guarda sessão entre
  lojas diferentes, então a seleção do certificado é sempre manual.
- **Formas de pagamento descontinuadas** (ERRO TEF CARTAO, FUNCIONAL CARD,
  VIDA LINK, CARTAO TEF) — se aparecerem no histórico, são ignoradas e
  avisadas na tela, não somadas em nenhuma linha.

## Transformando em .exe (pra entregar pro financeiro)

**Importante:** isso precisa ser feito rodando no **Windows** — o PyInstaller
não compila de um sistema pro outro. Rode os passos abaixo no seu PC (ou no
do financeiro), não é algo que eu gero por aqui.

### 1. Build de teste primeiro

Dê duplo clique em `build_teste.bat` (ou rode ele no terminal). Ele gera um
`.exe` com console visível — se algo der errado, o erro aparece na tela
preta em vez de o programa simplesmente fechar sem explicação. Isso poupa
muito tempo de debug em relação a já ir direto pro build final.

Depois de rodar, abra `dist\Sistema NFSe (teste)\Sistema NFSe (teste).exe`
e teste o programa inteiro: consultar SQL, abrir o navegador de NFS-e,
criar uma planilha nova, preencher. Se der algum erro, me manda a mensagem
do console.

### 2. Build final

Só depois que o de teste funcionar 100%, rode `build_final.bat`. Esse gera
um único arquivo `dist\Sistema NFSe.exe`, sem console (janela limpa) — é
esse arquivo, sozinho, que você entrega pro financeiro.

### Pontos de atenção

- **`--add-data "modelo_planilha.xlsx;."`** (já incluído nos dois scripts)
  é essencial — sem isso, o botão "Criar planilha nova" não funciona no
  `.exe`. No Windows o separador é `;`; seria `:` no Linux/Mac.
- **`configuracao.json` e `nfse_resultado.json`** são criados do lado de
  fora do `.exe`, na mesma pasta onde ele está (`configuracao.pasta_base()`
  detecta automaticamente que está rodando empacotado) — não precisa se
  preocupar com isso, mas por isso o `.exe` não pode ficar solto direto
  na Área de Trabalho sem estar numa pasta própria (ele vai criar esses
  arquivos ao lado dele).
- **Antivírus / SmartScreen do Windows** costuma marcar um `.exe` recém-criado
  pelo PyInstaller como suspeito na primeira execução, só por não reconhecer
  o arquivo ainda (não é um problema real) — a opção "Mais informações" →
  "Executar assim mesmo" resolve. Avise o financeiro disso com antecedência.
- **Chrome precisa estar instalado** no PC de quem for usar (o Selenium
  controla o Chrome existente, não vem embutido no `.exe`).
- **Primeira execução precisa de internet**: o `webdriver-manager` baixa o
  driver do Chrome certo pra versão instalada na primeira vez que abre a
  aba de NFS-e. Se o PC do financeiro tiver firewall restritivo, teste isso
  especificamente — se travar, me avise que existe uma alternativa (fixar
  a versão do driver manualmente).
- Teste sempre **no mesmo PC (ou pelo menos no mesmo tipo de rede) de quem
  vai usar de verdade** antes de considerar pronto — o `.exe` precisa
  alcançar o SQL Server pela rede interna.

### Distribuindo pro financeiro

Crie uma pasta (ex: `Sistema NFSe\`), coloque `Sistema NFSe.exe` dentro dela
e mande a pasta toda (não só o `.exe` solto) — assim `configuracao.json` e
as planilhas criadas ficam organizados num lugar só. Na primeira vez, ele
abre a aba "Configurações" e preenche os dados de conexão — depois disso
fica salvo, não precisa preencher de novo.



## Testando sem mexer no arquivo real

`preencher_planilha.py` tem um teste embutido com dados fictícios. Pra usar:
copie o modelo (`copy modelo_planilha.xlsx teste_planilha.xlsx` no Windows)
e rode `python preencher_planilha.py`.

## Sobre fechar o programa

Feche sempre pelo **X da janela**. Se você fechar apertando Ctrl+C no
terminal em vez disso, aparece um erro `KeyboardInterrupt` no console — não
é um bug, é só o Python avisando que foi interrompido à força; nenhum dado
é perdido, mas o navegador pode ficar aberto sem fechar direito.

## Publicando no GitHub

Recomendo **repositório privado** — mesmo com `.gitignore` bloqueando os
arquivos sensíveis, as *queries* SQL revelam a estrutura interna do banco
(nomes de tabela, colunas, regras de negócio), e isso não precisa ser
público.

O `.gitignore` já incluído bloqueia automaticamente: `configuracao.json`
(tem a senha do banco), qualquer planilha real (`*.xlsx`, com exceção do
`modelo_planilha.xlsx`, que não tem dado nenhum), backups, caches e logs.
Antes do primeiro commit, confira o que *seria* enviado:

```
git status
```

Se aparecer `configuracao.json` ou algum `ANALISE_NFS-E...xlsx` na lista,
**pare** e confira o `.gitignore` antes de continuar — não eram pra estar ali.

### Passo a passo (linha de comando)

1. Instale o Git, se ainda não tiver: https://git-scm.com/download/win
2. Crie o repositório no site do GitHub (botão "New repository") —
   marque **Private**, e NÃO marque "Add a README" (você já tem um).
3. No terminal, dentro da pasta do projeto:
   ```
   git init
   git add -A
   git status
   ```
   Confira a lista (passo acima) antes de prosseguir.
   ```
   git commit -m "Primeira versão do sistema"
   git branch -M main
   git remote add origin https://github.com/SEU_USUARIO/NOME_DO_REPO.git
   git push -u origin main
   ```
4. Da próxima vez que mudar algo, é só:
   ```
   git add -A
   git commit -m "Descrição do que mudou"
   git push
   ```

Na primeira vez que o Git pedir login, o GitHub não aceita mais senha da
conta direto no terminal — ele vai pedir um **Personal Access Token** (crie
em GitHub → Settings → Developer settings → Personal access tokens) ou vai
abrir uma janela de login pelo navegador, dependendo de como o Git está
configurado no PC.

### Alternativa mais visual: GitHub Desktop

Se preferir não usar linha de comando pra isso: https://desktop.github.com/
— instala, faz login com sua conta do GitHub, "Add local repository" apontando
pra essa pasta, e os botões "Commit" / "Push" fazem o mesmo que os comandos
acima, com uma tela mostrando exatamente quais arquivos vão ser enviados
(boa forma de checar visualmente que nenhuma planilha real ou senha está
na lista antes de confirmar).

### Depois de clonar em outro PC

Quem clonar o repositório não vai ter `configuracao.json` (fica de fora de
propósito) — é só abrir `python app_gui.py`, ir na aba "Configurações" e
preencher os dados de conexão de novo. Também não vai ter nenhuma planilha
real — use o botão "Criar planilha nova (a partir do modelo)" ou copie uma
existente pra pasta.

