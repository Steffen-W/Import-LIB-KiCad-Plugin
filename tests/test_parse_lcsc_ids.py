import pytest

from plugins.impart_easyeda import parse_lcsc_ids


@pytest.mark.parametrize(
    "text",
    ["C965840\nC2286\r\nC165948", " C965840, C2286;C165948 ", "c965840\tC2286  C165948"],
)
def test_separators(text: str) -> None:
    assert parse_lcsc_ids(text) == ["C965840", "C2286", "C165948"]


def test_single_id_and_duplicates() -> None:
    assert parse_lcsc_ids("C2040") == ["C2040"]
    assert parse_lcsc_ids("C2040 C2040") == ["C2040"]


@pytest.mark.parametrize(
    "text",
    ["", "  ", "C2040 X12", "C2040C2286", "C20-40", "C²", "C٢٠٤٠"],
)
def test_invalid_id_raises(text: str) -> None:
    with pytest.raises(ValueError, match="LCSC component ID"):
        parse_lcsc_ids(text)
