"""
Утилиты для захвата и отрисовки курсора мыши
"""

import ctypes
import ctypes.wintypes
import numpy as np
import cv2

# Windows API структуры
class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

class CURSORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("flags", ctypes.c_uint),
        ("hCursor", ctypes.c_void_p),
        ("ptScreenPos", POINT),
    ]

class ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", ctypes.c_bool),
        ("xHotspot", ctypes.c_uint),
        ("yHotspot", ctypes.c_uint),
        ("hbmMask", ctypes.c_void_p),
        ("hbmColor", ctypes.c_void_p),
    ]

class BITMAP(ctypes.Structure):
    _fields_ = [
        ("bmType", ctypes.c_long),
        ("bmWidth", ctypes.c_long),
        ("bmHeight", ctypes.c_long),
        ("bmWidthBytes", ctypes.c_long),
        ("bmPlanes", ctypes.c_ushort),
        ("bmBitsPixel", ctypes.c_ushort),
        ("bmBits", ctypes.c_void_p),
    ]

class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_uint),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", ctypes.c_ushort),
        ("biBitCount", ctypes.c_ushort),
        ("biCompression", ctypes.c_uint),
        ("biSizeImage", ctypes.c_uint),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", ctypes.c_uint),
        ("biClrImportant", ctypes.c_uint),
    ]


# Windows API функции
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

GetCursorInfo = user32.GetCursorInfo
GetIconInfo = user32.GetIconInfo
GetDC = user32.GetDC
ReleaseDC = user32.ReleaseDC
DrawIconEx = user32.DrawIconEx
DestroyIcon = user32.DestroyIcon
CopyIcon = user32.CopyIcon
GetCursorPos = user32.GetCursorPos
GetBitmapBits = gdi32.GetBitmapBits
GetObjectW = gdi32.GetObjectW
CreateCompatibleDC = gdi32.CreateCompatibleDC
SelectObject = gdi32.SelectObject
DeleteDC = gdi32.DeleteDC
DeleteObject = gdi32.DeleteObject
GetDIBits = gdi32.GetDIBits
CreateCompatibleBitmap = gdi32.CreateCompatibleBitmap
BitBlt = gdi32.BitBlt

# Константы
CURSOR_SHOWING = 0x00000001
DI_NORMAL = 0x0003


class CursorCapture:
    """Захват и отрисовка системного курсора"""

    def __init__(self):
        self._cursor_cache = {}
        self._fallback_cursor = self._create_fallback_cursor()

    def _create_fallback_cursor(self, size=20):
        """Создать простой курсор-стрелку если не удалось захватить системный"""
        cursor_img = np.zeros((size + 10, size + 10, 4), dtype=np.uint8)

        # Белая стрелка с чёрным контуром
        points_outline = np.array([
            [0, 0],
            [0, size],
            [size // 3, size * 2 // 3],
            [size // 2, size],
            [size * 2 // 3, size],
            [size // 3, size * 2 // 3 - 2],
            [size // 5, size - 2],
        ], dtype=np.int32)

        points_fill = np.array([
            [1, 1],
            [1, size - 2],
            [size // 3 - 1, size * 2 // 3 - 1],
            [size // 2 - 1, size - 2],
            [size * 2 // 3 - 2, size - 2],
            [size // 3, size * 2 // 3 - 3],
            [size // 5 + 1, size - 4],
        ], dtype=np.int32)

        # Чёрный контур
        cv2.fillPoly(cursor_img, [points_outline], (0, 0, 0, 255))
        # Белая заливка
        cv2.fillPoly(cursor_img, [points_fill], (255, 255, 255, 255))

        return cursor_img

    def get_cursor_pos(self):
        """Получить позицию курсора"""
        point = POINT()
        GetCursorPos(ctypes.byref(point))
        return point.x, point.y

    def get_cursor_info(self):
        """Получить информацию о курсоре"""
        ci = CURSORINFO()
        ci.cbSize = ctypes.sizeof(CURSORINFO)

        if GetCursorInfo(ctypes.byref(ci)):
            if ci.flags & CURSOR_SHOWING:
                return {
                    "visible": True,
                    "x": ci.ptScreenPos.x,
                    "y": ci.ptScreenPos.y,
                    "handle": ci.hCursor,
                }
        return {"visible": False, "x": 0, "y": 0, "handle": None}

    def get_cursor_image(self, cursor_handle):
        """Получить изображение курсора как numpy массив с альфа-каналом"""
        if cursor_handle is None:
            return self._fallback_cursor, 0, 0

        # Проверка кэша
        if cursor_handle in self._cursor_cache:
            return self._cursor_cache[cursor_handle]

        try:
            # Копируем курсор
            hicon = CopyIcon(cursor_handle)
            if not hicon:
                return self._fallback_cursor, 0, 0

            # Получаем информацию
            icon_info = ICONINFO()
            if not GetIconInfo(hicon, ctypes.byref(icon_info)):
                DestroyIcon(hicon)
                return self._fallback_cursor, 0, 0

            hotspot_x = icon_info.xHotspot
            hotspot_y = icon_info.yHotspot

            # Получаем размер bitmap
            bm = BITMAP()
            GetObjectW(icon_info.hbmMask, ctypes.sizeof(BITMAP), ctypes.byref(bm))

            width = bm.bmWidth
            height = bm.bmHeight

            # Если нет цветного bitmap — монохромный курсор
            has_color = icon_info.hbmColor != 0

            if has_color:
                cursor_height = height
            else:
                cursor_height = height // 2

            if width <= 0 or cursor_height <= 0:
                self._cleanup_bitmaps(icon_info, hicon)
                return self._fallback_cursor, 0, 0

            # Получаем пиксели через GDI
            hdc_screen = GetDC(0)
            hdc = CreateCompatibleDC(hdc_screen)

            # Создаём bitmap для рисования
            hbmp = CreateCompatibleBitmap(hdc_screen, width, cursor_height)
            old_bmp = SelectObject(hdc, hbmp)

            # Рисуем курсор на DC
            DrawIconEx(hdc, 0, 0, hicon, width, cursor_height, 0, 0, DI_NORMAL)

            # Читаем пиксели
            bmi = BITMAPINFOHEADER()
            bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.biWidth = width
            bmi.biHeight = -cursor_height  # Top-down
            bmi.biPlanes = 1
            bmi.biBitCount = 32
            bmi.biCompression = 0  # BI_RGB

            buffer_size = width * cursor_height * 4
            buffer = ctypes.create_string_buffer(buffer_size)

            GetDIBits(hdc, hbmp, 0, cursor_height, buffer,
                      ctypes.byref(bmi), 0)

            # Преобразуем в numpy массив
            cursor_img = np.frombuffer(buffer, dtype=np.uint8).reshape(
                (cursor_height, width, 4)).copy()

            # BGRA порядок из Windows
            # Если все пиксели чёрные — используем маску для создания альфа
            if not has_color or np.all(cursor_img[:, :, 3] == 0):
                # Генерируем альфа из яркости
                gray = cv2.cvtColor(cursor_img[:, :, :3], cv2.COLOR_BGR2GRAY)
                alpha = np.where(gray > 10, 255, 0).astype(np.uint8)

                # Также читаем маску
                old_bmp2 = SelectObject(hdc, icon_info.hbmMask)
                buffer_mask = ctypes.create_string_buffer(buffer_size)

                bmi_mask = BITMAPINFOHEADER()
                bmi_mask.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                bmi_mask.biWidth = width
                bmi_mask.biHeight = -cursor_height
                bmi_mask.biPlanes = 1
                bmi_mask.biBitCount = 32
                bmi_mask.biCompression = 0

                GetDIBits(hdc, icon_info.hbmMask, 0, cursor_height,
                          buffer_mask, ctypes.byref(bmi_mask), 0)

                mask_img = np.frombuffer(buffer_mask, dtype=np.uint8).reshape(
                    (cursor_height, width, 4)).copy()

                SelectObject(hdc, old_bmp2)

                # Маска: чёрный = рисовать, белый = прозрачный
                mask_gray = cv2.cvtColor(mask_img[:, :, :3], cv2.COLOR_BGR2GRAY)
                alpha = np.where(mask_gray < 128, 255, 0).astype(np.uint8)
                cursor_img[:, :, 3] = alpha
            else:
                # Уже есть альфа-канал — проверим что он не весь нулевой
                if np.all(cursor_img[:, :, 3] == 0):
                    # Делаем непрозрачным где есть цвет
                    gray = cv2.cvtColor(cursor_img[:, :, :3], cv2.COLOR_BGR2GRAY)
                    cursor_img[:, :, 3] = np.where(gray > 5, 255, 0).astype(np.uint8)

            # Очистка
            SelectObject(hdc, old_bmp)
            DeleteObject(hbmp)
            DeleteDC(hdc)
            ReleaseDC(0, hdc_screen)
            self._cleanup_bitmaps(icon_info, hicon)

            # Кэшируем
            result = (cursor_img, hotspot_x, hotspot_y)
            self._cursor_cache[cursor_handle] = result

            return result

        except Exception as e:
            return self._fallback_cursor, 0, 0

    def _cleanup_bitmaps(self, icon_info, hicon):
        """Очистка GDI ресурсов"""
        if icon_info.hbmColor:
            DeleteObject(icon_info.hbmColor)
        if icon_info.hbmMask:
            DeleteObject(icon_info.hbmMask)
        if hicon:
            DestroyIcon(hicon)

    def draw_cursor_on_frame(self, frame, region=None):
        """
        Нарисовать курсор поверх кадра

        frame:  numpy массив BGR (кадр экрана)
        region: dict {"left": x, "top": y, "width": w, "height": h}
                область захвата (для пересчёта координат)
        """
        cursor_info = self.get_cursor_info()

        if not cursor_info["visible"]:
            return frame

        cursor_x = cursor_info["x"]
        cursor_y = cursor_info["y"]

        # Пересчёт координат относительно области захвата
        if region:
            cursor_x -= region.get("left", 0)
            cursor_y -= region.get("top", 0)

        # Получаем изображение курсора
        cursor_img, hotspot_x, hotspot_y = self.get_cursor_image(
            cursor_info["handle"]
        )

        # Позиция отрисовки (с учётом hotspot)
        draw_x = cursor_x - hotspot_x
        draw_y = cursor_y - hotspot_y

        # Размеры
        ch, cw = cursor_img.shape[:2]
        fh, fw = frame.shape[:2]

        # Проверка границ
        if draw_x >= fw or draw_y >= fh:
            return frame
        if draw_x + cw <= 0 or draw_y + ch <= 0:
            return frame

        # Обрезка курсора по границам кадра
        src_x1 = max(0, -draw_x)
        src_y1 = max(0, -draw_y)
        src_x2 = min(cw, fw - draw_x)
        src_y2 = min(ch, fh - draw_y)

        dst_x1 = max(0, draw_x)
        dst_y1 = max(0, draw_y)
        dst_x2 = dst_x1 + (src_x2 - src_x1)
        dst_y2 = dst_y1 + (src_y2 - src_y1)

        if dst_x2 <= dst_x1 or dst_y2 <= dst_y1:
            return frame

        # Вырезаем нужную часть курсора
        cursor_crop = cursor_img[src_y1:src_y2, src_x1:src_x2]

        if cursor_crop.shape[2] == 4:
            # Есть альфа-канал — используем альфа-блендинг
            alpha = cursor_crop[:, :, 3].astype(float) / 255.0
            alpha = alpha[:, :, np.newaxis]

            cursor_bgr = cursor_crop[:, :, :3].astype(float)
            frame_roi = frame[dst_y1:dst_y2, dst_x1:dst_x2].astype(float)

            # Блендинг
            blended = cursor_bgr * alpha + frame_roi * (1.0 - alpha)
            frame[dst_y1:dst_y2, dst_x1:dst_x2] = blended.astype(np.uint8)
        else:
            # Нет альфа — просто накладываем
            frame[dst_y1:dst_y2, dst_x1:dst_x2] = cursor_crop[:, :, :3]

        return frame

    def draw_click_highlight(self, frame, region=None, radius=20,
                              color=(0, 255, 255), thickness=2):
        """
        Нарисовать подсветку клика (жёлтый кружок)
        Вызывайте при обнаружении нажатия кнопки мыши
        """
        import ctypes
        left_pressed = ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000
        right_pressed = ctypes.windll.user32.GetAsyncKeyState(0x02) & 0x8000

        if not (left_pressed or right_pressed):
            return frame

        cursor_x, cursor_y = self.get_cursor_pos()

        if region:
            cursor_x -= region.get("left", 0)
            cursor_y -= region.get("top", 0)

        fh, fw = frame.shape[:2]
        if 0 <= cursor_x < fw and 0 <= cursor_y < fh:
            if left_pressed:
                cv2.circle(frame, (cursor_x, cursor_y), radius,
                           (0, 255, 255), thickness)  # Жёлтый
            if right_pressed:
                cv2.circle(frame, (cursor_x, cursor_y), radius,
                           (255, 0, 255), thickness)  # Фиолетовый

        return frame