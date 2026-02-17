"""Barcode Printer GUI using Flet framework."""

import json
import os
import base64
import threading
import tempfile
import time
from io import BytesIO
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

import flet as ft
import flet_datatable2 as ftd

import barcode as python_barcode
from barcode.writer import ImageWriter
import qrcode
from PIL import Image, ImageWin
import win32con
import win32print
import win32ui


@dataclass
class PrintConfig:
    """Configuration constants for barcode printing."""

    width_inches: int = 4
    qr_box_size: int = 20
    qr_border: int = 4
    cache_max_size: int = 100
    history_max_entries: int = 100


# Global configuration instance
CONFIG = PrintConfig()

# Configuration Constants (for backwards compatibility)
CODE_TYPE_BARCODE = "barcode"
CODE_TYPE_QRCODE = "qrcode"
QRCODE_SELECTOR_VALUE = "2"


# Printer List Cache
_PRINTER_LIST_CACHE: Optional[list[str]] = None

# Thread lock for cache safety
_CACHE_LOCK = threading.Lock()


def get_printers(force_refresh: bool = False) -> list[str]:
    """Return a list of available printer names.

    Args:
        force_refresh: If True, refresh the cache even if it exists.

    Returns:
        List of available printer names. Returns empty list if enumeration fails.
    """
    global _PRINTER_LIST_CACHE
    if force_refresh or _PRINTER_LIST_CACHE is None:
        try:
            _PRINTER_LIST_CACHE = [
                printer[2]
                for printer in win32print.EnumPrinters(
                    win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
                )
            ]
        except Exception:
            # Print spooler might be down or no printers installed
            _PRINTER_LIST_CACHE = []
    return _PRINTER_LIST_CACHE


@lru_cache(maxsize=100)
def _generate_label_image_cached(
    barcode_text: str, code_type: str = CODE_TYPE_BARCODE
) -> Image.Image:
    """Internal cached image generation function.

    This function is wrapped by generate_label_image() with thread safety.
    """
    if code_type == CODE_TYPE_QRCODE:
        try:
            # Generate QR code with larger box_size for 4-inch printing
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=CONFIG.qr_box_size,
                border=CONFIG.qr_border,
            )
            qr.add_data(barcode_text)
            qr.make(fit=True)
            code_img = qr.make_image(fill_color="black", back_color="white")
            # Convert to PIL Image if needed
            if not isinstance(code_img, Image.Image):
                code_img = code_img.convert("RGB")

            return code_img
        except Exception as e:
            raise ValueError(f"Failed to generate QR code: {str(e)}")
    else:
        try:
            # Generate barcode using python-barcode
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
    """Generate a label image with a barcode or QR code for the given text.

    Uses LRU cache for performance optimization with thread safety.

    Args:
        barcode_text: The text to encode in the barcode/QR code.
        code_type: Type of code to generate - CODE_TYPE_BARCODE or CODE_TYPE_QRCODE.

    Returns:
        PIL Image object containing the barcode/QR code label.

    Raises:
        ValueError: If barcode_text is empty or contains invalid characters.
    """
    if not barcode_text or not barcode_text.strip():
        raise ValueError("Barcode text cannot be empty")

    # Thread-safe cache access
    with _CACHE_LOCK:
        return _generate_label_image_cached(barcode_text, code_type)


def print_image(img: Image.Image, printer_name: str) -> None:
    """Send the given image to the specified printer using Windows APIs.

    Args:
        img: PIL Image object to print.
        printer_name: Name of the Windows printer to use.

    Raises:
        RuntimeError: If printer device context cannot be created.
        ValueError: If printer_name is invalid or not found.
        Exception: If printing fails for any other reason.
    """
    if not printer_name:
        raise ValueError("Printer name cannot be empty")

    # Validate printer exists
    available_printers = get_printers()
    if printer_name not in available_printers:
        raise ValueError(f"Printer '{printer_name}' not found")

    pdc = win32ui.CreateDC()
    if pdc is None:
        raise RuntimeError("Failed to create printer device context")

    try:
        pdc.CreatePrinterDC(printer_name)
    except Exception as e:
        raise RuntimeError(
            f"Failed to create printer DC for '{printer_name}': {str(e)}"
        )

    try:
        pdc.StartDoc("Barcode Print")
        pdc.StartPage()

        # Get printable area size and printer DPI
        printable_width = pdc.GetDeviceCaps(win32con.HORZRES)
        printable_height = pdc.GetDeviceCaps(win32con.VERTRES)
        printer_dpi = pdc.GetDeviceCaps(win32con.LOGPIXELSX)

        # Calculate target dimensions based on configured width
        max_width = int(CONFIG.width_inches * printer_dpi)
        aspect_ratio = img.height / img.width

        # Start with desired width, then check both dimensions
        target_width = min(max_width, printable_width)
        target_height = int(target_width * aspect_ratio)

        # If height overflows, scale down based on height instead
        if target_height > printable_height:
            target_height = printable_height
            target_width = int(target_height / aspect_ratio)

        # Resize image with high-quality resampling
        img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)

        # Center the image on the page
        x1 = (printable_width - target_width) // 2
        y1 = (printable_height - target_height) // 2
        x2 = x1 + target_width
        y2 = y1 + target_height

        dib = ImageWin.Dib(img)
        dib.draw(pdc.GetHandleOutput(), (x1, y1, x2, y2))

        pdc.EndPage()
        pdc.EndDoc()
    except Exception as exc:
        raise Exception(f"Print operation failed: {str(exc)}")
    finally:
        pdc.DeleteDC()


# Define the settings file path in AppData
APPDATA_DIR = Path(os.getenv("APPDATA")) / "BarcodePrinter"
SETTINGS_FILE = APPDATA_DIR / "settings.json"
HISTORY_FILE = APPDATA_DIR / "history.json"


def ensure_appdata_dir() -> None:
    """Create AppData directory if it doesn't exist."""
    APPDATA_DIR.mkdir(parents=True, exist_ok=True)


def load_json_file(filepath: Path, default=None):
    """Load data from a JSON file.

    Args:
        filepath: Path to the JSON file.
        default: Default value to return if file doesn't exist or has errors.

    Returns:
        Loaded data or default value.
    """
    if not filepath.exists():
        return default

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        # Return default if file is corrupted or unreadable
        return default


def save_json_file(filepath: Path, data) -> None:
    """Save data to a JSON file atomically.

    Args:
        filepath: Path to the JSON file.
        data: Data to save (must be JSON serializable).
    """
    ensure_appdata_dir()

    # Write to temporary file first, then rename (atomic operation)
    temp_fd, temp_path = tempfile.mkstemp(dir=APPDATA_DIR, suffix=".json", text=True)
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        # Atomic rename
        os.replace(temp_path, filepath)
    except Exception:
        # Clean up temp file if something went wrong
        try:
            os.unlink(temp_path)
        except:
            pass
        raise


def save_settings(printer: str, theme_mode) -> None:
    """Save printer and theme mode settings to JSON file."""
    settings = {"printer": printer, "theme_mode": theme_mode.value}
    save_json_file(SETTINGS_FILE, settings)


def load_settings() -> Optional[dict]:
    """Load settings from JSON file if it exists."""
    return load_json_file(SETTINGS_FILE)


def save_history_entry(
    barcode_text: str, printer_name: str, code_type: str = CODE_TYPE_BARCODE
) -> None:
    """Save a print history entry.

    Args:
        barcode_text: The text that was encoded.
        printer_name: Name of the printer used.
        code_type: Type of code printed - CODE_TYPE_BARCODE or CODE_TYPE_QRCODE.
    """
    history = load_history()

    entry = {
        "barcode": barcode_text,
        "printer": printer_name,
        "code_type": code_type,
        "timestamp": datetime.now().isoformat(),
    }

    history.insert(0, entry)  # Add to beginning

    # Keep only last N entries
    history = history[: CONFIG.history_max_entries]

    save_json_file(HISTORY_FILE, history)


def load_history() -> list[dict]:
    """Load print history from JSON file."""
    return load_json_file(HISTORY_FILE, default=[])


def clear_history() -> None:
    """Clear all print history entries."""
    save_json_file(HISTORY_FILE, [])


def pil_to_base64(img: Image.Image) -> str:
    """Convert a PIL Image to a base64 encoded string for display in Flet.

    Args:
        img: PIL Image object to convert.

    Returns:
        Base64 encoded string suitable for use as image src in Flet.
    """
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.read()).decode()
    return f"data:image/png;base64,{img_base64}"


def get_code_type_display(code_type: str) -> str:
    """Convert code type to display text.

    Args:
        code_type: CODE_TYPE_BARCODE or CODE_TYPE_QRCODE.

    Returns:
        Display text for the code type.
    """
    return "QR Code" if code_type == CODE_TYPE_QRCODE else "Barcode"


def setup_page_config(page: ft.Page, saved_config: Optional[dict]) -> None:
    """Configure page settings and properties.

    Args:
        page: Flet page object.
        saved_config: Previously saved configuration or None.
    """
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.window.min_width = 600
    page.window.min_height = 700
    page.window.width = 600
    page.window.height = 700
    page.window.icon = os.path.abspath("barcode-scan.ico")
    page.title = "Barcode Printer"

    # Set theme from settings or default to DARK
    saved_theme = saved_config.get("theme_mode") if saved_config else "dark"
    page.theme_mode = ft.ThemeMode.DARK if saved_theme == "dark" else ft.ThemeMode.LIGHT


def create_ui_components(
    page: ft.Page, printers: list[str], saved_config: Optional[dict]
) -> dict:
    """Create all UI components.

    Args:
        page: Flet page object.
        printers: List of available printers.
        saved_config: Previously saved configuration or None.

    Returns:
        Dictionary of UI components.
    """
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

    preview_image = ft.Image(src="", width=200, visible=False, border_radius=5)

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
        width=None,  # Full width
        visible=False,
        color=ft.Colors.PRIMARY,
        height=4,  # Thin bar like YouTube/Google style
    )

    return {
        "barcode_chooser": barcode_chooser,
        "barcode_text": barcode_text,
        "preview_image": preview_image,
        "printer_dropdown": printer_dropdown,
        "progress_bar": progress_bar,
    }


def main(page: ft.Page) -> None:
    """Main application entry point."""
    # Load saved settings
    saved_config = load_settings()

    # Setup page configuration
    setup_page_config(page, saved_config)

    # Navigation state
    current_view = [0]  # Use list to allow modification in nested functions

    # Get printers and check if any are available
    printers = get_printers()
    if not printers:
        # Show error dialog if no printers found
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

    # Create UI components
    components = create_ui_components(page, printers, saved_config)
    barcode_chooser = components["barcode_chooser"]
    barcode_text = components["barcode_text"]
    preview_image = components["preview_image"]
    printer_dropdown = components["printer_dropdown"]
    progress_bar = components["progress_bar"]

    # Event Handlers
    async def on_window_event(e):
        """Handle window focus events."""
        if e.data == "focus":
            await barcode_text.focus()
            page.update()

    page.on_window_event = on_window_event

    def get_selected_code_type() -> str:
        """Get the currently selected code type from the segmented button.

        Returns:
            CODE_TYPE_BARCODE or CODE_TYPE_QRCODE.
        """
        return (
            CODE_TYPE_QRCODE
            if QRCODE_SELECTOR_VALUE in barcode_chooser.selected
            else CODE_TYPE_BARCODE
        )

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

    async def show_preview(e):
        """Generate and display barcode/QR code preview."""
        if not barcode_text.value or not barcode_text.value.strip():
            preview_image.visible = False
            page.update()
            return

        code_type = get_selected_code_type()

        try:
            # Generate image (synchronous but fast enough for preview)
            pil_img = generate_label_image(barcode_text.value.strip(), code_type)
            b64_string = pil_to_base64(pil_img)
            preview_image.src = b64_string
            preview_image.visible = True
        except ValueError as e:
            preview_image.visible = False
            page.show_dialog(ft.SnackBar(ft.Text(str(e)), bgcolor=ft.Colors.ERROR))
        except Exception as e:
            preview_image.visible = False
            page.show_dialog(
                ft.SnackBar(
                    ft.Text(f"Preview failed: {str(e)}"), bgcolor=ft.Colors.ERROR
                )
            )

        page.update()

    async def handle_print(e):
        """Print the barcode/QR code in a separate thread and reset the form."""
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

        # Show indeterminate progress bar
        progress_bar.visible = True
        progress_bar.value = None  # Indeterminate (animated)
        page.update()

        def print_in_thread():
            """Print function to run in separate thread."""
            try:
                img = generate_label_image(text_to_print, code_type)
                print_image(img, printer_name)

                # Save to history
                save_history_entry(text_to_print, printer_name, code_type)

                # Update UI on success - use run_thread for safe UI updates
                def show_success():
                    page.show_dialog(ft.SnackBar(ft.Text("Print complete!")))
                    page.update()

                def hide_progress_success():
                    progress_bar.visible = False
                    page.update()

                page.run_thread(show_success)
                # Use Timer to hide progress bar after delay (non-blocking)
                threading.Timer(
                    0.5, lambda: page.run_thread(hide_progress_success)
                ).start()

            except ValueError as ve:
                # Error - use run_thread for safe UI updates
                def show_error_value():
                    progress_bar.color = ft.Colors.ERROR
                    page.update()
                    page.show_dialog(
                        ft.SnackBar(ft.Text(str(ve)), bgcolor=ft.Colors.ERROR)
                    )
                    page.update()

                def hide_progress_error():
                    progress_bar.visible = False
                    progress_bar.color = ft.Colors.PRIMARY
                    page.update()

                page.run_thread(show_error_value)
                # Use Timer to hide progress bar after delay (non-blocking)
                threading.Timer(
                    0.5, lambda: page.run_thread(hide_progress_error)
                ).start()

            except Exception as exc:
                # Error - use run_thread for safe UI updates
                def show_error_general():
                    progress_bar.color = ft.Colors.ERROR
                    page.update()
                    page.show_dialog(
                        ft.SnackBar(
                            ft.Text(f"Print failed: {str(exc)}"),
                            bgcolor=ft.Colors.ERROR,
                        )
                    )
                    page.update()

                def hide_progress_error_general():
                    progress_bar.visible = False
                    progress_bar.color = ft.Colors.PRIMARY
                    page.update()

                page.run_thread(show_error_general)
                # Use Timer to hide progress bar after delay (non-blocking)
                threading.Timer(
                    0.5, lambda: page.run_thread(hide_progress_error_general)
                ).start()
                page.update()

                page.run_thread(on_error_general)

        # Run print in background thread
        print_thread = threading.Thread(target=print_in_thread, daemon=True)
        print_thread.start()

        # Clear form
        barcode_text.value = ""
        preview_image.visible = False
        await barcode_text.focus()
        page.update()

    async def focus_on_background_click(e):
        """Focus text field when background is clicked."""
        await barcode_text.focus()

    def build_history_table():
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

            # Get code type (default to barcode for old entries without this field)
            code_type = entry.get("code_type", CODE_TYPE_BARCODE)
            type_text = get_code_type_display(code_type)

            rows.append(
                ftd.DataRow2(
                    selected=False,
                    cells=[
                        ft.DataCell(ft.Text(type_text)),
                        ft.DataCell(ft.Text(entry["barcode"], selectable=True)),
                        ft.DataCell(ft.Text(entry["printer"], selectable=True)),
                        ft.DataCell(ft.Text(formatted_time, selectable=True)),
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
        """Clear all print history."""
        clear_history()
        update_view()
        page.show_dialog(ft.SnackBar(ft.Text("History cleared!")))
        page.update()

    def on_navigation_change(e):
        """Handle navigation bar changes."""
        current_view[0] = e.control.selected_index
        update_view()

    def update_view():
        """Update the displayed view based on navigation."""
        # Clear current content
        page.clean()

        # Always add progress bar at top (under appbar)
        page.add(progress_bar)

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

    theme_button = ft.IconButton(
        icon=initial_icon, on_click=toggle_theme, tooltip="Toggle Theme"
    )

    # Page Layout

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

    # Create print button as variable so it can be updated
    print_button = ft.FilledButton(
        width=245,
        height=50,
        content=ft.Text("Print Barcode"),
        icon=ft.Icons.PRINT_ROUNDED,
        on_click=handle_print,
    )

    # Define and set the code type change handler
    async def on_code_type_change(e):
        """Handle segmented button changes to auto-refresh preview and update button text."""
        code_type = get_selected_code_type()

        # Update print button text
        print_button.content = ft.Text(f"Print {get_code_type_display(code_type)}")

        # Auto-refresh preview if visible
        if preview_image.visible and barcode_text.value:
            await show_preview(None)
        else:
            page.update()

    # Set the on_change handler now that print_button exists
    barcode_chooser.on_change = on_code_type_change

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
                    barcode_chooser,
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
                            print_button,
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

    # Add initial view with progress bar
    page.add(progress_bar)
    page.add(print_view)


if __name__ == "__main__":
    ft.run(main)
