"""Reproducible one-folder packaging. Run inside the development environment."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
from toolkit import __version__
from prepare_release_materials import prepare

PUBLIC_FILES = (
    ".gitignore", "main.py", "build_release.py", "prepare_release_materials.py",
    "requirements.txt", "requirements-dev.txt", "pytest.ini", "LICENSE", "README.md",
    "THIRD_PARTY_NOTICES.md", "TESTING.md", "RELEASE_NOTES.md", "CONTRIBUTING.md",
    "docs/screenshots/desktop-preview.png", "docs/screenshots/about.png",
)
PUBLIC_TREES = {"toolkit": ".py", "tests": ".py"}


def copy_public_source(source: Path, destination: Path):
    """Explicit release allowlist: internal notes and future scratch files stay private."""
    destination.mkdir(parents=True, exist_ok=True)
    for name in PUBLIC_FILES:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, target)
    for folder, extension in PUBLIC_TREES.items():
        for path in (source / folder).rglob(f"*{extension}"):
            if "__pycache__" not in path.parts:
                target = destination / path.relative_to(source)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, default=Path("build"))
    parser.add_argument("--materials", type=Path)
    parser.add_argument("--offline", action="store_true", help="Use cached dependency sources without networking")
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    output = args.output.resolve()
    if (output / "Local Image Toolkit").exists():
        raise SystemExit("This output already contains an app. Choose a new output folder so an existing or running release is not modified.")
    materials = prepare(args.materials or source / ".release-materials", args.offline)
    output.mkdir(parents=True, exist_ok=True)
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--onedir",
               "--name", "Local Image Toolkit", "--distpath", str(output),
               "--workpath", str(work), "--specpath", str(work),
               "--paths", str(source), "--hidden-import", "PIL.ImageCms"]
    for module in ("QtNetwork", "QtQml", "QtQuick", "QtWebEngineCore", "QtDBus", "QtOpenGL", "QtSql", "QtTest"):
        command.extend(["--exclude-module", f"PySide6.{module}"])
    command.append(str(source / "main.py"))
    subprocess.run(command, check=True, cwd=source)
    release = output / "Local Image Toolkit"
    # Qt's Windows build imports the native, unversioned ICU API. PyInstaller
    # can accidentally resolve icuuc.dll from unrelated software on PATH.
    # That DLL exports versioned symbols and makes QtWidgets fail at startup.
    internal = release / "_internal"
    for pattern in ("icuuc.dll", "icudt*.dll", "icuin*.dll"):
        for dll in internal.glob(pattern):
            dll.unlink()
    # Use the compatible redistributable runtimes supplied with the pinned Qt
    # wheel, rather than an older copy discovered beside the Python interpreter.
    import PySide6
    qt = Path(PySide6.__file__).parent
    for name in ("vcruntime140.dll", "vcruntime140_1.dll"):
        shutil.copy2(qt / name, internal / name.upper().replace(".DLL", ".dll"))
    for name in ("LICENSE", "README.md", "THIRD_PARTY_NOTICES.md", "TESTING.md", "RELEASE_NOTES.md", "CONTRIBUTING.md"):
        shutil.copy2(source / name, release / name)
    shutil.copytree(materials / "licenses", release / "licenses", dirs_exist_ok=True)
    shutil.copytree(materials / "dependency-sources", release / "dependency-sources", dirs_exist_ok=True)
    copy_public_source(source, release / "source")
    shutil.copytree(source / "docs/screenshots", release / "screenshots", dirs_exist_ok=True)
    archive = output / f"Local-Image-Toolkit-{__version__}-Windows-x64.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
        for path in release.rglob("*"):
            if path.is_file():
                zipped.write(path, path.relative_to(output))
    print(archive)


if __name__ == "__main__":
    main()
