@echo off
REM Clean previous builds
rmdir /s /q build
rmdir /s /q dist
del /q main.spec

REM Build the .exe with PyInstaller including MetaTrader5
pyinstaller --onefile --hidden-import=MetaTrader5 main.py

echo Build complete! Check the dist folder for main.exe
pause
