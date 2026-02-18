# 🖨️ Barcode & QR Code Printer

A modern, production-ready desktop application for generating and printing Code128 barcodes and QR codes on Windows. Built with Python and Flet for a beautiful native experience with threaded printing and atomic file operations.

## ✨ Features

### Core Features
- 🎯 **Simple Interface** - Clean, Material Design 3 interface for quick barcode printing
- 📱 **Dual Code Support** - Generate both Code128 barcodes and QR codes
- ⌨️ **Barcode Scanner Support** - Scan barcodes directly with USB/Bluetooth scanners
- 🖨️ **Multi-Printer Support** - Select from any installed Windows printer
- 👁️ **Preview** - See your barcode/QR code before printing with async generation
- 📊 **Print History** - Track all printed codes with timestamps and type indicators
- 🔁 **One-Click Reprint** - Tap any history entry to copy it to the clipboard and text field, ready to reprint instantly
- 🗑️ **Clear History** - Contextual floating action button appears when history has entries to clear it in one tap
- 🏷️ **Dynamic Print Button** - Button label updates to "Print Barcode" or "Print QR Code" based on the selected code type
- 🎨 **Dark/Light Mode** - Choose your preferred theme with persistent settings
- 💾 **Settings Persistence** - Remembers your printer and theme preferences with atomic file writes

### Technical Features
- ⚡ **Performance Optimized** - LRU cache with thread-safe access for instant code generation
- 🎯 **Auto-Focus** - Automatically re-focuses the input field on window focus and background click, always ready for the next scan
- 🧵 **Threaded Printing** - Non-blocking print operations keep UI responsive
- 📐 **Smart Scaling** - Auto-scales to 4 inches or page width, handles both dimensions
- 🔒 **Thread-Safe** - Proper locking for concurrent operations
- 💪 **Robust Error Handling** - Graceful handling of printer failures and invalid input with backward-compatible history entries
- 🎚️ **Progress Indicator** - Visual indeterminate progress bar during print with delayed auto-hide via `threading.Timer`
- 📐 **DPI Aware Printing** - Adapts to any printer resolution (300, 600, 1200+ DPI)
- 🖥️ **Per-Monitor DPI Aware** - Display renders sharply on high-DPI and multi-monitor setups via `SetProcessDpiAwareness`
- 🪟 **Minimum Window Size** - Enforces a 700×700px minimum to prevent layout breakage
- 🚫 **Zero pywin32 Dependency** - All printer access, clipboard, and GDI printing handled natively via `ctypes`

## 📸 Screenshots

![Screenshot of Barcode Printer](screenshot.avif)

## 🚀 Quick Start

### Download the Installer

The easiest way to get started is to download the pre-built installer directly from the [Releases](https://github.com/dannyphamv/flet-barcode-printer/releases) page. Run `BarcodePrinter_Setup.exe` and follow the prompts — no Python required.

### Build from Source

**Prerequisites:** Python 3.10+

1. **Clone the repository and install dependencies:**

   ```bash
   git clone https://github.com/dannyphamv/flet-barcode-printer.git
   cd flet-barcode-printer
   pip install -r requirements.txt
   ```

2. **Build the standalone Windows executable:**

   ```bash
   flet build windows
   ```

3. **Create the installer with Inno Setup:**

   [Download and install Inno Setup](https://jrsoftware.org/isdl.php), then double-click `installer.iss` to open it in Inno Setup Compiler and click the **Compile** button.

   Your installer will be output to `installer_output\BarcodePrinter_Setup.exe`.

## 💡 Usage

1. **Select Code Type** - Choose between Barcode or QR Code
2. **Enter/Scan Data** - Type or scan your barcode data
3. **Preview** (Optional) - Click Preview to see the generated code
4. **Select Printer** - Choose your target printer from the dropdown
5. **Print** - Click Print or press Enter
6. **Reprint** - In the History tab, tap any row to copy the data to your clipboard and jump back to the Print tab ready to go

The app automatically:
- Generates high-quality codes optimized for 4-inch printing
- Scales to fit smaller label sizes
- Centers the code on the page
- Maintains aspect ratio
- Saves to print history


## 🔧 Dependencies

| Package                | Version  | Purpose                          |
| ---------------------- | -------- | -------------------------------- |
| flet                   | >=0.80.5 | Modern GUI framework             |
| flet-datatable2        | >=0.80.5 | Enhanced data tables             |
| python-barcode[images] | >=0.16.1 | Code128 barcode generation       |
| qrcode[pil]            | >=8.2    | QR code generation               |
| Pillow                 | >=12.1.1 | Image processing & LANCZOS resampling |

> `pywin32` is **not required**. Printer enumeration, GDI printing, and clipboard access are all handled through Python's built-in `ctypes` module.

See [requirements.txt](requirements.txt) for exact versions.

## 🏗️ Technical Architecture

### Threading Model
- **Main Thread**: Flet UI event loop
- **Background Threads**: Print operations run in daemon threads
- **Thread Safety**: `threading.Lock` protects LRU cache, `page.run_thread()` for UI updates
- **Non-blocking**: `threading.Timer` for delayed progress bar hide instead of `time.sleep()`

### Data Persistence
- **Atomic Writes**: Uses `tempfile.mkstemp()` + `os.replace()` to prevent corruption
- **JSON Storage**: Settings and history stored in `%APPDATA%/BarcodePrinter/`
- **Graceful Degradation**: Handles corrupted files by returning defaults
- **Backward-Compatible History**: Old entries without a `code_type` field default to barcode automatically

### Print Quality
- **DPI Detection**: Queries printer capabilities via `GetDeviceCaps()` through `ctypes`
- **Dynamic Scaling**: Calculates exact pixel dimensions based on printer DPI
- **High-Quality Resampling**: Uses Pillow's LANCZOS algorithm
- **Overflow Protection**: Checks both width and height constraints

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.