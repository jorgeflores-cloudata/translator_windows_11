"""Product identity and resources shared by source and installed builds."""
from pathlib import Path
import ctypes
import os

APP_NAME = "Dova Translator"
APP_VERSION = "1.0.0"
APP_ID = "Dova.Translator.Desktop"
ASSET_DIR = Path(__file__).resolve().parent / "assets"


def configure_taskbar():
    if os.name == "nt":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except OSError:
            pass


def brand_window(root):
    root.title(APP_NAME)
    icon = ASSET_DIR / "dova-translator.ico"
    if icon.is_file():
        try:
            root.iconbitmap(default=str(icon))
        except Exception:
            pass

