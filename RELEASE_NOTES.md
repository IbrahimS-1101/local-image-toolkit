# Local Image Toolkit 1.0.0

Created by **Ibrahim Samir**.

An offline Windows desktop utility for everyday image preparation. Resize images, convert
between JPEG, PNG, and WebP, and add a logo — one image at a time or across a batch.

## Included in this release

- Drag-and-drop image queue with thumbnails and original/processed previews.
- Proportion-preserving resizing by box, width, height, or percentage, plus optional exact stretching.
- JPEG and WebP quality controls, PNG transparency, and selectable JPEG backgrounds.
- Logo placement, size, opacity, and margins.
- Direct output-folder saving without overwriting originals or existing outputs.
- Batch progress, cancellation between files, per-file errors, and retry.
- Saved presets and remembered output folder.
- Orientation correction, sRGB conversion, and removal of EXIF/GPS/text metadata.

## Download and run

Download `Local-Image-Toolkit-1.0.0-Windows-x64.zip`, extract the entire archive, and open
`Local Image Toolkit.exe`. Keep `_internal` beside the executable. No Python installation
is required. The ZIP includes application source, documentation, and dependency materials.

## Validation

The automated suite passed. A packaged-app acceptance run covered 100
mixed-format images, preview, failure/retry, cancellation, and presets. User testing also
passed mixed JPEG/PNG batches, format conversion, batch logo changes, and several resize modes.
Creator testing on a fresh Windows 10 VM passed PNG to WebP with 200% enlargement
and a bottom-right logo with custom margins. A repeat PNG to JPEG test passed with
network access disabled; command checks found Store Python aliases and no Python launcher.
See `TESTING.md` for reproducible checks and verification boundaries.

## Current limits

Windows x64: Windows 10 version 1809 (build 17763) or later, or Windows 11. Still JPEG, PNG, and WebP images only, with a 50-megapixel limit per
input, logo, and output. No cropping, text watermarks, animation editing, HEIC/RAW, or
automatic updates. The executable is unsigned. Windows 10 version 1607 is unsupported and failed to launch. The exact build of the
successful Windows 10 VM was not recorded; the dependency minimum is not itself a
claim that every supported Windows build has been tested.

## License

Application source: MIT. Qt/PySide6, Pillow, Python, and other bundled components retain
their respective licenses. See `LICENSE`, `THIRD_PARTY_NOTICES.md`, `licenses/`, and
`dependency-sources/` before redistribution.
