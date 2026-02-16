"""Barcode Printer GUI using Flet framework."""

import json
import os
import base64
from io import BytesIO
from pathlib import Path
from datetime import datetime

import flet as ft

import io
import logging
from collections import OrderedDict

import barcode as python_barcode
from barcode.writer import ImageWriter
from PIL import Image, ImageWin
import win32con
import win32print
import win32ui


# Printer List Cache
_PRINTER_LIST_CACHE = None


def get_printers(force_refresh=False) -> list[str]:
    """Return a list of available printer names.

    Args:
        force_refresh: If True, refresh the cache even if it exists.

    Returns:
        List of available printer names.
    """
    global _PRINTER_LIST_CACHE
    if force_refresh or _PRINTER_LIST_CACHE is None:
        _PRINTER_LIST_CACHE = [
            printer[2]
            for printer in win32print.EnumPrinters(
                win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            )
        ]
    return _PRINTER_LIST_CACHE


# Barcode Image Cache (LRU cache limited to 100 items)
BARCODE_IMAGE_CACHE = OrderedDict()
BARCODE_IMAGE_CACHE_MAXSIZE = 100


def generate_label_image(barcode_text: str) -> Image.Image:
    """Generate a label image with a barcode for the given text.

    Uses LRU cache for performance optimization.

    Args:
        barcode_text: The text to encode in the barcode.

    Returns:
        PIL Image object containing the barcode label.
    """
    if barcode_text in BARCODE_IMAGE_CACHE:
        # Move to end to mark as recently used
        BARCODE_IMAGE_CACHE.move_to_end(barcode_text)
        return BARCODE_IMAGE_CACHE[barcode_text].copy()

    # Generate barcode using python-barcode
    code128 = python_barcode.get("code128", barcode_text, writer=ImageWriter())
    with io.BytesIO() as buffer:
        code128.write(buffer)
        buffer.seek(0)
        barcode_img = Image.open(buffer).copy()

    # Create a white label and center the barcode on it
    label_width, label_height = 600, 300
    label_img = Image.new("RGB", (label_width, label_height), 0xFFFFFF)
    barcode_x = (label_width - barcode_img.width) // 2
    barcode_y = (label_height - barcode_img.height) // 2
    label_img.paste(barcode_img, (barcode_x, barcode_y))

    # Add to cache and enforce max size
    BARCODE_IMAGE_CACHE[barcode_text] = label_img.copy()
    BARCODE_IMAGE_CACHE.move_to_end(barcode_text)
    if len(BARCODE_IMAGE_CACHE) > BARCODE_IMAGE_CACHE_MAXSIZE:
        BARCODE_IMAGE_CACHE.popitem(last=False)

    return label_img


def print_image(img: Image.Image, printer_name: str) -> None:
    """Send the given image to the specified printer using Windows APIs.

    Args:
        img: PIL Image object to print.
        printer_name: Name of the Windows printer to use.

    Raises:
        RuntimeError: If printer device context cannot be created.
        Exception: If printing fails for any other reason.
    """
    pdc = win32ui.CreateDC()
    if pdc is None:
        logging.error("Failed to create printer device context.")
        raise RuntimeError("Failed to create printer device context.")

    pdc.CreatePrinterDC(printer_name)
    try:
        pdc.StartDoc("Barcode Print")
        pdc.StartPage()

        # Get printable area size
        printable_width = pdc.GetDeviceCaps(win32con.HORZRES)
        printable_height = pdc.GetDeviceCaps(win32con.VERTRES)

        # Resize image to fit printable width (maintain aspect ratio)
        if img.width != printable_width:
            scale = printable_width / img.width
            scaled_width = printable_width
            scaled_height = int(img.height * scale)
            img = img.resize((scaled_width, scaled_height))

        # Center the image on the page
        x1 = 0
        if printable_height > img.height:
            y1 = (printable_height - img.height) // 2
        else:
            y1 = 0
        x2 = x1 + img.width
        y2 = y1 + img.height

        dib = ImageWin.Dib(img)
        dib.draw(pdc.GetHandleOutput(), (x1, y1, x2, y2))

        pdc.EndPage()
        pdc.EndDoc()
    except Exception as exc:
        logging.error("Print error: %s", exc)
        raise
    finally:
        pdc.DeleteDC()


# Define the settings file path in AppData
APPDATA_DIR = Path(os.getenv("APPDATA")) / "BarcodePrinter"
SETTINGS_FILE = APPDATA_DIR / "settings.json"
HISTORY_FILE = APPDATA_DIR / "history.json"


def ensure_appdata_dir():
    """Create AppData directory if it doesn't exist."""
    APPDATA_DIR.mkdir(parents=True, exist_ok=True)


def save_settings(printer, theme_mode):
    """Save printer and theme mode settings to JSON file."""
    ensure_appdata_dir()
    settings = {"printer": printer, "theme_mode": theme_mode.value}
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f)


def load_settings():
    """Load settings from JSON file if it exists."""
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def save_history_entry(barcode_text, printer_name):
    """Save a print history entry."""
    ensure_appdata_dir()
    history = load_history()

    entry = {
        "barcode": barcode_text,
        "printer": printer_name,
        "timestamp": datetime.now().isoformat(),
    }

    history.insert(0, entry)  # Add to beginning

    # Keep only last 100 entries
    history = history[:100]

    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def load_history():
    """Load print history from JSON file."""
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def clear_history():
    """Clear all print history entries."""
    ensure_appdata_dir()
    with open(HISTORY_FILE, "w") as f:
        json.dump([], f)


def main(page: ft.Page):
    """Main application entry point."""
    # Load saved settings
    saved_config = load_settings()

    # Initial setup
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.window.min_width = 600
    page.window.min_height = 700
    page.window.width = 600
    page.window.height = 700
    icon_path = os.path.abspath("barcode-scan.ico")
    page.window.icon = icon_path
    page.title = "Barcode Printer"

    # Navigation state
    current_view = [0]  # Use list to allow modification in nested functions

    # Set theme from settings or default to DARK
    saved_theme = saved_config.get("theme_mode") if saved_config else "dark"
    if saved_theme == "dark":
        page.theme_mode = ft.ThemeMode.DARK
    else:
        page.theme_mode = ft.ThemeMode.LIGHT

    # UI Components
    barcode_text = ft.TextField(
        label="Enter or Scan Barcode",
        width=500,
        autofocus=True,
        border_color=ft.Colors.BLUE,
    )

    preview_image = ft.Image(src="", width=300, visible=False, border_radius=5)

    printers = get_printers()
    default_printer = printers[0] if printers else None
    if saved_config and saved_config.get("printer") in printers:
        default_printer = saved_config["printer"]

    printer_dropdown = ft.Dropdown(
        label="Select Printer",
        width=500,
        value=default_printer,
        options=[ft.dropdown.Option(p) for p in printers],
        border_color=ft.Colors.BLUE,
    )

    # Event Handlers
    async def on_window_event(e):
        """Handle window focus events."""
        if e.data == "focus":
            await barcode_text.focus()
            page.update()

    page.on_window_event = on_window_event

    def pil_to_base64(pil_img):
        """Convert PIL Image to base64 encoded string."""
        buffered = BytesIO()
        pil_img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{img_str}"

    def toggle_theme(e):
        """Toggle between dark and light theme modes."""
        if page.theme_mode == ft.ThemeMode.LIGHT:
            page.theme_mode = ft.ThemeMode.DARK
        else:
            page.theme_mode = ft.ThemeMode.LIGHT

        if page.theme_mode == ft.ThemeMode.LIGHT:
            theme_button.icon = ft.CupertinoIcons.SUN_MAX_FILL
        else:
            theme_button.icon = ft.CupertinoIcons.MOON_FILL

        page.update()

    def handle_save_settings(e):
        """Save current settings to file."""
        save_settings(printer_dropdown.value, page.theme_mode)
        page.show_dialog(ft.SnackBar(ft.Text("Settings saved!")))
        page.update()

    def show_preview(e):
        """Generate and display barcode preview."""
        if not barcode_text.value:
            preview_image.visible = False
            page.update()
            return
        pil_img = generate_label_image(barcode_text.value)
        b64_string = pil_to_base64(pil_img)
        preview_image.src = b64_string
        preview_image.visible = True
        page.update()

    async def handle_print(e):
        """Print the barcode and reset the form."""
        if not barcode_text.value:
            await barcode_text.focus()
            return

        print_image(generate_label_image(barcode_text.value), printer_dropdown.value)

        # Save to history
        save_history_entry(barcode_text.value, printer_dropdown.value)

        barcode_text.value = ""
        preview_image.visible = False
        await barcode_text.focus()
        page.show_dialog(ft.SnackBar(ft.Text("Printing!")))
        page.update()

    async def focus_on_background_click(e):
        """Focus text field when background is clicked."""
        await barcode_text.focus()

    def build_history_table():
        """Build the history table view."""
        history = load_history()

        if not history:
            return ft.Container(
                content=ft.Text(
                    "No print history yet", size=20, color=ft.Colors.GREY_500
                ),
                alignment=ft.alignment.Alignment(0, 0),
                expand=True,
            )

        # Create table rows
        rows = []
        for entry in history:
            timestamp = datetime.fromisoformat(entry["timestamp"])
            formatted_time = timestamp.strftime("%m/%d/%Y %I:%M %p")

            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(entry["barcode"], selectable=True)),
                        ft.DataCell(ft.Text(entry["printer"], selectable=True)),
                        ft.DataCell(ft.Text(formatted_time, selectable=True)),
                    ]
                )
            )

        return ft.Column(
            [
                ft.DataTable(
                    columns=[
                        ft.DataColumn(ft.Text("Barcode")),
                        ft.DataColumn(ft.Text("Printer")),
                        ft.DataColumn(ft.Text("Date & Time")),
                    ],
                    rows=rows,
                ),
            ],
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    def handle_clear_history(e):
        """Clear all print history."""
        clear_history()
        update_view()
        page.snack_bar = ft.SnackBar(ft.Text("History cleared!"))
        page.snack_bar.open = True
        page.update()

    def on_navigation_change(e):
        """Handle navigation bar changes."""
        current_view[0] = e.control.selected_index
        update_view()

    def update_view():
        """Update the displayed view based on navigation."""
        # Clear current content
        page.clean()

        if current_view[0] == 0:
            # Print view
            page.floating_action_button = None
            page.add(print_view)
        else:
            # History view - show clear history button
            history = load_history()
            if history:
                page.floating_action_button = ft.FloatingActionButton(
                    icon=ft.Icons.DELETE_SWEEP_ROUNDED,
                    tooltip="Clear History",
                    on_click=handle_clear_history,
                )
            else:
                page.floating_action_button = None
            page.add(build_history_table())

        page.update()

    # Set up event handlers
    barcode_text.on_submit = handle_print

    # UI Components - Theme Button
    if page.theme_mode == ft.ThemeMode.DARK:
        initial_icon = ft.CupertinoIcons.MOON_FILL
    else:
        initial_icon = ft.CupertinoIcons.SUN_MAX_FILL

    theme_button = ft.IconButton(icon=initial_icon, on_click=toggle_theme)

    # Page Layout

    page.appbar = ft.AppBar(
        title=ft.Text("🖨️ Barcode Printer"),
        actions=[
            theme_button,
            ft.IconButton(
                icon=ft.CupertinoIcons.FLOPPY_DISK,
                on_click=handle_save_settings,
                tooltip="Save Settings",
            ),
        ],
        bgcolor=ft.Colors.SURFACE_CONTAINER,
    )

    page.navigation_bar = ft.NavigationBar(
        destinations=[
            ft.NavigationBarDestination(icon=ft.Icons.BARCODE_READER, label="Print"),
            ft.NavigationBarDestination(icon=ft.Icons.HISTORY_ROUNDED, label="History"),
        ],
        on_change=on_navigation_change,
    )

    # Create the print view
    print_view = ft.Stack(
        [
            # Background layer - clickable
            ft.GestureDetector(
                content=ft.Container(
                    expand=True,
                ),
                on_tap=focus_on_background_click,
            ),
            # Foreground content layer
            ft.Column(
                controls=[
                    printer_dropdown,
                    barcode_text,
                    ft.Row(
                        controls=[
                            ft.OutlinedButton(
                                width=245,
                                height=50,
                                content=ft.Text("Preview"),
                                icon=ft.Icons.REMOVE_RED_EYE_ROUNDED,
                                on_click=show_preview,
                            ),
                            ft.FilledButton(
                                width=245,
                                height=50,
                                content=ft.Text("Print Barcode"),
                                icon=ft.CupertinoIcons.PRINTER_FILL,
                                on_click=handle_print,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=10,
                    ),
                    preview_image,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
        ],
        expand=True,
    )

    # Add initial view
    page.add(print_view)


if __name__ == "__main__":
    ft.run(main)
