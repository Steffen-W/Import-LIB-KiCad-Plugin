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

    def get_lib_table(self):
        path = os.path.join(self.SettingPath, "fp-lib-table")
        return self.__parse_table__(path)

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

    def get_kicad_json(self):
        path = os.path.join(self.SettingPath, "kicad.json")

        with open(path) as json_data:
            data = json.load(json_data)

        return data

    def get_kicad_common(self):
        path = os.path.join(self.SettingPath, "kicad_common.json")

        with open(path) as json_data:
            data = json.load(json_data)

        return data

    def get_kicad_GlobalVars(self):
        KiCadjson = self.get_kicad_common()
        return KiCadjson["environment"]["vars"]

    def check_footprintlib(self, SearchLib):
        msg = ""
        FootprintLibs = self.get_lib_table()
        temp_path = "${KICAD_3RD_PARTY}/" + SearchLib + ".pretty"
        if SearchLib in FootprintLibs:
            # print(footprintLibs[SearchLib]["uri"])
            if not FootprintLibs[SearchLib]["uri"] == temp_path:
                msg += (
                    "\n"
                    + SearchLib
                    + " in the Footprint Libraries is not imported correctly."
                )
                msg += "\nYou have to import the library '" + SearchLib
                msg += "' with the path '" + temp_path + "' in Footprint Libraries."
        else:
            msg += "\n" + SearchLib + " is not in the Footprint Libraries."
            msg += "\nYou have to import the library '" + SearchLib
            msg += "' with the path '" + temp_path + "' in the Footprint Libraries."
        return msg

    def check_symbollib(self, SearchLib):
        msg = ""
        SymbolLibs = self.get_sym_table()
        temp_path = "${KICAD_3RD_PARTY}/" + SearchLib
        SymbolLibsUri = [SymbolLibs[lib]["uri"] for lib in SymbolLibs]
        if not temp_path in SymbolLibsUri:
            msg += "\n'" + temp_path + "' is not imported into the Symbol Libraries."
        return msg

    def check_GlobalVar(self, LocalLibFolder):
        msg = ""
        GlobalVars = self.get_kicad_GlobalVars()
        if GlobalVars and "KICAD_3RD_PARTY" in GlobalVars:
            # print("KICAD_3RD_PARTY", GlobalVars["KICAD_3RD_PARTY"])
            if not GlobalVars["KICAD_3RD_PARTY"] == LocalLibFolder:
                msg += "\nKICAD_3RD_PARTY is defined as '"
                msg += GlobalVars["KICAD_3RD_PARTY"]
                msg += "' and not '" + LocalLibFolder + "'."
        else:
            msg += "\nKICAD_3RD_PARTY" + " is not defined in Environment Variables."
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
