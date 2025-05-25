import subprocess
import logging
import shutil


class kicad_cli:

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.kicad_cmd = self._find_kicad_cli()

    def _find_kicad_cli(self):
        """Find KiCad CLI command across different platforms"""
        possible_commands = ["kicad-cli", "kicad-cli.exe"]
        for cmd in possible_commands:
            if shutil.which(cmd):
                return cmd
        return "kicad-cli"  # fallback to original

    def run_kicad_cli(self, command):
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

    def exists(self):
        def version_to_tuple(version_str):
            try:
                return tuple(map(int, version_str.split("-")[0].split(".")))
            except (ValueError, AttributeError) as e:
                self.logger.error(f"Version extraction error '{version_str}': {e}")
                return (0, 0, 0)

        try:
            result = subprocess.run(
                [self.kicad_cmd, "--version"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10,
            )
            version = result.stdout.strip()
            min_version = "8.0.4"
            kicad_vers = version_to_tuple(version)

            if not kicad_vers or kicad_vers < version_to_tuple(min_version):
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

    def upgrade_sym_lib(self, input_file, output_file):
        return self.run_kicad_cli(["sym", "upgrade", input_file, "-o", output_file])

    def upgrade_footprint_lib(self, pretty_folder):
        return self.run_kicad_cli(["fp", "upgrade", pretty_folder])


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    cli = kicad_cli()
    if cli.exists():
        input_file = "UltraLibrarian_kicad_sym.kicad_sym"
        output_file = "UltraLibrarian.kicad_sym"

        cli.upgrade_sym_lib(input_file, output_file)
        cli.upgrade_footprint_lib("test.pretty")
