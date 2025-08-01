import re
from pathlib import Path
from typing import Optional


class FootprintModelParser:
    """Simple and reliable parser for KiCad footprint model paths with validation."""

    def validate_footprint_content(self, content: str) -> bool:
        """Check if content is a valid footprint file."""
        if not content.strip():
            return False

        # Check for both old (module) and new (footprint) format
        return re.search(r"\((module|footprint)\s+", content) is not None

    def extract_footprint_name(self, content: str) -> Optional[str]:
        """Extract footprint name from content and clean it."""
        if not self.validate_footprint_content(content):
            return None

        # Extract module/footprint name - support both formats
        match = re.search(r'\((module|footprint)\s+"([^"]*)"', content)
        if match:
            name = match.group(2)  # group(1) is module/footprint, group(2) is the name
            if name.strip():
                return self.clean_name(name)

        return None

    def clean_name(self, name: str) -> str:
        """Clean footprint name by removing invalid characters."""
        invalid = '<>:"/\\|?* '
        name = name.strip()
        for char in invalid:
            name = name.replace(char, "_")
        return name

    def extract_model_info(self, footprint_content: str) -> Optional[str]:
        """Extract model filename from footprint content."""
        match = re.search(r'\(model\s+"([^"]*)"', footprint_content)
        if match:
            model_path = match.group(1)
            return Path(model_path).name
        return None

    def has_model(self, footprint_content: str) -> bool:
        """Check if footprint has a model defined."""
        return re.search(r'\(model\s+"[^"]*"', footprint_content) is not None

    def update_model_path(self, footprint_content: str, new_model_path: str) -> str:
        """Simply replace the model path, leave everything else untouched."""
        pattern = re.compile(r'(\(model\s+)"[^"]*"')

        def replace_path(match):
            return f'{match.group(1)}"{new_model_path}"'

        return pattern.sub(replace_path, footprint_content)

    def add_model(self, footprint_content: str, model_path: str) -> str:
        """Add model block before the last closing parenthesis."""
        model_block = f'\t(model "{model_path}"\n\t\t(offset\n\t\t\t(xyz 0 0 0)\n\t\t)\n\t\t(scale\n\t\t\t(xyz 1 1 1)\n\t\t)\n\t\t(rotate\n\t\t\t(xyz 0 0 0)\n\t\t)\n\t)'

        # Find last closing parenthesis
        content = footprint_content.rstrip()
        if content.endswith(")"):
            return content[:-1] + f"\n{model_block}\n)"
        else:
            return footprint_content + f"\n{model_block}"

    def update_or_add_model(self, footprint_content: str, model_path: str) -> str:
        """Update existing model path or add new model to footprint."""
        if self.has_model(footprint_content):
            return self.update_model_path(footprint_content, model_path)
        else:
            return self.add_model(footprint_content, model_path)


if __name__ == "__main__":
    parser = FootprintModelParser()

    # Test validation
    valid_content = """(footprint "Test" (layer F.Cu)
  (pad 1 smd rect (at 0 0) (size 1 1) (layers F.Cu F.Paste F.Mask))
)"""

    invalid_content = """This is not a footprint file"""

    print("=== Test: Validation ===")
    print(f"Valid content: {parser.validate_footprint_content(valid_content)}")
    print(f"Invalid content: {parser.validate_footprint_content(invalid_content)}")
    print(f"Extract name: {parser.extract_footprint_name(valid_content)}")

    # Test with existing model
    content_with_model = """(footprint "Test" (layer F.Cu)
  (pad 1 smd rect (at 0 0) (size 1 1) (layers F.Cu F.Paste F.Mask))
  (model "${KICAD_3RD_PARTY}/old.3dshapes/old_model.step"    
        (offset
            (xyz 0 0 0)
        )
        (scale
            (xyz 1 1 1)
        )
        (rotate
            (xyz 0 0 0)
        )
  )
)"""

    print("\n=== Test: Update existing model path ===")
    new_path = "${KICAD_3RD_PARTY}/Samacsys.3dshapes/new_model.step"
    result = parser.update_or_add_model(content_with_model, new_path)
    print(result)
