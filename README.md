# Import-LIB-KiCad-Plugin ![icon](plugins/icon_small.png)

Assembles KiCad "legacy" format component libraries from downloaded
[Octopart](https://octopart.com/), [Samacsys](https://componentsearchengine.com/), [Ultralibrarian](https://app.ultralibrarian.com/search) and [Snapeda](https://www.snapeda.com/home/) zipfiles. Imports symbol, footprint, description and if available 3D file. Normally, when you select the imported symbol in KiCad 7, the appropriate footprint and the 3D file should also be linked. Provided, of course, that the libraries have been included as specified below. 

[![SC2 Video](doc/demo.gif)](https://youtu.be/cdOKDY-F4ZU)

## Warranty

**None. Zero. Zilch. Use at your own risk, and please be sure to use git or some other means of backing up/reverting changes caused by this script. This script will modify existing lib, dcm, footprint or 3D model files. It is your responsiblity to back them up or have a way to revert changes should you inadvertantly mess something up using this tool** 

## Installation

The easiest way to install is to open **KiCad** -> **Plugin And Content Manager**. Select ![icon](plugins/icon_small.png) **Import-LIB-KiCad-Plugin** in the Plugins tab, press **Install** and then **Apply Pending Changes**.

## Use of the application

![Screenshot_GUI](doc/Screenshot_GUI.png)

The libraries to import must be located in the folder specified as **Folder of the library** to import". After pressing Start, the libraries will be imported into the specified folder (**Library save location**). Provided that the paths have been [added correctly in KiCad](#including-the-imported-libraries-in-kicad), the parts can be used immediately in KiCad.

## Including the imported libraries in KiCad

**Preferences** -> **Configure paths** -> **Environment Variables** -> Add the following entry
|Name            |Path    |
|----------------|--------|
|KICAD_3RD_PARTY |**YourLibraryFolder**/KiCad |

**Preferences** -> **Manage Symbol Libraries** -> **Global Libraries** -> Add the following entries
|Active            |Visible           |Nickname       |Library Path                           | Library Format|
|------------------|------------------|---------------|---------------------------------------|---------------|
|:heavy_check_mark:|:heavy_check_mark:|Samacsys       |${KICAD_3RD_PARTY}/Samacsys.lib        | Legacy        |
|:heavy_check_mark:|:heavy_check_mark:|Snapeda        |${KICAD_3RD_PARTY}/Snapeda.lib         | Legacy        |
|:heavy_check_mark:|:heavy_check_mark:|UltraLibrarian |${KICAD_3RD_PARTY}/UltraLibrarian.lib  | Legacy        |

**Preferences** -> **Manage Footprint Libraries** -> **Global Libraries** -> Add the following entries
|Active             |Nickname       |Library Path                             | Library Format|
|-------------------|---------------|-----------------------------------------|---------------|
|:heavy_check_mark: |Samacsys       | ${KICAD_3RD_PARTY}/Samacsys.pretty      | KiCad         |
|:heavy_check_mark: |Snapeda        | ${KICAD_3RD_PARTY}/Snapeda.pretty       | KiCad         |
|:heavy_check_mark: |UltraLibrarian | ${KICAD_3RD_PARTY}/UltraLibrarian.pretty| KiCad         |

## Library sources tested
- [x] [Samacsys](https://componentsearchengine.com/) (COMPONENT SEARCH ENGINE)
- [x] [Ultralibrarian](https://app.ultralibrarian.com/search)
- [x] [Snapeda](https://www.snapeda.com/home/) (KiCad V4 Setting)
- [x] [Snapeda](https://www.snapeda.com/home/) (KiCad V6 Setting)
- [ ] [Octopart](https://octopart.com/)

Operating systems
- [x] Windows
- [x] Linux
- [x] Mac

KiCad versions
- [x] KiCad 6
- [x] KiCad 7

Please write an issues if an import does not work as requested.

## To DO


## Done

- [x] Automatic background import
- [x] Test on a Mac
- [x] Testing all library formats
- [x] Using the new KiCad format

## Many thanks to

[wexi with impart](https://github.com/wexi/impart) and [topherbuckley](https://github.com/topherbuckley/kicad_remote_import) for the code on which the GUI is based.
