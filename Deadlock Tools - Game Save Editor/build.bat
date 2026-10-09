@echo off
setlocal
cd /d "%~dp0"

echo Converting GameSaveEditor.png to assets\GameSaveEditor.ico...
python build_icon.py
if errorlevel 1 (
  echo Icon conversion failed.
  exit /b 1
)

echo Building Game Save Editor standalone executable...
python -m PyInstaller --noconfirm --clean GameSaveEditor.spec

if errorlevel 1 (
  echo Build failed.
  exit /b 1
)

echo.
echo Done: dist\GameSaveEditor.exe
exit /b 0
