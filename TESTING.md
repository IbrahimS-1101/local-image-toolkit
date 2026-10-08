# Testing and compatibility

## Run automated tests

From the repository root, after installing `requirements-dev.txt`:

```powershell
.venv\Scripts\python.exe -m pytest tests -q
```

Tests generate their own images and use temporary folders. They do not need personal
photos or saved application preferences. Qt UI tests use its offscreen platform.

For the desktop acceptance harness:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
.venv\Scripts\python.exe main.py --smoke-test .\test-artifacts
```

Use a fresh output directory for each run. The harness creates 100 generated images in
mixed formats, exercises drag/drop handlers and previews, checks a corrupt-file failure
and retry, and tests cancellation and preset persistence. It writes screenshots and
`acceptance.json`. The packaged executable supports the same `--smoke-test` arguments.

## Verification to date

On Windows 11 x64 with Python 3.12.4, the engine/filesystem/UI tests passed. Packaged-app
acceptance also passed with external Python unavailable on PATH. Normal and simulated
150% scaling screenshots were inspected.

Hands-on testing by the creator confirmed JPEG → PNG, mixed JPEG/PNG batches exported
as PNG, batch logo size/margin changes, resizing modes including percentage and fit box,
and PNG → WebP. These were functional checks, not a comprehensive image-quality benchmark.

## Compatibility boundaries

The Qt 6.11 dependency requires Windows 10 version 1809 (build 17763) or later,
or Windows 11, on x64. See [Qt platform requirements](https://doc.qt.io/qt-6.11/supported-platforms.html).

On 2026-10-08, the creator tested `release-public` in a fresh Windows 10 version 1607
(build 14393) VM. It failed before application startup with a Python DLL LoadLibrary
error. This OS is below the dependency minimum; the precise failing dependency has not
been identified. This does not establish whether the package works on supported Windows 10.

The current portable build is unsigned. A clean supported Windows 10 VM without Python
(Windows 10 22H2 is the next test target), physical high-DPI behavior, and a physically
disconnected-network test remain pending. Offscreen UI checks do not replace hands-on
Explorer drag/drop and keyboard usability checks.

The application uses no networking APIs. The build-time materials collector downloads
dependency sources when they are not cached; `--offline` prevents those downloads.

Before a public release, also inspect transparency-to-JPEG backgrounds, filename
collisions, corrupt-file messaging, cancellation, and presets across restarts manually.
