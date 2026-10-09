@echo off
setlocal
cd /d "%~dp0"

echo Converting ResearchEditor.png to assets\ResearchEditor.ico...
python build_icon.py
if errorlevel 1 (
  echo Icon conversion failed.
  exit /b 1
)

echo Building Research Editor standalone executable...
python -m PyInstaller --noconfirm --clean ResearchEditor.spec

if errorlevel 1 (
  echo Build failed.
  exit /b 1
)

echo.
echo Done: dist\ResearchEditor.exe
exit /b 0
