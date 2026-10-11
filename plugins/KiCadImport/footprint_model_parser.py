from __future__ import annotations

import re
from collections.abc import Iterator

# An S-expression atom: a quoted string or a bare token
_ATOM = r'"(?:[^"\\]|\\.)*"|[^\s()"]+'
_FOOTPRINT_HEAD = re.compile(rf"\((?:module|footprint)\s+({_ATOM})")
_MODEL_HEAD = re.compile(rf"\(model\s+({_ATOM})")


def _parens(content: str) -> Iterator[tuple[int, int]]:
    """Yield (index, depth) of each parenthesis outside string literals.

    The depth includes an opening parenthesis and excludes a closing one, so the
    top-level expression opens at depth 1 and closes at depth 0.
    """
    depth = 0
    in_string = escaped = False
    for i, char in enumerate(content):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "(":
            depth += 1
            yield i, depth
        elif char == ")":
            depth -= 1
            yield i, depth


def _expression_parens(content: str) -> list[tuple[int, int]]:
    """Return the parentheses of content, which must be exactly one closed S-expression."""
    parens = list(_parens(content))
    if (
        not parens
        or content[parens[0][0]] != "("
        or content[: parens[0][0]].strip()
        or parens[-1][1] != 0
        or any(depth <= 0 for _, depth in parens[:-1])
        or content[parens[-1][0] + 1 :].strip()
    ):
        raise ValueError("Footprint is not a single closed S-expression")
    return parens


def _model_block(model_path: str) -> str:
    return f'\t(model "{model_path}"\n\t\t(offset\n\t\t\t(xyz 0 0 0)\n\t\t)\n\t\t(scale\n\t\t\t(xyz 1 1 1)\n\t\t)\n\t\t(rotate\n\t\t\t(xyz 0 0 0)\n\t\t)\n\t)'


class FootprintModelParser:
    """Reads the name and rewrites the 3D model references of KiCad footprint files."""

    def extract_footprint_name(self, content: str) -> str | None:
        """Return the footprint name, or None if the expression is not a named footprint.

        Raises ValueError unless the content is exactly one closed S-expression.
        """
        match = _FOOTPRINT_HEAD.match(content, _expression_parens(content)[0][0])
        if not match:
            return None
        atom = match.group(1)
        name = atom[1:-1] if atom.startswith('"') else atom
        return name.strip() or None

    def update_or_add_model(self, footprint_content: str, model_path: str) -> str:
        """Point all model references to model_path, adding one if the footprint has none.

        Raises ValueError unless the content is exactly one closed S-expression.
        """
        parens = _expression_parens(footprint_content)
        end = parens[-1][0]

        paths = [
            match.span(1)
            for i, depth in parens
            if depth == 2 and (match := _MODEL_HEAD.match(footprint_content, i))
        ]
        if not paths:
            return (
                footprint_content[:end]
                + f"\n{_model_block(model_path)}\n"
                + footprint_content[end:]
            )

        for start, stop in reversed(paths):
            footprint_content = (
                f'{footprint_content[:start]}"{model_path}"{footprint_content[stop:]}'
            )
        return footprint_content
