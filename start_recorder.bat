@echo off
chcp 65001 >nul 2>&1
title Screen Recorder
color 0B

echo ══════════════════════════════════════
echo   Запуск Screen Recorder...
echo ══════════════════════════════════════
echo.

REM Проверка Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ОШИБКА: Python не найден!
    echo Скачайте с https://www.python.org
    pause
    exit /b 1
)

REM Проверка зависимостей
python -c "import cv2, mss, numpy, keyboard" >nul 2>&1
if errorlevel 1 (
    echo Не все библиотеки установлены.
    echo Запускаю установку...
    echo.
    call "%~dp0install_deps.bat"
)

REM Запуск программы
cd /d "%~dp0"
python recorder.py

if errorlevel 1 (
    echo.
    echo Произошла ошибка при запуске.
    echo Попробуйте запустить install_deps.bat
    pause
)