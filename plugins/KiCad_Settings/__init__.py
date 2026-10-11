from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

current_dir = Path(__file__).resolve().parent
kiutils_src = current_dir.parent / "kiutils" / "src"
if str(kiutils_src) not in sys.path:
    sys.path.insert(0, str(kiutils_src))

from kiutils.libraries import Library, LibTable  # noqa: E402

README_SETUP_URL = (
    "github.com/Steffen-W/Import-LIB-KiCad-Plugin#including-the-imported-libraries-in-kicad"
)


def _manual_steps(dialog: str, name: str, path: str) -> str:
    return (
        f"\nPlease add the entry manually:"
        f"\n  Preferences -> {dialog} -> Add entry:"
        f"\n  Name: {name}"
        f"\n  Path: {path}"
        f"\n  See: {README_SETUP_URL}"
    )


class KiCad_Settings:
    """Read-only check of KiCad's library tables and environment variables."""

    def __init__(self, SettingPath: str, path_prefix: str = "${KICAD_3RD_PARTY}") -> None:
        self.logger = logging.getLogger(__name__)
        self.path_prefix = path_prefix
        base_path = Path(SettingPath)

        if not base_path.is_dir():
            raise NotADirectoryError(f"KiCad settings path is not a directory: {SettingPath}")

        if not (base_path / "sym-lib-table").exists() and not (base_path / "fp-lib-table").exists():
            try:
                version_dirs = [
                    d
                    for d in base_path.iterdir()
                    if d.is_dir() and d.name.replace(".", "").isdigit()
                ]
            except OSError as e:
                self.logger.warning(f"Could not scan settings path {SettingPath}: {e}")
                version_dirs = []

            if version_dirs:
                # Sort by version and take the highest
                latest_version = max(
                    version_dirs,
                    key=lambda x: tuple(int(p) for p in x.name.split(".") if p.isdigit()),
                )
                self.SettingPath = str(latest_version)
                self.logger.info(f"Auto-detected KiCad version directory: {self.SettingPath}")
            else:
                self.SettingPath = SettingPath
        else:
            self.SettingPath = SettingPath

        self.logger.info(f"Initializing KiCad_Settings with path: {SettingPath}")

    def _read_lib_table(self, filename: str) -> list[Library]:
        """Return the entries of a library table; a missing table has none."""
        path = os.path.join(self.SettingPath, filename)
        if not os.path.exists(path):
            return []
        libs: list[Library] = LibTable.from_file(path, encoding="utf-8").libs
        return libs

    def _read_environment_vars(self) -> dict[str, str]:
        """Return the user-defined path variables from kicad_common.json."""
        path = os.path.join(self.SettingPath, "kicad_common.json")
        try:
            with open(path, encoding="utf-8") as file:
                kicad_common = json.load(file)
        except FileNotFoundError:
            return {}
        env_vars: dict[str, str] = (kicad_common.get("environment") or {}).get("vars") or {}
        return env_vars

    def check_footprintlib(self, SearchLib: str) -> str:
        uri = f"{self.path_prefix}/{SearchLib}.pretty"
        try:
            libs = {lib.name: lib for lib in self._read_lib_table("fp-lib-table")}
        except Exception as e:
            self.logger.error(f"Failed to read footprint library table: {e}")
            return f"\nCould not read the footprint library table: {e}"

        lib = libs.get(SearchLib)
        if lib is None:
            return f"\n{SearchLib} is not in the Footprint Libraries." + _manual_steps(
                "Manage Footprint Libraries", SearchLib, uri
            )
        if lib.uri != uri:
            return (
                f"\n{SearchLib} in the Footprint Libraries points to '{lib.uri}' instead of "
                f"'{uri}'.\nThe entry must either be corrected manually or deleted."
            )
        return ""

    def check_symbollib(self, SearchLib: str) -> str:
        uri = f"{self.path_prefix}/{SearchLib}"
        try:
            libs = self._read_lib_table("sym-lib-table")
        except Exception as e:
            self.logger.error(f"Failed to read symbol library table: {e}")
            return f"\nCould not read the symbol library table: {e}"

        if any(lib.uri == uri for lib in libs):
            return ""

        msg = f"\n'{uri}' is not imported into the Symbol Libraries."
        full_name = SearchLib.split(".")[0]
        taken = {lib.name for lib in libs}
        name = next((n for n in (full_name.split("_")[0], full_name) if n not in taken), None)
        if name is None:
            return msg + "\nThe entry must either be corrected manually or deleted."
        return msg + _manual_steps("Manage Symbol Libraries", name, uri)

    def check_GlobalVar(self, LocalLibFolder: str) -> str:
        try:
            value = self._read_environment_vars().get("KICAD_3RD_PARTY")
        except Exception as e:
            self.logger.error(f"Failed to read KiCad environment variables: {e}")
            return f"\nCould not read the KiCad environment variables: {e}"

        if value is None:
            return "\nKICAD_3RD_PARTY is not defined in Environment Variables." + _manual_steps(
                "Configure Paths -> Environment Variables", "KICAD_3RD_PARTY", LocalLibFolder
            )
        if value != LocalLibFolder:
            return (
                f"\nKICAD_3RD_PARTY is defined as '{value}' and not '{LocalLibFolder}'."
                "\nChange the entry in Preferences -> Configure Paths -> Environment Variables."
            )
        return ""
