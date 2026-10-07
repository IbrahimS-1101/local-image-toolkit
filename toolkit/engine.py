"""UI-independent processing. No networking or filesystem preferences here."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from io import BytesIO
from pathlib import Path
import os
import tempfile
import threading
from typing import Callable

from PIL import Image, ImageCms, ImageColor, ImageOps, UnidentifiedImageError

MAX_PIXELS = 50_000_000
FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
SRGB = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
SRGB_BYTES = SRGB.tobytes()


class ImageError(ValueError):
    """An error safe to display to a user."""


@dataclass(frozen=True)
class Settings:
    output_format: str = "Original"
    quality: int = 90
    background: str = "#ffffff"
    resize_mode: str = "None"
    width: int = 1920
    height: int = 1080
    percent: float = 100
    enlarge: bool = False
    logo_path: str = ""
    logo_enabled: bool = False
    position: str = "Bottom right"
    logo_width: float = 15
    opacity: float = 100
    margin: float = 3

    def validate(self):
        if self.output_format not in ("Original", *FORMATS):
            raise ImageError("Choose JPEG, PNG, WebP, or Original.")
        if self.resize_mode not in ("None", "Fit box", "Width", "Height", "Percentage", "Exact dimensions"):
            raise ImageError("Unknown resize mode.")
        if self.position not in ("Top left", "Top right", "Bottom left", "Bottom right", "Center"):
            raise ImageError("Unknown logo position.")
        if not 1 <= self.quality <= 100 or not 1 <= self.width <= 50000 or not 1 <= self.height <= 50000:
            raise ImageError("Quality must be 1–100 and dimensions 1–50,000 pixels.")
        if not 0.1 <= self.percent <= 1000 or not 1 <= self.logo_width <= 100:
            raise ImageError("Invalid resize percentage or logo width.")
        if not 0 <= self.opacity <= 100 or not 0 <= self.margin <= 45:
            raise ImageError("Invalid logo opacity or margin.")
        try:
            ImageColor.getrgb(self.background)
        except (ValueError, TypeError) as exc:
            raise ImageError("Choose a valid JPEG background color.") from exc
        if self.logo_enabled and not Path(self.logo_path).is_file():
            raise ImageError("The logo file is missing. Choose a logo or disable it.")

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or set(data) - set(cls.__dataclass_fields__):
            raise ImageError("This preset contains unsupported settings.")
        try:
            result = cls(**data)
            result.validate()
            return result
        except (TypeError, ValueError) as exc:
            raise ImageError(f"Invalid preset: {exc}") from exc


@dataclass(frozen=True)
class Info:
    format: str
    size: tuple[int, int]


@dataclass(frozen=True)
class Result:
    source: Path
    output: Path | None = None
    size: tuple[int, int] | None = None
    bytes_written: int = 0
    error: str = ""


def inspect(path: Path) -> Info:
    try:
        with Image.open(path) as image:
            if image.format not in FORMATS:
                raise ImageError("Unsupported image. Use a still JPEG, PNG, or WebP.")
            if getattr(image, "n_frames", 1) != 1:
                raise ImageError("Animated images are not supported. Export a still frame first.")
            w, h = image.size
            if w * h > MAX_PIXELS:
                raise ImageError("Image exceeds the 50-megapixel limit.")
            orientation = image.getexif().get(274, 1)
            return Info(image.format, (h, w) if orientation in (5, 6, 7, 8) else (w, h))
    except ImageError:
        raise
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise ImageError(f"Cannot read {Path(path).name}: {exc}") from exc


def load(path: Path) -> tuple[Image.Image, str]:
    info = inspect(path)
    try:
        with Image.open(path) as raw:
            oriented = ImageOps.exif_transpose(raw)
            oriented.load()
            alpha = oriented.convert("RGBA").getchannel("A")
            profile = raw.info.get("icc_profile")
            if profile:
                try:
                    src = ImageCms.ImageCmsProfile(BytesIO(profile))
                    color_mode = oriented.mode if oriented.mode in ("RGB", "CMYK", "LAB", "L") else "RGB"
                    color = ImageCms.profileToProfile(oriented.convert(color_mode), src, SRGB, outputMode="RGB")
                except Exception as exc:
                    raise ImageError("Invalid or incompatible embedded color profile. Re-export the image with a valid profile.") from exc
            else:
                color = oriented.convert("RGB")
            color.putalpha(alpha)
            color.info.clear()
            return color, info.format
    except ImageError:
        raise
    except (OSError, ValueError) as exc:
        raise ImageError(f"Cannot decode {Path(path).name}: {exc}") from exc


def dimensions(size: tuple[int, int], settings: Settings) -> tuple[int, int]:
    w, h = size
    mode = settings.resize_mode
    if mode == "Exact dimensions":
        result = settings.width, settings.height
    else:
        scale = {"None": 1, "Fit box": min(settings.width / w, settings.height / h),
                 "Width": settings.width / w, "Height": settings.height / h,
                 "Percentage": settings.percent / 100}[mode]
        if not settings.enlarge:
            scale = min(scale, 1)
        result = max(1, round(w * scale)), max(1, round(h * scale))
    if result[0] * result[1] > MAX_PIXELS:
        raise ImageError("Requested output exceeds the 50-megapixel limit. Reduce its dimensions.")
    return result


def composite(image: Image.Image, logo: Image.Image, s: Settings) -> Image.Image:
    w, h = image.size
    margin = round(min(w, h) * s.margin / 100)
    available_w, available_h = max(1, w - 2 * margin), max(1, h - 2 * margin)
    factor = min(w * s.logo_width / 100 / logo.width, available_w / logo.width, available_h / logo.height)
    mark = logo.resize((max(1, round(logo.width * factor)), max(1, round(logo.height * factor))), Image.Resampling.LANCZOS)
    mark.putalpha(mark.getchannel("A").point(lambda a: round(a * s.opacity / 100)))
    if s.position == "Center":
        x, y = (w - mark.width) // 2, (h - mark.height) // 2
    else:
        x = w - margin - mark.width if "right" in s.position else margin
        y = h - margin - mark.height if "Bottom" in s.position else margin
    image.alpha_composite(mark, (max(0, x), max(0, y)))
    return image


def transform(path: Path, s: Settings, preview_bound: int | None = None):
    s.validate()
    image, original_format = load(path)
    output_size = dimensions(image.size, s)
    target = output_size
    if preview_bound:
        scale = min(1, preview_bound / max(output_size))
        target = max(1, round(output_size[0] * scale)), max(1, round(output_size[1] * scale))
    if image.size != target:
        image = image.resize(target, Image.Resampling.LANCZOS)
    if s.logo_enabled:
        logo, _ = load(Path(s.logo_path))
        image = composite(image, logo, s)
    fmt = original_format if s.output_format == "Original" else s.output_format
    if fmt == "JPEG":
        flattened = Image.new("RGB", image.size, ImageColor.getrgb(s.background))
        flattened.paste(image, mask=image.getchannel("A"))
        image = flattened
    image.info.clear()
    return image, fmt, output_size


def save_result(path: Path, folder: Path, s: Settings) -> Result:
    temporary = None
    try:
        if not folder.is_dir():
            raise ImageError("Output folder does not exist. Choose an existing folder.")
        image, fmt, size = transform(path, s)
        handle, name = tempfile.mkstemp(prefix=".lit-", suffix=".tmp", dir=folder)
        temporary = Path(name)
        os.close(handle)
        options = {"icc_profile": SRGB_BYTES}
        if fmt in ("JPEG", "WEBP"):
            options["quality"] = s.quality
        image.save(temporary, format=fmt, **options)
        # Windows rename is atomic, works on FAT/exFAT too, and never replaces
        # an existing destination. POSIX uses a non-replacing hard link.
        index = 0
        while True:
            suffix = "" if index == 0 else f"_{index}"
            destination = folder / f"{path.stem}_processed{suffix}.{FORMATS[fmt]}"
            try:
                if os.name == "nt":
                    os.rename(temporary, destination)
                else:
                    os.link(temporary, destination)
                break
            except FileExistsError:
                index += 1
        return Result(path, destination, size, destination.stat().st_size)
    except Exception as exc:
        return Result(path, error=str(exc) or type(exc).__name__)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def run_batch(paths: list[Path], folder: Path, s: Settings,
              cancel: threading.Event, callback: Callable[[int, Result], None]):
    """Settings are immutable; cancellation occurs between files."""
    results = []
    for i, path in enumerate(paths):
        if cancel.is_set():
            break
        result = save_result(path, folder, s)
        results.append(result)
        callback(i, result)
    return results
