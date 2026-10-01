@echo off

setlocal

cd /d "%~dp0"

echo Building WAIL32 Patch standalone executable...

python -m PyInstaller --noconfirm --clean Wail32Patch.spec

if errorlevel 1 (
  echo Build failed.
  exit /b 1
)

echo.
echo Done: dist\Wail32Patch.exe
exit /b 0
