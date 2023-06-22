import configparser
import os
from pathlib import Path


class filehandler():
    def __init__(self, path):
        self.path = ''
        self.filelist = []
        self.change_path(path)

    def change_path(self, newpath):
        if not os.path.isdir(newpath):
            newpath = '.'
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
            if i not in self.filelist and i.endswith('.zip'):
                pathtemp = os.path.join(self.path, i)
                # the file is less than 10 MB and larger 1kB
                if (os.path.getsize(pathtemp) < 1000*1000*10) and (os.path.getsize(pathtemp) > 1000):
                    newFiles.append(pathtemp)
                    self.filelist.append(i)
        return newFiles


class config_handler():
    def __init__(self, config_path):
        self.config = configparser.ConfigParser()
        self.config_path = config_path
        try:
            self.config.read(self.config_path)
            self.config['config']['SRC_PATH']  # only for check
            self.config['config']['DEST_PATH']  # only for check
        except:
            self.print("An exception occurred during import " +
                       self.config_path)
            self.config = configparser.ConfigParser()
            self.config.add_section("config")
            self.config.set("config", "SRC_PATH", "")
            self.config.set("config", "DEST_PATH", "")

        if self.config['config']['SRC_PATH'] == "":
            self.config['config']['SRC_PATH'] = str(Path.home() / 'Downloads')
        if self.config['config']['DEST_PATH'] == "":
            self.config['config']['DEST_PATH'] = str(Path.home() / 'KiCad')

    def get_SRC_PATH(self):
        return self.config['config']['SRC_PATH']

    def set_SRC_PATH(self, var):
        self.config['config']['SRC_PATH'] = var
        self.save_config()

    def get_DEST_PATH(self):
        return self.config['config']['DEST_PATH']

    def set_DEST_PATH(self, var):
        self.config['config']['DEST_PATH'] = var
        self.save_config()

    def save_config(self):
        with open(self.config_path, 'w') as configfile:
            self.config.write(configfile)

    def print(self, text):
        print(text)
