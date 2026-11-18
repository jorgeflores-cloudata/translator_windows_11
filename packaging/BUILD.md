# Building the Windows 11 installer

The installer contains the app, a private official CPython 3.12 x64 runtime,
and prebuilt dependencies. It does not rely on a Python installation on the
destination PC and does not change PATH or Windows security settings.

From this repository, run with the official 64-bit Python 3.12 runtime:

```powershell
py -3.12 packaging\build_msi.py --redist-dir C:\BuildTools\Microsoft.VC143.CRT
```

The default dependency source is
`%LOCALAPPDATA%\TranslatorES\venv-py312\Lib\site-packages`.
Use `--runtime PATH` and `--site-packages PATH` to override the build inputs.
`--redist-dir` must point to the x64 CRT DLL directory extracted from an official
Microsoft Visual C++ Redistributable. The complete compatible DLL family is
copied beside the bundled Python runtime, including `msvcp140.dll` and
`msvcp140_1.dll`; this avoids relying on another application's system-wide CRT.
Build inputs must have been installed from the project's requirements using
binary wheels. The builder retains package metadata and license files and
produces `bundle-manifest.json` with file hashes in the payload.

Output:

- `dist/DovaTranslator-1.0.0-win11-x64.msi`
- Adjacent SHA-256 and build metadata files.
- An isolated, timestamped staging directory under `build/`.

The MSI uses Windows Installer's own interface and installs for the current
user at `%LOCALAPPDATA%\Programs\DovaTranslator`. It creates desktop and Start
menu shortcuts, and registers in Installed apps. Updates share a stable
UpgradeCode; increment `--version` for a release. The builder deliberately
does not overwrite an existing MSI. Use `--output` for a separate candidate.
An existing staging payload can be reused with `--stage PATH`. When preparing
a new candidate from that payload, `--refresh-app` refreshes the application,
installation guide, lock file and file manifest. `--redist-dir` can also be
used while reusing a stage. All staging trees are checked for reparse points.

The app shortcuts launch the bundled Python with `-I -B`: external Python
environment variables and user packages are ignored, and bytecode caches are
not written into the installation directory. Settings and downloaded models
remain in user data directories, outside the installation, across uninstall.

For a silent validation installation:

```powershell
msiexec.exe /i "dist\DovaTranslator-1.0.0-win11-x64.msi" /qn /norestart /L*v install.log
```

Run the installed bundle self-test with:

```powershell
& "$env:LOCALAPPDATA\Programs\DovaTranslator\runtime\python.exe" -I -B `
  "$env:LOCALAPPDATA\Programs\DovaTranslator\app\launcher.py" `
  --self-test --report "$env:TEMP\dova-self-test.json"
```

The generated package is not digitally signed. Public distribution should
use the publisher's trusted code-signing certificate; the builder does not
create or trust certificates and does not bypass Application Control.
