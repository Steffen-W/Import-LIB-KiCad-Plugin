import subprocess
import logging
import shutil
import os
from typing import Optional, List, Tuple
from dataclasses import dataclass


@dataclass
class CommandResult:
    """Detailed result information for KiCad CLI commands."""

    success: bool
    stdout: str
    stderr: str
    return_code: int
    message: str = ""


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
        return "kicad-cli"

    def run_kicad_cli(self, command: List[str]) -> CommandResult:
        """Execute a KiCad CLI command with detailed result information."""
        full_command = [self.kicad_cmd] + command
        self.logger.info(f"Executing: {' '.join(full_command)}")

        try:
            result = subprocess.run(
                full_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30,
            )

            success = result.returncode == 0
            if success:
                self.logger.info("Command completed successfully")
            else:
                self.logger.error(
                    f"Command failed with return code {result.returncode}"
                )

            return CommandResult(
                success=success,
                stdout=result.stdout,
                stderr=result.stderr,
                return_code=result.returncode,
                message=f"Command {'succeeded' if success else 'failed'}",
            )

        except subprocess.TimeoutExpired:
            error_msg = f"Timeout: Command took too long: {' '.join(full_command)}"
            self.logger.error(error_msg)
            return CommandResult(False, "", "Timeout expired", -1, error_msg)
        except FileNotFoundError:
            error_msg = f"KiCad CLI not found: {self.kicad_cmd}"
            self.logger.error(error_msg)
            return CommandResult(False, "", "Command not found", -1, error_msg)
        except Exception as e:
            error_msg = f"Unexpected error running command: {e}"
            self.logger.error(error_msg)
            return CommandResult(False, "", str(e), -1, error_msg)

    def version_to_tuple(self, version_str: str) -> Tuple[int, int, int]:
        """Convert a version string like '8.0.4' or '8.0.4-rc1' to tuple."""
        try:
            clean_version: str = version_str.split("-")[0]
            parts: List[str] = clean_version.split(".")
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

    def _is_valid_symbol_file(self, filepath: str) -> bool:
        """Check if file appears to be a valid KiCad symbol file."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read(100)
                return content.strip().startswith("(kicad_symbol_lib")
        except (IOError, UnicodeDecodeError):
            return False

    def _validate_upgrade_result(
        self, input_file: str, output_file: str, result: CommandResult
    ) -> CommandResult:
        """Validate that the upgrade operation was successful."""
        target_file = output_file if input_file != output_file else input_file

        if not os.path.exists(target_file):
            result.success = False
            result.message = f"Output file was not created: {target_file}"
            self.logger.error(result.message)
            return result

        if not self._is_valid_symbol_file(target_file):
            result.success = False
            result.message = (
                f"Output file is not a valid KiCad symbol file: {target_file}"
            )
            self.logger.error(result.message)
            return result

        output_text = (result.stdout + result.stderr).lower()
        success_indicators = ["successfully", "completed", "upgraded"]
        error_indicators = ["error", "failed", "cannot", "unable"]

        has_success = any(indicator in output_text for indicator in success_indicators)
        has_error = any(indicator in output_text for indicator in error_indicators)

        if has_error and not has_success:
            result.success = False
            result.message = "Error indicators found in command output"
            self.logger.warning(result.message)
        elif not has_success and result.success:
            result.message = "Command completed but no explicit success confirmation"
            self.logger.info(result.message)
        else:
            result.message = "Upgrade completed successfully"
            self.logger.info(result.message)

        return result

    def upgrade_sym_lib(
        self, input_file: str, output_file: str, force: bool = True
    ) -> CommandResult:
        """Upgrade a KiCad symbol library file to current format."""
        input_file = str(input_file)
        output_file = str(output_file)
        if not os.path.exists(input_file):
            error_msg = f"Input file does not exist: {input_file}"
            self.logger.error(error_msg)
            return CommandResult(False, "", error_msg, -1, error_msg)

        if not self._is_valid_symbol_file(input_file):
            error_msg = f"Input file is not a valid KiCad symbol file: {input_file}"
            self.logger.error(error_msg)
            return CommandResult(False, "", error_msg, -1, error_msg)

        backup_path = None
        if input_file == output_file:
            backup_path = f"{input_file}.backup"
            try:
                shutil.copy2(input_file, backup_path)
                self.logger.info(f"Created backup: {backup_path}")
            except Exception as e:
                error_msg = f"Failed to create backup: {e}"
                self.logger.error(error_msg)
                return CommandResult(False, "", str(e), -1, error_msg)

        try:
            if input_file == output_file:
                command = ["sym", "upgrade", input_file]
            else:
                command = ["sym", "upgrade", input_file, "-o", output_file]

            if force:
                command.append("--force")

            result = self.run_kicad_cli(command)

            if result.success:
                result = self._validate_upgrade_result(input_file, output_file, result)

            if result.success and backup_path and os.path.exists(backup_path):
                os.remove(backup_path)
                self.logger.info("Backup removed after successful upgrade")

            if not result.success and backup_path and os.path.exists(backup_path):
                try:
                    shutil.move(backup_path, input_file)
                    self.logger.info("Restored from backup after upgrade failure")
                except Exception as e:
                    self.logger.error(f"Failed to restore backup: {e}")

            return result

        except Exception as e:
            if backup_path and os.path.exists(backup_path):
                try:
                    shutil.move(backup_path, input_file)
                    self.logger.info("Restored from backup after exception")
                except Exception as restore_e:
                    self.logger.error(
                        f"Failed to restore backup after exception: {restore_e}"
                    )

            error_msg = f"Unexpected error during upgrade: {e}"
            self.logger.error(error_msg)
            return CommandResult(False, "", str(e), -1, error_msg)

    def upgrade_footprint_lib(
        self,
        pretty_folder: str,
        output_folder: Optional[str] = None,
        force: bool = False,
    ) -> CommandResult:
        """Upgrade a KiCad footprint library folder to current format."""
        pretty_folder = str(pretty_folder)

        if not os.path.exists(pretty_folder):
            error_msg = f"Footprint folder does not exist: {pretty_folder}"
            self.logger.error(error_msg)
            return CommandResult(False, "", error_msg, -1, error_msg)

        if not os.path.isdir(pretty_folder):
            error_msg = f"Path is not a directory: {pretty_folder}"
            self.logger.error(error_msg)
            return CommandResult(False, "", error_msg, -1, error_msg)

        command = ["fp", "upgrade", pretty_folder]

        if output_folder is not None:
            output_folder = str(output_folder)
            command.extend(["-o", output_folder])

        if force:
            command.append("--force")

        result = self.run_kicad_cli(command)

        target_folder = output_folder if output_folder is not None else pretty_folder

        if result.success and not os.path.exists(target_folder):
            result.success = False
            result.message = (
                f"Footprint folder disappeared after upgrade: {target_folder}"
            )
            self.logger.error(result.message)
        elif result.success:
            upgrade_mode = (
                "to output folder" if output_folder is not None else "in-place"
            )
            result.message = (
                f"Footprint library upgrade completed successfully ({upgrade_mode})"
            )
            self.logger.info(result.message)

        return result


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    cli: kicad_cli = kicad_cli()

    if not cli.exists():
        print("KiCad CLI not found or version too old!")
        exit(1)

    input_file: str = "UltraLibrarian_kicad_sym.kicad_sym"
    output_file: str = "UltraLibrarian.kicad_sym"

    result = cli.upgrade_sym_lib(input_file, output_file)

    print(f"Symbol library upgrade: {'SUCCESS' if result.success else 'FAILED'}")
    print(f"Message: {result.message}")
    if not result.success:
        print(f"Error details: {result.stderr}")

    result2 = cli.upgrade_footprint_lib("test.pretty", force=True)

    print(f"Footprint library upgrade: {'SUCCESS' if result2.success else 'FAILED'}")
    print(f"Message: {result2.message}")
    if not result2.success:
        print(f"Error details: {result2.stderr}")
