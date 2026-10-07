"""Offline acceptance harness usable from the frozen executable."""
import json
import time
from pathlib import Path
from PIL import Image, ImageDraw
from PySide6.QtCore import QTimer, QMimeData, QUrl, QPointF, Qt
from PySide6.QtGui import QDropEvent, QDragEnterEvent
from .engine import Settings
from .ui import MainWindow
from .storage import Store


def run(app, directory: Path):
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    inputs, exports = directory / "inputs", directory / "exports"
    inputs.mkdir(exist_ok=True)
    exports.mkdir(exist_ok=True)
    image = Image.new("RGB", (1200, 800), "#cbd9c4")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1200, 450), fill="#dce7ef")
    draw.polygon([(0, 530), (300, 260), (600, 530)], fill="#718b75")
    draw.polygon([(360, 580), (820, 190), (1200, 580)], fill="#4e6f65")
    draw.ellipse((900, 80, 1000, 180), fill="#fff4ce")
    logo = Image.new("RGBA", (240, 80), (255, 255, 255, 0))
    mark = ImageDraw.Draw(logo)
    mark.rounded_rectangle((0, 0, 239, 79), radius=12, fill="#245bd7")
    mark.text((24, 22), "LOCAL / STUDIO", fill="white", font_size=24)
    logo.save(inputs / "logo.png")
    for i in range(100):
        fmt = ["PNG", "JPEG", "WEBP"][i % 3]
        image.save(inputs / f"Landscape {i+1:03d}.{dict(PNG='png', JPEG='jpg', WEBP='webp')[fmt]}", fmt)
    bad = inputs / "broken.png"
    bad.write_bytes(b"not an image")
    window = MainWindow(Store(directory / "preferences"))
    window.folder.setText(str(exports))
    window.apply_settings(Settings(resize_mode="Width", width=800, output_format="JPEG",
                                   logo_enabled=True, logo_path=str(inputs / "logo.png")))
    window.store.presets["Web with logo"] = window.settings().to_dict()
    window.store.save()
    window.restore_presets("Web with logo")
    window.show()
    paths = sorted(p for p in inputs.iterdir() if p.name.startswith("Landscape")) + [bad]
    # Exercise the real window's drag/drop entry points, not only its add method.
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    enter = QDragEnterEvent(window.rect().center(), Qt.DropAction.CopyAction, mime,
                            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    window.dragEnterEvent(enter)
    assert enter.isAccepted()
    drop = QDropEvent(QPointF(window.rect().center()), Qt.DropAction.CopyAction, mime,
                      Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    window.dropEvent(drop)
    state = {"stage": "import", "ticks": 0, "heartbeat": 0, "success": False}
    started = time.monotonic()

    def tick():
        state["heartbeat"] += 1
        try:
            if time.monotonic() - started > 180:
                raise AssertionError("Acceptance run timed out")
            stage = state["stage"]
            if stage == "import" and not window.import_worker:
                assert window.queue.count() == 101
                state["stage"] = "preview"
            elif stage == "preview" and window.processed.picture and not window.preview_worker:
                window.grab().save(str(directory / "desktop-preview.png"))
                window.start_batch()
                assert not window.settings_widget.isEnabled()
                state["stage"] = "batch"
            elif stage == "batch" and not window.batch_worker:
                assert len(list(exports.glob("*.jpg"))) == 100
                assert window.failed_paths == [bad]
                assert window.progress.value() == 101
                image.save(bad, "PNG")
                window.retry_failed()
                state["stage"] = "retry"
            elif stage == "retry" and not window.batch_worker:
                assert len(list(exports.glob("*.jpg"))) == 101
                assert not window.failed_paths
                window.start_batch()
                window.cancel_batch()
                state["stage"] = "cancel"
            elif stage == "cancel" and not window.batch_worker:
                assert "Cancelled" in window.status.text()
                assert not list(exports.glob(".lit-*"))
                assert Store(directory / "preferences").preset("Web with logo").width == 800
                window.grab().save(str(directory / "desktop-complete.png"))
                state["success"] = True
                state["seconds"] = round(time.monotonic() - started, 2)
                finish()
        except Exception as exc:
            import traceback
            state["error"] = traceback.format_exc()
            finish()

    def finish():
        timer.stop()
        (directory / "acceptance.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
        # Do not destroy running QThreads on a failed assertion.
        for worker in (window.import_worker, window.preview_worker, window.batch_worker):
            if worker and worker.isRunning():
                if hasattr(worker, "cancel"):
                    worker.cancel.set()
                worker.wait()
        app.exit(0 if state["success"] else 1)

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(40)
    app.exec()
    return 0 if state["success"] else 1
