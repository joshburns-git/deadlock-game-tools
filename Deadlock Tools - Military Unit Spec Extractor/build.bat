@echo off
setlocal
cd /d "%~dp0"

echo Converting MilitaryUnitSpecExtractor.png to assets\MilitaryUnitSpecExtractor.ico...
python build_icon.py
if errorlevel 1 (
  echo Icon conversion failed.
  exit /b 1
)

echo Building Military Unit Spec Extractor standalone executable...
python -m PyInstaller --noconfirm --clean MilitaryUnitSpecExtractor.spec

if errorlevel 1 (
  echo Build failed.
  exit /b 1
)

echo.
echo Done: dist\MilitaryUnitSpecExtractor.exe
exit /b 0
