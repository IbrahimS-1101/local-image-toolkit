"""Versioned, atomic preferences. No image contents are persisted."""
import json
import os
import tempfile
from pathlib import Path
from .engine import Settings, ImageError


class Store:
    def __init__(self, root=None):
        self.root = Path(root) if root else Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share")) / "LocalImageToolkit"
        self.path = self.root / "preferences.json"
        self.presets = {}
        self.output_folder = ""
        self.warning = ""
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if data.get("version") != 1 or not isinstance(data.get("presets"), dict):
                    raise ValueError("Unsupported preferences version or structure")
                self.presets = data["presets"]
                self.output_folder = str(data.get("output_folder", ""))
            except (OSError, ValueError, AttributeError) as exc:
                self.warning = f"Preferences could not be loaded: {exc}. The original file has been kept."

    def save(self):
        if self.warning:
            raise ImageError(self.warning + " Rename the preferences file before saving new preferences.")
        self.root.mkdir(parents=True, exist_ok=True)
        descriptor, filename = tempfile.mkstemp(dir=self.root, suffix=".tmp")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump({"version": 1, "output_folder": self.output_folder, "presets": self.presets}, stream, indent=2)
            os.replace(filename, self.path)
        finally:
            Path(filename).unlink(missing_ok=True)

    def preset(self, name):
        return Settings.from_dict(self.presets[name])
