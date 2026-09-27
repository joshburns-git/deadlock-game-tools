@echo off
setlocal
cd /d "%~dp0"

echo Converting SpriteExtractor.png to assets\SpriteExtractor.ico...
python build_icon.py
if errorlevel 1 (
  echo Icon conversion failed.
  exit /b 1
)

echo Building Sprite Extractor standalone executable...
python -m PyInstaller --noconfirm --clean SpriteExtractor.spec

if errorlevel 1 (
  echo Build failed.
  exit /b 1
)

echo.
echo Done: dist\SpriteExtractor.exe
exit /b 0
