# Third-party software

The MIT license covers Local Image Toolkit's application source only. The included libraries
and interpreter retain their respective copyrights and license conditions. In portable
releases, full collected texts are in `licenses/`. In a source checkout, the build-time
`prepare_release_materials.py` script collects them with the dependency source archives
into the ignored `.release-materials/` folder. No commercial Qt license is asserted.

## PySide6 / Shiboken / Qt 6.11.2

Copyright The Qt Company Ltd. and contributors. Used through dynamically loaded libraries.
Only Qt Core, Gui, and Widgets are imported by the application. The community distribution
offers LGPLv3/GPL alternatives; this application uses the LGPLv3 option for these components.
Additional third-party notices from Qt's source distribution also apply to its bundled components.
Unmodified corresponding-source archives for Qt Base, Qt SVG, Qt Image Formats, PySide,
and Shiboken are included in `dependency-sources/` alongside the application. License and
attribution texts have also been collected from those archives into `licenses/upstream/`.

- PySide/Shiboken corresponding source: https://code.qt.io/cgit/pyside/pyside-setup.git/?h=v6.11.2
- Qt corresponding source: https://download.qt.io/archive/qt/6.11/6.11.2/single/
- Qt source and dependency attributions: https://code.qt.io/cgit/qt/qtbase.git/tree/?h=v6.11.2
- Build instructions: https://doc.qt.io/qtforpython-6/building_from_source/index.html
- Qt license reference: https://doc.qt.io/qt-6/licensing.html

The Qt/PySide/Shiboken libraries are unmodified. You may replace compatible libraries under
`_internal` with modified versions; preserve the module names, architecture, and compatible ABI.
Application source and rebuild instructions are included. Nothing in the application license
restricts reverse engineering for debugging modifications to these libraries. Do not repackage
the application into an installer that prevents library replacement. See LGPLv3/GPLv3 texts.

## Pillow 12.3.0

Copyright Pillow contributors. MIT-CMU/Pillow license. Includes image-codec and color-management
libraries with their own notices, collected from Pillow's wheel in `licenses/`.
Source: https://github.com/python-pillow/Pillow/tree/12.3.0

## Python 3.12.4

Copyright Python Software Foundation and contributors. PSF License, including bundled-library
notices in the Python license text. Source: https://www.python.org/downloads/release/python-3124/

## PyInstaller bootloader

Copyright PyInstaller Development Team. GPL with the bootloader distribution exception.
The exception permits shipping the executable under the application's license. The included
license text describes the exception. Source: https://github.com/pyinstaller/pyinstaller/tree/v6.22.3

## Microsoft Visual C++ runtime

Copyright Microsoft Corporation. Redistributable runtime DLLs supplied with the Python and
PySide6 distributions are included for standalone execution. These DLLs are not MIT-licensed
application code. Runtime license reference: https://visualstudio.microsoft.com/license-terms/vs2022-cruntime/

## Release maintenance

Retain this notice, the license directory, upstream source references, and application source
when redistributing the ZIP. Recheck bundled dependencies and corresponding-source availability
before a public release, particularly if changing Qt versions or enabling extra modules.
