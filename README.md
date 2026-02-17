# 🖨️ Barcode & QR Code Printer

A modern, production-ready desktop application for generating and printing Code128 barcodes and QR codes on Windows. Built with Python and Flet for a beautiful native experience with threaded printing and atomic file operations.

## ✨ Features

### Core Features
- 🎯 **Simple Interface** - Clean, Material Design 3 interface for quick barcode printing
- 📱 **Dual Code Support** - Generate both Code128 barcodes and QR codes
- ⌨️ **Barcode Scanner Support** - Scan barcodes directly with USB/Bluetooth scanners
- 🖨️ **Multi-Printer Support** - Select from any installed Windows printer
- 👁️ **Live Preview** - See your barcode/QR code before printing with async generation
- 📊 **Print History** - Track all printed codes with timestamps and type indicators
- 🎨 **Dark/Light Mode** - Choose your preferred theme with persistent settings
- 💾 **Settings Persistence** - Remembers your printer and theme preferences with atomic file writes

### Technical Features
- ⚡ **Performance Optimized** - LRU cache with thread-safe access for instant code generation
- 🎯 **Auto-Focus** - Always ready for the next scan with smart focus management
- 🧵 **Threaded Printing** - Non-blocking print operations keep UI responsive
- 📏 **Smart Scaling** - Auto-scales to 4 inches or page width, handles both dimensions
- 🔒 **Thread-Safe** - Proper locking for concurrent operations
- 💪 **Robust Error Handling** - Graceful handling of printer failures and invalid input
- 🎚️ **Progress Indicator** - Visual progress bar for print operations
- ⌨️ **Keyboard Shortcuts** - Ctrl+P (Print), Ctrl+S (Save), Ctrl+R (Preview), Esc (Clear)
- 📐 **DPI Aware Printing** - Adapts to any printer resolution (300, 600, 1200+ DPI)

## 📸 Screenshots

![Screenshot of Barcode Printer](screenshot.avif)

## 🚀 Quick Start

### Prerequisites

- **Python 3.9 or higher** (required for modern features)
- **Windows OS** (for printer integration via pywin32)

### Installation

1. **Clone or download this repository**

   ```bash
   git clone https://github.com/dannyphamv/flet-barcode-printer.git
   cd flet-barcode-printer
   ```

2. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**
   ```bash
   python main.py
   ```
   **Or launch from .bat file**
   ```bash
   run.bat
   ```

## 💡 Usage

1. **Select Code Type** - Choose between Barcode or QR Code
2. **Enter/Scan Data** - Type or scan your barcode data
3. **Preview** (Optional) - Click Preview to see the generated code
4. **Select Printer** - Choose your target printer from the dropdown
5. **Print** - Click Print or press Enter

The app automatically:
- Generates high-quality codes optimized for 4-inch printing
- Scales to fit smaller label sizes
- Centers the code on the page
- Maintains aspect ratio
- Saves to print history

## 📁 Project Structure

```
flet-barcode-printer/
├── main.py               # Main application (850+ lines, production-ready)
├── requirements.txt      # Python dependencies
├── run.bat               # Windows launcher
├── barcode-scan.ico      # Application icon
├── README.md             # This file
└── LICENSE               # MIT License
```

## 🔧 Dependencies

| Package                | Version  | Purpose              |
| ---------------------- | -------- | -------------------- |
| flet                   | >=0.24.0 | Modern GUI framework        |
| flet-datatable2        | >=0.80.5 | Enhanced data tables |
| python-barcode[images] | >=0.15.1 | Code128 barcode generation   |
| qrcode                 | >=0.4.6  | QR code generation   |
| Pillow                 | >=10.0.0 | Image processing & LANCZOS resampling    |
| pywin32                | >=306    | Windows printer APIs |

See [requirements.txt](requirements.txt) for exact versions.

## 🏗️ Technical Architecture

### Threading Model
- **Main Thread**: Flet UI event loop
- **Background Threads**: Print operations run in daemon threads
- **Thread Safety**: `threading.Lock` protects LRU cache, `page.run_thread()` for UI updates
- **Non-blocking**: `threading.Timer` for delayed operations instead of `time.sleep()`

### Data Persistence
- **Atomic Writes**: Uses `tempfile.mkstemp()` + `os.replace()` to prevent corruption
- **JSON Storage**: Settings and history stored in `%APPDATA%/BarcodePrinter/`
- **Graceful Degradation**: Handles corrupted files by returning defaults

### Print Quality
- **DPI Detection**: Queries printer capabilities via `GetDeviceCaps()`
- **Dynamic Scaling**: Calculates exact pixel dimensions based on printer DPI
- **High-Quality Resampling**: Uses Pillow's LANCZOS algorithm
- **Overflow Protection**: Checks both width and height constraints

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Flet](https://flet.dev/) - Beautiful Python GUI framework
- [Fluent Emoji](https://github.com/microsoft/fluentui-emoji) - Fluent Emoji from Microsoft
- [python-barcode](https://github.com/WhyNotHugo/python-barcode) - Barcode generation library
- [qrcode](https://github.com/lincolnloop/python-qrcode) - QR code generation library