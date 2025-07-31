import re
from pathlib import Path
from typing import Optional


class FootprintModelParser:
    """Simple parser for KiCad footprint files to handle 3D model references."""

    def __init__(self):
        self.last_paren_pattern = re.compile(r"\n(\s*)\)(\s*)$")

    def extract_model_info(self, footprint_content: str) -> Optional[str]:
        """Extract model filename from footprint content."""
        extract_pattern = re.compile(r'\(model\s+"([^"]*)"')
        match = extract_pattern.search(footprint_content)
        if match:
            model_path = match.group(1)
            return Path(model_path).name
        return None

    def has_model(self, footprint_content: str) -> bool:
        """Check if footprint has a model defined."""
        return re.search(r'\(model\s+"[^"]*"', footprint_content) is not None

    def update_model_path(self, footprint_content: str, new_model_path: str) -> str:
        """Update existing model path in footprint content."""
        model_block_pattern = re.compile(
            r'(\s*)\(model\s+"[^"]*"\s*\n(?:(?:\s*\([^)]*\)\s*\n)*)\s*\)', re.MULTILINE
        )

        def replace_model(match):
            indent = match.group(1)
            return f'{indent}(model "{new_model_path}"\n{indent}  (at (xyz 0 0 0))\n{indent}  (scale (xyz 1 1 1))\n{indent}  (rotate (xyz 0 0 0))\n{indent})'

        return model_block_pattern.sub(replace_model, footprint_content)

    def add_model(self, footprint_content: str, model_path: str) -> str:
        """Add model block before the last closing parenthesis."""
        model_block = f"""  (model "{model_path}"
    (at (xyz 0 0 0))
    (scale (xyz 1 1 1))
    (rotate (xyz 0 0 0))
  )"""

        match = self.last_paren_pattern.search(footprint_content)
        if match:
            indent = match.group(1)
            ending = match.group(2)
            insertion_point = match.start()
            result = (
                footprint_content[:insertion_point]
                + f"\n{model_block}\n{indent}){ending}"
            )
            return result
        else:
            if footprint_content.rstrip().endswith(")"):
                content = footprint_content.rstrip()
                return content[:-1] + f"\n{model_block}\n)"
            else:
                return footprint_content + f"\n{model_block}"

    def update_or_add_model(self, footprint_content: str, model_path: str) -> str:
        """Update existing model or add new model to footprint."""
        if self.has_model(footprint_content):
            return self.update_model_path(footprint_content, model_path)
        else:
            return self.add_model(footprint_content, model_path)


def update_footprint_model_simple(
    footprint_file: Path,
    model_filename: str,
    remote_type: str,
    kicad_link: str = "${KICAD_3RD_PARTY}",
) -> bool:
    """Update footprint file with new model path using string manipulation."""
    if not footprint_file.exists():
        return False

    try:
        content = footprint_file.read_text(encoding="utf-8")
        model_path = f"{kicad_link}/{remote_type}.3dshapes/{model_filename}"

        parser = FootprintModelParser()
        updated_content = parser.update_or_add_model(content, model_path)

        footprint_file.write_text(updated_content, encoding="utf-8")
        return True

    except Exception as e:
        print(f"Error updating footprint model: {e}")
        return False


if __name__ == "__main__":
    # Minimal example usage
    parser = FootprintModelParser()

    # Example footprint without model
    content = """(module "Test" (layer F.Cu)
  (pad 1 smd rect (at 0 0) (size 1 1) (layers F.Cu F.Paste F.Mask))
)"""

    model_path = "${KICAD_3RD_PARTY}/Samacsys.3dshapes/test_model.step"
    result = parser.update_or_add_model(content, model_path)

    print("Result:")
    print(result)
