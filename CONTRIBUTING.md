# Contributing

Contributions are welcome. Local Image Toolkit is a small offline desktop utility, so
changes should keep common image tasks simple, preserve originals, and avoid runtime
network dependencies.

## Report a problem or suggest a change

Describe what you tried, what you expected, and what happened. Include the app version,
Windows version, input/output formats, and relevant settings. Use a generated or freely
redistributable sample image when one is needed to reproduce a problem.

Discuss larger features before implementing them so their scope fits the app.

## Make a change

1. Follow the development setup in `README.md`.
2. Keep image processing in `toolkit/engine.py` independent of the interface.
3. Keep changes focused and explain the user-visible result.
4. Run `python -m pytest tests -q`; add meaningful regression coverage for behavior changes.
5. For UI or packaging changes, describe the manual checks performed and their limitations.
6. Submit the change with a short description, validation results, and screenshots when useful.

Application contributions are made under this project's MIT license. Preserve existing
copyright notices and third-party license materials. New dependencies need their licenses
and distribution requirements reviewed before inclusion.

Contributor acknowledgments will be added as contributions are accepted.
