"""Build-time collection of licenses and pinned corresponding source archives.

The desktop application does not import this module or use the network.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
from pathlib import Path
import shutil
import sys
import tarfile
import urllib.request

QT_VERSION = "6.11.2"
SOURCES = {
    "qtbase-everywhere-src-6.11.2.tar.xz": (
        "https://download.qt.io/archive/qt/6.11/6.11.2/submodules/qtbase-everywhere-src-6.11.2.tar.xz",
        "5b2e00eccaf5a4d8c14134ffa0ea8dfd0a35ae1ffc7f8d87fa4305a1ed23cf22"),
    "qtsvg-everywhere-src-6.11.2.tar.xz": (
        "https://download.qt.io/archive/qt/6.11/6.11.2/submodules/qtsvg-everywhere-src-6.11.2.tar.xz",
        "d594337feca84c26fb67fe87b85e6a5c12fda404b611d905f9d138210c311876"),
    "qtimageformats-everywhere-src-6.11.2.tar.xz": (
        "https://download.qt.io/archive/qt/6.11/6.11.2/submodules/qtimageformats-everywhere-src-6.11.2.tar.xz",
        "cecd8900f34b6550076309bc94f62f828008b633a4239e0a08c86788f41001f8"),
    "pyside-setup-everywhere-src-6.11.2.tar.xz": (
        "https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.2-src/pyside-setup-everywhere-src-6.11.2.tar.xz",
        "cba47efbaad1bedd529725cbc14e21f156c7a19366f07b3edfbb076ffd7afdf8"),
}


def digest(path: Path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def collect_licenses(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    for name in ("PySide6-Essentials", "shiboken6", "Pillow", "PyInstaller"):
        distribution = metadata.distribution(name)
        for file in distribution.files or []:
            parts = Path(str(file)).parts
            if "licenses" not in parts:
                continue
            src = Path(distribution.locate_file(file))
            if src.is_file():
                # Keep each distribution's notices separate, including bundled-codec notices.
                relative = Path(*parts[parts.index("licenses") + 1:])
                destination = directory / f"{distribution.metadata['Name']}-{distribution.version}" / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, destination)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.is_file():
        raise RuntimeError("Python's LICENSE.txt was not found. Use the official Windows Python distribution.")
    shutil.copy2(python_license, directory / "Python-LICENSE.txt")


def prepare(directory: Path, offline=False):
    directory = directory.resolve()
    if metadata.version("PySide6-Essentials") != QT_VERSION or metadata.version("shiboken6") != QT_VERSION:
        raise RuntimeError("Qt dependencies differ from the pinned source archives. Install requirements-dev.txt first.")
    archives = directory / "dependency-sources"
    licenses = directory / "licenses"
    archives.mkdir(parents=True, exist_ok=True)
    for name, (url, expected) in SOURCES.items():
        archive = archives / name
        if not archive.is_file():
            if offline:
                raise RuntimeError(f"Missing cached source archive: {name}. Prepare materials online first.")
            temporary = archive.with_suffix(".download")
            try:
                print(f"Downloading {name}", flush=True)
                with urllib.request.urlopen(url, timeout=120) as response, temporary.open("wb") as out:
                    shutil.copyfileobj(response, out)
                if digest(temporary) != expected:
                    raise RuntimeError(f"Source checksum mismatch: {name}")
                temporary.replace(archive)
            finally:
                temporary.unlink(missing_ok=True)
        if digest(archive) != expected:
            raise RuntimeError(f"Cached source checksum mismatch: {name}")
        with tarfile.open(archive) as source:
            for item in source.getmembers():
                if not item.isfile() or item.size > 2_000_000:
                    continue
                path = Path(item.name)
                if not any(word in path.name.lower() for word in ("license", "copying", "copyright", "attribution")):
                    continue
                if path.suffix.lower() not in ("", ".txt", ".md", ".json", ".spdx"):
                    continue
                destination = (licenses / "upstream" / path).resolve()
                if not destination.is_relative_to((licenses / "upstream").resolve()):
                    raise RuntimeError("Unsafe path in upstream archive")
                destination.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(item) as inp, destination.open("wb") as out:
                    shutil.copyfileobj(inp, out)
    collect_licenses(licenses)
    (archives / "README.txt").write_text(
        "Unmodified corresponding source for bundled Qt/PySide libraries.\n"
        "Keep these archives with the portable application when redistributing.\n\n" +
        "\n".join(f"{name}\n{url}\nSHA256: {sha}" for name, (url, sha) in SOURCES.items()) + "\n",
        encoding="utf-8")
    return directory


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path(__file__).resolve().parent / ".release-materials")
    parser.add_argument("--offline", action="store_true")
    arguments = parser.parse_args()
    print(prepare(arguments.directory, arguments.offline))
