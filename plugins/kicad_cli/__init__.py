import subprocess
import logging
import shutil
from typing import Optional, List, Tuple


class kicad_cli:
    def __init__(self) -> None:
        """Initialize the KiCad CLI wrapper with logger and command discovery."""
        self.logger: logging.Logger = logging.getLogger(__name__)
        self.kicad_cmd: str = self._find_kicad_cli()

    def _find_kicad_cli(self) -> str:
        """Find KiCad CLI command across different platforms."""
        possible_commands: List[str] = ["kicad-cli", "kicad-cli.exe"]
        for cmd in possible_commands:
            if shutil.which(cmd):
                return cmd
        return "kicad-cli"  # fallback to original

    def run_kicad_cli(self, command: List[str]) -> Optional[bool]:
        """Execute a KiCad CLI command with error handling and timeout."""
        try:
            result = subprocess.run(
                [self.kicad_cmd] + command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30,
            )
            return True
        except subprocess.TimeoutExpired:
            self.logger.error(
                f"Timeout: Command took too long: {' '.join([self.kicad_cmd] + command)}"
            )
            return None
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Command failed: {' '.join([self.kicad_cmd] + command)}")
            self.logger.error(f"Error: {e.stderr}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error running command: {e}")
            return None

    def version_to_tuple(self, version_str: str) -> Tuple[int, int, int]:
        """Convert a version string like '8.0.4' or '8.0.4-rc1' to tuple."""
        try:
            clean_version: str = version_str.split("-")[0]
            parts: List[str] = clean_version.split(".")
            # Ensure we have at least 3 parts
            while len(parts) < 3:
                parts.append("0")
            return (int(parts[0]), int(parts[1]), int(parts[2]))
        except (ValueError, AttributeError, TypeError, IndexError):
            return (0, 0, 0)

    def exists(self) -> bool:
        """Check if KiCad CLI exists and meets minimum version requirements."""
        try:
            result = subprocess.run(
                [self.kicad_cmd, "--version"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10,
            )
            version: str = result.stdout.strip()
            min_version: str = "8.0.4"
            kicad_vers: Tuple[int, int, int] = self.version_to_tuple(version)

            if not kicad_vers or kicad_vers < self.version_to_tuple(min_version):
                self.logger.warning(f"KiCad Version: {version}")
                self.logger.warning(f"Minimum required KiCad version is: {min_version}")
                return False
            else:
                return True

        except subprocess.TimeoutExpired:
            self.logger.error("Timeout checking KiCad version")
            return False
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.logger.error("kicad-cli does not exist or is not accessible")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error checking KiCad: {e}")
            return False

    def upgrade_sym_lib(self, input_file: str, output_file: str) -> Optional[bool]:
            """Upgrade a KiCad symbol library file to current format."""
            if input_file == output_file:
                # If input and output are the same, omit -o parameter to avoid conflict
                return self.run_kicad_cli(["sym", "upgrade", input_file])
            else:
                return self.run_kicad_cli(["sym", "upgrade", input_file, "-o", output_file])

    def upgrade_footprint_lib(self, pretty_folder: str) -> Optional[bool]:
        """Upgrade a KiCad footprint library folder to current format."""
        return self.run_kicad_cli(["fp", "upgrade", pretty_folder])


if __name__ == "__main__":
    """Main entry point for the KiCad CLI wrapper script."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    cli: kicad_cli = kicad_cli()
    if cli.exists():
        input_file: str = "UltraLibrarian_kicad_sym.kicad_sym"
        output_file: str = "UltraLibrarian.kicad_sym"
        cli.upgrade_sym_lib(input_file, output_file)
        cli.upgrade_footprint_lib("test.pretty")
