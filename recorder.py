"""
╔══════════════════════════════════════════════╗
║     SCREEN RECORDER v2.0                      ║
║     Запись экрана с GUI интерфейсом           ║
║     Поддержка: экран, область, окно, звук     ║
╚══════════════════════════════════════════════╝
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import time
import os
import subprocess
import sys
import json
import wave
import struct
from datetime import datetime
from pathlib import Path

# Проверка и импорт зависимостей
try:
    import cv2
    import numpy as np
    import mss
    import mss.tools
    import keyboard
except ImportError as e:
    print(f"Ошибка импорта: {e}")
    print("Запустите install_deps.bat для установки зависимостей")
    input("Нажмите Enter...")
    sys.exit(1)

try:
    import pyaudio
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    print("PyAudio не установлен - запись звука недоступна")

try:
    import pygetwindow as gw
    WINDOW_CAPTURE_AVAILABLE = True
except ImportError:
    WINDOW_CAPTURE_AVAILABLE = False
    print("pygetwindow не установлен - захват окна недоступен")


class Config:
    """Управление настройками"""
    DEFAULT = {
        "output_dir": "",
        "fps": 30,
        "codec": "libx265",
        "crf": 20,
        "preset": "fast",
        "audio_enabled": True,
        "audio_device": 0,
        "audio_bitrate": "192k",
        "hotkey_start": "F9",
        "hotkey_stop": "F10",
        "hotkey_pause": "F11",
        "capture_mode": "fullscreen",
        "monitor_index": 0,
        "show_cursor": True,
        "countdown": 3,
        "filename_template": "recording_{date}_{time}",
        "container": "mp4",
        "mouse_highlight": False,
        "minimize_on_record": True,
    }

    def __init__(self, path="config.json"):
        self.path = path
        self.data = dict(self.DEFAULT)
        self.load()

    def load(self):
        try:
            if os.path.exists(self.path):
                with open(self.path, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                    self.data.update(saved)
        except Exception:
            pass

    def save(self):
        try:
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
        except Exception:
            pass

    def get(self, key):
        return self.data.get(key, self.DEFAULT.get(key))

    def set(self, key, value):
        self.data[key] = value


class AudioRecorder:
    """Запись звука"""

    def __init__(self, device_index=0, sample_rate=44100, channels=2, chunk=1024):
        self.device_index = device_index
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk = chunk
        self.frames = []
        self.recording = False
        self.paused = False
        self.stream = None
        self.audio = None

    def start(self):
        if not AUDIO_AVAILABLE:
            return

        try:
            self.audio = pyaudio.PyAudio()
            self.frames = []
            self.recording = True
            self.paused = False

            # Попытка открыть WASAPI loopback (системный звук Windows)
            try:
                self.stream = self.audio.open(
                    format=pyaudio.paInt16,
                    channels=self.channels,
                    rate=self.sample_rate,
                    input=True,
                    input_device_index=self.device_index,
                    frames_per_buffer=self.chunk,
                )
            except Exception:
                # Если не получилось — берем устройство по умолчанию
                self.stream = self.audio.open(
                    format=pyaudio.paInt16,
                    channels=self.channels,
                    rate=self.sample_rate,
                    input=True,
                    frames_per_buffer=self.chunk,
                )

            self.thread = threading.Thread(target=self._record, daemon=True)
            self.thread.start()

        except Exception as e:
            print(f"Ошибка запуска аудио: {e}")
            self.recording = False

    def _record(self):
        while self.recording:
            if self.paused:
                time.sleep(0.01)
                continue
            try:
                data = self.stream.read(self.chunk, exception_on_overflow=False)
                self.frames.append(data)
            except Exception:
                break

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def stop(self, output_path):
        self.recording = False

        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except Exception:
                pass

        if self.audio:
            try:
                self.audio.terminate()
            except Exception:
                pass

        if self.frames:
            try:
                with wave.open(output_path, 'wb') as wf:
                    wf.setnchannels(self.channels)
                    wf.setsampwidth(2)  # 16 bit
                    wf.setframerate(self.sample_rate)
                    wf.writeframes(b''.join(self.frames))
                return True
            except Exception as e:
                print(f"Ошибка сохранения аудио: {e}")
        return False

    @staticmethod
    def get_devices():
        """Получить список аудиоустройств"""
        devices = []
        if not AUDIO_AVAILABLE:
            return devices

        try:
            audio = pyaudio.PyAudio()
            for i in range(audio.get_device_count()):
                info = audio.get_device_info_by_index(i)
                if info['maxInputChannels'] > 0:
                    devices.append({
                        'index': i,
                        'name': info['name'],
                        'channels': int(info['maxInputChannels']),
                        'rate': int(info['defaultSampleRate']),
                    })
            audio.terminate()
        except Exception:
            pass
        return devices


class ScreenRecorder:
    """Запись экрана"""

    def __init__(self, config):
        self.config = config
        self.recording = False
        self.paused = False
        self.frames = []
        self.frame_times = []
        self.start_time = 0
        self.frame_count = 0
        self.capture_region = None
        self.audio_recorder = None
        self.status_callback = None
        self.sct = None

        # Импорт модуля курсора
        try:
            from cursor_utils import CursorCapture
            self.cursor_capture = CursorCapture()
            self.cursor_available = True
        except ImportError:
            self.cursor_capture = None
            self.cursor_available = False
            print("cursor_utils.py не найден — курсор не будет записываться")

    def set_status_callback(self, callback):
        self.status_callback = callback

    def _update_status(self, text):
        if self.status_callback:
            self.status_callback(text)

    def get_monitors(self):
        """Получить список мониторов"""
        monitors = []
        with mss.mss() as sct:
            for i, mon in enumerate(sct.monitors):
                if i == 0:
                    monitors.append(f"Все мониторы ({mon['width']}x{mon['height']})")
                else:
                    monitors.append(f"Монитор {i} ({mon['width']}x{mon['height']})")
        return monitors

    def set_region(self, region):
        self.capture_region = region

    def start(self, output_path):
        self.recording = True
        self.paused = False
        self.frames = []
        self.frame_times = []
        self.frame_count = 0
        self.output_path = output_path

        if self.config.get("audio_enabled") and AUDIO_AVAILABLE:
            self.audio_recorder = AudioRecorder(
                device_index=self.config.get("audio_device")
            )
        else:
            self.audio_recorder = None

        self.thread = threading.Thread(target=self._record, daemon=True)
        self.thread.start()

    def _get_capture_region(self, sct):
        mode = self.config.get("capture_mode")

        if self.capture_region:
            return self.capture_region

        if mode == "fullscreen":
            mon_idx = self.config.get("monitor_index")
            if mon_idx < len(sct.monitors):
                return sct.monitors[mon_idx]
            return sct.monitors[0]

        return sct.monitors[0]

    def _record(self):
        """Основной цикл записи С КУРСОРОМ"""
        fps = self.config.get("fps")
        frame_duration = 1.0 / fps
        show_cursor = self.config.get("show_cursor")
        mouse_highlight = self.config.get("mouse_highlight")

        # Запуск аудио
        if self.audio_recorder:
            self.audio_recorder.start()

        self.start_time = time.time()

        with mss.mss() as sct:
            region = self._get_capture_region(sct)

            width = region["width"]
            height = region["height"]
            if width % 2 != 0:
                width -= 1
            if height % 2 != 0:
                height -= 1

            temp_video = self.output_path + "_temp.avi"
            fourcc = cv2.VideoWriter_fourcc(*'XVID')
            writer = cv2.VideoWriter(temp_video, fourcc, fps, (width, height))

            if not writer.isOpened():
                self._update_status("ОШИБКА: Не удалось создать видеофайл")
                self.recording = False
                return

            self._update_status("● ЗАПИСЬ")

            while self.recording:
                loop_start = time.time()

                if self.paused:
                    time.sleep(0.05)
                    continue

                try:
                    # Захват экрана
                    screenshot = sct.grab(region)
                    frame = np.array(screenshot)
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                    frame = frame[:height, :width]

                    # ===== РИСУЕМ КУРСОР =====
                    if show_cursor and self.cursor_available:
                        frame = self.cursor_capture.draw_cursor_on_frame(
                            frame, region
                        )

                        # Подсветка кликов
                        if mouse_highlight:
                            frame = self.cursor_capture.draw_click_highlight(
                                frame, region
                            )
                    # ==========================

                    writer.write(frame)
                    self.frame_count += 1

                    elapsed = time.time() - self.start_time
                    mins = int(elapsed // 60)
                    secs = int(elapsed % 60)
                    self._update_status(
                        f"● ЗАПИСЬ  {mins:02d}:{secs:02d}  |  "
                        f"Кадров: {self.frame_count}  |  "
                        f"FPS: {self.frame_count / max(elapsed, 0.1):.1f}"
                    )

                except Exception as e:
                    print(f"Ошибка захвата: {e}")
                    continue

                elapsed_frame = time.time() - loop_start
                sleep_time = frame_duration - elapsed_frame
                if sleep_time > 0:
                    time.sleep(sleep_time)

            writer.release()

        # Сохранение аудио
        temp_audio = self.output_path + "_temp.wav"
        has_audio = False
        if self.audio_recorder:
            has_audio = self.audio_recorder.stop(temp_audio)

        self._update_status("Обработка видео...")
        self._finalize(temp_video, temp_audio, has_audio)

        try:
            if os.path.exists(temp_video):
                os.remove(temp_video)
            if os.path.exists(temp_audio):
                os.remove(temp_audio)
        except Exception:
            pass

        elapsed = time.time() - self.start_time
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)

        if os.path.exists(self.output_path):
            size_mb = os.path.getsize(self.output_path) / (1024 * 1024)
            self._update_status(
                f"✓ Сохранено! {mins:02d}:{secs:02d} | "
                f"{size_mb:.1f} МБ | {self.output_path}"
            )
        else:
            self._update_status("✓ Запись завершена")

    def _finalize(self, temp_video, temp_audio, has_audio):
        codec = self.config.get("codec")
        crf = self.config.get("crf")
        preset = self.config.get("preset")
        audio_bitrate = self.config.get("audio_bitrate")

        try:
            if has_audio and os.path.exists(temp_audio):
                cmd = [
                    "ffmpeg", "-y",
                    "-i", temp_video,
                    "-i", temp_audio,
                    "-c:v", codec,
                    "-crf", str(crf),
                    "-preset", preset,
                    "-c:a", "aac",
                    "-b:a", audio_bitrate,
                    "-movflags", "+faststart",
                    "-shortest",
                    self.output_path
                ]
            else:
                cmd = [
                    "ffmpeg", "-y",
                    "-i", temp_video,
                    "-c:v", codec,
                    "-crf", str(crf),
                    "-preset", preset,
                    "-an",
                    "-movflags", "+faststart",
                    self.output_path
                ]

            if codec == "libx265":
                idx = cmd.index("-preset")
                cmd.insert(idx + 2, "-tag:v")
                cmd.insert(idx + 3, "hvc1")

            subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )

        except FileNotFoundError:
            self._update_status("FFmpeg не найден — сохранено без сжатия")
            import shutil
            raw_output = self.output_path.rsplit('.', 1)[0] + '.avi'
            shutil.copy2(temp_video, raw_output)

    def pause(self):
        self.paused = True
        if self.audio_recorder:
            self.audio_recorder.pause()
        self._update_status("⏸ ПАУЗА")

    def resume(self):
        self.paused = False
        if self.audio_recorder:
            self.audio_recorder.resume()
        self._update_status("● ЗАПИСЬ")

    def toggle_pause(self):
        if self.paused:
            self.resume()
        else:
            self.pause()

    def stop(self):
        self.recording = False


class RegionSelector:
    """Окно выбора области экрана"""

    def __init__(self, callback):
        self.callback = callback
        self.start_x = 0
        self.start_y = 0
        self.rect = None

    def select(self):
        self.root = tk.Tk()
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-alpha', 0.3)
        self.root.attributes('-topmost', True)
        self.root.configure(bg='black')
        self.root.title("Выберите область")

        self.canvas = tk.Canvas(self.root, cursor="cross", bg='black',
                                highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Инструкция
        self.canvas.create_text(
            self.root.winfo_screenwidth() // 2,
            50,
            text="Выделите область мышью. ESC — отмена.",
            fill="white", font=("Arial", 20, "bold")
        )

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.root.bind("<Escape>", lambda e: self.root.destroy())

        self.root.mainloop()

    def _on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(
            self.start_x, self.start_y,
            self.start_x, self.start_y,
            outline='red', width=3
        )

    def _on_drag(self, event):
        if self.rect:
            self.canvas.coords(self.rect,
                               self.start_x, self.start_y,
                               event.x, event.y)

    def _on_release(self, event):
        x1 = min(self.start_x, event.x)
        y1 = min(self.start_y, event.y)
        x2 = max(self.start_x, event.x)
        y2 = max(self.start_y, event.y)

        width = x2 - x1
        height = y2 - y1

        if width > 10 and height > 10:
            region = {
                "left": x1,
                "top": y1,
                "width": width,
                "height": height
            }
            self.root.destroy()
            self.callback(region)
        else:
            self.root.destroy()


class MainWindow:
    """Главное окно программы"""

    def __init__(self):
        self.config = Config()
        self.recorder = ScreenRecorder(self.config)
        self.recorder.set_status_callback(self._update_status_threadsafe)
        self.is_recording = False
        self.selected_region = None
        self.selected_window = None
        self.hotkeys_registered = False

        self._build_ui()
        self._load_settings_to_ui()
        self._register_hotkeys()

    def _build_ui(self):
        self.root = tk.Tk()
        self.root.title("Screen Recorder v2.0")
        self.root.geometry("700x750")
        self.root.resizable(False, False)
        self.root.configure(bg="#1e1e2e")

        style = ttk.Style()
        style.theme_use('clam')

        # Цвета
        bg = "#1e1e2e"
        fg = "#cdd6f4"
        accent = "#89b4fa"
        frame_bg = "#313244"
        entry_bg = "#45475a"

        style.configure("Title.TLabel", background=bg, foreground=accent,
                         font=("Segoe UI", 16, "bold"))
        style.configure("TLabel", background=frame_bg, foreground=fg,
                         font=("Segoe UI", 10))
        style.configure("Status.TLabel", background=bg, foreground="#a6e3a1",
                         font=("Segoe UI", 11, "bold"))
        style.configure("TLabelframe", background=frame_bg, foreground=fg)
        style.configure("TLabelframe.Label", background=frame_bg,
                         foreground=accent, font=("Segoe UI", 10, "bold"))
        style.configure("TCombobox", fieldbackground=entry_bg, background=entry_bg,
                         foreground=fg)
        style.configure("TCheckbutton", background=frame_bg, foreground=fg)
        style.configure("TSpinbox", fieldbackground=entry_bg, foreground=fg)
        style.configure("TButton", font=("Segoe UI", 10))
        style.configure("Record.TButton", font=("Segoe UI", 12, "bold"))

        # Заголовок
        header = ttk.Label(self.root, text="🎬 Screen Recorder",
                           style="Title.TLabel")
        header.pack(pady=(10, 5))

        # Статус
        self.status_var = tk.StringVar(value="Готов к записи")
        self.status_label = ttk.Label(self.root, textvariable=self.status_var,
                                       style="Status.TLabel")
        self.status_label.pack(pady=5)

        # Основной контейнер
        main_frame = tk.Frame(self.root, bg=bg)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

        # === РЕЖИМ ЗАХВАТА ===
        capture_frame = ttk.LabelFrame(main_frame, text="  Режим захвата  ",
                                        padding=10)
        capture_frame.pack(fill=tk.X, pady=5)

        # Режим
        row1 = tk.Frame(capture_frame, bg=frame_bg)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="Режим:").pack(side=tk.LEFT, padx=5)

        self.capture_mode_var = tk.StringVar(value="fullscreen")
        modes = [
            ("Весь экран", "fullscreen"),
            ("Область", "region"),
            ("Окно", "window"),
        ]
        for text, value in modes:
            rb = ttk.Radiobutton(row1, text=text, variable=self.capture_mode_var,
                                  value=value, command=self._on_mode_change)
            rb.pack(side=tk.LEFT, padx=10)

        # Монитор
        row2 = tk.Frame(capture_frame, bg=frame_bg)
        row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="Монитор:").pack(side=tk.LEFT, padx=5)

        monitors = self.recorder.get_monitors()
        self.monitor_var = tk.StringVar(value=monitors[0] if monitors else "")
        self.monitor_combo = ttk.Combobox(row2, textvariable=self.monitor_var,
                                           values=monitors, state="readonly", width=40)
        self.monitor_combo.pack(side=tk.LEFT, padx=5)

        # Кнопки выбора области/окна
        row3 = tk.Frame(capture_frame, bg=frame_bg)
        row3.pack(fill=tk.X, pady=2)

        self.btn_select_region = ttk.Button(row3, text="📐 Выбрать область",
                                             command=self._select_region)
        self.btn_select_region.pack(side=tk.LEFT, padx=5)
        self.btn_select_region.configure(state="disabled")

        self.btn_select_window = ttk.Button(row3, text="🪟 Выбрать окно",
                                              command=self._select_window)
        self.btn_select_window.pack(side=tk.LEFT, padx=5)
        self.btn_select_window.configure(state="disabled")

        self.region_info_var = tk.StringVar(value="")
        ttk.Label(row3, textvariable=self.region_info_var).pack(side=tk.LEFT, padx=10)

        # === НАСТРОЙКИ ВИДЕО ===
        video_frame = ttk.LabelFrame(main_frame, text="  Настройки видео  ",
                                      padding=10)
        video_frame.pack(fill=tk.X, pady=5)

        # FPS
        vrow1 = tk.Frame(video_frame, bg=frame_bg)
        vrow1.pack(fill=tk.X, pady=2)

        ttk.Label(vrow1, text="FPS:").pack(side=tk.LEFT, padx=5)
        self.fps_var = tk.IntVar(value=30)
        fps_spin = ttk.Spinbox(vrow1, from_=10, to=120, textvariable=self.fps_var,
                                width=5)
        fps_spin.pack(side=tk.LEFT, padx=5)

        ttk.Label(vrow1, text="Кодек:").pack(side=tk.LEFT, padx=(20, 5))
        self.codec_var = tk.StringVar(value="libx265")
        codec_combo = ttk.Combobox(vrow1, textvariable=self.codec_var,
                                    values=["libx264", "libx265", "libsvtav1"],
                                    state="readonly", width=12)
        codec_combo.pack(side=tk.LEFT, padx=5)

        # CRF и Пресет
        vrow2 = tk.Frame(video_frame, bg=frame_bg)
        vrow2.pack(fill=tk.X, pady=2)

        ttk.Label(vrow2, text="Качество (CRF):").pack(side=tk.LEFT, padx=5)
        self.crf_var = tk.IntVar(value=20)
        self.crf_scale = ttk.Scale(vrow2, from_=15, to=35,
                                    variable=self.crf_var, orient=tk.HORIZONTAL,
                                    length=150, command=self._on_crf_change)
        self.crf_scale.pack(side=tk.LEFT, padx=5)
        self.crf_label = ttk.Label(vrow2, text="20")
        self.crf_label.pack(side=tk.LEFT, padx=5)

        ttk.Label(vrow2, text="Пресет:").pack(side=tk.LEFT, padx=(10, 5))
        self.preset_var = tk.StringVar(value="fast")
        preset_combo = ttk.Combobox(vrow2, textvariable=self.preset_var,
                                     values=["ultrafast", "superfast", "veryfast",
                                             "faster", "fast", "medium", "slow",
                                             "slower", "veryslow"],
                                     state="readonly", width=10)
        preset_combo.pack(side=tk.LEFT, padx=5)

        # === НАСТРОЙКИ ЗВУКА ===
        audio_frame = ttk.LabelFrame(main_frame, text="  Звук  ", padding=10)
        audio_frame.pack(fill=tk.X, pady=5)

        arow1 = tk.Frame(audio_frame, bg=frame_bg)
        arow1.pack(fill=tk.X, pady=2)

        self.audio_enabled_var = tk.BooleanVar(value=True)
        audio_check = ttk.Checkbutton(arow1, text="Записывать звук",
                                       variable=self.audio_enabled_var,
                                       command=self._on_audio_toggle)
        audio_check.pack(side=tk.LEFT, padx=5)

        if not AUDIO_AVAILABLE:
            audio_check.configure(state="disabled")
            self.audio_enabled_var.set(False)

        ttk.Label(arow1, text="Битрейт:").pack(side=tk.LEFT, padx=(20, 5))
        self.audio_bitrate_var = tk.StringVar(value="192k")
        abr_combo = ttk.Combobox(arow1, textvariable=self.audio_bitrate_var,
                                  values=["96k", "128k", "192k", "256k", "320k"],
                                  state="readonly", width=8)
        abr_combo.pack(side=tk.LEFT, padx=5)

        # Устройство
        arow2 = tk.Frame(audio_frame, bg=frame_bg)
        arow2.pack(fill=tk.X, pady=2)

        ttk.Label(arow2, text="Устройство:").pack(side=tk.LEFT, padx=5)

        devices = AudioRecorder.get_devices()
        device_names = [f"{d['index']}: {d['name']}" for d in devices]
        if not device_names:
            device_names = ["Нет устройств"]

        self.audio_device_var = tk.StringVar(
            value=device_names[0] if device_names else "")
        device_combo = ttk.Combobox(arow2, textvariable=self.audio_device_var,
                                     values=device_names, state="readonly", width=50)
        device_combo.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        # === ГОРЯЧИЕ КЛАВИШИ ===
        hotkey_frame = ttk.LabelFrame(main_frame, text="  Горячие клавиши  ",
                                       padding=10)
        hotkey_frame.pack(fill=tk.X, pady=5)

        hrow = tk.Frame(hotkey_frame, bg=frame_bg)
        hrow.pack(fill=tk.X)

        ttk.Label(hrow, text="Старт/Стоп:").pack(side=tk.LEFT, padx=5)
        self.hotkey_start_var = tk.StringVar(value="F9")
        ttk.Entry(hrow, textvariable=self.hotkey_start_var, width=8).pack(
            side=tk.LEFT, padx=5)

        ttk.Label(hrow, text="Пауза:").pack(side=tk.LEFT, padx=(15, 5))
        self.hotkey_pause_var = tk.StringVar(value="F11")
        ttk.Entry(hrow, textvariable=self.hotkey_pause_var, width=8).pack(
            side=tk.LEFT, padx=5)

        # === СОХРАНЕНИЕ ===
        save_frame = ttk.LabelFrame(main_frame, text="  Сохранение  ",
                                     padding=10)
        save_frame.pack(fill=tk.X, pady=5)

        srow = tk.Frame(save_frame, bg=frame_bg)
        srow.pack(fill=tk.X)

        ttk.Label(srow, text="Папка:").pack(side=tk.LEFT, padx=5)

        default_dir = self.config.get("output_dir")
        if not default_dir:
            default_dir = str(Path.home() / "Videos" / "ScreenRecorder")

        self.output_dir_var = tk.StringVar(value=default_dir)
        dir_entry = ttk.Entry(srow, textvariable=self.output_dir_var, width=40)
        dir_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        ttk.Button(srow, text="📁", width=3,
                    command=self._browse_output).pack(side=tk.LEFT, padx=5)

        # === КНОПКИ УПРАВЛЕНИЯ ===
        btn_frame = tk.Frame(self.root, bg=bg)
        btn_frame.pack(pady=10)

        self.btn_record = tk.Button(
            btn_frame,
            text="⏺  НАЧАТЬ ЗАПИСЬ",
            font=("Segoe UI", 14, "bold"),
            bg="#f38ba8",
            fg="white",
            activebackground="#ef6d90",
            activeforeground="white",
            relief=tk.FLAT,
            padx=30, pady=10,
            cursor="hand2",
            command=self._toggle_recording
        )
        self.btn_record.pack(side=tk.LEFT, padx=10)

        self.btn_pause = tk.Button(
            btn_frame,
            text="⏸ ПАУЗА",
            font=("Segoe UI", 12),
            bg="#fab387",
            fg="white",
            activebackground="#e8a070",
            activeforeground="white",
            relief=tk.FLAT,
            padx=20, pady=10,
            cursor="hand2",
            command=self._toggle_pause,
            state=tk.DISABLED
        )
        self.btn_pause.pack(side=tk.LEFT, padx=10)

        # Нижняя строка
        bottom = tk.Frame(self.root, bg=bg)
        bottom.pack(side=tk.BOTTOM, fill=tk.X, padx=15, pady=5)

        ttk.Button(bottom, text="💾 Сохранить настройки",
                    command=self._save_settings).pack(side=tk.LEFT)
        ttk.Button(bottom, text="📂 Открыть папку записей",
                    command=self._open_output_dir).pack(side=tk.LEFT, padx=10)

    def _on_crf_change(self, val):
        v = int(float(val))
        self.crf_var.set(v)
        quality_map = {
            range(15, 19): "Визуально без потерь",
            range(19, 22): "Отличное",
            range(22, 25): "Хорошее",
            range(25, 29): "Среднее",
            range(29, 36): "Низкое",
        }
        label = str(v)
        for r, name in quality_map.items():
            if v in r:
                label = f"{v} ({name})"
                break
        self.crf_label.configure(text=label)

    def _on_mode_change(self):
        mode = self.capture_mode_var.get()
        if mode == "region":
            self.btn_select_region.configure(state="normal")
            self.btn_select_window.configure(state="disabled")
            self.monitor_combo.configure(state="disabled")
        elif mode == "window":
            self.btn_select_region.configure(state="disabled")
            self.btn_select_window.configure(state="normal")
            self.monitor_combo.configure(state="disabled")
        else:
            self.btn_select_region.configure(state="disabled")
            self.btn_select_window.configure(state="disabled")
            self.monitor_combo.configure(state="readonly")
        self.selected_region = None
        self.region_info_var.set("")

    def _on_audio_toggle(self):
        pass

    def _select_region(self):
        """Выбор области экрана"""
        self.root.withdraw()
        time.sleep(0.3)

        def on_region_selected(region):
            self.selected_region = region
            self.region_info_var.set(
                f"Область: {region['width']}x{region['height']} "
                f"({region['left']}, {region['top']})"
            )
            self.root.deiconify()

        selector = RegionSelector(on_region_selected)
        selector.select()

        if not self.selected_region:
            self.root.deiconify()

    def _select_window(self):
        """Выбор окна для захвата"""
        if not WINDOW_CAPTURE_AVAILABLE:
            messagebox.showwarning("Ошибка",
                                   "pygetwindow не установлен!\nЗапустите install_deps.bat")
            return

        # Создаём окно выбора
        win_select = tk.Toplevel(self.root)
        win_select.title("Выберите окно")
        win_select.geometry("500x400")
        win_select.transient(self.root)
        win_select.grab_set()

        ttk.Label(win_select, text="Выберите окно для записи:",
                  font=("Segoe UI", 12, "bold")).pack(pady=10)

        # Список окон
        listbox = tk.Listbox(win_select, font=("Segoe UI", 10), width=60, height=15)
        listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        scrollbar = ttk.Scrollbar(listbox, orient=tk.VERTICAL, command=listbox.yview)
        listbox.configure(yscrollcommand=scrollbar.set)

        windows = gw.getAllWindows()
        valid_windows = []
        for w in windows:
            if w.title and w.visible and w.width > 0 and w.height > 0:
                valid_windows.append(w)
                listbox.insert(tk.END,
                               f"{w.title[:60]}  ({w.width}x{w.height})")

        def on_select():
            selection = listbox.curselection()
            if selection:
                idx = selection[0]
                w = valid_windows[idx]
                self.selected_region = {
                    "left": w.left,
                    "top": w.top,
                    "width": w.width,
                    "height": w.height,
                }
                self.selected_window = w.title
                self.region_info_var.set(
                    f"Окно: {w.title[:30]}... ({w.width}x{w.height})"
                )
                win_select.destroy()

        def on_refresh():
            listbox.delete(0, tk.END)
            valid_windows.clear()
            for w in gw.getAllWindows():
                if w.title and w.visible and w.width > 0 and w.height > 0:
                    valid_windows.append(w)
                    listbox.insert(tk.END,
                                   f"{w.title[:60]}  ({w.width}x{w.height})")

        btn_frame = tk.Frame(win_select)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="✓ Выбрать", command=on_select).pack(
            side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="🔄 Обновить", command=on_refresh).pack(
            side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="✕ Отмена",
                    command=win_select.destroy).pack(side=tk.LEFT, padx=5)

    def _browse_output(self):
        dir_path = filedialog.askdirectory(
            title="Выберите папку для записей",
            initialdir=self.output_dir_var.get()
        )
        if dir_path:
            self.output_dir_var.set(dir_path)

    def _generate_filename(self):
        now = datetime.now()
        filename = f"recording_{now.strftime('%Y-%m-%d_%H-%M-%S')}"
        container = self.config.get("container")
        return f"{filename}.{container}"

    def _toggle_recording(self):
        if not self.is_recording:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self):
        # Сохранение настроек в конфиг
        self._apply_settings()

        # Создание папки
        output_dir = self.output_dir_var.get()
        os.makedirs(output_dir, exist_ok=True)

        # Генерация имени файла
        filename = self._generate_filename()
        output_path = os.path.join(output_dir, filename)

        # Установка области
        mode = self.capture_mode_var.get()
        if mode == "region" and self.selected_region:
            self.recorder.set_region(self.selected_region)
        elif mode == "window" and self.selected_region:
            # Обновляем позицию окна
            if WINDOW_CAPTURE_AVAILABLE and self.selected_window:
                try:
                    wins = gw.getWindowsWithTitle(self.selected_window)
                    if wins:
                        w = wins[0]
                        self.selected_region = {
                            "left": max(0, w.left),
                            "top": max(0, w.top),
                            "width": w.width,
                            "height": w.height,
                        }
                except Exception:
                    pass
            self.recorder.set_region(self.selected_region)
        else:
            # Полный экран
            mon_idx = self.monitor_combo.current()
            if mon_idx < 0:
                mon_idx = 0
            self.config.set("monitor_index", mon_idx)
            self.recorder.set_region(None)

        # Обратный отсчёт
        countdown = self.config.get("countdown")
        if countdown > 0:
            for i in range(countdown, 0, -1):
                self.status_var.set(f"Начало через {i}...")
                self.root.update()
                time.sleep(1)

        # Минимизация окна
        if self.config.get("minimize_on_record"):
            self.root.iconify()

        # Старт
        self.is_recording = True
        self.recorder = ScreenRecorder(self.config)
        self.recorder.set_status_callback(self._update_status_threadsafe)

        if mode == "region" and self.selected_region:
            self.recorder.set_region(self.selected_region)
        elif mode == "window" and self.selected_region:
            self.recorder.set_region(self.selected_region)

        self.recorder.start(output_path)

        # Обновление UI
        self.btn_record.configure(text="⏹  ОСТАНОВИТЬ", bg="#a6e3a1")
        self.btn_pause.configure(state=tk.NORMAL)

    def _stop_recording(self):
        self.is_recording = False
        self.recorder.stop()

        self.btn_record.configure(text="⏺  НАЧАТЬ ЗАПИСЬ", bg="#f38ba8")
        self.btn_pause.configure(state=tk.DISABLED, text="⏸ ПАУЗА")

        # Восстановление окна
        self.root.deiconify()
        self.root.lift()

    def _toggle_pause(self):
        if not self.is_recording:
            return

        if self.recorder.paused:
            self.recorder.resume()
            self.btn_pause.configure(text="⏸ ПАУЗА", bg="#fab387")
        else:
            self.recorder.pause()
            self.btn_pause.configure(text="▶ ПРОДОЛЖИТЬ", bg="#a6e3a1")

    def _update_status_threadsafe(self, text):
        try:
            self.root.after(0, lambda: self.status_var.set(text))
        except Exception:
            pass

    def _apply_settings(self):
        self.config.set("fps", self.fps_var.get())
        self.config.set("codec", self.codec_var.get())
        self.config.set("crf", self.crf_var.get())
        self.config.set("preset", self.preset_var.get())
        self.config.set("audio_enabled", self.audio_enabled_var.get())
        self.config.set("audio_bitrate", self.audio_bitrate_var.get())
        self.config.set("capture_mode", self.capture_mode_var.get())
        self.config.set("output_dir", self.output_dir_var.get())
        self.config.set("hotkey_start", self.hotkey_start_var.get())
        self.config.set("hotkey_pause", self.hotkey_pause_var.get())

        # Устройство аудио
        dev_str = self.audio_device_var.get()
        try:
            dev_idx = int(dev_str.split(":")[0])
            self.config.set("audio_device", dev_idx)
        except Exception:
            pass

    def _save_settings(self):
        self._apply_settings()
        self.config.save()
        self.status_var.set("✓ Настройки сохранены!")

    def _load_settings_to_ui(self):
        self.fps_var.set(self.config.get("fps"))
        self.codec_var.set(self.config.get("codec"))
        self.crf_var.set(self.config.get("crf"))
        self.preset_var.set(self.config.get("preset"))
        self.audio_enabled_var.set(self.config.get("audio_enabled"))
        self.audio_bitrate_var.set(self.config.get("audio_bitrate"))
        self.capture_mode_var.set(self.config.get("capture_mode"))
        self.hotkey_start_var.set(self.config.get("hotkey_start"))
        self.hotkey_pause_var.set(self.config.get("hotkey_pause"))

        output_dir = self.config.get("output_dir")
        if output_dir:
            self.output_dir_var.set(output_dir)

        self._on_crf_change(str(self.config.get("crf")))
        self._on_mode_change()

    def _register_hotkeys(self):
        """Регистрация глобальных горячих клавиш"""
        try:
            hotkey_start = self.config.get("hotkey_start")
            hotkey_pause = self.config.get("hotkey_pause")

            keyboard.add_hotkey(hotkey_start, self._hotkey_toggle_record)
            keyboard.add_hotkey(hotkey_pause, self._hotkey_toggle_pause)
            self.hotkeys_registered = True
        except Exception as e:
            print(f"Не удалось зарегистрировать горячие клавиши: {e}")

    def _hotkey_toggle_record(self):
        self.root.after(0, self._toggle_recording)

    def _hotkey_toggle_pause(self):
        self.root.after(0, self._toggle_pause)

    def _open_output_dir(self):
        output_dir = self.output_dir_var.get()
        os.makedirs(output_dir, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(output_dir)
        else:
            subprocess.run(["xdg-open", output_dir])

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        if self.is_recording:
            if messagebox.askyesno("Запись идёт",
                                   "Идёт запись! Остановить и выйти?"):
                self._stop_recording()
                time.sleep(1)
            else:
                return

        if self.hotkeys_registered:
            try:
                keyboard.unhook_all()
            except Exception:
                pass

        self.root.destroy()


def main():
    print("Запуск Screen Recorder...")
    app = MainWindow()
    app.run()


if __name__ == "__main__":
    main()