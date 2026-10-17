@echo off
echo A instalar ferramentas e a criar o executavel (so e preciso fazer isto uma vez)...
pip install flask segno pyinstaller
pyinstaller --onefile --name Inventario app.py
echo.
echo Pronto! O programa esta em: dist\Inventario.exe
echo Copia esse ficheiro para onde quiseres e faz duplo clique.
pause
