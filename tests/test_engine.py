import dataclasses
import threading
from pathlib import Path
import pytest
from PIL import Image, ImageCms
from toolkit import engine
from toolkit.engine import Settings, ImageError, dimensions, inspect, load, transform, save_result, run_batch
from toolkit.storage import Store


@pytest.fixture
def picture(tmp_path):
    path = tmp_path / "صورة.png"
    Image.new("RGBA", (200, 100), (220, 20, 10, 128)).save(path)
    return path


@pytest.mark.parametrize("mode,kwargs,expected", [
    ("None", {}, (200, 100)), ("Fit box", {"width": 80, "height": 80}, (80, 40)),
    ("Width", {"width": 50}, (50, 25)), ("Height", {"height": 30}, (60, 30)),
    ("Percentage", {"percent": 25}, (50, 25)), ("Exact dimensions", {"width": 75, "height": 80}, (75, 80)),
    ("Width", {"width": 500}, (200, 100)), ("Width", {"width": 500, "enlarge": True}, (500, 250)),
])
def test_dimensions(mode, kwargs, expected):
    assert dimensions((200, 100), Settings(resize_mode=mode, **kwargs)) == expected


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP", "Original"])
def test_formats_metadata_transparency(picture, tmp_path, fmt):
    result = save_result(picture, tmp_path, Settings(output_format=fmt))
    assert not result.error
    with Image.open(result.output) as output:
        assert output.format == ("PNG" if fmt == "Original" else fmt)
        assert output.info.get("icc_profile")
        assert not output.getexif()
        if fmt in ("PNG", "Original", "WEBP"):
            assert abs(output.convert("RGBA").getpixel((50, 50))[3] - 128) <= 1
        else:
            assert all(abs(a-b) < 5 for a,b in zip(output.getpixel((50,50)), (237,137,132)))


def test_orientation(tmp_path):
    p = tmp_path / "rotated.jpg"
    exif = Image.Exif()
    exif[274] = 6
    Image.new("RGB", (80, 40), "red").save(p, exif=exif)
    assert inspect(p).size == (40, 80)
    image, _ = load(p)
    assert image.size == (40, 80)
    result = save_result(p, tmp_path, Settings())
    with Image.open(result.output) as out:
        assert out.size == (40, 80)
        assert not out.getexif()


@pytest.mark.parametrize("position,xy", [("Top left", (1,1)), ("Top right", (90,1)), ("Bottom left", (1,90)), ("Bottom right", (90,90)), ("Center", (50,50))])
def test_logo_positions(tmp_path, position, xy):
    base, logo = tmp_path / "base.png", tmp_path / "logo.png"
    Image.new("RGBA", (100, 100), "white").save(base)
    Image.new("RGBA", (20, 20), "red").save(logo)
    s = Settings(logo_enabled=True, logo_path=str(logo), position=position, margin=0, logo_width=20, opacity=50)
    output, _, _ = transform(base, s)
    assert output.getpixel(xy) == (255, 127, 127, 255)
    assert output.getpixel((30,30)) == (255,255,255,255)


def test_logo_is_after_resize_and_constrained(tmp_path):
    base, logo = tmp_path / "base.png", tmp_path / "logo.png"
    Image.new("RGBA", (200, 100), "white").save(base)
    Image.new("RGBA", (20, 100), "blue").save(logo)
    s = Settings(resize_mode="Width", width=20, logo_enabled=True, logo_path=str(logo), logo_width=100, margin=0)
    output, _, size = transform(base, s)
    assert size == (20, 10)
    assert output.getpixel((19,9))[:3] == (0,0,255)


def test_no_overwrite_and_temporary_cleanup(picture, tmp_path):
    original = picture.read_bytes()
    first = save_result(picture, tmp_path, Settings())
    before = first.output.read_bytes()
    second = save_result(picture, tmp_path, Settings())
    assert first.output != second.output
    assert first.output.read_bytes() == before
    assert picture.read_bytes() == original
    assert not list(tmp_path.glob(".lit-*"))


def test_encoding_failure_cleanup(picture, tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(Image.Image, "save", fail)
    result = save_result(picture, tmp_path, Settings())
    assert "disk full" in result.error
    assert not list(tmp_path.glob(".lit-*"))
    assert not list(tmp_path.glob("*processed*"))


def test_unwritable_destination(picture, tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise PermissionError("Destination is read-only")
    monkeypatch.setattr(engine.tempfile, "mkstemp", fail)
    result = save_result(picture, tmp_path, Settings())
    assert "read-only" in result.error


def test_bad_inputs_and_content_detection(tmp_path):
    p = tmp_path / "wrong-extension.bin"
    Image.new("RGB", (20, 20)).save(p, "JPEG")
    assert inspect(p).format == "JPEG"
    p.write_bytes(b"broken")
    with pytest.raises(ImageError):
        load(p)
    Image.new("RGB", (20,20)).save(p, "BMP")
    with pytest.raises(ImageError, match="Unsupported"):
        inspect(p)


def test_animated_rejected(tmp_path):
    p = tmp_path / "animated.webp"
    Image.new("RGB", (20,20), "red").save(p, "WEBP", save_all=True, append_images=[Image.new("RGB", (20,20), "blue")], duration=100, loop=0)
    with pytest.raises(ImageError, match="Animated"):
        inspect(p)


def test_bad_and_valid_icc(tmp_path):
    p = tmp_path / "icc.png"
    Image.new("RGB", (20,20)).save(p, icc_profile=b"invalid profile")
    with pytest.raises(ImageError, match="profile"):
        load(p)
    Image.new("RGB", (20,20)).save(p, icc_profile=engine.SRGB_BYTES)
    assert load(p)[0].mode == "RGBA"


def test_metadata_stripped(tmp_path):
    from PIL.PngImagePlugin import PngInfo
    p = tmp_path / "metadata.png"
    info = PngInfo()
    info.add_text("secret", "location")
    Image.new("RGB", (20,20)).save(p, pnginfo=info)
    result = save_result(p, tmp_path, Settings())
    with Image.open(result.output) as output:
        assert "secret" not in output.info


def test_limits(picture, monkeypatch):
    monkeypatch.setattr(engine, "MAX_PIXELS", 100)
    with pytest.raises(ImageError, match="megapixel"):
        inspect(picture)
    with pytest.raises(ImageError, match="megapixel"):
        dimensions((200,100), Settings())


def test_missing_logo_and_invalid_settings(picture):
    with pytest.raises(ImageError, match="logo"):
        transform(picture, Settings(logo_enabled=True, logo_path="missing.png"))
    with pytest.raises(ImageError):
        Settings(quality=0).validate()
    with pytest.raises(ImageError):
        Settings.from_dict({"width": "bad"})


def test_batch_continues_cancellation_and_frozen_settings(picture, tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"invalid")
    cancel = threading.Event()
    settings = Settings()
    with pytest.raises(dataclasses.FrozenInstanceError):
        settings.width = 12
    results = run_batch([bad,picture], tmp_path, settings, cancel, lambda *args: None)
    assert results[0].error and results[1].output
    results = run_batch([picture,picture,picture], tmp_path, settings, cancel, lambda *args: cancel.set())
    assert len(results) == 1


def test_preferences_roundtrip_and_missing_logo(tmp_path):
    store = Store(tmp_path / "preferences")
    store.presets["Web"] = Settings(width=800).to_dict()
    store.output_folder = str(tmp_path)
    store.save()
    restored = Store(store.root)
    assert restored.preset("Web").width == 800
    assert restored.output_folder == str(tmp_path)
    restored.presets["Missing"] = Settings(logo_enabled=True, logo_path="missing.png").to_dict()
    with pytest.raises(ImageError, match="logo"):
        restored.preset("Missing")


def test_corrupt_preferences_kept(tmp_path):
    (tmp_path / "preferences.json").write_text("bad json")
    store = Store(tmp_path)
    assert store.warning
    with pytest.raises(ImageError):
        store.save()
    assert store.path.read_text() == "bad json"
