from __future__ import annotations

from pathlib import Path
import threading

from PIL import Image
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSize, QUrl
from PySide6.QtGui import QImage, QPixmap, QIcon, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QHBoxLayout, QVBoxLayout,
    QFormLayout, QGroupBox, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox,
    QSlider, QLineEdit, QFileDialog, QColorDialog, QMessageBox, QInputDialog,
    QListWidget, QListWidgetItem, QAbstractItemView, QSplitter, QScrollArea, QProgressBar,
)

from .engine import Settings, Result, ImageError, inspect, load, transform, run_batch
from .storage import Store
from . import APP_NAME, COPYRIGHT_HOLDER, __version__

STYLE = """
QWidget { font-family: 'Segoe UI'; font-size: 10pt; color: #24344a; }
QMainWindow, QWidget#workspace { background: #f4f6fa; }
QGroupBox { background: white; border: 1px solid #dce3ed; border-radius: 8px;
    margin-top: 15px; padding: 14px 10px 10px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
QPushButton { background: white; border: 1px solid #cdd7e4; border-radius: 5px; padding: 7px 11px; }
QPushButton:hover { background: #eaf0fc; border-color: #92afd9; }
QPushButton:disabled { color: #98a3b3; background: #edf0f5; }
QPushButton#primary { background: #245bd7; color: white; border: 0; font-weight: 600; padding: 10px 20px; }
QPushButton#primary:disabled { background: #aabce6; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { background: white; border: 1px solid #ccd6e3;
    border-radius: 4px; padding: 5px; min-height: 18px; }
QListWidget { background: white; border: 1px solid #dce3ed; border-radius: 7px; padding: 5px; }
QListWidget::item { padding: 8px; border-bottom: 1px solid #edf0f5; }
QListWidget::item:selected { background: #e6edff; color: #163d85; border-radius: 4px; }
QLabel#muted { color: #67778d; font-size: 9pt; }
QLabel#preview { background: #e9edf3; border: 1px solid #dce3ed; border-radius: 8px; }
QProgressBar { border: 0; background: #dfe6f2; border-radius: 4px; height: 8px; text-align: center; }
QProgressBar::chunk { background: #245bd7; border-radius: 4px; }
QScrollArea { border: 0; background: transparent; }
QToolTip { background: white; color: #24344a; border: 1px solid #ccd6e3; padding: 5px; }
"""


def qt_image(image):
    image = image.convert("RGBA")
    return QImage(image.tobytes(), image.width, image.height, image.width * 4, QImage.Format.Format_RGBA8888).copy()


class PreviewLabel(QLabel):
    def __init__(self, text):
        super().__init__(text)
        self.setObjectName("preview")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(180, 170)
        self.picture = None

    def show_image(self, image):
        self.picture = QPixmap.fromImage(image)
        self.refresh()

    def refresh(self):
        if self.picture:
            self.setPixmap(self.picture.scaled(self.size() - QSize(20, 20), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def clear_image(self, text):
        self.picture = None
        self.clear()
        self.setText(text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh()


class ImportWorker(QThread):
    item_ready = Signal(object, object, object, str)

    def __init__(self, paths):
        super().__init__()
        self.paths = paths

    def run(self):
        for path in self.paths:
            try:
                info = inspect(path)
                image, _ = load(path)
                image.thumbnail((64, 64), Image.Resampling.LANCZOS)
                self.item_ready.emit(path, info, qt_image(image), "")
            except Exception as exc:
                self.item_ready.emit(path, None, None, str(exc))


class PreviewWorker(QThread):
    ready = Signal(int, object, object, object, str)

    def __init__(self, token, path, settings):
        super().__init__()
        self.token, self.path, self.settings = token, path, settings

    def run(self):
        try:
            original, _ = load(self.path)
            original.thumbnail((1000, 1000), Image.Resampling.LANCZOS)
            processed, fmt, size = transform(self.path, self.settings, preview_bound=1000)
            # Round-trip the small preview through the encoder to show compression too.
            from io import BytesIO
            stream = BytesIO()
            opts = {"quality": self.settings.quality} if fmt in ("JPEG", "WEBP") else {}
            processed.save(stream, format=fmt, **opts)
            stream.seek(0)
            with Image.open(stream) as encoded:
                result = qt_image(encoded)
            self.ready.emit(self.token, qt_image(original), result, size, "")
        except Exception as exc:
            self.ready.emit(self.token, None, None, None, str(exc))


class BatchWorker(QThread):
    result_ready = Signal(int, object)
    completed = Signal(object)

    def __init__(self, paths, folder, settings):
        super().__init__()
        self.paths, self.folder, self.settings = paths, folder, settings
        self.cancel = threading.Event()
        self.results = []

    def run(self):
        self.results = run_batch(self.paths, self.folder, self.settings, self.cancel,
                                 lambda i, result: self.result_ready.emit(i, result))
        self.completed.emit(self.results)


class MainWindow(QMainWindow):
    def __init__(self, store=None):
        super().__init__()
        self.store = store or Store()
        self.setWindowTitle("Local Image Toolkit")
        self.resize(1420, 900)
        self.setMinimumSize(1040, 700)
        self.setAcceptDrops(True)
        self.preview_token = 0
        self.preview_pending = None
        self.preview_worker = None
        self.import_worker = None
        self.batch_worker = None
        self.batch_items = []
        self.failed_paths = []
        self.controls = []
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.start_preview)
        self.build_ui()
        self.restore_presets()
        self.update_controls()
        QShortcut(QKeySequence("Ctrl+O"), self, self.pick_files)
        QShortcut(QKeySequence("Delete"), self.queue, self.remove_selected)
        if self.store.warning:
            self.status.setText(self.store.warning)

    def button(self, text, callback, parent_layout=None):
        button = QPushButton(text)
        button.clicked.connect(callback)
        if parent_layout:
            parent_layout.addWidget(button)
        return button

    def combo(self, values):
        control = QComboBox()
        control.addItems(values)
        self.controls.append(control)
        control.currentIndexChanged.connect(self.changed)
        return control

    def spin(self, value, low, high, suffix="", decimal=False):
        control = QDoubleSpinBox() if decimal else QSpinBox()
        control.setRange(low, high)
        control.setValue(value)
        control.setSuffix(suffix)
        self.controls.append(control)
        control.valueChanged.connect(self.changed)
        return control

    def check(self, text, checked=False):
        control = QCheckBox(text)
        control.setChecked(checked)
        self.controls.append(control)
        control.toggled.connect(self.changed)
        return control

    def group(self, title, layout):
        group = QGroupBox(title)
        form = QFormLayout(group)
        form.setSpacing(9)
        layout.addWidget(group)
        return form

    def build_ui(self):
        root = QWidget()
        root.setObjectName("workspace")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 16, 20, 16)
        header = QHBoxLayout()
        title = QLabel("Local Image Toolkit")
        title.setStyleSheet("font-size: 22pt; font-weight: 700;")
        header.addWidget(title)
        header.addStretch()
        self.button("About", self.about, header)
        layout.addLayout(header)
        tagline = QLabel("Resize, convert, and add your logo. All on your computer.")
        tagline.setObjectName("muted")
        layout.addWidget(tagline)
        layout.addSpacing(8)
        splitter = QSplitter()
        layout.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 8, 0)
        row = QHBoxLayout()
        self.add_button = self.button("+ Add images", self.pick_files, row)
        self.clear_button = self.button("Clear", self.clear_queue, row)
        left_layout.addLayout(row)
        self.queue = QListWidget()
        self.queue.setIconSize(QSize(48, 48))
        self.queue.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.queue.currentItemChanged.connect(self.changed)
        left_layout.addWidget(self.queue)
        self.remove_button = self.button("Remove selected", self.remove_selected, left_layout)
        hint = QLabel("Drop JPEG, PNG, or WebP files here.\nOriginal files are always kept.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        left_layout.addWidget(hint)
        splitter.addWidget(left)

        middle = QWidget()
        middle_layout = QVBoxLayout(middle)
        middle_layout.setContentsMargins(8, 0, 8, 0)
        self.preview_title = QLabel("Select an image to preview")
        self.preview_title.setStyleSheet("font-weight: 600; padding: 8px 0;")
        middle_layout.addWidget(self.preview_title)
        middle_layout.addWidget(QLabel("Original"))
        self.original = PreviewLabel("Your image will appear here")
        middle_layout.addWidget(self.original, 1)
        middle_layout.addWidget(QLabel("Processed preview"))
        self.processed = PreviewLabel("Choose settings to see the result")
        middle_layout.addWidget(self.processed, 1)
        self.preview_info = QLabel("Preview uses a smaller image; exports use the full output dimensions.")
        self.preview_info.setObjectName("muted")
        self.preview_info.setWordWrap(True)
        middle_layout.addWidget(self.preview_info)
        splitter.addWidget(middle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(325)
        settings_widget = QWidget()
        self.settings_widget = settings_widget
        settings_layout = QVBoxLayout(settings_widget)
        settings_layout.setContentsMargins(8, 0, 0, 0)
        preset = self.group("Saved presets", settings_layout)
        self.presets = QComboBox()
        self.presets.currentTextChanged.connect(self.load_preset)
        preset.addRow(self.presets)
        buttons = QHBoxLayout()
        self.button("Save as…", self.save_preset, buttons)
        self.button("Rename", self.rename_preset, buttons)
        self.button("Delete", self.delete_preset, buttons)
        preset.addRow(buttons)

        form = self.group("1   Output format", settings_layout)
        self.format = self.combo(["Original", "JPEG", "PNG", "WEBP"])
        form.addRow("Format", self.format)
        quality_row = QHBoxLayout()
        self.quality = QSlider(Qt.Orientation.Horizontal)
        self.quality.setRange(1, 100)
        self.quality.setValue(90)
        self.quality.valueChanged.connect(self.changed)
        self.quality_text = QLabel("90")
        quality_row.addWidget(self.quality)
        quality_row.addWidget(self.quality_text)
        form.addRow("Quality", quality_row)
        self.background = "#ffffff"
        self.color_button = self.button("White · #ffffff", self.choose_color)
        form.addRow("JPEG background", self.color_button)

        form = self.group("2   Resize", settings_layout)
        self.resize_mode = self.combo(["None", "Fit box", "Width", "Height", "Percentage", "Exact dimensions"])
        self.width = self.spin(1920, 1, 50000, " px")
        self.height = self.spin(1080, 1, 50000, " px")
        self.percent = self.spin(100, 0.1, 1000, " %", True)
        self.enlarge = self.check("Allow enlargement")
        form.addRow("Mode", self.resize_mode)
        form.addRow("Width", self.width)
        form.addRow("Height", self.height)
        form.addRow("Scale", self.percent)
        form.addRow(self.enlarge)
        self.resize_note = QLabel("Proportions are preserved.")
        self.resize_note.setWordWrap(True)
        self.resize_note.setObjectName("muted")
        form.addRow(self.resize_note)

        form = self.group("3   Logo watermark", settings_layout)
        self.logo_enabled = self.check("Add a logo")
        form.addRow(self.logo_enabled)
        self.logo_path = QLineEdit()
        self.logo_path.setReadOnly(True)
        self.logo_path.setPlaceholderText("Transparent PNG recommended")
        form.addRow(self.logo_path)
        self.logo_button = self.button("Choose logo…", self.choose_logo)
        form.addRow(self.logo_button)
        self.position = self.combo(["Bottom right", "Bottom left", "Top right", "Top left", "Center"])
        self.logo_width = self.spin(15, 1, 100, " %", True)
        self.opacity = self.spin(100, 0, 100, " %", True)
        self.margin = self.spin(3, 0, 45, " %", True)
        form.addRow("Position", self.position)
        form.addRow("Logo width", self.logo_width)
        form.addRow("Opacity", self.opacity)
        form.addRow("Margin", self.margin)
        note = QLabel("Width is relative to the output image. Margin uses its shorter side.")
        note.setWordWrap(True)
        note.setObjectName("muted")
        form.addRow(note)
        settings_layout.addStretch()
        scroll.setWidget(settings_widget)
        splitter.addWidget(scroll)
        splitter.setSizes([280, 670, 380])

        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("Save to"))
        self.folder = QLineEdit(self.store.output_folder)
        self.folder.setPlaceholderText("Choose an output folder")
        self.folder.textChanged.connect(self.update_controls)
        folder_row.addWidget(self.folder, 1)
        self.folder_button = self.button("Browse…", self.choose_folder, folder_row)
        self.open_button = self.button("Open folder", self.open_folder, folder_row)
        layout.addLayout(folder_row)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        footer = QHBoxLayout()
        self.status = QLabel("Ready. Add images to begin.")
        self.status.setWordWrap(True)
        footer.addWidget(self.status, 1)
        self.retry_button = self.button("Retry failed", self.retry_failed, footer)
        self.cancel_button = self.button("Cancel", self.cancel_batch, footer)
        self.process_button = self.button("Process batch", self.start_batch, footer)
        self.process_button.setObjectName("primary")
        layout.addLayout(footer)

    def settings(self):
        return Settings(output_format=self.format.currentText(), quality=self.quality.value(), background=self.background,
                        resize_mode=self.resize_mode.currentText(), width=self.width.value(), height=self.height.value(),
                        percent=self.percent.value(), enlarge=self.enlarge.isChecked(), logo_path=self.logo_path.text(),
                        logo_enabled=self.logo_enabled.isChecked(), position=self.position.currentText(),
                        logo_width=self.logo_width.value(), opacity=self.opacity.value(), margin=self.margin.value())

    def apply_settings(self, s):
        pairs = [(self.format, s.output_format), (self.resize_mode, s.resize_mode), (self.position, s.position)]
        for control, text in pairs:
            control.setCurrentText(text)
        for name in ("quality", "width", "height", "percent", "logo_width", "opacity", "margin"):
            getattr(self, name).setValue(getattr(s, name))
        self.enlarge.setChecked(s.enlarge)
        self.logo_path.setText(s.logo_path)
        self.logo_enabled.setChecked(s.logo_enabled)
        self.background = s.background
        self.color_button.setText(s.background)
        self.changed()

    def busy(self):
        return bool((self.import_worker and self.import_worker.isRunning()) or (self.batch_worker and self.batch_worker.isRunning()))

    def update_controls(self, *args):
        if not hasattr(self, "process_button"):
            return
        busy = self.busy()
        batch = bool(self.batch_worker and self.batch_worker.isRunning())
        for button in (self.add_button, self.clear_button, self.remove_button, self.folder_button, self.folder):
            button.setEnabled(not busy)
        self.settings_widget.setEnabled(not busy)
        self.process_button.setEnabled(not busy and self.queue.count() > 0 and Path(self.folder.text()).is_dir() and bool(self.folder.text()))
        self.retry_button.setEnabled(not busy and bool(self.failed_paths) and bool(self.folder.text()) and Path(self.folder.text()).is_dir())
        self.cancel_button.setEnabled(batch)
        self.open_button.setEnabled(bool(self.folder.text()) and Path(self.folder.text()).is_dir())
        mode = self.resize_mode.currentText()
        self.width.setEnabled(mode in ("Fit box", "Width", "Exact dimensions"))
        self.height.setEnabled(mode in ("Fit box", "Height", "Exact dimensions"))
        self.percent.setEnabled(mode == "Percentage")
        self.enlarge.setEnabled(mode not in ("None", "Exact dimensions"))
        self.resize_note.setText("Exact dimensions can distort the image." if mode == "Exact dimensions" else "Proportions are preserved. No cropping or padding.")
        self.quality.setEnabled(self.format.currentText() != "PNG")
        self.quality_text.setText(str(self.quality.value()))
        for control in (self.position, self.logo_width, self.opacity, self.margin):
            control.setEnabled(self.logo_enabled.isChecked())

    def changed(self, *args):
        if not hasattr(self, "process_button"):
            return
        self.update_controls()
        self.preview_token += 1
        self.timer.start()

    def start_preview(self):
        item = self.queue.currentItem()
        if item is None:
            self.preview_pending = None
            self.original.clear_image("Your image will appear here")
            self.processed.clear_image("Choose settings to see the result")
            self.preview_title.setText("Select an image to preview")
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        self.preview_title.setText(path.name)
        self.preview_pending = (self.preview_token, path, self.settings())
        self.processed.clear_image("Updating preview…")
        self.launch_pending_preview()

    def launch_pending_preview(self):
        if self.preview_worker and self.preview_worker.isRunning():
            return
        if not self.preview_pending or (self.batch_worker and self.batch_worker.isRunning()):
            return
        self.preview_worker = PreviewWorker(*self.preview_pending)
        self.preview_pending = None
        self.preview_worker.ready.connect(self.preview_ready)
        self.preview_worker.finished.connect(self.preview_finished)
        self.preview_worker.start()

    def preview_finished(self):
        if self.preview_worker:
            self.preview_worker.deleteLater()
            self.preview_worker = None
        self.launch_pending_preview()

    def preview_ready(self, token, original, processed, size, error):
        if token != self.preview_token:
            return
        if error:
            self.original.clear_image("Cannot preview this image")
            self.processed.clear_image("Preview unavailable")
            self.preview_info.setText(error)
            return
        self.original.show_image(original)
        self.processed.show_image(processed)
        self.preview_info.setText(f"Output: {size[0]:,} × {size[1]:,} px · Reduced preview; full resolution on export.")

    def pick_files(self):
        if self.busy():
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "Add images", "", "Images (*.jpg *.jpeg *.png *.webp);;All files (*)")
        self.add_paths([Path(path) for path in paths])

    def add_paths(self, paths):
        if self.busy():
            return
        existing = {self.queue.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.queue.count())}
        paths = list(dict.fromkeys(Path(path).resolve() for path in paths if Path(path).is_file()))
        paths = [path for path in paths if path not in existing]
        if not paths:
            return
        self.status.setText(f"Reading {len(paths)} image(s)…")
        self.import_worker = ImportWorker(paths)
        self.import_worker.item_ready.connect(self.import_item)
        self.import_worker.finished.connect(self.import_finished)
        self.import_worker.start()
        self.update_controls()

    def import_item(self, path, info, thumbnail, error):
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, path)
        item.setData(Qt.ItemDataRole.UserRole + 1, info)
        if thumbnail:
            item.setIcon(QIcon(QPixmap.fromImage(thumbnail)))
        if error:
            item.setText(f"{path.name}\nCannot read · select for details")
            item.setToolTip(error)
        else:
            item.setText(f"{path.name}\n{info.size[0]:,} × {info.size[1]:,} · {info.format}")
            item.setToolTip(str(path))
        self.queue.addItem(item)
        if self.queue.count() == 1:
            self.queue.setCurrentItem(item)

    def import_finished(self):
        self.import_worker.deleteLater()
        self.import_worker = None
        self.status.setText(f"{self.queue.count()} image(s) in queue. Ready to process.")
        self.update_controls()

    def clear_queue(self):
        if not self.busy():
            self.queue.clear()
            self.failed_paths = []
            self.changed()

    def remove_selected(self):
        if not self.busy():
            for item in self.queue.selectedItems():
                path = item.data(Qt.ItemDataRole.UserRole)
                self.failed_paths = [p for p in self.failed_paths if p != path]
                self.queue.takeItem(self.queue.row(item))
            self.changed()

    def choose_logo(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Choose logo — transparent PNG recommended", "", "Images (*.png *.webp *.jpg *.jpeg);;All files (*)")
        if filename:
            self.logo_path.setText(filename)
            self.logo_enabled.setChecked(True)
            self.changed()

    def choose_color(self):
        from PySide6.QtGui import QColor
        color = QColorDialog.getColor(QColor(self.background), self, "JPEG background")
        if color.isValid():
            self.background = color.name()
            self.color_button.setText(color.name())
            self.changed()

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose output folder", self.folder.text())
        if folder:
            self.folder.setText(folder)
            self.persist_folder()

    def persist_folder(self):
        self.store.output_folder = self.folder.text()
        try:
            self.store.save()
        except (OSError, ImageError) as exc:
            self.status.setText(f"Could not save preferences: {exc}")

    def open_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.folder.text()))

    def start_batch(self, paths=None):
        if self.busy():
            return
        if not self.folder.text() or not Path(self.folder.text()).is_dir():
            QMessageBox.warning(self, "Choose a folder", "Choose an existing output folder first.")
            return
        try:
            settings = self.settings()
            settings.validate()
        except (ImageError, ValueError) as exc:
            QMessageBox.warning(self, "Check settings", str(exc))
            return
        # QPushButton.clicked supplies a boolean, not a path list.
        if not isinstance(paths, list):
            paths = [self.queue.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.queue.count())]
        if not paths:
            return
        self.persist_folder()
        self.failed_paths = []
        self.batch_items = [next(self.queue.item(i) for i in range(self.queue.count()) if self.queue.item(i).data(Qt.ItemDataRole.UserRole) == path) for path in paths]
        for item in self.batch_items:
            item.setText(f"{item.data(Qt.ItemDataRole.UserRole).name}\nWaiting…")
        self.progress.setRange(0, len(paths))
        self.progress.setValue(0)
        self.status.setText(f"Processing {len(paths)} image(s)…")
        self.batch_worker = BatchWorker(paths, Path(self.folder.text()), settings)
        self.batch_worker.result_ready.connect(self.batch_result)
        self.batch_worker.completed.connect(self.batch_completed)
        self.batch_worker.finished.connect(self.batch_finished)
        self.batch_worker.start()
        self.update_controls()

    def batch_result(self, index, result):
        item = self.batch_items[index]
        if result.error:
            item.setText(f"{result.source.name}\nFailed · select for details")
            item.setToolTip(result.error)
            self.failed_paths.append(result.source)
        else:
            item.setText(f"{result.source.name}\nSaved · {result.size[0]} × {result.size[1]} · {result.bytes_written / 1024:,.1f} KB")
            item.setToolTip(str(result.output))
        self.progress.setValue(index + 1)
        self.status.setText(f"Processed {index + 1} of {len(self.batch_items)}")

    def batch_completed(self, results):
        success = sum(not result.error for result in results)
        failures = len(results) - success
        pending = len(self.batch_items) - len(results)
        for item in self.batch_items[len(results):]:
            item.setText(f"{item.data(Qt.ItemDataRole.UserRole).name}\nNot processed · cancelled")
        self.status.setText(f"{'Cancelled' if pending else 'Complete'} · {success} saved · {failures} failed · {pending} not processed")

    def batch_finished(self):
        self.batch_worker.deleteLater()
        self.batch_worker = None
        self.update_controls()
        self.launch_pending_preview()

    def cancel_batch(self):
        if self.batch_worker:
            self.batch_worker.cancel.set()
            self.cancel_button.setEnabled(False)
            self.status.setText("Cancelling after the current image…")

    def retry_failed(self):
        self.start_batch(list(self.failed_paths))

    def restore_presets(self, selected=""):
        self.presets.blockSignals(True)
        self.presets.clear()
        self.presets.addItems(["Custom settings", *sorted(self.store.presets)])
        if selected:
            self.presets.setCurrentText(selected)
        self.presets.blockSignals(False)

    def load_preset(self, name):
        if name in self.store.presets:
            try:
                self.apply_settings(self.store.preset(name))
            except (ImageError, TypeError) as exc:
                QMessageBox.warning(self, "Cannot load preset", str(exc))

    def save_preset(self):
        name, ok = QInputDialog.getText(self, "Save preset", "Preset name")
        name = name.strip()
        if not ok or not name:
            return
        if name == "Custom settings":
            QMessageBox.warning(self, "Choose another name", "This name is reserved.")
            return
        if name in self.store.presets and QMessageBox.question(self, "Replace preset?", f"Replace ‘{name}’?") != QMessageBox.StandardButton.Yes:
            return
        try:
            settings = self.settings()
            settings.validate()
            self.store.presets[name] = settings.to_dict()
            self.store.save()
            self.restore_presets(name)
        except (OSError, ImageError) as exc:
            QMessageBox.warning(self, "Cannot save preset", str(exc))

    def rename_preset(self):
        old = self.presets.currentText()
        if old not in self.store.presets:
            return
        name, ok = QInputDialog.getText(self, "Rename preset", "New name", text=old)
        name = name.strip()
        if not ok or not name or name == old:
            return
        if name in self.store.presets or name == "Custom settings":
            QMessageBox.warning(self, "Choose another name", "A preset already uses that name.")
            return
        try:
            self.store.presets[name] = self.store.presets.pop(old)
            self.store.save()
            self.restore_presets(name)
        except (OSError, ImageError) as exc:
            QMessageBox.warning(self, "Cannot rename preset", str(exc))

    def delete_preset(self):
        name = self.presets.currentText()
        if name in self.store.presets and QMessageBox.question(self, "Delete preset?", f"Delete ‘{name}’?") == QMessageBox.StandardButton.Yes:
            try:
                del self.store.presets[name]
                self.store.save()
                self.restore_presets()
            except (OSError, ImageError) as exc:
                QMessageBox.warning(self, "Cannot delete preset", str(exc))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.busy():
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.add_paths([Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()])
        event.acceptProposedAction()

    def closeEvent(self, event):
        active = [worker for worker in (self.import_worker, self.preview_worker, self.batch_worker) if worker and worker.isRunning()]
        if active:
            event.ignore()
            self.status.setText("Wait for current work to finish before closing. You can cancel a batch.")
            return
        self.persist_folder()
        event.accept()

    def about(self):
        QMessageBox.about(self, f"About {APP_NAME}",
                          f"{APP_NAME} {__version__}\n"
                          "Resize, convert, and watermark images — individually or in batches.\n\n"
                          f"Created by {COPYRIGHT_HOLDER}\n"
                          f"Copyright © 2026 {COPYRIGHT_HOLDER}\n"
                          "Application source released under the MIT license.\n\n"
                          "Works offline. No uploads, accounts, or telemetry.\n\n"
                          "Built with PySide6 / Qt (LGPLv3) and Pillow (MIT-CMU).\n"
                          "Dependencies retain their own licenses.\n"
                          "See LICENSE and THIRD_PARTY_NOTICES.md in the app folder.")
