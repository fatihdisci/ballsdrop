@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

echo Kontrol ediliyor...

where python >nul 2>&1
if errorlevel 1 (
    echo.
    echo [HATA] Python bulunamadi!
    echo https://python.org adresinden Python 3.10+ yukle
    echo Kurulumda "Add Python to PATH" secenegini isaretle
    echo.
    pause
    exit /b 1
)

where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo.
    echo [HATA] FFmpeg bulunamadi!
    echo winget install Gyan.FFmpeg  komutunu cmd'de calistir
    echo Sonra bilgisayari yeniden baslat.
    echo.
    pause
    exit /b 1
)

python -c "import pygame, pymunk, numpy" >nul 2>&1
if errorlevel 1 (
    echo Gerekli kutuphaneler yukleniyor...
    pip install pygame pymunk numpy
)

if not exist "gui.py" (
    echo [HATA] gui.py bulunamadi!
    pause
    exit /b 1
)

start "" pythonw gui.py
