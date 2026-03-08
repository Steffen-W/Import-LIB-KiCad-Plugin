import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, cast

current_dir = Path(__file__).resolve().parent
kiutils_src = current_dir.parent / "kiutils" / "src"
if str(kiutils_src) not in sys.path:
    sys.path.insert(0, str(kiutils_src))

from kiutils.libraries import Library, LibTable  # noqa: E402


class KiCad_Settings:
    def __init__(
        self, SettingPath: str, path_prefix: str = "${KICAD_3RD_PARTY}"
    ) -> None:
        self.logger = logging.getLogger(__name__)
        self.path_prefix = path_prefix
        base_path = Path(SettingPath)

        if (
            not (base_path / "sym-lib-table").exists()
            and not (base_path / "fp-lib-table").exists()
        ):
            version_dirs = [
                d
                for d in base_path.iterdir()
                if d.is_dir() and d.name.replace(".", "").isdigit()
            ]

            if version_dirs:
                # Sort by version and take the highest
                latest_version = max(
                    version_dirs,
                    key=lambda x: tuple(
                        int(p) for p in x.name.split(".") if p.isdigit()
                    ),
                )
                self.SettingPath = str(latest_version)
                self.logger.info(
                    f"Auto-detected KiCad version directory: {self.SettingPath}"
                )
            else:
                self.SettingPath = SettingPath
        else:
            self.SettingPath = SettingPath

        self.logger.info(f"Initializing KiCad_Settings with path: {SettingPath}")

    def get_sym_table(self) -> List[Dict[str, str]]:
        path = os.path.join(self.SettingPath, "sym-lib-table")
        self.logger.debug(f"Attempting to read symbol library table from: {path}")

        try:
            if not os.path.exists(path):
                self.logger.info(
                    f"Symbol library table not found, creating empty table: {path}"
                )
                empty_table = LibTable()
                empty_table.to_file(path)

            sym_table = LibTable.from_file(path)
            self.logger.info(
                f"Successfully loaded symbol library table with {len(sym_table.libs)} entries"
            )

            # Convert libraries to dictionaries
            result = [
                {
                    "name": lib.name,
                    "type": lib.type,
                    "uri": lib.uri,
                    "options": lib.options,
                    "descr": lib.description,
                }
                for lib in sym_table.libs
            ]
            return result

        except FileNotFoundError:
            self.logger.warning(f"Symbol library table not found: {path}")
            return []
        except Exception as e:
            self.logger.error(f"Failed to parse symbol library table from {path}: {e}")
            return []

    def set_sym_table(self, libname: str, libpath: str) -> None:
        path = os.path.join(self.SettingPath, "sym-lib-table")
        self.logger.debug(
            f"Adding symbol library '{libname}' with path '{libpath}' to {path}"
        )

        try:
            if not os.path.exists(path):
                self.logger.info(
                    f"Symbol library table not found, creating empty table: {path}"
                )
                empty_table = LibTable()
                empty_table.to_file(path)

            sym_table = LibTable.from_file(path)

            # Check if library already exists
            for lib in sym_table.libs:
                if lib.name == libname:
                    self.logger.error(
                        f"Symbol library '{libname}' already exists in table"
                    )
                    raise ValueError(f"Entry with the name '{libname}' already exists.")

            # Create new library and add it to the table
            new_lib = Library(
                name=libname, type="KiCad", uri=libpath, options="", description=""
            )
            sym_table.libs.append(new_lib)
            sym_table.to_file(path)

            self.logger.info(f"Successfully added symbol library '{libname}' to table")

        except Exception as e:
            self.logger.error(f"Failed to add symbol library '{libname}': {e}")
            raise

    def sym_table_change_entry(self, old_uri: str, new_uri: str) -> None:
        path = os.path.join(self.SettingPath, "sym-lib-table")
        self.logger.debug(
            f"Changing symbol library URI from '{old_uri}' to '{new_uri}'"
        )

        try:
            sym_table = LibTable.from_file(path)

            uri_found = False
            for lib in sym_table.libs:
                if lib.uri == old_uri:
                    lib.uri = new_uri
                    uri_found = True
                    self.logger.info(
                        f"Changed URI for library '{lib.name}' from '{old_uri}' to '{new_uri}'"
                    )
                    break

            if not uri_found:
                self.logger.error(f"URI '{old_uri}' not found in symbol library table")
                raise ValueError(f"URI '{old_uri}' not found in the file.")

            sym_table.to_file(path)
            self.logger.info("Successfully updated symbol library table")

        except Exception as e:
            self.logger.error(f"Failed to change symbol library URI: {e}")
            raise

    def get_lib_table(self) -> List[Dict[str, str]]:
        path = os.path.join(self.SettingPath, "fp-lib-table")
        self.logger.debug(f"Attempting to read footprint library table from: {path}")

        try:
            if not os.path.exists(path):
                self.logger.info(
                    f"Footprint library table not found, creating empty table: {path}"
                )
                empty_table = LibTable()
                empty_table.to_file(path)

            fp_table = LibTable.from_file(path)
            self.logger.info(
                f"Successfully loaded footprint library table with {len(fp_table.libs)} entries"
            )

            # Convert libraries to dictionaries
            result = [
                {
                    "name": lib.name,
                    "type": lib.type,
                    "uri": lib.uri,
                    "options": lib.options,
                    "descr": lib.description,
                }
                for lib in fp_table.libs
            ]
            return result

        except FileNotFoundError:
            self.logger.warning(f"Footprint library table not found: {path}")
            return []
        except Exception as e:
            self.logger.error(
                f"Failed to parse footprint library table from {path}: {e}"
            )
            return []

    def set_lib_table_entry(self, libname: str) -> None:
        path = os.path.join(self.SettingPath, "fp-lib-table")
        self.logger.debug(f"Adding footprint library '{libname}' to {path}")

        try:
            if not os.path.exists(path):
                self.logger.info(
                    f"Footprint library table not found, creating empty table: {path}"
                )
                empty_table = LibTable()
                empty_table.to_file(path)

            fp_table = LibTable.from_file(path)

            # Check if library already exists
            for lib in fp_table.libs:
                if lib.name == libname:
                    self.logger.error(
                        f"Footprint library '{libname}' already exists in table"
                    )
                    raise ValueError(f"Entry with the name '{libname}' already exists.")

            uri_lib = self.path_prefix + "/" + libname + ".pretty"
            new_lib = Library(
                name=libname, type="KiCad", uri=uri_lib, options="", description=""
            )
            fp_table.libs.append(new_lib)
            fp_table.to_file(path)

            self.logger.info(
                f"Successfully added footprint library '{libname}' with URI '{uri_lib}'"
            )

        except Exception as e:
            self.logger.error(f"Failed to add footprint library '{libname}': {e}")
            raise

    def get_kicad_json(self) -> Dict[str, Any]:
        path = os.path.join(self.SettingPath, "kicad.json")
        self.logger.debug(f"Attempting to read KiCad JSON config from: {path}")

        try:
            with open(path) as json_data:
                data = json.load(json_data)
            self.logger.info("Successfully loaded KiCad JSON config")
            return cast(Dict[str, Any], data)

        except FileNotFoundError:
            self.logger.warning(f"KiCad JSON config not found: {path}")
            return {}
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in KiCad config file {path}: {e}")
            return {}
        except Exception as e:
            self.logger.error(f"Failed to read KiCad JSON config from {path}: {e}")
            return {}

    def set_kicad_json(self, kicad_json: Dict[str, Any]) -> None:
        path = os.path.join(self.SettingPath, "kicad.json")
        self.logger.debug(f"Writing KiCad JSON config to: {path}")

        try:
            with open(path, "w") as file:
                json.dump(kicad_json, file, indent=2)
            self.logger.info("Successfully wrote KiCad JSON config")

        except Exception as e:
            self.logger.error(f"Failed to write KiCad JSON config to {path}: {e}")
            raise

    def get_kicad_common(self) -> Dict[str, Any]:
        path = os.path.join(self.SettingPath, "kicad_common.json")
        self.logger.debug(f"Attempting to read KiCad common config from: {path}")

        try:
            with open(path) as json_data:
                data = json.load(json_data)
            self.logger.info("Successfully loaded KiCad common config")
            return cast(Dict[str, Any], data)

        except FileNotFoundError:
            self.logger.warning(f"KiCad common config not found: {path}")
            return {"environment": {"vars": {}}}
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in KiCad common config file {path}: {e}")
            return {"environment": {"vars": {}}}
        except Exception as e:
            self.logger.error(f"Failed to read KiCad common config from {path}: {e}")
            return {"environment": {"vars": {}}}

    def set_kicad_common(self, kicad_common: Dict[str, Any]) -> None:
        path = os.path.join(self.SettingPath, "kicad_common.json")
        self.logger.debug(f"Writing KiCad common config to: {path}")

        try:
            with open(path, "w") as file:
                json.dump(kicad_common, file, indent=2)
            self.logger.info("Successfully wrote KiCad common config")

        except Exception as e:
            self.logger.error(f"Failed to write KiCad common config to {path}: {e}")
            raise

    def get_kicad_GlobalVars(self) -> Dict[str, str]:
        self.logger.debug("Getting KiCad global variables")

        try:
            KiCadjson = self.get_kicad_common()
            global_vars = KiCadjson.get("environment", {}).get("vars", {})
            self.logger.info(f"Found {len(global_vars)} global variables")
            return cast(Dict[str, str], global_vars)

        except Exception as e:
            self.logger.error(f"Failed to get KiCad global variables: {e}")
            return {}

    def check_footprintlib(self, SearchLib: str, add_if_possible: bool = True) -> str:
        msg = ""
        try:
            FootprintTable = self.get_lib_table()
            FootprintLibs = {lib["name"]: lib for lib in FootprintTable}

            temp_path = self.path_prefix + "/" + SearchLib + ".pretty"
            if SearchLib in FootprintLibs:
                if not FootprintLibs[SearchLib]["uri"] == temp_path:
                    msg += "\n" + SearchLib
                    msg += " in the Footprint Libraries is not imported correctly."
                    msg += "\nYou have to import the library " + SearchLib
                    msg += "' with the path '" + temp_path + "' in Footprint Libraries."
                    if add_if_possible:
                        msg += (
                            "\nThe entry must either be corrected manually or deleted."
                        )
                        # self.set_lib_table_entry(SearchLib) # TODO
            else:
                msg += "\n" + SearchLib + " is not in the Footprint Libraries."
                if add_if_possible:
                    try:
                        self.set_lib_table_entry(SearchLib)
                        msg += "\nThe library " + SearchLib
                        msg += " has been successfully added."
                        msg += "\n##### A restart of KiCad is necessary. #####"
                    except Exception:
                        msg += "\nFailed to add library automatically."
                        msg += "\nPlease add the library manually following the steps in the README:"
                        msg += "\n  Preferences -> Manage Footprint Libraries -> Add entry:"
                        msg += "\n  Name: " + SearchLib.split(".")[0]
                        msg += "\n  Path: " + temp_path
                        msg += "\n  See: github.com/Steffen-W/Import-LIB-KiCad-Plugin#including-the-imported-libraries-in-kicad"
                else:
                    msg += "\nPlease add the library " + SearchLib + " manually:"
                    msg += "\n  Preferences -> Manage Footprint Libraries -> Add entry:"
                    msg += "\n  Name: " + SearchLib.split(".")[0]
                    msg += "\n  Path: " + temp_path
                    msg += "\n  Note: The automatic option may not work reliably."
                    msg += "\n  See: github.com/Steffen-W/Import-LIB-KiCad-Plugin#including-the-imported-libraries-in-kicad"
        except Exception:
            msg += f"\nError checking footprint library {SearchLib}."

        return msg

    def check_symbollib(self, SearchLib: str, add_if_possible: bool = True) -> str:
        msg = ""
        try:
            SearchLib_name = SearchLib.split(".")[0]
            SearchLib_name_short = SearchLib_name.split("_")[0]

            SymbolTable = self.get_sym_table()
            SymbolLibs = {lib["name"]: lib for lib in SymbolTable}
            SymbolLibsUri = {lib["uri"]: lib for lib in SymbolTable}

            temp_path = self.path_prefix + "/" + SearchLib

            if temp_path not in SymbolLibsUri:
                msg += (
                    "\n'" + temp_path + "' is not imported into the Symbol Libraries."
                )
                if add_if_possible:
                    try:
                        if SearchLib_name_short not in SymbolLibs:
                            self.set_sym_table(SearchLib_name_short, temp_path)
                            msg += "\nThe library " + SearchLib
                            msg += " has been successfully added."
                            msg += "\n##### A restart of KiCad is necessary. #####"
                        elif SearchLib_name not in SymbolLibs:
                            self.set_sym_table(SearchLib_name, temp_path)
                            msg += "\nThe library " + SearchLib
                            msg += " has been successfully added."
                            msg += "\n##### A restart of KiCad is necessary. #####"
                        else:
                            msg += "\nThe entry must either be corrected manually or deleted."
                            # self.set_sym_table(SearchLib_name, temp_path) # TODO
                    except Exception:
                        msg += "\nFailed to add symbol library automatically."
                        msg += "\nPlease add the library manually following the steps in the README:"
                        msg += (
                            "\n  Preferences -> Manage Symbol Libraries -> Add entry:"
                        )
                        msg += "\n  Name: " + SearchLib_name_short
                        msg += "\n  Path: " + temp_path
                        msg += "\n  See: github.com/Steffen-W/Import-LIB-KiCad-Plugin#including-the-imported-libraries-in-kicad"
                else:
                    msg += "\nPlease add the library manually:"
                    msg += "\n  Preferences -> Manage Symbol Libraries -> Add entry:"
                    msg += "\n  Name: " + SearchLib_name_short
                    msg += "\n  Path: " + temp_path
                    msg += "\n  Note: The automatic option may not work reliably."
                    msg += "\n  See: github.com/Steffen-W/Import-LIB-KiCad-Plugin#including-the-imported-libraries-in-kicad"
        except Exception:
            msg += f"\nError checking symbol library {SearchLib}."

        return msg

    def check_GlobalVar(self, LocalLibFolder: str, add_if_possible: bool = True) -> str:
        msg = ""
        GlobalVars = self.get_kicad_GlobalVars()

        def setup_kicad_common() -> None:
            kicad_common = self.get_kicad_common()
            # Ensure the nested structure exists
            if "environment" not in kicad_common:
                kicad_common["environment"] = {}
            if "vars" not in kicad_common["environment"]:
                kicad_common["environment"]["vars"] = {}

            kicad_common["environment"]["vars"]["KICAD_3RD_PARTY"] = LocalLibFolder
            self.set_kicad_common(kicad_common)

        if GlobalVars and "KICAD_3RD_PARTY" in GlobalVars:
            if not GlobalVars["KICAD_3RD_PARTY"] == LocalLibFolder:
                msg += "\nKICAD_3RD_PARTY is defined as '"
                msg += GlobalVars["KICAD_3RD_PARTY"]
                msg += "' and not '" + LocalLibFolder + "'."
                if add_if_possible:
                    setup_kicad_common()
                    msg += "\nThe entry was changed automatically."
                    msg += "\n##### A restart of KiCad is necessary. #####"
                else:
                    msg += "\nChange the entry or select the automatic option."
        else:
            msg += "\nKICAD_3RD_PARTY" + " is not defined in Environment Variables."
            if add_if_possible:
                setup_kicad_common()
                msg += "\nThe entry has been added successfully."
                msg += "\n##### A restart of KiCad is necessary. #####"
            else:
                msg += "\nYou must add them manually or select the automatic option."

        return msg
