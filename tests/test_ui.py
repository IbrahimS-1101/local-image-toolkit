import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox
from toolkit.ui import MainWindow, STYLE
from toolkit.storage import Store
from toolkit.engine import Settings


@pytest.fixture
def window(tmp_path):
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLE)
    w = MainWindow(Store(tmp_path))
    yield w
    w.timer.stop()
    w.close()
    app.processEvents()


def test_resize_and_logo_controls(window):
    assert not window.width.isEnabled()
    window.resize_mode.setCurrentText("Width")
    assert window.width.isEnabled() and not window.height.isEnabled()
    window.resize_mode.setCurrentText("Exact dimensions")
    assert window.width.isEnabled() and window.height.isEnabled()
    assert not window.enlarge.isEnabled()
    assert "distort" in window.resize_note.text()
    window.format.setCurrentText("PNG")
    assert not window.quality.isEnabled()
    window.logo_enabled.setChecked(True)
    assert window.position.isEnabled()


def test_preset_actions(window, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("Website", True))
    window.width.setValue(800)
    window.save_preset()
    assert window.store.preset("Website").width == 800
    window.width.setValue(320)
    window.load_preset("Website")
    assert window.width.value() == 800
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("Renamed", True))
    window.rename_preset()
    assert "Renamed" in Store(window.store.root).presets
    assert "Website" not in window.store.presets
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    window.delete_preset()
    assert not Store(window.store.root).presets


def test_stale_preview_discarded(window):
    window.preview_token = 9
    window.preview_info.setText("Latest result")
    window.preview_ready(8, None, None, None, "Stale error")
    assert window.preview_info.text() == "Latest result"


def test_settings_roundtrip(window):
    settings = Settings(output_format="WEBP", resize_mode="Percentage", percent=50, background="#aabbcc", margin=5)
    window.apply_settings(settings)
    assert window.settings() == settings
