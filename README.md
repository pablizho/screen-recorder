# screen-recorder

**Windows screen recorder that burns the real mouse cursor into the video.**

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)
![Win32](https://img.shields.io/badge/Win32-ctypes%20GDI-0078D6?style=flat-square&logo=windows&logoColor=white)
![FFmpeg](https://img.shields.io/badge/FFmpeg-007808?style=flat-square&logo=ffmpeg&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-5C3EE8?style=flat-square&logo=opencv&logoColor=white)

~1800 lines of Python · H.264 / H.265 / AV1 · region, window and multi-monitor capture

---

## Why it exists

A bug report video is only useful if the reviewer can see what was clicked. Almost every screen capture API on Windows returns frames **without the mouse pointer** — you get a recording where menus open for no visible reason and the developer replies "cannot reproduce, what did you press?".

This recorder pulls the actual system cursor bitmap through Win32 GDI and composites it into every frame, and draws a coloured ring at the moment of a click. The resulting file is evidence rather than a mystery.

## What it does

- Capture **fullscreen**, a **specific monitor**, a **rubber-band region**, or a **named window**.
- Real system cursor burned in, with the correct hotspot, correctly clipped at frame edges.
- Click highlights — yellow ring for left button, magenta for right.
- Microphone track with a device picker, muxed into the final file.
- Codec, CRF and preset selectable: `libx264`, `libx265`, AV1.
- Global hotkeys, pause/resume, countdown before start, auto-minimise on record.
- Settings persisted to `config.json`; live status line with elapsed time, frame count and effective FPS.
- Graceful degradation — missing PyAudio, pygetwindow or FFmpeg disables a feature instead of crashing the app.

There is also `quick_record.py`: no GUI at all, F9 start/stop, F11 pause, F12 exit, output straight to `~/Videos/ScreenRecorder`. That is the one I actually use during a test pass.

## Architecture

| Component | Responsibility |
|---|---|
| `MainWindow` | Tkinter/ttk GUI, settings groups, status line. |
| `ScreenRecorder` | Capture loop on a daemon thread: `mss` grab → BGRA→BGR → cursor composite → `cv2.VideoWriter` (XVID AVI). |
| `AudioRecorder` | Own daemon thread, PyAudio chunks into a list, written as 16-bit WAV on stop. |
| `CursorCapture` | Pure `ctypes` against `user32`/`gdi32`. Structures (`CURSORINFO`, `ICONINFO`, `BITMAPINFOHEADER`) declared by hand. |
| `RegionSelector` | Fullscreen translucent topmost window with a canvas rubber band. |
| `Config` | 18-key dict persisted to `config.json`. |
| `_finalize()` | Shells out to FFmpeg to mux the temp AVI + temp WAV into the final container. |

**Two-stage encode by design.** The hot loop writes fast XVID AVI; a single FFmpeg transcode runs afterwards. Encoding x265 inline at 30 fps drops frames — so it doesn't.

## Engineering notes

**Getting the cursor bitmap out of Windows is the whole project.** `CursorCapture.get_cursor_image()` copies the live `HCURSOR`, calls `GetIconInfo`, creates a compatible DC and bitmap, renders with `DrawIconEx`, then reads the pixels back with `GetDIBits` — passing `biHeight = -height` to force a top-down DIB, because otherwise the cursor comes out vertically flipped.

**Cursors lie about their alpha channel.** Many come back from `DrawIconEx` with an all-zero alpha channel, which blends to nothing. The code detects `np.all(alpha == 0)`, re-reads `icon_info.hbmMask`, and derives alpha from the AND mask with `np.where(mask_gray < 128, 255, 0)` — black in the mask means draw. There is a second fallback deriving alpha from luminance, and a hand-drawn polygon arrow if every path fails. Monochrome cursors are handled separately: `hbmColor == 0` and the mask bitmap is double height.

**Compositing solves three problems at once.** `draw_cursor_on_frame(frame, region)` subtracts the region origin so the cursor lands correctly when recording a sub-region or a secondary monitor, subtracts the icon hotspot so the *tip* sits at the pointer rather than the corner, and computes independent source and destination rectangles so a cursor half off the frame edge is clipped instead of raising a broadcast error.

**Even dimensions are forced before the writer is opened.** `if width % 2 != 0: width -= 1`. H.264/H.265 in yuv420p requires even width and height; an odd-sized region would fail in FFmpeg *after* the take was already captured.

**HEVC in MP4 needs `-tag:v hvc1`.** Without it the file is a black frame in QuickTime and on iPhones. `_finalize()` locates `-preset` in the argv list and splices the tag in after it, and adds `-movflags +faststart`. `creationflags=subprocess.CREATE_NO_WINDOW` stops FFmpeg flashing a console over the desktop you just recorded.

**You never lose a take.** If FFmpeg is not on PATH, `_finalize` catches `FileNotFoundError` and copies the raw temp AVI next to the intended output instead of deleting it.

**Click detection is cheap.** `GetAsyncKeyState(0x01)` / `(0x02)` polled per frame — no hooks, no elevation.

## Install

```bash
pip install -r requirements.txt        # or run install_deps.bat
```

FFmpeg must be on PATH. Then:

```bash
python recorder.py        # GUI
python quick_record.py    # headless: F9 record, F11 pause, F12 quit
```

## Known issues

- **`_start_recording` has dead setup code.** It configures `self.recorder`, then reassigns `self.recorder = ScreenRecorder(self.config)` and throws the configured object away, re-applying region only on two branches. The first ~25 lines are a copy-paste leftover.
- **Timing is the real flaw.** The `VideoWriter` is opened at a fixed FPS while the capture loop is a best-effort `sleep(frame_duration - elapsed)`. If capture runs slower than the target, playback is sped up. `self.frame_times` is collected and never used to correct anything; there is no PTS-based or variable-frame-rate path. This is the thing I would fix first.
- Pause/resume keeps no timestamp bookkeeping, so A/V sync after a pause depends on two threads noticing a flag at the same moment; `-shortest` just truncates the longer stream.
- `Config.DEFAULT` declares `hotkey_stop: F10`, which is never registered.
- Window capture snapshots the window rectangle once at record start — move the window and you record the wrong area.
- `RegionSelector` builds a second `tk.Tk()` instead of a `Toplevel` and uses canvas-local coordinates, so monitors at negative X/Y can't be selected.
- `_cursor_cache` is keyed on the raw `HCURSOR` handle and never invalidated; Windows recycles handles, so a long session can draw a stale bitmap.
- `except Exception: pass` in `Config.load/save`, `AudioRecorder.stop` and the per-frame handler — a permanently failing `sct.grab` spins silently.
- Windows only. `cursor_utils.py` touches `ctypes.windll` at module scope, so it can't even be imported elsewhere.

---

<details>
<summary><b>🇷🇺 По-русски</b></summary>

<br>

**Запись экрана под Windows, которая вжигает в кадр настоящий курсор мыши.**

### Зачем

Видео в баг-репорте полезно, только если видно, куда нажали. Почти все API захвата экрана под Windows отдают кадры **без указателя мыши** — получается запись, где меню открываются сами собой, а разработчик отвечает «не воспроизводится, что вы нажали?».

Здесь курсор вытаскивается напрямую из Win32 GDI и композитится в каждый кадр, а в момент клика рисуется цветное кольцо. Файл становится доказательством, а не загадкой.

### Что умеет

Захват всего экрана, отдельного монитора, выделенной области или конкретного окна · настоящий системный курсор с правильной точкой привязки · подсветка кликов (жёлтое кольцо — ЛКМ, пурпурное — ПКМ) · запись микрофона · H.264 / H.265 / AV1 с выбором CRF и пресета · глобальные хоткеи, пауза, обратный отсчёт · настройки в `config.json`.

Отдельно есть `quick_record.py` — без интерфейса вообще: F9 старт/стоп, F11 пауза, F12 выход. Им я и пользуюсь во время прогона.

### Интересные места в коде

- **Вытащить битмап курсора из Windows — это и есть весь проект.** `CopyIcon` → `GetIconInfo` → `DrawIconEx` в совместимый DC → `GetDIBits` с `biHeight = -height`, иначе курсор приходит перевёрнутым по вертикали.
- **Курсоры врут про альфа-канал.** Часто он приходит нулевым, и композит даёт пустоту. Код это ловит и восстанавливает альфу из AND-маски: `np.where(mask_gray < 128, 255, 0)`. Есть второй фолбэк через яркость и третий — нарисованная стрелка.
- Композит решает три задачи разом: вычитает начало области (запись части экрана или второго монитора), вычитает hotspot (чтобы у пикселя указателя было остриё, а не угол) и обрезает курсор на краю кадра отдельными прямоугольниками источника и приёмника.
- Чётность размеров форсируется **до** открытия writer'а: yuv420p требует чётных сторон, иначе FFmpeg упал бы уже после того, как дубль записан.
- Для HEVC в MP4 добавляется `-tag:v hvc1` — без него файл чёрный в QuickTime и на iPhone.
- Если FFmpeg не найден, сырой AVI не удаляется, а копируется рядом. Дубль не теряется никогда.

### Известные проблемы

Главная — **тайминги**: writer открыт на фиксированный FPS, а цикл захвата работает «как получится», поэтому при просадке видео проигрывается ускоренным. Плюс мёртвый код в `_start_recording`, отсутствующий хоткей F10, снимок геометрии окна только на старте и `except: pass` в нескольких местах. Только Windows.

</details>
