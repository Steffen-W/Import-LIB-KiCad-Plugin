import os.path
import json
import configparser
from pathlib import Path


class filehandler:
    def __init__(self, path):
        self.path = ""
        self.filelist = []
        self.change_path(path)

    def change_path(self, newpath):
        if not os.path.isdir(newpath):
            newpath = "."
        if newpath != self.path:
            self.filelist = []
        self.path = newpath

    def GetNewFiles(self, path):
        if path != self.path:
            self.change_path(path)

        filelist = os.listdir(self.path)
        filelist.sort()
        newFiles = []
        for i in filelist:
            if i not in self.filelist and i.endswith(".zip"):
                pathtemp = os.path.join(self.path, i)
                # the file is less than 50 MB and larger 1kB
                if (os.path.getsize(pathtemp) < 1000 * 1000 * 50) and (
                    os.path.getsize(pathtemp) > 1000
                ):
                    newFiles.append(pathtemp)
                    self.filelist.append(i)
        return newFiles


class config_handler:
    def __init__(self, config_path):
        self.config = configparser.ConfigParser()
        self.config_path = config_path
        self.config_is_set = False
        try:
            self.config.read(self.config_path)
            self.config["config"]["SRC_PATH"]  # only for check
            self.config["config"]["DEST_PATH"]  # only for check
            self.config_is_set = True
        except:
            self.print("An exception occurred during import " + self.config_path)
            self.config = configparser.ConfigParser()
            self.config.add_section("config")
            self.config.set("config", "SRC_PATH", "")
            self.config.set("config", "DEST_PATH", "")

        if self.config["config"]["SRC_PATH"] == "":
            self.config["config"]["SRC_PATH"] = str(Path.home() / "Downloads")
        if self.config["config"]["DEST_PATH"] == "":
            self.config["config"]["DEST_PATH"] = str(Path.home() / "KiCad")
            self.config_is_set = False

    def get_SRC_PATH(self):
        return self.config["config"]["SRC_PATH"]

    def set_SRC_PATH(self, var):
        self.config["config"]["SRC_PATH"] = var
        self.save_config()

    def get_DEST_PATH(self):
        return self.config["config"]["DEST_PATH"]

    def set_DEST_PATH(self, var):
        self.config["config"]["DEST_PATH"] = var
        self.save_config()

    def save_config(self):
        with open(self.config_path, "w") as configfile:
            self.config.write(configfile)

    def print(self, text):
        print(text)


class KiCad_Settings:
    def __init__(self, SettingPath):
        self.SettingPath = SettingPath

    def get_sym_table(self):
        path = os.path.join(self.SettingPath, "sym-lib-table")
        return self.__parse_table__(path)

    def set_sym_table(self, libname: str, libpath: str):
        path = os.path.join(self.SettingPath, "sym-lib-table")
        self.__add_entry_sexp__(path, name=libname, uri=libpath)

    def get_lib_table(self):
        path = os.path.join(self.SettingPath, "fp-lib-table")
        return self.__parse_table__(path)

    def set_lib_table_entry(self, libname: str):
        path = os.path.join(self.SettingPath, "fp-lib-table")
        uri_lib = "${KICAD_3RD_PARTY}/" + libname + ".pretty"
        self.__add_entry_sexp__(path, name=libname, uri=uri_lib)

    def __parse_table__(self, path):
        with open(path, "r") as file:
            data = file.read()

        def get_value(line, key):
            start = line.find("(" + key)
            if start == -1:
                return None
            start = line.find("(" + key)
            end = line.find(")", start)
            value = line[start + len(key) + 2 : end].strip('"')
            return value

        entries = {}
        lines = data.split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("(lib"):
                entry = {}
                entry["name"] = get_value(line, "name")
                entry["type"] = get_value(line, "type")
                entry["uri"] = get_value(line, "uri")
                entry["options"] = get_value(line, "options")
                entry["descr"] = get_value(line, "descr")
                entries[entry["name"]] = entry
        return entries

    def __add_entry_sexp__(
        self,
        path,
        name="Snapeda",
        uri="${KICAD_3RD_PARTY}/Snapeda.pretty",
        type="KiCad",
        options="",
        descr="",
    ):
        entries = self.__parse_table__(path)

        if name in entries:
            raise ValueError(f"Entry with the name '{name}' already exists.")

        # New entry
        new_entry = f'  (lib (name "{name}")(type "{type}")(uri "{uri}")(options "{options}")(descr "{descr}"))\n'

        with open(path, "r") as file:
            data = file.readlines()

        # Insert the new entry before the last bracket character
        insert_index = len(data) - 1
        data.insert(insert_index, new_entry)

        with open(path, "w") as file:
            file.writelines(data)

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
        FootprintLibs = self.get_lib_table()
        temp_path = "${KICAD_3RD_PARTY}/" + SearchLib + ".pretty"
        if SearchLib in FootprintLibs:
            if not FootprintLibs[SearchLib]["uri"] == temp_path:
                msg += (
                    "\n"
                    + SearchLib
                    + " in the Footprint Libraries is not imported correctly."
                )
                msg += "\nYou have to import the library '" + SearchLib
                msg += "' with the path '" + temp_path + "' in Footprint Libraries."
                if add_if_possible:
                    msg += "\nThe entry must either be corrected manually or deleted."
                    # self.set_lib_table_entry(SearchLib) # TODO
        else:
            msg += "\n" + SearchLib + " is not in the Footprint Libraries."
            if add_if_possible:
                self.set_lib_table_entry(SearchLib)
                msg += "\nThe library '" + SearchLib
                msg += " has been successfully added."
                msg += "\n##### A restart of KiCad is necessary. #####"
            else:
                msg += "\nYou have to import the library '" + SearchLib
                msg += "' with the path '" + temp_path
                msg += "' in the Footprint Libraries or select the automatic option."

        return msg

    def check_symbollib(self, SearchLib: str, add_if_possible: bool = True):
        msg = ""
        SearchLib_name = SearchLib.split("_")[0]

        SymbolLibs = self.get_sym_table()
        temp_path = "${KICAD_3RD_PARTY}/" + SearchLib
        SymbolLibsUri = [SymbolLibs[lib]["uri"] for lib in SymbolLibs]

        if not temp_path in SymbolLibsUri:
            msg += "\n'" + temp_path + "' is not imported into the Symbol Libraries."
            if add_if_possible:
                if SearchLib_name not in SymbolLibs:
                    self.set_sym_table(SearchLib_name, temp_path)
                    msg += "\nThe library '" + SearchLib
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
                else:
                    msg += "\nChange the entry or select the automatic option."
        else:
            msg += "\nKICAD_3RD_PARTY" + " is not defined in Environment Variables."
            if add_if_possible:
                setup_kicad_common()
            else:
                msg += "\nYou must add them manually or select the automatic option."

        return msg


if __name__ == "__main__":
    import pcbnew

    Manager = pcbnew.SETTINGS_MANAGER()
    Setting = KiCad_Settings(Manager.GetUserSettingsPath())

    SearchLib = "Samacsys"
    LocalLibFolder = "~/KiCad"

    Setting.check_footprintlib(SearchLib)
    Setting.check_symbollib(SearchLib)
    Setting.check_GlobalVar(SearchLib)
