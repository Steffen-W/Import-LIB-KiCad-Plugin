from __future__ import annotations

import json
from pathlib import Path

import pytest

from plugins.KiCad_Settings import KiCad_Settings

LIB = "/home/user/KiCad"

SYM_LIB_TABLE = """(sym_lib_table
\t(version 7)
\t(lib (name "Snapeda") (type "KiCad") (uri "${KICAD_3RD_PARTY}/Snapeda.kicad_sym") (options "") (descr "Bibliothek für Ð-Teile") (hidden))
)
"""

FP_LIB_TABLE = """(fp_lib_table
\t(version 7)
\t(lib (name "Snapeda") (type "KiCad") (uri "${KICAD_3RD_PARTY}/Snapeda.pretty") (options "") (descr ""))
)
"""


def write_kicad_common(settings_dir: Path, env_vars: dict[str, str]) -> None:
    kicad_common = {"environment": {"vars": env_vars}, "input": {"note": "Größe Ð"}}
    (settings_dir / "kicad_common.json").write_text(json.dumps(kicad_common), encoding="utf-8")


@pytest.fixture
def settings_dir(tmp_path: Path) -> Path:
    (tmp_path / "sym-lib-table").write_text(SYM_LIB_TABLE, encoding="utf-8")
    (tmp_path / "fp-lib-table").write_text(FP_LIB_TABLE, encoding="utf-8")
    write_kicad_common(tmp_path, {"KICAD_3RD_PARTY": LIB, "KICAD10_3RD_PARTY": "/other"})
    return tmp_path


def run_all_checks(settings: KiCad_Settings, lib_name: str) -> str:
    return (
        settings.check_GlobalVar(LIB)
        + settings.check_symbollib(f"{lib_name}.kicad_sym")
        + settings.check_footprintlib(lib_name)
    )


def snapshot(directory: Path) -> dict[str, tuple[bytes, int]]:
    return {
        str(path.relative_to(directory)): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in directory.rglob("*")
        if path.is_file()
    }


def test_matching_configuration_reports_nothing(settings_dir: Path) -> None:
    assert run_all_checks(KiCad_Settings(str(settings_dir)), "Snapeda") == ""


@pytest.mark.parametrize("lib_name", ["Snapeda", "Samacsys"])
def test_checks_never_modify_kicad_files(settings_dir: Path, lib_name: str) -> None:
    write_kicad_common(settings_dir, {})
    before = snapshot(settings_dir)

    assert run_all_checks(KiCad_Settings(str(settings_dir)), lib_name)

    assert snapshot(settings_dir) == before


def test_missing_configuration_is_reported_without_creating_files(tmp_path: Path) -> None:
    msg = run_all_checks(KiCad_Settings(str(tmp_path)), "Snapeda")

    assert "KICAD_3RD_PARTY is not defined" in msg
    assert "'${KICAD_3RD_PARTY}/Snapeda.kicad_sym' is not imported" in msg
    assert "Snapeda is not in the Footprint Libraries" in msg
    assert not list(tmp_path.iterdir())


def test_mismatching_entries_are_reported(settings_dir: Path) -> None:
    write_kicad_common(settings_dir, {"KICAD_3RD_PARTY": "/elsewhere"})
    (settings_dir / "fp-lib-table").write_text(
        FP_LIB_TABLE.replace("Snapeda.pretty", "Old.pretty"), encoding="utf-8"
    )
    settings = KiCad_Settings(str(settings_dir))

    assert "defined as '/elsewhere'" in settings.check_GlobalVar(LIB)
    assert "points to '${KICAD_3RD_PARTY}/Old.pretty'" in settings.check_footprintlib("Snapeda")


@pytest.mark.parametrize(
    ("taken", "suggestion"),
    [
        ([], "Name: Snapeda\n"),
        (["Snapeda"], "Name: Snapeda_kicad_sym\n"),
        (["Snapeda", "Snapeda_kicad_sym"], "corrected manually or deleted"),
    ],
)
def test_symbol_entry_suggests_free_name(tmp_path: Path, taken: list[str], suggestion: str) -> None:
    rows = "".join(f'\t(lib (name "{name}") (type "KiCad") (uri "/x"))\n' for name in taken)
    (tmp_path / "sym-lib-table").write_text(f"(sym_lib_table\n{rows})\n", encoding="utf-8")

    msg = KiCad_Settings(str(tmp_path)).check_symbollib("Snapeda_kicad_sym.kicad_sym")

    assert suggestion in msg


def test_unreadable_kicad_common_is_not_reported_as_missing(settings_dir: Path) -> None:
    (settings_dir / "kicad_common.json").write_text("{ truncated", encoding="utf-8")

    msg = KiCad_Settings(str(settings_dir)).check_GlobalVar(LIB)

    assert "Could not read the KiCad environment variables" in msg
    assert "not defined" not in msg


@pytest.mark.parametrize("name", ["missing", "file"])
def test_settings_reject_non_directory_path(tmp_path: Path, name: str) -> None:
    (tmp_path / "file").write_text("")
    with pytest.raises(NotADirectoryError):
        KiCad_Settings(str(tmp_path / name))
