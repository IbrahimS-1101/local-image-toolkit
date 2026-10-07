"""Regression checks for the boundary between internal work and distributed source."""
from pathlib import Path
import pytest
from build_release import copy_public_source, PUBLIC_FILES
from prepare_release_materials import prepare


def test_public_copy_excludes_internal_notes_and_generated_files(tmp_path):
    source, public = tmp_path / "source", tmp_path / "public"
    for name in PUBLIC_FILES:
        file = source / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("public")
    for name in ("toolkit/engine.py", "tests/test_example.py", "toolkit/__pycache__/engine.pyc",
                 "PLAN.md", "VALIDATION.md", "RELEASE_CHECKLIST.md", ".env", "private.txt",
                 "work/private.py", "licenses/generated.txt", "dependency-sources/qt.tar.xz",
                 "docs/screenshots/unreviewed.png", "preferences.json", "dist/app.exe"):
        file = source / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("test fixture")
    copy_public_source(source, public)
    expected = set(PUBLIC_FILES) | {"toolkit/engine.py", "tests/test_example.py"}
    assert {p.relative_to(public).as_posix() for p in public.rglob("*") if p.is_file()} == expected


def test_offline_materials_fail_clearly_when_missing(tmp_path):
    with pytest.raises(RuntimeError, match="Missing cached source archive"):
        prepare(tmp_path, offline=True)
