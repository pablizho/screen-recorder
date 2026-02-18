@echo off
chcp 65001 >nul 2>&1
title Диагностика
color 0E

echo ══════════════════════════════════════
echo   ДИАГНОСТИКА
echo ══════════════════════════════════════
echo.

echo --- Версия Python ---
python --version 2>&1
echo.

echo --- Путь к Python ---
where python 2>&1
echo.

echo --- Версия pip ---
python -m pip --version 2>&1
echo.

echo --- Установленные пакеты ---
python -m pip list 2>&1
echo.

echo --- Проверка модулей ---
echo.

echo Проверка cv2 (opencv)...
python -c "import cv2; print('  OK - версия:', cv2.__version__)" 2>&1
echo.

echo Проверка numpy...
python -c "import numpy; print('  OK - версия:', numpy.__version__)" 2>&1
echo.

echo Проверка mss...
python -c "import mss; print('  OK')" 2>&1
echo.

echo Проверка keyboard...
python -c "import keyboard; print('  OK')" 2>&1
echo.

echo Проверка PIL (pillow)...
python -c "from PIL import Image; print('  OK')" 2>&1
echo.

echo Проверка pyaudio...
python -c "import pyaudio; print('  OK')" 2>&1
echo.

echo Проверка pygetwindow...
python -c "import pygetwindow; print('  OK')" 2>&1
echo.

echo Проверка FFmpeg...
where ffmpeg 2>&1
echo.

echo ══════════════════════════════════════
echo   Скопируйте весь текст выше
echo   если нужна помощь
echo ══════════════════════════════════════
pause