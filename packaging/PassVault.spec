# PyInstaller spec: builds PassVault.exe (GUI) and passvault_host.exe (Chrome
# native messaging host) into one folder so they share the same runtime files.
from pathlib import Path

ROOT = Path(SPECPATH).parent
ICON = str(ROOT / "assets" / "passvault.ico")

app_a = Analysis(
    [str(ROOT / "packaging" / "entry_app.py")],
    pathex=[str(ROOT)],
    datas=[(ICON, "assets")],
    excludes=["PIL"],
)
host_a = Analysis(
    [str(ROOT / "packaging" / "entry_host.py")],
    pathex=[str(ROOT)],
    excludes=["PIL", "tkinter"],
)

app_exe = EXE(
    PYZ(app_a.pure), app_a.scripts, [],
    exclude_binaries=True, name="PassVault", icon=ICON, console=False,
)
host_exe = EXE(
    PYZ(host_a.pure), host_a.scripts, [],
    exclude_binaries=True, name="passvault_host", icon=ICON, console=True,
)

COLLECT(
    app_exe, app_a.binaries, app_a.datas,
    host_exe, host_a.binaries, host_a.datas,
    name="PassVault",
)
