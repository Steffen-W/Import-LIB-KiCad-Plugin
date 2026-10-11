from __future__ import annotations

import os
import stat
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest
from kiutils.symbol import SymbolLib

from plugins import KiCadImport
from plugins.KiCadImport import LibImporter, find_in_zip
from plugins.KiCadImport.footprint_model_parser import FootprintModelParser

SYMBOL_LIB = """(kicad_symbol_lib (version 20211014) (generator test)
  (symbol "PART" (in_bom yes) (on_board yes)
    (property "Reference" "U" (at 0 0 0) (effects (font (size 1.27 1.27))))
    (property "Value" "PART" (at 0 0 0) (effects (font (size 1.27 1.27))))
    (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27))))
  )
)
"""

MakeZip = Callable[[dict[str, str]], Path]


def footprint(name: str) -> str:
    return f'(footprint "{name}" (layer "F.Cu"))\n'


@pytest.fixture
def importer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LibImporter:
    monkeypatch.setattr(KiCadImport, "cli", None)
    imp = LibImporter()
    monkeypatch.setattr(imp, "print", lambda txt: None)
    imp.set_DEST_PATH(tmp_path / "lib")
    return imp


@pytest.fixture
def make_zip(tmp_path: Path) -> MakeZip:
    def _make(members: dict[str, str]) -> Path:
        path = tmp_path / "part.zip"
        with zipfile.ZipFile(path, "w") as zf:
            for name, content in members.items():
                zf.writestr(name, content)
        return path

    return _make


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("R_0603", "R_0603"),
        ("a b", "a_b"),
        ("CON", "_CON"),
        ("con.kicad_mod", "_con.kicad_mod"),
        ("COM1", "_COM1"),
        ("COM10", "COM10"),
        ("CONSOLE", "CONSOLE"),
        ("Name.", "Name"),
        ("..", "_"),
    ],
)
def test_clean_name(raw: str, clean: str) -> None:
    imp = LibImporter()
    assert imp.cleanName(raw) == clean
    assert imp.cleanName(clean) == clean


def test_find_in_zip_returns_first_match_in_archive_order(tmp_path: Path) -> None:
    path = tmp_path / "a.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("a/b/one.kicad_mod", "")
        zf.writestr("a/c/two.kicad_mod", "")
        zf.writestr("/".join(["d"] * 1500) + "/deep.stp", "")
    with zipfile.ZipFile(path) as zf:
        root = zipfile.Path(zf)
        match = find_in_zip(root, ".kicad_mod")
        assert match is not None and match.at == "a/b/one.kicad_mod"
        assert find_in_zip(root, ".stp") is not None
        assert find_in_zip(root, ".wrl") is None


def test_extract_file_to_temp_removes_temp_dir_on_failure(
    importer: LibImporter, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    temp_dir = tmp_path / "extract"

    def mkdtemp() -> str:
        temp_dir.mkdir()
        return str(temp_dir)

    monkeypatch.setattr(tempfile, "mkdtemp", mkdtemp)
    with pytest.raises(FileNotFoundError):
        importer.extract_file_to_temp(tmp_path / "missing.step")
    assert not temp_dir.exists()


def test_import_names_footprint_by_content(importer: LibImporter, make_zip: MakeZip) -> None:
    archive = make_zip({"PART.kicad_sym": SYMBOL_LIB, "foo.kicad_mod": footprint("CON")})

    assert importer.import_all(archive) == ("OK",)

    pretty = importer.DEST_PATH / "Snapeda.pretty"
    assert [p.name for p in pretty.iterdir()] == ["_CON.kicad_mod"]
    assert '"Snapeda:_CON"' in (importer.DEST_PATH / "Snapeda.kicad_sym").read_text()


def test_import_without_overwrite_keeps_existing_footprint(
    importer: LibImporter, make_zip: MakeZip
) -> None:
    existing = importer.DEST_PATH / "Snapeda.pretty" / "bar.kicad_mod"
    existing.parent.mkdir(parents=True)
    existing.write_text("OLD")
    archive = make_zip({"PART.kicad_sym": SYMBOL_LIB, "foo.kicad_mod": footprint("bar")})

    assert importer.import_all(archive, overwrite_if_exists=False) == ("OK",)

    assert existing.read_text() == "OLD"
    assert [p.name for p in existing.parent.iterdir()] == ["bar.kicad_mod"]
    assert importer.footprint_skipped


def test_failed_save_rolls_back_all_files(importer: LibImporter, make_zip: MakeZip) -> None:
    existing = importer.DEST_PATH / "Snapeda.pretty" / "bar.kicad_mod"
    existing.parent.mkdir(parents=True)
    existing.write_text("OLD")
    # A file where the model directory belongs makes the final save step fail.
    (importer.DEST_PATH / "Snapeda.3dshapes").write_text("")
    archive = make_zip(
        {"PART.kicad_sym": SYMBOL_LIB, "foo.kicad_mod": footprint("bar"), "part.step": "x"}
    )

    assert importer.import_all(archive) is None

    assert existing.read_text() == "OLD"
    assert not (importer.DEST_PATH / "Snapeda.kicad_sym").exists()
    assert not list(importer.DEST_PATH.rglob("*.backup"))
    assert not list(importer.DEST_PATH.rglob("*.tmp"))


@pytest.mark.parametrize(
    ("content", "name"),
    [
        ('(footprint "R 0603" (layer "F.Cu"))', "R 0603"),
        ("(module SOIC-8 (layer F.Cu))", "SOIC-8"),
        ('(footprint "" (layer "F.Cu"))', None),
        ('(symbol "x")', None),
    ],
)
def test_extract_footprint_name(content: str, name: str | None) -> None:
    assert FootprintModelParser().extract_footprint_name(content) == name


def test_update_or_add_model_replaces_quoted_and_bare_references() -> None:
    content = '(module X\n  (model old.wrl (scale (xyz 1 1 1)))\n  (model "a b.step"))'

    result = FootprintModelParser().update_or_add_model(content, "new.step")

    assert result == '(module X\n  (model "new.step" (scale (xyz 1 1 1)))\n  (model "new.step"))'


def test_update_or_add_model_ignores_model_text_in_strings() -> None:
    content = '(footprint "x" (descr "literal (model fake.wrl) text"))'

    result = FootprintModelParser().update_or_add_model(content, "real.step")

    assert '(descr "literal (model fake.wrl) text")' in result
    assert '(model "real.step"' in result


def test_update_or_add_model_inserts_into_top_level_expression() -> None:
    content = '(footprint "a)b" (descr "x \\" (y")\n  (layer "F.Cu"))\n'

    result = FootprintModelParser().update_or_add_model(content, "m.step")

    head, model, tail = result.partition('\n\t(model "m.step"')
    assert head == content[: content.rindex(")")]
    assert model and tail.endswith("\n\t)\n)\n")


@pytest.mark.parametrize(
    "content",
    [
        '(footprint "a" (layer "F.Cu")',
        '(footprint "a" (layer "F.Cu") (model old.step)',
        '(footprint "a)"',
        '(footprint "a") trailing',
        'garbage (footprint "a" (layer "F.Cu"))',
        '(footprint "a") (footprint "b")',
        ') (footprint "a")',
        "garbage",
        "",
    ],
)
def test_parser_rejects_malformed_footprint(content: str) -> None:
    parser = FootprintModelParser()
    with pytest.raises(ValueError, match="not a single closed"):
        parser.extract_footprint_name(content)
    with pytest.raises(ValueError, match="not a single closed"):
        parser.update_or_add_model(content, "m.step")


def test_footprint_references_installed_model(importer: LibImporter, make_zip: MakeZip) -> None:
    importer.compress_models = True
    archive = make_zip(
        {"PART.kicad_sym": SYMBOL_LIB, "foo.kicad_mod": footprint("bar"), "part.stp": "x"}
    )

    assert importer.import_all(archive) == ("OK",)

    assert (importer.DEST_PATH / "Snapeda.3dshapes" / "part.stp.gz").exists()
    content = (importer.DEST_PATH / "Snapeda.pretty" / "bar.kicad_mod").read_text()
    assert '(model "${KICAD_3RD_PARTY}/Snapeda.3dshapes/part.stp.gz"' in content


@pytest.mark.parametrize("overwrite_fails", [False, True])
def test_save_keeps_unrelated_backup_and_tmp_files(
    importer: LibImporter, make_zip: MakeZip, overwrite_fails: bool
) -> None:
    pretty = importer.DEST_PATH / "Snapeda.pretty"
    pretty.mkdir(parents=True)
    (pretty / "bar.kicad_mod").write_text(footprint("bar"))
    user_files = [pretty / "bar.kicad_mod.backup", importer.DEST_PATH / "Snapeda.tmp"]
    for user_file in user_files:
        user_file.write_text("user")
    if overwrite_fails:
        (importer.DEST_PATH / "Snapeda.3dshapes").write_text("")
    members = {"PART.kicad_sym": SYMBOL_LIB, "foo.kicad_mod": footprint("bar"), "part.step": "x"}

    importer.import_all(make_zip(members))

    assert all(user_file.read_text() == "user" for user_file in user_files)
    assert not list(importer.DEST_PATH.rglob(".*.backup"))


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits")
def test_installed_files_keep_default_permissions(importer: LibImporter, make_zip: MakeZip) -> None:
    archive = make_zip({"PART.kicad_sym": SYMBOL_LIB, "foo.kicad_mod": footprint("bar")})

    assert importer.import_all(archive) == ("OK",)

    umask = os.umask(0)
    os.umask(umask)
    expected = 0o666 & ~umask
    for installed in ("Snapeda.kicad_sym", "Snapeda.pretty/bar.kicad_mod"):
        assert stat.S_IMODE((importer.DEST_PATH / installed).stat().st_mode) == expected


def test_failed_model_reference_rolls_back_import(
    importer: LibImporter, make_zip: MakeZip, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(footprint_content: str, model_path: str) -> str:
        raise ValueError("model reference failed")

    monkeypatch.setattr(importer.footprint_parser, "update_or_add_model", fail)
    archive = make_zip(
        {"PART.kicad_sym": SYMBOL_LIB, "foo.kicad_mod": footprint("bar"), "part.step": "x"}
    )

    assert importer.import_all(archive) is None

    assert not [p for p in importer.DEST_PATH.rglob("*") if p.is_file()]


def test_failed_symbol_verification_leaves_no_files(importer: LibImporter) -> None:
    foreign = importer.DEST_PATH / "foreign.tmp"
    foreign.parent.mkdir(parents=True)
    foreign.write_text("keep")

    saved = importer.save_to_library(
        SymbolLib(), None, None, KiCadImport.REMOTE_TYPES.Snapeda, "PART"
    )

    assert not saved
    assert [p.name for p in importer.DEST_PATH.iterdir()] == ["foreign.tmp"]


def test_unparsable_footprint_reports_incomplete_import(
    importer: LibImporter, make_zip: MakeZip
) -> None:
    archive = make_zip({"PART.kicad_sym": SYMBOL_LIB, "foo.kicad_mod": "garbage"})

    assert importer.import_all(archive) == ("Warning",)

    assert (importer.DEST_PATH / "Snapeda.kicad_sym").exists()
    assert not (importer.DEST_PATH / "Snapeda.pretty").exists()


def test_import_state_is_reset_per_import(importer: LibImporter, make_zip: MakeZip) -> None:
    importer.lib_skipped = importer.footprint_skipped = importer.model_skipped = True
    archive = make_zip({"PART.kicad_sym": SYMBOL_LIB})

    assert importer.import_all(archive) == ("OK",)

    assert not (importer.lib_skipped or importer.footprint_skipped or importer.model_skipped)
