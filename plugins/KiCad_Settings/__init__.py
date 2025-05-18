import os
import json
import re
from kiutils.libraries import LibTable, Library


class KiCad_Settings:
    def __init__(self, SettingPath):
        self.SettingPath = SettingPath

    def get_sym_table(self):
        path = os.path.join(self.SettingPath, "sym-lib-table")
        sym_table = LibTable.from_file(path)
        # Convert libraries to dictionaries
        return [
            {
                "name": lib.name,
                "type": lib.type,
                "uri": lib.uri,
                "options": lib.options,
                "descr": lib.description,
            }
            for lib in sym_table.libs
        ]

    def set_sym_table(self, libname: str, libpath: str):
        path = os.path.join(self.SettingPath, "sym-lib-table")
        sym_table = LibTable.from_file(path)

        # Check if library already exists
        for lib in sym_table.libs:
            if lib.name == libname:
                raise ValueError(f"Entry with the name '{libname}' already exists.")

        # Create new library and add it to the table
        new_lib = Library(
            name=libname, type="KiCad", uri=libpath, options="", description=""
        )
        sym_table.libs.append(new_lib)
        sym_table.to_file(path)

    def sym_table_change_entry(self, old_uri, new_uri):
        path = os.path.join(self.SettingPath, "sym-lib-table")
        sym_table = LibTable.from_file(path)

        uri_found = False
        for lib in sym_table.libs:
            if lib.uri == old_uri:
                lib.uri = new_uri
                uri_found = True
                break

        if not uri_found:
            raise ValueError(f"URI '{old_uri}' not found in the file.")

        sym_table.to_file(path)

    def get_lib_table(self):
        path = os.path.join(self.SettingPath, "fp-lib-table")
        fp_table = LibTable.from_file(path)
        # Convert libraries to dictionaries
        return [
            {
                "name": lib.name,
                "type": lib.type,
                "uri": lib.uri,
                "options": lib.options,
                "descr": lib.description,
            }
            for lib in fp_table.libs
        ]

    def set_lib_table_entry(self, libname: str):
        path = os.path.join(self.SettingPath, "fp-lib-table")
        fp_table = LibTable.from_file(path)

        # Check if library already exists
        for lib in fp_table.libs:
            if lib.name == libname:
                raise ValueError(f"Entry with the name '{libname}' already exists.")

        uri_lib = "${KICAD_3RD_PARTY}/" + libname + ".pretty"
        new_lib = Library(
            name=libname, type="KiCad", uri=uri_lib, options="", description=""
        )
        fp_table.libs.append(new_lib)
        fp_table.to_file(path)

    def get_kicad_json(self):
        path = os.path.join(self.SettingPath, "kicad.json")
        with open(path) as json_data:
            data = json.load(json_data)
        return data

    def set_kicad_json(self, kicad_json):
        path = os.path.join(self.SettingPath, "kicad.json")
        with open(path, "w") as file:
            json.dump(kicad_json, file, indent=2)

    def get_kicad_common(self):
        path = os.path.join(self.SettingPath, "kicad_common.json")
        with open(path) as json_data:
            data = json.load(json_data)
        return data

    def set_kicad_common(self, kicad_common):
        path = os.path.join(self.SettingPath, "kicad_common.json")
        with open(path, "w") as file:
            json.dump(kicad_common, file, indent=2)

    def get_kicad_GlobalVars(self):
        KiCadjson = self.get_kicad_common()
        return KiCadjson["environment"]["vars"]

    def check_footprintlib(self, SearchLib, add_if_possible=True):
        msg = ""
        FootprintTable = self.get_lib_table()
        FootprintLibs = {lib["name"]: lib for lib in FootprintTable}

        temp_path = "${KICAD_3RD_PARTY}/" + SearchLib + ".pretty"
        if SearchLib in FootprintLibs:
            if not FootprintLibs[SearchLib]["uri"] == temp_path:
                msg += "\n" + SearchLib
                msg += " in the Footprint Libraries is not imported correctly."
                msg += "\nYou have to import the library " + SearchLib
                msg += "' with the path '" + temp_path + "' in Footprint Libraries."
                if add_if_possible:
                    msg += "\nThe entry must either be corrected manually or deleted."
                    # self.set_lib_table_entry(SearchLib) # TODO
        else:
            msg += "\n" + SearchLib + " is not in the Footprint Libraries."
            if add_if_possible:
                self.set_lib_table_entry(SearchLib)
                msg += "\nThe library " + SearchLib
                msg += " has been successfully added."
                msg += "\n##### A restart of KiCad is necessary. #####"
            else:
                msg += "\nYou have to import the library " + SearchLib
                msg += "' with the path '" + temp_path
                msg += "' in the Footprint Libraries or select the automatic option."

        return msg

    def check_symbollib(self, SearchLib: str, add_if_possible: bool = True):
        msg = ""
        SearchLib_name = SearchLib.split(".")[0]
        SearchLib_name_short = SearchLib_name.split("_")[0]

        SymbolTable = self.get_sym_table()
        SymbolLibs = {lib["name"]: lib for lib in SymbolTable}
        SymbolLibsUri = {lib["uri"]: lib for lib in SymbolTable}

        temp_path = "${KICAD_3RD_PARTY}/" + SearchLib

        if temp_path not in SymbolLibsUri:
            msg += "\n'" + temp_path + "' is not imported into the Symbol Libraries."
            if add_if_possible:
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
            else:
                msg += "\nYou must add them manually or select the automatic option."

        return msg

    def check_GlobalVar(self, LocalLibFolder, add_if_possible=True):
        msg = ""
        GlobalVars = self.get_kicad_GlobalVars()

        def setup_kicad_common():
            kicad_common = self.get_kicad_common()
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
            else:
                msg += "\nYou must add them manually or select the automatic option."

        return msg

    def prepare_library_migration(self, libs_to_migrate):
        """Prepares library migration by analyzing which symbol libraries need to be updated

        Args:
            libs_to_migrate (list): List of tuples with (old_lib, new_lib) format

        Returns:
            tuple: (message, libraries_to_rename)
                - message: Information about the changes to be made
                - libraries_to_rename: List of dictionaries with library renaming information
        """
        if not libs_to_migrate or len(libs_to_migrate) <= 0:
            return "Error in prepare_library_migration()", []

        SymbolTable = self.get_sym_table()
        SymbolLibsUri = {lib["uri"]: lib for lib in SymbolTable}
        libraries_to_rename = []

        def lib_entry(lib):
            return "${KICAD_3RD_PARTY}/" + lib

        msg = ""
        for old_lib, new_lib in libs_to_migrate:
            if new_lib.endswith(".blk"):
                msg += f"\n{old_lib} rename to {new_lib}"
            else:
                msg += f"\n{old_lib} convert to {new_lib}"

            # Check if this library is in the symbol table
            if lib_entry(old_lib) in SymbolLibsUri:
                entry = SymbolLibsUri[lib_entry(old_lib)]
                tmp = {
                    "oldURI": entry["uri"],
                    "newURI": lib_entry(new_lib),
                    "name": entry["name"],
                }
                libraries_to_rename.append(tmp)

        # Create message about symbol library changes
        msg_lib = ""
        if len(libraries_to_rename):
            msg_lib += "The following changes must be made to the list of imported Symbol libs:\n"
            for tmp in libraries_to_rename:
                msg_lib += f"\n{tmp['name']} : {tmp['oldURI']} \n-> {tmp['newURI']}"
            msg_lib += "\n\n"
            msg_lib += "It is necessary to adjust the settings of the imported symbol libraries in KiCad."

        msg += "\n\n" + msg_lib
        msg += "\n\nBackup files are also created automatically. "
        msg += "These are named '*.blk'.\nShould the changes be applied?"

        return msg, libraries_to_rename

    def execute_library_migration(self, libraries_to_rename):
        """Executes the library migration by changing entries in the symbol table

        Args:
            libraries_to_rename (list): List of dictionaries with library renaming information

        Returns:
            str: Message about the changes made
        """
        if not libraries_to_rename or len(libraries_to_rename) <= 0:
            return "No libraries to migrate."

        msg = ""
        for lib in libraries_to_rename:
            msg += f"\n{lib['name']} : {lib['oldURI']} \n-> {lib['newURI']}"
            self.sym_table_change_entry(lib["oldURI"], lib["newURI"])

        msg += "\n\nA restart of KiCad is necessary to apply all changes."
        return msg
