@echo off
REM Build de TESTE: mantém o console aberto (mostra erros/tracebacks) e usa
REM --onedir (inicia mais rápido que --onefile, bom pra ficar testando).
REM Use isso enquanto ainda está validando se tudo funciona empacotado.

pip install pyinstaller

pyinstaller --onedir --name "Sistema NFSe (teste)" ^
    --add-data "modelo_planilha.xlsx;." ^
    app_gui.py

echo.
echo ============================================================
echo Pronto! Abra: dist\Sistema NFSe (teste)\Sistema NFSe (teste).exe
echo Se der erro, ele aparece no console (essa janela preta) —
echo copie a mensagem e me mande.
echo ============================================================
pause
