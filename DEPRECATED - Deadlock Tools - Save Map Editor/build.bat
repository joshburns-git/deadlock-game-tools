@echo off

setlocal

cd /d "%~dp0"

echo Building Save Map Editor standalone executable...

python build_icon.py
python -m PyInstaller --noconfirm --clean MapEditor.spec

if errorlevel 1 (
  echo Build failed.
  exit /b 1
)

echo.
echo Done: dist\MapEditor.exe
exit /b 0
