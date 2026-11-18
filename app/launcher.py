"""Installed entry point, launched by the bundled Python runtime in isolated mode."""
from pathlib import Path
import argparse
import ctypes
from ctypes import wintypes
import json
import os
import sys
import traceback

APP_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_ROOT))

from product import APP_NAME, APP_VERSION, configure_taskbar


def self_test():
    """Exercise the shipped runtime/UI without recording audio or using the network."""
    import av
    import ctranslate2
    import faster_whisper
    import numpy
    import sounddevice
    import keyboard
    import pyperclip
    import anthropic
    import openai
    import keyring
    import websockets
    import language_tool_python
    import translator_app as appmod
    from product import ASSET_DIR

    appmod.SMOKE = True
    appmod.load_cfg = lambda: dict(appmod.DEFAULTS, mic_open=False, topmost=False)
    appmod.App.register_hotkey = lambda self: None
    appmod.App.refresh_key_status = lambda self: self.key_status.configure(text="Prueba local")
    root = appmod.tk.Tk()
    root.withdraw()
    application = appmod.App(root)
    root.after(600, root.quit)
    root.mainloop()
    if not application.ready:
        raise RuntimeError("La interfaz no llego al estado listo.")
    if not (ASSET_DIR / "dova-translator.ico").is_file():
        raise RuntimeError("Falta el icono de la aplicacion.")
    tk_version = root.tk.call("info", "patchlevel")
    root.destroy()
    return {
        "ok": True,
        "application": APP_NAME,
        "version": APP_VERSION,
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "prefix": sys.prefix,
        "tk": tk_version,
        "av": av.__version__,
        "numpy": numpy.__version__,
        "module_locations": {
            "av": av.__file__,
            "ctranslate2": ctranslate2.__file__,
            "faster_whisper": faster_whisper.__file__,
            "openai": openai.__file__,
        },
        "recording": False,
        "network_used": False,
    }


def main():
    parser = argparse.ArgumentParser(prog=APP_NAME)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    configure_taskbar()
    mutex = None
    kernel32 = None
    try:
        if args.self_test:
            result = self_test()
            if args.report:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(json.dumps(result, indent=2), encoding="utf-8")
            if sys.stdout is not None:
                print(json.dumps(result, ensure_ascii=False))
            return 0

        if os.name == "nt":
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
            kernel32.CreateMutexW.restype = wintypes.HANDLE
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
            ctypes.set_last_error(0)
            mutex = kernel32.CreateMutexW(None, False, "Local\\DovaTranslatorDesktop")
            if not mutex:
                raise ctypes.WinError(ctypes.get_last_error())
            if mutex and ctypes.get_last_error() == 183:
                ctypes.windll.user32.MessageBoxW(None,
                    "Dova Translator ya esta abierto. Busca su ventana en la barra de tareas.",
                    APP_NAME, 0x40)
                return 0
        from translator_app import main as run_application
        run_application()
        return 0
    except Exception as error:
        log_dir = Path(os.environ.get("APPDATA", str(Path.home()))) / "DovaTranslator"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "error.log"
        with log_path.open("a", encoding="utf-8") as log:
            log.write("\n" + traceback.format_exc())
        if args.self_test:
            result = {"ok": False, "error": str(error), "log": str(log_path)}
            if args.report:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(json.dumps(result, indent=2), encoding="utf-8")
            if sys.stderr is not None:
                print(json.dumps(result, ensure_ascii=False), file=sys.stderr)
        elif os.name == "nt":
            ctypes.windll.user32.MessageBoxW(None,
                "No se pudo iniciar Dova Translator.\n\n"
                f"Detalle: {error}\n\nEl registro esta en:\n{log_path}", APP_NAME, 0x10)
        return 1
    finally:
        if mutex and kernel32:
            kernel32.CloseHandle(mutex)


if __name__ == "__main__":
    raise SystemExit(main())
