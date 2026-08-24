@echo off
REM Build FINAL: --onefile (um .exe só, fácil de compartilhar) e --windowed
REM (sem janela preta de console atrás). Só use isso depois que o build de
REM teste (build_teste.bat) já funcionou sem erros.

pip install pyinstaller

pyinstaller --onefile --windowed --name "Sistema NFSe" ^
    --add-data "modelo_planilha.xlsx;." ^
    app_gui.py

echo.
echo ============================================================
echo Pronto! O executavel final esta em: dist\Sistema NFSe.exe
echo Esse arquivo (so ele) e o que voce entrega pro financeiro.
echo ============================================================
pause
