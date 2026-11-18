"""Build the self-contained Windows 11 x64 Dova Translator MSI.

Run with the official 64-bit Python 3.12 runtime. msilib embeds the payload CAB;
the target PC needs neither Python nor a package manager. No credentials,
settings, recorded audio or model cache are copied into the payload.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import gc
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import sys
import uuid
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning, module="msilib")
import msilib
from msilib import schema, sequence, text


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = "Dova Translator"
PUBLISHER = "Dova"
NAMESPACE = uuid.UUID("00610b19-3fba-4c62-a357-8434034e96ca")
UPGRADE_CODE = "{" + str(uuid.uuid5(NAMESPACE, "Dova.Translator.Upgrade")).upper() + "}"
IGNORE_DIRS = {"__pycache__", "test", "tests", ".git", ".pytest_cache"}
SKIP_PACKAGES = {"pip", "PIL", "PyInstaller", "_pyinstaller_hooks_contrib"}
SKIP_DIST_PREFIXES = ("pip-", "pillow-", "pyinstaller-", "pyinstaller_hooks_contrib-")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def guid(key: str) -> str:
    return "{" + str(uuid.uuid5(NAMESPACE, key.casefold())).upper() + "}"


def ident(prefix: str, relative: str) -> str:
    return prefix + hashlib.sha256(relative.casefold().encode("utf-8")).hexdigest()[:28]


def skip_entry(name: str, packages=False) -> bool:
    if name in IGNORE_DIRS or name.endswith((".pyc", ".pyo")):
        return True
    if packages and (name in SKIP_PACKAGES or name.lower().startswith(SKIP_DIST_PREFIXES)):
        return True
    return False


def copy_tree(source: Path, target: Path, *, packages=False):
    for entry in sorted(source.iterdir()):
        if skip_entry(entry.name, packages):
            continue
        attributes = getattr(entry.lstat(), "st_file_attributes", 0)
        if entry.is_symlink() or attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise RuntimeError(f"Do not package a symlink or junction: {entry}")
        out = target / entry.name
        if entry.is_dir():
            out.mkdir(parents=True, exist_ok=True)
            copy_tree(entry, out)
        elif entry.is_file():
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(entry, out)


def build_stage(args, work: Path) -> Path:
    runtime = args.runtime.resolve()
    site_packages = args.site_packages.resolve()
    if not (runtime / "pythonw.exe").is_file() or not (runtime / "python312.dll").is_file():
        raise RuntimeError("--runtime must be the official 64-bit Python 3.12 directory")
    if not (site_packages / "faster_whisper").is_dir():
        raise RuntimeError("--site-packages must contain the installed app requirements")
    payload = work / "payload"
    payload.mkdir(parents=True)
    target_runtime = payload / "runtime"
    target_runtime.mkdir()
    for name in ("python.exe", "pythonw.exe", "python3.dll", "python312.dll",
                 "vcruntime140.dll", "vcruntime140_1.dll", "LICENSE.txt"):
        shutil.copy2(runtime / name, target_runtime / name)
    for name in ("DLLs", "tcl"):
        copy_tree(runtime / name, target_runtime / name)
    lib = target_runtime / "Lib"
    lib.mkdir()
    for entry in sorted((runtime / "Lib").iterdir()):
        if entry.name in {"site-packages", "ensurepip", "idlelib", "venv", "turtledemo"} or skip_entry(entry.name):
            continue
        if entry.is_dir():
            copy_tree(entry, lib / entry.name)
        elif entry.is_file():
            shutil.copy2(entry, lib / entry.name)
    copy_tree(site_packages, lib / "site-packages", packages=True)
    if args.redist_dir:
        copy_redist(args.redist_dir, payload)
    copy_tree(ROOT / "app", payload / "app")
    if not (payload / "app" / "launcher.py").is_file():
        raise RuntimeError("Missing app/launcher.py")
    if not (payload / "app" / "assets" / "dova-translator.ico").is_file():
        raise RuntimeError("Missing app/assets/dova-translator.ico")
    copy_documents(payload)
    packages = []
    for dist in importlib.metadata.distributions(path=[str(site_packages)]):
        name = dist.metadata.get("Name", "")
        if name.lower() in {"pip", "pillow", "pyinstaller", "pyinstaller-hooks-contrib"}:
            continue
        packages.append({
            "name": name, "version": dist.version,
            "license": dist.metadata.get("License-Expression") or dist.metadata.get("License") or "See bundled distribution metadata",
        })
    packages.sort(key=lambda item: item["name"].casefold())
    notices = ["# Third-party notices", "", "Dova Translator includes CPython 3.12 and the packages below.",
               "CPython terms are in runtime/LICENSE.txt. Package license files and metadata are retained in runtime/Lib/site-packages.",
               "Models downloaded on first use are not part of this installer.", ""]
    for package in packages:
        license_text = " ".join(package["license"].split())
        notices.append(f"- {package['name']} {package['version']}: {license_text}")
    if (payload / "third-party" / "Microsoft-Visual-Cpp-License.html").is_file():
        notices.extend(["", "## Microsoft Visual C++ runtime", "",
                        "Signed Microsoft Visual C++ x64 runtime DLLs are included. See third-party/Microsoft-Visual-Cpp-License.html and Microsoft-Visual-Cpp-Provenance.json."])
    (payload / "THIRD-PARTY-NOTICES.md").write_text("\n".join(notices) + "\n", encoding="utf-8")
    write_manifest(payload, args.version, packages)
    files = [p for p in payload.rglob("*") if p.is_file()]
    print(f"Staged {len(files)} files ({sum(p.stat().st_size for p in files) / 1024**2:.1f} MiB): {payload}", flush=True)
    return payload


def copy_documents(payload):
    for name in ("README.md", "INSTALL.md", "requirements-windows-lock.txt"):
        if (ROOT / name).is_file():
            shutil.copy2(ROOT / name, payload / name)


def copy_redist(source, payload):
    source = source.resolve()
    for name in ("msvcp140.dll", "msvcp140_1.dll"):
        if not (source / name).is_file():
            raise RuntimeError(f"Missing official Microsoft VC++ runtime file: {source / name}")
    for path in source.glob("*.dll"):
        shutil.copy2(path, payload / "runtime" / path.name)
    notices = payload / "third-party"
    notices.mkdir(exist_ok=True)
    for name in ("Microsoft-Visual-Cpp-License.html", "Microsoft-Visual-Cpp-Provenance.json"):
        if not (source / name).is_file():
            raise RuntimeError(f"Missing Microsoft redistributable license/provenance: {source / name}")
        shutil.copy2(source / name, notices / name)
    notice_path = payload / "THIRD-PARTY-NOTICES.md"
    if notice_path.exists():
        notice_text = notice_path.read_text(encoding="utf-8")
        if "## Microsoft Visual C++ runtime" not in notice_text:
            notice_text += ("\n## Microsoft Visual C++ runtime\n\n"
                            "The app includes signed Microsoft Visual C++ x64 runtime DLLs. "
                            "See third-party/Microsoft-Visual-Cpp-License.html and "
                            "third-party/Microsoft-Visual-Cpp-Provenance.json for the official license and source verification.\n")
            notice_path.write_text(notice_text, encoding="utf-8")


def write_manifest(payload, version, packages=None):
    if packages is None:
        previous = payload / "bundle-manifest.json"
        packages = json.loads(previous.read_text(encoding="utf-8")).get("packages", []) if previous.exists() else []
    files = [{"path": path.relative_to(payload).as_posix(), "size": path.stat().st_size,
              "sha256": digest(path)} for path in sorted(payload.rglob("*")) if path.is_file()]
    files = [item for item in files if item["path"] != "bundle-manifest.json"]
    manifest = {"product": PRODUCT, "version": version, "architecture": "x64",
                "minimum_windows_build": 22000, "python": "3.12", "packages": packages, "files": files}
    (payload / "bundle-manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def validate_stage(payload):
    for relative in ("app/launcher.py", "app/assets/dova-translator.ico", "runtime/pythonw.exe",
                     "runtime/python.exe", "runtime/python312.dll", "runtime/Lib/site-packages/faster_whisper/__init__.py",
                     "runtime/msvcp140.dll", "runtime/msvcp140_1.dll",
                     "third-party/Microsoft-Visual-Cpp-License.html", "third-party/Microsoft-Visual-Cpp-Provenance.json"):
        if not (payload / relative).is_file():
            raise RuntimeError(f"Incomplete payload: {relative}")
    for path in payload.rglob("*"):
        if getattr(path.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise RuntimeError(f"Reparse point in payload: {path}")


def add_ui(db):
    msilib.add_data(db, "TextStyle", [
        ("DovaFont", "Segoe UI", 9, None, 0),
        ("DovaTitle", "Segoe UI", 18, 0x463121, 1),
        ("DovaHeading", "Segoe UI", 11, None, 1),
    ])

    def dialog(name, heading, body, *, button="Cerrar", event="Return"):
        dlg = msilib.Dialog(db, name, 50, 50, 370, 230, 3,
                            "Dova Translator", "Primary", "Primary", "Cancel")
        dlg.text("Heading", 22, 18, 326, 35, 3, "{\\DovaTitle}" + heading)
        dlg.line("Separator", 20, 61, 330, 1)
        dlg.text("Body", 22, 78, 325, 96, 3, body)
        dlg.line("Footer", 20, 186, 330, 1)
        primary = dlg.pushbutton("Primary", 253, 199, 95, 20, 3, button, "Cancel")
        primary.event("EndDialog", event)
        cancel = dlg.pushbutton("Cancel", 150, 199, 95, 20, 3, "Cancelar", "Primary")
        cancel.event("EndDialog", "Exit")
        return dlg

    dialog("WelcomeDlg", "Dova Translator", "Dicta con tu voz y escribe en otro idioma.\n\n"
           "Se instalara para tu usuario en:\n[APPDIR]\n\nPython y las dependencias estan incluidos. No necesitas instalar herramientas adicionales.",
           button="Instalar")
    dialog("ExitDialog", "Instalacion completada", "Dova Translator ya esta instalado.\n\n"
           "Abre la aplicacion desde el escritorio o el menu Inicio.\n\nLos modelos locales se descargan la primera vez que se utilizan.", button="Finalizar")
    dialog("FatalError", "No se pudo completar", "La instalacion no se completo. No cambies las protecciones de Windows.\n\n"
           "Consulta el registro de Windows Installer o contacta con quien te proporciono el instalador.", event="Exit")
    dialog("UserExit", "Instalacion cancelada", "La instalacion se ha cancelado.", event="Exit")

    maintenance = msilib.Dialog(db, "MaintenanceDlg", 50, 50, 370, 230, 3,
                               "Dova Translator", "Repair", "Repair", "Cancel")
    maintenance.text("Heading", 22, 18, 326, 35, 3, "{\\DovaTitle}Dova Translator")
    maintenance.line("Separator", 20, 61, 330, 1)
    maintenance.text("Body", 22, 78, 325, 90, 3,
                     "Dova Translator ya esta instalado.\n\nPuedes reparar sus archivos o quitar la aplicacion. Tus ajustes personales se conservaran.")
    repair = maintenance.pushbutton("Repair", 150, 198, 60, 20, 3, "Reparar", "Remove")
    repair.event("[REINSTALL]", "ALL", ordering=1)
    repair.event("[REINSTALLMODE]", "amus", ordering=2)
    repair.event("EndDialog", "Return", ordering=3)
    remove = maintenance.pushbutton("Remove", 219, 198, 60, 20, 3, "Quitar", "Cancel")
    remove.event("[REMOVE]", "ALL", ordering=1)
    remove.event("EndDialog", "Return", ordering=2)
    cancel = maintenance.pushbutton("Cancel", 288, 198, 60, 20, 3, "Cancelar", "Repair")
    cancel.event("EndDialog", "Exit")

    progress = msilib.Dialog(db, "ProgressDlg", 50, 50, 370, 230, 1,
                            "Dova Translator", "Cancel", "Cancel", "Cancel")
    progress.text("Heading", 22, 18, 326, 35, 3, "{\\DovaTitle}Dova Translator")
    progress.text("Body", 22, 78, 325, 30, 3, "Espera mientras Windows actualiza la aplicacion.")
    action = progress.text("Action", 22, 118, 325, 22, 3, "Preparando archivos...")
    action.mapping("ActionText", "Text")
    bar = progress.control("Progress", "ProgressBar", 22, 149, 325, 14, 65537, None, None, None, None)
    bar.mapping("SetProgress", "Progress")
    cancel = progress.pushbutton("Cancel", 253, 199, 95, 20, 3, "Cancelar", None)
    cancel.event("EndDialog", "Exit")

    msilib.add_data(db, "InstallUISequence", [
        ("WelcomeDlg", "NOT Installed", 1100),
        ("MaintenanceDlg", "Installed AND NOT RESUME AND NOT Preselected", 1100),
        ("ProgressDlg", None, 1250),
    ])


def create_msi(payload: Path, output: Path, version: str):
    validate_stage(payload)
    product_code = guid("product:" + version)
    db = msilib.init_database(str(output), schema, PRODUCT, product_code, version, PUBLISHER)
    summary = db.GetSummaryInformation(20)
    summary.SetProperty(msilib.PID_PAGECOUNT, 500)
    summary.SetProperty(msilib.PID_WORDCOUNT, 10)  # compressed, non-elevated package
    summary.SetProperty(msilib.PID_COMMENTS, "Dova Translator for Windows 11 x64; bundled Python runtime")
    summary.Persist()
    for table in sequence.tables:
        rows = list(getattr(sequence, table))
        rows = [(action, condition, 450 if action == "LaunchConditions" else
                 1501 if action == "RemoveExistingProducts" else number)
                for action, condition, number in rows]
        msilib.add_data(db, table, rows)
    msilib.add_tables(db, text)
    msilib.add_data(db, "Property", [
        ("ALLUSERS", "2"), ("MSIINSTALLPERUSER", "1"), ("INSTALLLEVEL", "1"),
        ("UpgradeCode", UPGRADE_CODE), ("DefaultUIFont", "DovaFont"),
        ("ARPPRODUCTICON", "DovaIcon"), ("ARPNOMODIFY", "1"),
        ("ARPCOMMENTS", "Voice dictation and translation. Python runtime included."),
        ("SecureCustomProperties", "DOVA_OLDPRODUCTS;DOVA_NEWERPRODUCTS"),
        ("DiskPrompt", "Dova Translator installation"),
    ])
    msilib.add_data(db, "RegLocator", [
        ("WindowsBuildRegistry", 2, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "CurrentBuildNumber", 18),
    ])
    msilib.add_data(db, "AppSearch", [("DOVA_WINDOWS_BUILD", "WindowsBuildRegistry")])
    msilib.add_data(db, "LaunchCondition", [
        ("Installed OR (VersionNT64 AND DOVA_WINDOWS_BUILD >= 22000)", "Dova Translator requiere Windows 11 de 64 bits."),
        ("NOT DOVA_NEWERPRODUCTS", "Ya hay una version mas reciente de Dova Translator instalada."),
    ])
    # Upgrade old product versions transactionally; do not remove an equal/newer release.
    msilib.add_data(db, "Upgrade", [
        (UPGRADE_CODE, None, version, None, 1, None, "DOVA_OLDPRODUCTS"),
        (UPGRADE_CODE, version, None, None, 258, None, "DOVA_NEWERPRODUCTS"),
    ])
    msilib.add_data(db, "Directory", [
        ("TARGETDIR", None, "SourceDir"),
        ("LocalAppDataFolder", "TARGETDIR", "."),
        ("UserProgramsDir", "LocalAppDataFolder", "Programs"),
        ("APPDIR", "UserProgramsDir", "DOVATR~1|DovaTranslator"),
        ("ProgramMenuFolder", "TARGETDIR", "."),
        ("DovaMenuDir", "ProgramMenuFolder", "DOVATR~1|Dova Translator"),
        ("DesktopFolder", "TARGETDIR", "."),
    ])
    feature = msilib.Feature(db, "Complete", PRODUCT, "Application and included runtime", 1, directory="APPDIR")
    feature.set_current()
    directories = {".": "APPDIR"}
    for directory in sorted((p for p in payload.rglob("*") if p.is_dir()), key=lambda p: (len(p.parts), str(p))):
        relative = directory.relative_to(payload)
        name = relative.as_posix()
        parent = relative.parent.as_posix()
        directory_id = ident("dir_", name)
        short = "D" + hashlib.sha256(name.encode()).hexdigest()[:7].upper()
        msilib.add_data(db, "Directory", [(directory_id, directories[parent], short + "|" + directory.name)])
        directories[name] = directory_id

    cab = msilib.CAB("DovaPayload.cab")
    paths = sorted(p for p in payload.rglob("*") if p.is_file())
    if len(paths) >= 32767:
        raise RuntimeError("Payload exceeds MSI file sequence capacity")
    file_ids = {}
    registry_key = r"Software\Dova\DovaTranslator\Components"
    component_rows, feature_rows, registry_rows, file_rows = [], [], [], []
    for index, path in enumerate(paths, 1):
        relative = path.relative_to(payload).as_posix()
        directory_id = directories[path.relative_to(payload).parent.as_posix()]
        component = ident("cmp_", relative)
        registry_id = ident("reg_", relative)
        file_id = ident("file_", relative)
        file_ids[relative] = file_id
        component_rows.append((component, guid("component:" + relative), directory_id, 260, None, registry_id))
        feature_rows.append((feature.id, component))
        registry_rows.append((registry_id, 1, registry_key, component, "#1", component))
        sequence_number, _ = cab.append(str(path), path.name, file_id)
        short_name = "F" + hashlib.sha256(relative.encode()).hexdigest()[:7].upper()
        if path.suffix:
            short_name += "." + "".join(c for c in path.suffix[1:] if c.isalnum())[:3].upper()
        file_rows.append((file_id, component, short_name + "|" + path.name,
                          path.stat().st_size, None, None, 512, sequence_number))
        if index % 1000 == 0:
            print(f"MSI tables: {index}/{len(paths)} files", flush=True)
    for table, rows in (("Component", component_rows), ("FeatureComponents", feature_rows),
                        ("Registry", registry_rows), ("File", file_rows)):
        msilib.add_data(db, table, rows)

    launcher_component = "DovaShortcuts"
    msilib.add_data(db, "Component", [(launcher_component, guid("component:shortcuts"), "APPDIR", 260, None, "DovaInstallPath")])
    msilib.add_data(db, "FeatureComponents", [(feature.id, launcher_component)])
    msilib.add_data(db, "Registry", [("DovaInstallPath", 1, r"Software\Dova\DovaTranslator", "InstallPath", "[APPDIR]", launcher_component)])
    icon = payload / "app" / "assets" / "dova-translator.ico"
    msilib.add_data(db, "Icon", [("DovaIcon", msilib.Binary(str(icon)))])
    target = "[#" + file_ids["runtime/pythonw.exe"] + "]"
    arguments = '-I -B "[APPDIR]app\\launcher.py"'
    msilib.add_data(db, "Shortcut", [
        ("DovaStartMenu", "DovaMenuDir", "DOVATR~1|Dova Translator", launcher_component, target, arguments,
         "Dictado por voz y traduccion", None, "DovaIcon", 0, 1, "APPDIR"),
        ("DovaDesktop", "DesktopFolder", "DOVATR~1|Dova Translator", launcher_component, target, arguments,
         "Dictado por voz y traduccion", None, "DovaIcon", 0, 1, "APPDIR"),
    ])
    msilib.add_data(db, "RemoveFile", [("RemoveDovaMenu", launcher_component, None, "DovaMenuDir", 2)])
    add_ui(db)
    db.Commit()
    print(f"Compressing and embedding {len(paths)} files...", flush=True)
    cab.commit(db)
    db.Commit()
    # OLE storage is finalized on handle release; hash only the closed package.
    del summary
    del db
    gc.collect()
    report = {"product": PRODUCT, "version": version, "product_code": product_code,
              "upgrade_code": UPGRADE_CODE, "file_count": len(paths), "payload": str(payload),
              "msi": str(output), "bytes": output.stat().st_size, "sha256": digest(output),
              "built_utc": datetime.now(timezone.utc).isoformat(),
              "signature": "Unsigned. Apply an organization code-signing certificate for public distribution."}
    report_path = output.with_suffix(".build.json")
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    output.with_suffix(".msi.sha256").write_text(f"{report['sha256']}  {output.name}\n", encoding="ascii")
    print(json.dumps(report, indent=2), flush=True)


def main():
    if os.name != "nt" or sys.version_info[:2] != (3, 12) or struct.calcsize("P") != 8:
        raise SystemExit("Build with Windows 64-bit Python 3.12 (msilib is required).")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, default=Path(os.environ["LOCALAPPDATA"]) / "Python/pythoncore-3.12-64")
    parser.add_argument("--site-packages", type=Path, default=Path(os.environ["LOCALAPPDATA"]) / "TranslatorES/venv-py312/Lib/site-packages")
    parser.add_argument("--version", default="1.0.0")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--stage", type=Path, help="Reuse an existing payload rather than copying it again")
    parser.add_argument("--refresh-app", action="store_true", help="Refresh app/docs and manifest in a reused payload")
    parser.add_argument("--redist-dir", type=Path, help="Folder of official Microsoft VC++ x64 redistributable DLLs")
    parser.add_argument("--stage-only", action="store_true")
    args = parser.parse_args()
    output = (args.output or ROOT / "dist" / f"DovaTranslator-{args.version}-win11-x64.msi").resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not args.stage_only:
        raise SystemExit(f"Output already exists; choose a new path or explicitly archive it: {output}")
    if args.stage:
        payload = args.stage.resolve()
        if args.refresh_app:
            copy_tree(ROOT / "app", payload / "app")
            copy_documents(payload)
        if args.redist_dir:
            copy_redist(args.redist_dir, payload)
        if args.refresh_app or args.redist_dir:
            write_manifest(payload, args.version)
    else:
        build_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        work = ROOT / "build" / build_id
        work.mkdir(parents=True)
        payload = build_stage(args, work)
    if not args.stage_only:
        create_msi(payload, output, args.version)


if __name__ == "__main__":
    main()
