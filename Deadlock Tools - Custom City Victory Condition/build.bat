@echo off

setlocal

cd /d "%~dp0"



echo Building Custom City Victory Condition standalone executable...

python -m PyInstaller --noconfirm --clean CityVictory.spec



if errorlevel 1 (

  echo Build failed.

  exit /b 1

)



echo.

echo Done: dist\CityVictory.exe

exit /b 0
