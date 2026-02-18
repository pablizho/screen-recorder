@echo off
chcp 65001 >nul 2>&1
title Установка зависимостей
color 0A

echo ══════════════════════════════════════════════
echo   УСТАНОВКА ЗАВИСИМОСТЕЙ Screen Recorder
echo ══════════════════════════════════════════════
echo.

REM --- Проверка Python ---
python --version >nul 2>&1
if errorlevel 1 (
    echo ОШИБКА: Python не найден!
    echo.
    echo 1. Скачайте с https://www.python.org/downloads/
    echo 2. При установке ОБЯЗАТЕЛЬНО поставьте галочку:
    echo    [x] Add Python to PATH
    echo 3. Перезагрузите компьютер
    echo 4. Запустите этот файл снова
    echo.
    pause
    exit /b 1
)

echo [OK] Python найден:
python --version
echo.

REM --- Обновление pip ---
echo [1/8] Обновление pip...
python -m pip install --upgrade pip
echo.

REM --- Установка пакетов по одному ---
echo [2/8] Установка numpy...
python -m pip install numpy
echo.

echo [3/8] Установка opencv-python...
python -m pip install opencv-python
echo.

echo [4/8] Установка mss...
python -m pip install mss
echo.

echo [5/8] Установка Pillow...
python -m pip install Pillow
echo.

echo [6/8] Установка keyboard...
python -m pip install keyboard
echo.

echo [7/8] Установка pygetwindow...
python -m pip install pygetwindow
echo.

echo [8/8] Установка pyaudio...
python -m pip install pyaudio
if errorlevel 1 (
    echo.
    echo PyAudio не установился стандартно, пробую другой способ...
    python -m pip install pipwin
    python -m pipwin install pyaudio
    if errorlevel 1 (
        echo.
        echo PyAudio не удалось установить.
        echo Запись звука будет недоступна.
        echo Программа будет работать БЕЗ звука.
    )
)
echo.

echo ══════════════════════════════════════════════
echo   ПРОВЕРКА УСТАНОВКИ
echo ══════════════════════════════════════════════
echo.

set "ERRORS=0"

python -c "import cv2; print('[OK] opencv-python:', cv2.__version__)" 2>nul
if errorlevel 1 (
    echo [ОШИБКА] opencv-python НЕ установлен!
    set /a ERRORS+=1
)

python -c "import numpy; print('[OK] numpy:', numpy.__version__)" 2>nul
if errorlevel 1 (
    echo [ОШИБКА] numpy НЕ установлен!
    set /a ERRORS+=1
)

python -c "import mss; print('[OK] mss')" 2>nul
if errorlevel 1 (
    echo [ОШИБКА] mss НЕ установлен!
    set /a ERRORS+=1
)

python -c "import keyboard; print('[OK] keyboard')" 2>nul
if errorlevel 1 (
    echo [ОШИБКА] keyboard НЕ установлен!
    set /a ERRORS+=1
)

python -c "from PIL import Image; print('[OK] Pillow')" 2>nul
if errorlevel 1 (
    echo [ОШИБКА] Pillow НЕ установлен!
    set /a ERRORS+=1
)

python -c "import pygetwindow; print('[OK] pygetwindow')" 2>nul
if errorlevel 1 (
    echo [ВНИМАНИЕ] pygetwindow НЕ установлен (захват окна недоступен^)
)

python -c "import pyaudio; print('[OK] pyaudio')" 2>nul
if errorlevel 1 (
    echo [ВНИМАНИЕ] pyaudio НЕ установлен (запись звука недоступна^)
)

echo.

if %ERRORS% gtr 0 (
    echo ══════════════════════════════════════════════
    echo   ЕСТЬ ОШИБКИ! Смотрите выше.
    echo   Попробуйте вручную:
    echo.
    echo   1. Откройте командную строку (cmd)
    echo   2. Введите:
    echo      python -m pip install opencv-python
    echo      python -m pip install numpy
    echo      python -m pip install mss
    echo      python -m pip install keyboard
    echo      python -m pip install Pillow
    echo ══════════════════════════════════════════════
) else (
    echo ══════════════════════════════════════════════
    echo   ВСЁ УСТАНОВЛЕНО УСПЕШНО!
    echo   Запустите start_recorder.bat
    echo ══════════════════════════════════════════════
)

echo.
pause