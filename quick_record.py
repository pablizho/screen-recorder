"""
Быстрая запись экрана без GUI
F9 — начать/остановить запись
F11 — пауза/продолжить
F12 — выход
"""

import time
import os
import sys
import subprocess
import threading
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import mss
import keyboard

# Курсор
try:
    from cursor_utils import CursorCapture
    cursor_capture = CursorCapture()
    CURSOR_AVAILABLE = True
except ImportError:
    cursor_capture = None
    CURSOR_AVAILABLE = False
    print("cursor_utils.py не найден — курсор не будет виден")

# Настройки
FPS = 30
CODEC = "libx265"
CRF = 20
PRESET = "fast"
OUTPUT_DIR = str(Path.home() / "Videos" / "ScreenRecorder")
MONITOR = 0
SHOW_CURSOR = True
HIGHLIGHT_CLICKS = True

# Состояние
recording = False
paused = False
writer = None
record_thread = None
frame_count = 0


def record_screen(output_path):
    global recording, paused, writer, frame_count

    frame_duration = 1.0 / FPS
    frame_count = 0

    with mss.mss() as sct:
        monitor = sct.monitors[MONITOR]
        width = monitor["width"]
        height = monitor["height"]

        if width % 2 != 0:
            width -= 1
        if height % 2 != 0:
            height -= 1

        temp_video = output_path + "_temp.avi"
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        writer = cv2.VideoWriter(temp_video, fourcc, FPS, (width, height))

        start_time = time.time()

        print(f"\n● ЗАПИСЬ НАЧАТА ({width}x{height} @ {FPS}fps)")
        if CURSOR_AVAILABLE and SHOW_CURSOR:
            print("  Курсор: ДА")
        else:
            print("  Курсор: НЕТ")
        print(f"  F9 — стоп | F11 — пауза")

        while recording:
            loop_start = time.time()

            if paused:
                time.sleep(0.05)
                continue

            try:
                screenshot = sct.grab(monitor)
                frame = np.array(screenshot)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                frame = frame[:height, :width]

                # ===== КУРСОР =====
                if SHOW_CURSOR and CURSOR_AVAILABLE:
                    frame = cursor_capture.draw_cursor_on_frame(frame, monitor)

                    if HIGHLIGHT_CLICKS:
                        frame = cursor_capture.draw_click_highlight(frame, monitor)
                # ==================

                writer.write(frame)
                frame_count += 1

                elapsed = time.time() - start_time
                mins = int(elapsed // 60)
                secs = int(elapsed % 60)
                actual_fps = frame_count / max(elapsed, 0.1)
                print(f"\r  ● {mins:02d}:{secs:02d} | "
                      f"Кадров: {frame_count} | "
                      f"FPS: {actual_fps:.1f}   ", end="", flush=True)

            except Exception as e:
                print(f"\nОшибка: {e}")
                continue

            sleep_time = frame_duration - (time.time() - loop_start)
            if sleep_time > 0:
                time.sleep(sleep_time)

        writer.release()
        elapsed = time.time() - start_time

        print(f"\n\n⏳ Обработка видео (FFmpeg)...")

        try:
            cmd = [
                "ffmpeg", "-y",
                "-i", temp_video,
                "-c:v", CODEC,
                "-crf", str(CRF),
                "-preset", PRESET,
                "-movflags", "+faststart",
                "-an",
                output_path
            ]

            if CODEC == "libx265":
                cmd.insert(-1, "-tag:v")
                cmd.insert(-1, "hvc1")

            subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            os.remove(temp_video)

            if os.path.exists(output_path):
                size_mb = os.path.getsize(output_path) / (1024 * 1024)
                print(f"✓ Сохранено: {output_path}")
                print(f"  Длительность: {int(elapsed // 60):02d}:{int(elapsed % 60):02d}")
                print(f"  Размер: {size_mb:.1f} МБ")

        except FileNotFoundError:
            import shutil
            raw = output_path.rsplit('.', 1)[0] + '.avi'
            shutil.copy2(temp_video, raw)
            print(f"FFmpeg не найден. Сохранено: {raw}")

    print(f"\nF9 — новая запись | F12 — выход")


def toggle_record():
    global recording, record_thread

    if not recording:
        recording = True
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        now = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        output_path = os.path.join(OUTPUT_DIR, f"recording_{now}.mp4")
        record_thread = threading.Thread(target=record_screen,
                                          args=(output_path,), daemon=True)
        record_thread.start()
    else:
        recording = False


def toggle_pause():
    global paused
    if recording:
        paused = not paused
        if paused:
            print("\n⏸ ПАУЗА")
        else:
            print("\n● ПРОДОЛЖЕНИЕ")


def main():
    print("╔══════════════════════════════════════════╗")
    print("║     Quick Screen Recorder                ║")
    print("╠══════════════════════════════════════════╣")
    print("║  F9  — Начать / Остановить запись        ║")
    print("║  F11 — Пауза / Продолжить               ║")
    print("║  F12 — Выход                             ║")
    print("╠══════════════════════════════════════════╣")
    print(f"║  FPS: {FPS} | Кодек: {CODEC} | CRF: {CRF}")
    print(f"║  Курсор: {'ДА' if SHOW_CURSOR and CURSOR_AVAILABLE else 'НЕТ'}")
    print(f"║  Подсветка кликов: {'ДА' if HIGHLIGHT_CLICKS else 'НЕТ'}")
    print(f"║  Папка: {OUTPUT_DIR}")
    print("╚══════════════════════════════════════════╝")
    print()
    print("Ожидание... Нажмите F9 для начала записи.")

    keyboard.add_hotkey('F9', toggle_record)
    keyboard.add_hotkey('F11', toggle_pause)
    keyboard.wait('F12')

    global recording
    if recording:
        recording = False
        time.sleep(2)

    print("\nВыход.")


if __name__ == "__main__":
    main()