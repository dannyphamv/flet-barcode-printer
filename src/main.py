"""Barcode Printer GUI using Flet framework."""

import base64
import ctypes
import ctypes.wintypes
import json
import os
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Optional

import barcode as python_barcode
import flet as ft
import flet_datatable2 as ftd
import qrcode
from barcode.writer import ImageWriter
from PIL import Image

ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE

# ── Windows API constants (replaces win32con) ─────────────────────────────────
HORZRES = 8
VERTRES = 10
LOGPIXELSX = 88
CF_UNICODETEXT = 13

# ── Windows API via ctypes (replaces win32print / win32ui / win32clipboard) ───
winspool = ctypes.WinDLL("winspool.drv")
gdi32 = ctypes.WinDLL("gdi32")
user32 = ctypes.WinDLL("user32")
kernel32 = ctypes.WinDLL("kernel32")

PRINTER_ENUM_LOCAL = 0x00000002
PRINTER_ENUM_CONNECTIONS = 0x00000004


class PRINTER_INFO_4(ctypes.Structure):
    """PRINTER_INFO_4W structure – the lightest enumeration level."""

    _fields_ = [
        ("pPrinterName", ctypes.c_wchar_p),
        ("pServerName", ctypes.c_wchar_p),
        ("Attributes", ctypes.c_uint32),
    ]


def _enum_printers_simple() -> list[str]:
    """Enumerate printers using PRINTER_INFO_4 (level 4) via winspool.drv."""
    flags = PRINTER_ENUM_LOCAL | PRINTER_ENUM_CONNECTIONS
    level = 4

    needed = ctypes.c_ulong(0)
    returned = ctypes.c_ulong(0)

    # First call: get required buffer size (will fail with ERROR_INSUFFICIENT_BUFFER)
    winspool.EnumPrintersW(
        flags, None, level, None, 0, ctypes.byref(needed), ctypes.byref(returned)
    )
    if needed.value == 0:
        return []

    buf = (ctypes.c_byte * needed.value)()
    ok = winspool.EnumPrintersW(
        flags, None, level, buf, needed, ctypes.byref(needed), ctypes.byref(returned)
    )
    if not ok or returned.value == 0:
        return []

    # Cast buffer to an array of PRINTER_INFO_4 structs
    arr = (PRINTER_INFO_4 * returned.value).from_buffer(buf)
    return [entry.pPrinterName for entry in arr if entry.pPrinterName]


def _get_default_printer() -> str:
    buf = ctypes.create_unicode_buffer(256)
    size = ctypes.c_ulong(256)
    winspool.GetDefaultPrinterW(buf, ctypes.byref(size))
    return buf.value


# ── Clipboard via ctypes (replaces win32clipboard) ────────────────────────────


def set_clipboard_text(text: str) -> None:
    """Copy unicode text to clipboard."""
    GMEM_MOVEABLE = 0x0002
    data = (text + "\0").encode("utf-16-le")
    h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    ptr = kernel32.GlobalLock(h)
    ctypes.memmove(ptr, data, len(data))
    kernel32.GlobalUnlock(h)
    user32.OpenClipboard(None)
    user32.EmptyClipboard()
    user32.SetClipboardData(CF_UNICODETEXT, h)
    user32.CloseClipboard()


# ── Printing via GDI (replaces win32ui / win32print / PIL.ImageWin) ───────────


class _DOCINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_int),
        ("lpszDocName", ctypes.c_wchar_p),
        ("lpszOutput", ctypes.c_wchar_p),
        ("lpszDatatype", ctypes.c_wchar_p),
        ("fwType", ctypes.c_uint),
    ]


def _print_image_gdi(img: Image.Image, printer_name: str) -> None:
    """Send PIL image to a Windows printer using raw GDI / ctypes."""
    # Create printer DC
    hdc = gdi32.CreateDCW("WINSPOOL", printer_name, None, None)
    if not hdc:
        raise RuntimeError(f"CreateDC failed for '{printer_name}'")

    try:
        # Start document
        di = _DOCINFOW()
        di.cbSize = ctypes.sizeof(_DOCINFOW)
        di.lpszDocName = "Barcode Print"
        if gdi32.StartDocW(hdc, ctypes.byref(di)) <= 0:
            raise RuntimeError("StartDoc failed")
        gdi32.StartPage(hdc)

        # Query printable area & DPI
        pw = gdi32.GetDeviceCaps(hdc, HORZRES)
        ph = gdi32.GetDeviceCaps(hdc, VERTRES)
        dpi = gdi32.GetDeviceCaps(hdc, LOGPIXELSX)

        max_w = int(CONFIG.width_inches * dpi)
        ratio = img.height / img.width
        target_w = min(max_w, pw)
        target_h = int(target_w * ratio)
        if target_h > ph:
            target_h = ph
            target_w = int(target_h / ratio)

        img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
        img = img.convert("RGB")

        x1 = (pw - target_w) // 2
        y1 = (ph - target_h) // 2
        x2 = x1 + target_w
        y2 = y1 + target_h

        # Build a DIB section and StretchDIBits to the printer DC
        w, h = img.size
        pixels = img.tobytes("raw", "BGR")  # GDI expects BGR

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", ctypes.c_uint32),
                ("biWidth", ctypes.c_int32),
                ("biHeight", ctypes.c_int32),
                ("biPlanes", ctypes.c_uint16),
                ("biBitCount", ctypes.c_uint16),
                ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32),
                ("biXPelsPerMeter", ctypes.c_int32),
                ("biYPelsPerMeter", ctypes.c_int32),
                ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32),
            ]

        bih = BITMAPINFOHEADER()
        bih.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bih.biWidth = w
        bih.biHeight = -h  # negative = top-down
        bih.biPlanes = 1
        bih.biBitCount = 24
        bih.biCompression = 0  # BI_RGB
        bih.biSizeImage = len(pixels)

        DIB_RGB_COLORS = 0
        SRCCOPY = 0x00CC0020

        gdi32.StretchDIBits(
            hdc,
            x1,
            y1,
            target_w,
            target_h,  # dest rect
            0,
            0,
            w,
            h,  # src rect
            pixels,
            ctypes.byref(bih),
            DIB_RGB_COLORS,
            SRCCOPY,
        )

        gdi32.EndPage(hdc)
        gdi32.EndDoc(hdc)
    finally:
        gdi32.DeleteDC(hdc)


@dataclass
class PrintConfig:
    """Configuration constants for barcode printing."""

    width_inches: int = 4
    qr_box_size: int = 20
    qr_border: int = 4
    history_max_entries: int = 100


CONFIG = PrintConfig()

CODE_TYPE_BARCODE = "barcode"
CODE_TYPE_QRCODE = "qrcode"
QRCODE_SELECTOR_VALUE = "2"

_PRINTER_LIST_CACHE: Optional[list[str]] = None
_CACHE_LOCK = threading.Lock()


def get_printers(force_refresh: bool = False) -> list[str]:
    global _PRINTER_LIST_CACHE
    if force_refresh or _PRINTER_LIST_CACHE is None:
        try:
            _PRINTER_LIST_CACHE = _enum_printers_simple()
        except Exception:
            _PRINTER_LIST_CACHE = []
    return _PRINTER_LIST_CACHE


@lru_cache(maxsize=100)
def _generate_label_image_cached(
    barcode_text: str, code_type: str = CODE_TYPE_BARCODE
) -> Image.Image:
    if code_type == CODE_TYPE_QRCODE:
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=CONFIG.qr_box_size,
                border=CONFIG.qr_border,
            )
            qr.add_data(barcode_text)
            qr.make(fit=True)
            code_img = qr.make_image(fill_color="black", back_color="white")
            if not isinstance(code_img, Image.Image):
                code_img = code_img.convert("RGB")
            return code_img
        except Exception as e:
            raise ValueError(f"Failed to generate QR code: {str(e)}")
    else:
        try:
            code128 = python_barcode.get("code128", barcode_text, writer=ImageWriter())
            with BytesIO() as buffer:
                code128.write(buffer)
                buffer.seek(0)
                return Image.open(buffer).copy()
        except Exception as e:
            raise ValueError(f"Failed to generate barcode: {str(e)}")


def generate_label_image(
    barcode_text: str, code_type: str = CODE_TYPE_BARCODE
) -> Image.Image:
    if not barcode_text or not barcode_text.strip():
        raise ValueError("Barcode text cannot be empty")
    with _CACHE_LOCK:
        return _generate_label_image_cached(barcode_text, code_type)


def print_image(img: Image.Image, printer_name: str) -> None:
    if not printer_name:
        raise ValueError("Printer name cannot be empty")
    available_printers = get_printers()
    if printer_name not in available_printers:
        raise ValueError(f"Printer '{printer_name}' not found")
    try:
        _print_image_gdi(img, printer_name)
    except Exception as exc:
        raise Exception(f"Print operation failed: {str(exc)}")


APPDATA_DIR = Path(os.getenv("APPDATA")) / "BarcodePrinter"
SETTINGS_FILE = APPDATA_DIR / "settings.json"
HISTORY_FILE = APPDATA_DIR / "history.json"


def ensure_appdata_dir() -> None:
    APPDATA_DIR.mkdir(parents=True, exist_ok=True)


def load_json_file(filepath: Path, default=None):
    if not filepath.exists():
        return default
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return default


def save_json_file(filepath: Path, data) -> None:
    ensure_appdata_dir()
    temp_fd, temp_path = tempfile.mkstemp(dir=APPDATA_DIR, suffix=".json", text=True)
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(temp_path, filepath)
    except Exception:
        try:
            os.unlink(temp_path)
        except Exception:
            pass
        raise


def save_settings(printer: str, theme_mode) -> None:
    settings = {"printer": printer, "theme_mode": theme_mode.value}
    save_json_file(SETTINGS_FILE, settings)


def load_settings() -> Optional[dict]:
    return load_json_file(SETTINGS_FILE)


def save_history_entry(
    barcode_text: str, printer_name: str, code_type: str = CODE_TYPE_BARCODE
) -> None:
    history = load_history()
    entry = {
        "barcode": barcode_text,
        "printer": printer_name,
        "code_type": code_type,
        "timestamp": datetime.now().isoformat(),
    }
    history.insert(0, entry)
    history = history[: CONFIG.history_max_entries]
    save_json_file(HISTORY_FILE, history)


def load_history() -> list[dict]:
    return load_json_file(HISTORY_FILE, default=[])


def clear_history() -> None:
    save_json_file(HISTORY_FILE, [])


def pil_to_base64(img: Image.Image) -> str:
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.read()).decode()
    return f"data:image/png;base64,{img_base64}"


def get_code_type_display(code_type: str) -> str:
    return "QR Code" if code_type == CODE_TYPE_QRCODE else "Barcode"


def setup_page_config(page: ft.Page, saved_config: Optional[dict]) -> None:
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.window.min_width = 700
    page.window.min_height = 700
    page.window.width = 700
    page.window.height = 700
    page.window.icon = os.path.abspath("src/assets/icon.ico")
    page.title = "Barcode Printer"
    saved_theme = saved_config.get("theme_mode") if saved_config else "dark"
    page.theme_mode = ft.ThemeMode.DARK if saved_theme == "dark" else ft.ThemeMode.LIGHT


def create_ui_components(
    page: ft.Page, printers: list[str], saved_config: Optional[dict]
) -> dict:
    barcode_chooser = ft.SegmentedButton(
        selected=["1"],
        segments=[
            ft.Segment(
                value="1",
                label=ft.Text("Barcode"),
                icon=ft.Icon(ft.CupertinoIcons.BARCODE),
            ),
            ft.Segment(
                value="2",
                label=ft.Text("QR Code"),
                icon=ft.Icon(ft.CupertinoIcons.QRCODE),
            ),
        ],
    )

    barcode_text = ft.TextField(
        label="Enter or Scan Barcode",
        width=500,
        autofocus=True,
        border_color=ft.Colors.PRIMARY,
    )

    default_printer = printers[0] if printers else None
    if saved_config and saved_config.get("printer") in printers:
        default_printer = saved_config["printer"]

    printer_dropdown = ft.Dropdown(
        label="Select Printer",
        width=500,
        value=default_printer,
        options=[ft.dropdown.Option(p) for p in printers],
        border_color=ft.Colors.PRIMARY,
        disabled=len(printers) == 0,
    )

    progress_bar = ft.ProgressBar(
        width=None,
        visible=False,
        color=ft.Colors.PRIMARY,
        height=4,
    )

    return {
        "barcode_chooser": barcode_chooser,
        "barcode_text": barcode_text,
        "printer_dropdown": printer_dropdown,
        "progress_bar": progress_bar,
    }


def main(page: ft.Page) -> None:
    saved_config = load_settings()
    setup_page_config(page, saved_config)

    current_view = [0]

    printers = get_printers()
    if not printers:

        def close_dialog(e):
            page.window.destroy()

        error_dialog = ft.AlertDialog(
            title=ft.Text("No Printers Found"),
            content=ft.Text(
                "No printers are installed on this system. Please install a printer and restart the application."
            ),
            actions=[ft.TextButton("Close", on_click=close_dialog)],
        )
        page.show_dialog(error_dialog)

    components = create_ui_components(page, printers, saved_config)
    barcode_chooser = components["barcode_chooser"]
    barcode_text = components["barcode_text"]
    printer_dropdown = components["printer_dropdown"]
    progress_bar = components["progress_bar"]

    async def on_window_event(e):
        if e.data == "focus":
            await barcode_text.focus()
            page.update()

    page.on_window_event = on_window_event

    def get_selected_code_type() -> str:
        return (
            CODE_TYPE_QRCODE
            if QRCODE_SELECTOR_VALUE in barcode_chooser.selected
            else CODE_TYPE_BARCODE
        )

    def toggle_theme(e):
        if page.theme_mode == ft.ThemeMode.LIGHT:
            page.theme_mode = ft.ThemeMode.DARK
        else:
            page.theme_mode = ft.ThemeMode.LIGHT
        theme_button.icon = (
            ft.CupertinoIcons.MOON_FILL
            if page.theme_mode == ft.ThemeMode.DARK
            else ft.CupertinoIcons.SUN_MAX_FILL
        )
        page.update()

    def handle_save_settings(e):
        save_settings(printer_dropdown.value, page.theme_mode)
        page.show_dialog(ft.SnackBar(ft.Text("Settings saved!")))
        page.update()

    async def show_preview(e):
        if not barcode_text.value or not barcode_text.value.strip():
            return
        code_type = get_selected_code_type()
        try:
            pil_img = generate_label_image(barcode_text.value.strip(), code_type)
            b64_string = pil_to_base64(pil_img)
            display_h = 200
            img_w, img_h = pil_img.size
            display_w = int(img_w * (display_h / img_h))

            dialog_image = ft.Image(
                src=b64_string, width=display_w, height=display_h, border_radius=4
            )

            def close_preview(e):
                preview_dialog.open = False
                page.update()

            preview_dialog = ft.AlertDialog(
                content=dialog_image,
                actions=[ft.TextButton("Close", on_click=close_preview)],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            page.show_dialog(preview_dialog)
        except ValueError as e:
            page.show_dialog(ft.SnackBar(ft.Text(str(e)), bgcolor=ft.Colors.ERROR))
        except Exception as e:
            page.show_dialog(
                ft.SnackBar(
                    ft.Text(f"Preview failed: {str(e)}"), bgcolor=ft.Colors.ERROR
                )
            )
        page.update()

    async def handle_print(e):
        if not barcode_text.value or not barcode_text.value.strip():
            await barcode_text.focus()
            return
        if not printer_dropdown.value:
            page.show_dialog(
                ft.SnackBar(ft.Text("Please select a printer"), bgcolor=ft.Colors.ERROR)
            )
            page.update()
            return

        code_type = get_selected_code_type()
        text_to_print = barcode_text.value.strip()
        printer_name = printer_dropdown.value

        progress_bar.visible = True
        progress_bar.value = None
        page.update()

        def print_in_thread():
            try:
                img = generate_label_image(text_to_print, code_type)
                print_image(img, printer_name)
                save_history_entry(text_to_print, printer_name, code_type)

                def show_success():
                    page.show_dialog(ft.SnackBar(ft.Text("Print complete!")))
                    page.update()

                def hide_progress_success():
                    progress_bar.visible = False
                    page.update()

                page.run_thread(show_success)
                threading.Timer(
                    0.5, lambda: page.run_thread(hide_progress_success)
                ).start()

            except Exception:

                def show_error():
                    progress_bar.color = ft.Colors.ERROR
                    page.update()
                    page.show_dialog(
                        ft.SnackBar(
                            ft.Text(f"Print failed: {str(exc)}"),
                            bgcolor=ft.Colors.ERROR,
                        )
                    )
                    page.update()

                def hide_progress_error():
                    progress_bar.visible = False
                    progress_bar.color = ft.Colors.PRIMARY
                    page.update()

                page.run_thread(show_error)
                threading.Timer(
                    0.5, lambda: page.run_thread(hide_progress_error)
                ).start()

        threading.Thread(target=print_in_thread, daemon=True).start()
        barcode_text.value = ""
        await barcode_text.focus()
        page.update()

    async def focus_on_background_click(e):
        await barcode_text.focus()

    async def reprint_from_history(barcode: str, code_type: str):
        try:
            set_clipboard_text(barcode)
        except Exception:
            pass  # clipboard failure is non-fatal

        barcode_text.value = barcode
        if code_type == CODE_TYPE_QRCODE:
            barcode_chooser.selected = [QRCODE_SELECTOR_VALUE]
        else:
            barcode_chooser.selected = ["1"]

        print_button.content = ft.Text(f"Print {get_code_type_display(code_type)}")
        current_view[0] = 0
        page.navigation_bar.selected_index = 0
        update_view()
        await barcode_text.focus()
        page.show_dialog(ft.SnackBar(ft.Text("Copied to clipboard & text field!")))
        page.update()

    def build_history_table():
        history = load_history()
        if not history:
            return ft.Container(
                content=ft.Text(
                    "History Empty\n\nMade with ❤️ by Danny Pham",
                    size=20,
                    color=ft.Colors.GREY,
                    text_align=ft.TextAlign.CENTER,
                ),
                alignment=ft.alignment.Alignment(0, 0),
                expand=True,
            )

        rows = []
        for entry in history:
            timestamp = datetime.fromisoformat(entry["timestamp"])
            formatted_time = timestamp.strftime("%m/%d/%Y %I:%M %p")
            code_type = entry.get("code_type", CODE_TYPE_BARCODE)
            type_text = get_code_type_display(code_type)
            entry_barcode = entry["barcode"]
            entry_code_type = code_type

            async def on_row_tap(e, b=entry_barcode, ct=entry_code_type):
                await reprint_from_history(b, ct)

            rows.append(
                ftd.DataRow2(
                    selected=False,
                    on_tap=on_row_tap,
                    cells=[
                        ft.DataCell(ft.Text(type_text)),
                        ft.DataCell(ft.Text(entry["barcode"])),
                        ft.DataCell(ft.Text(entry["printer"])),
                        ft.DataCell(ft.Text(formatted_time)),
                    ],
                )
            )

        return ft.Column(
            [
                ftd.DataTable2(
                    expand=True,
                    column_spacing=0,
                    heading_row_color=ft.Colors.PRIMARY_CONTAINER,
                    min_width=500,
                    columns=[
                        ftd.DataColumn2(ft.Text("Type"), size="s"),
                        ftd.DataColumn2(ft.Text("Data"), size="l"),
                        ftd.DataColumn2(ft.Text("Printer"), size="m"),
                        ftd.DataColumn2(ft.Text("Date & Time"), size="m"),
                    ],
                    rows=rows,
                ),
            ],
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    def handle_clear_history(e):
        clear_history()
        update_view()
        page.show_dialog(ft.SnackBar(ft.Text("History cleared!")))
        page.update()

    def on_navigation_change(e):
        current_view[0] = e.control.selected_index
        update_view()

    def update_view():
        page.clean()
        page.add(progress_bar)
        if current_view[0] == 0:
            page.floating_action_button = None
            page.add(print_view)
        else:
            history = load_history()
            page.floating_action_button = (
                ft.FloatingActionButton(
                    icon=ft.CupertinoIcons.DELETE_SOLID,
                    tooltip="Clear History",
                    on_click=handle_clear_history,
                )
                if history
                else None
            )
            page.add(build_history_table())
        page.update()

    barcode_text.on_submit = handle_print

    initial_icon = (
        ft.CupertinoIcons.MOON_FILL
        if page.theme_mode == ft.ThemeMode.DARK
        else ft.CupertinoIcons.SUN_MAX_FILL
    )
    theme_button = ft.IconButton(
        icon=initial_icon, on_click=toggle_theme, tooltip="Toggle Theme"
    )

    page.appbar = ft.AppBar(
        title=ft.Text("Barcode Printer"),
        actions=[
            theme_button,
            ft.IconButton(
                icon=ft.CupertinoIcons.FLOPPY_DISK,
                on_click=handle_save_settings,
                tooltip="Save Settings",
            ),
        ],
        actions_padding=5,
        bgcolor=ft.Colors.SURFACE_CONTAINER,
    )

    page.navigation_bar = ft.NavigationBar(
        destinations=[
            ft.NavigationBarDestination(icon=ft.Icons.BARCODE_READER, label="Print"),
            ft.NavigationBarDestination(icon=ft.Icons.HISTORY_ROUNDED, label="History"),
        ],
        on_change=on_navigation_change,
    )

    print_button = ft.FilledButton(
        width=245,
        height=50,
        content=ft.Text("Print Barcode"),
        icon=ft.CupertinoIcons.PRINTER_FILL,
        on_click=handle_print,
    )

    async def on_code_type_change(e):
        code_type = get_selected_code_type()
        print_button.content = ft.Text(f"Print {get_code_type_display(code_type)}")
        page.update()

    barcode_chooser.on_change = on_code_type_change

    print_view = ft.Stack(
        [
            ft.GestureDetector(
                content=ft.Container(expand=True),
                on_tap=focus_on_background_click,
            ),
            ft.Column(
                controls=[
                    barcode_chooser,
                    printer_dropdown,
                    barcode_text,
                    ft.Row(
                        controls=[
                            ft.OutlinedButton(
                                width=245,
                                height=50,
                                content=ft.Text("Preview"),
                                icon=ft.CupertinoIcons.EYE_FILL,
                                on_click=show_preview,
                            ),
                            print_button,
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=10,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
        ],
        expand=True,
    )

    page.add(progress_bar)
    page.add(print_view)


if __name__ == "__main__":
    ft.run(main)
