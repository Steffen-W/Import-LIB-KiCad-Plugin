#!/usr/bin/env python3
# coding: utf-8

# Assembles local KiCad component libraries from downloaded Octopart,
# Samacsys, Ultralibrarian and Snapeda zipfiles using kiutils.
# Supports KiCad 7.0 and newer.

import zipfile
import tempfile
import shutil
import logging
import time
from enum import Enum
from typing import Tuple, Union, List, Dict, Any, Optional
from pathlib import Path

from kiutils.footprint import Footprint, Model, Coordinate
from kiutils.symbol import SymbolLib, Property, Effects
from kiutils.items.common import Position, Font

from kiutils.libraries import Library, LibTable

try:
    from ..kicad_cli import kicad_cli
except ImportError:
    from kicad_cli import kicad_cli

cli = kicad_cli()
logger = logging.getLogger(__name__)


class Modification(Enum):
    MKDIR = 0
    TOUCH_FILE = 1
    MODIFIED_FILE = 2
    EXTRACTED_FILE = 3


class ModifiedObject:
    def __init__(self):
        self.dict = {}

    def append(self, obj: Path, modification: Modification):
        self.dict[obj] = modification


# keeps track of which files were modified in case an error occurs we can revert these changes before exiting
modified_objects = ModifiedObject()


def check_file(path: Path):
    """
    Check if file exists, if not create parent directories and touch file
    :param path:
    """
    if not path.exists():
        if not path.parent.is_dir():
            path.parent.mkdir(parents=True)
            modified_objects.append(path.parent, Modification.MKDIR)
        path.touch(mode=0o666)
        modified_objects.append(path, Modification.TOUCH_FILE)


def find_in_zip(root: zipfile.Path, suffix: str) -> Optional[zipfile.Path]:
    """
    Recursively search under `root` for the first file whose name ends with `suffix`.
    Returns a zipfile.Path if found, otherwise None.
    """
    if root.name.endswith(suffix):
        return root
    elif root.is_dir():
        for child in root.iterdir():
            match = find_in_zip(child, suffix)
            if match:
                return match
    return None


class REMOTE_TYPES(Enum):
    Octopart = 0
    Samacsys = 1
    UltraLibrarian = 2
    Snapeda = 3
    Partial = 4  # For archives with incomplete data


class LibImporter:
    def print(self, txt):
        print("->" + txt)

    def __init__(self):
        self.KICAD_3RD_PARTY_LINK: str = "${KICAD_3RD_PARTY}"
        self.DEST_PATH = Path.home() / "KiCad"
        self.dcm_skipped = False
        self.lib_skipped = False
        self.footprint_skipped = False
        self.model_skipped = False
        self.footprint_name = None

    def set_DEST_PATH(self, DEST_PATH_=Path.home() / "KiCad"):
        self.DEST_PATH = Path(DEST_PATH_)

    def cleanName(self, name):
        invalid = '<>:"/\\|?* '
        name = name.strip()
        original_name = name
        for char in invalid:  # remove invalid characters
            name = name.replace(char, "_")
        if original_name != name:
            logger.debug(f"Cleaned name: {original_name} -> {name}")
        return name

    def identify_remote_type(
        self, zf: zipfile.ZipFile
    ) -> Tuple[REMOTE_TYPES, dict[str, Optional[Union[Path, zipfile.Path]]]]:
        """
        Identifies the source of the component library and locates key files

        Args:
            zf: The opened zipfile object

        Returns:
            Tuple with remote type and dictionary of paths to important files
        """
        root_path = zipfile.Path(zf)
        files: dict[str, Optional[Union[Path, zipfile.Path]]] = {
            "symbol": None,
            "footprint": None,
            "model": None,
            "dcm": None,
        }

        # Check for Octopart format
        dcm_path = find_in_zip(root_path, "device.dcm")
        lib_path = find_in_zip(root_path, "device.lib")
        sym_path = find_in_zip(root_path, ".kicad_sym")
        footprint_pretty = None

        # Look for .pretty directory
        for item in root_path.iterdir():
            if item.name.endswith(".pretty") and item.is_dir():
                footprint_pretty = item
                break

        # Search for model files
        model_path = find_in_zip(root_path, ".step")
        if not model_path:
            model_path = find_in_zip(root_path, ".stp")
        if not model_path:
            model_path = find_in_zip(root_path, ".wrl")

        # Try to identify format based on directory structure and files

        # Check for Octopart format
        octopart_check = (
            find_in_zip(root_path, "device.lib") is not None
            and find_in_zip(root_path, "device.dcm") is not None
        )
        if octopart_check:
            logger.info("Identified as Octopart format")
            files["symbol"] = find_in_zip(root_path, "device.lib")
            files["dcm"] = find_in_zip(root_path, "device.dcm")
            files["footprint"] = footprint_pretty
            files["model"] = model_path
            return REMOTE_TYPES.Octopart, files

        # Check for Samacsys format
        kicad_dir = find_in_zip(root_path, "KiCad")
        if kicad_dir and kicad_dir.is_dir():
            logger.info("Identified as Samacsys format")
            files["symbol"] = find_in_zip(kicad_dir, ".lib") or find_in_zip(
                kicad_dir, ".kicad_sym"
            )
            files["dcm"] = find_in_zip(kicad_dir, ".dcm")
            files["footprint"] = kicad_dir  # Footprints are stored in this directory
            files["model"] = model_path
            return REMOTE_TYPES.Samacsys, files

        # Check for UltraLibrarian format
        kicad_dir = find_in_zip(root_path, "KiCAD")
        if kicad_dir and kicad_dir.is_dir():
            logger.info("Identified as UltraLibrarian format")
            files["symbol"] = find_in_zip(kicad_dir, ".lib") or find_in_zip(
                kicad_dir, ".kicad_sym"
            )
            files["dcm"] = find_in_zip(kicad_dir, ".dcm")
            files["footprint"] = find_in_zip(kicad_dir, ".pretty")
            files["model"] = model_path
            return REMOTE_TYPES.UltraLibrarian, files

        # Default to Snapeda format if we have symbols and footprints
        footprint_file = find_in_zip(root_path, ".kicad_mod")
        symbol_file = find_in_zip(root_path, ".lib") or find_in_zip(
            root_path, ".kicad_sym"
        )

        if symbol_file:
            logger.info("Identified as Snapeda format")
            files["symbol"] = symbol_file
            files["dcm"] = find_in_zip(root_path, ".dcm")
            files["footprint"] = footprint_file
            files["model"] = model_path
            return REMOTE_TYPES.Snapeda, files

        # If we can't determine the type but have essential files, default to Snapeda
        if sym_path or lib_path:
            logger.warning("Defaulting to Snapeda format")
            files["symbol"] = sym_path or lib_path
            files["dcm"] = dcm_path
            files["footprint"] = footprint_file
            files["model"] = model_path
            return REMOTE_TYPES.Snapeda, files

        # Handle partial archives (e.g., only 3D models)
        if model_path:
            logger.warning(f"Archive contains only partial data: 3D model found")
            files["model"] = model_path
            return REMOTE_TYPES.Partial, files

        logger.error("Unable to identify library format - no usable files found")
        raise ValueError("Unable to identify library format. Missing essential files.")

    def extract_file_to_temp(
        self, file_path: Optional[Union[Path, zipfile.Path]]
    ) -> Tuple[Path, Path]:
        """
        Extract a file from zipfile.Path to a temporary location

        Returns:
            Tuple of (temp_dir, extracted_file_path)
        """
        if not file_path:
            logger.error("No file path provided for extraction")
            raise ValueError("No file path")

        temp_dir = Path(tempfile.mkdtemp())
        extracted = temp_dir / file_path.name

        try:
            with file_path.open("rb") as src, open(extracted, "wb") as dst:
                shutil.copyfileobj(src, dst)
        except Exception as e:
            logger.error(f"Failed to extract {file_path}: {e}")
            raise

        return temp_dir, extracted

    def load_symbol_lib(
        self, symbol_path: Optional[Union[Path, zipfile.Path]]
    ) -> Tuple[SymbolLib, str]:
        """
        Load a symbol library from a path in a zip file

        Returns:
            Tuple of (SymbolLib object, symbol name)
        """
        if not symbol_path:
            logger.error("No symbol path provided")
            raise ValueError("No symbol path")

        temp_dir, extracted_path = self.extract_file_to_temp(symbol_path)
        try:
            # Always try to convert to new format
            if extracted_path.suffix == ".lib":
                if cli.exists():
                    new_path = extracted_path.with_suffix(".kicad_sym")
                    cli.upgrade_sym_lib(str(extracted_path), str(new_path))
                    if new_path.exists():
                        symbol_lib = SymbolLib().from_file(str(new_path))
                    else:
                        logger.error(f"Conversion failed for {extracted_path}")
                        raise ValueError(
                            f"Failed to convert {extracted_path} to KiCad 7 format"
                        )
                else:
                    logger.error("KiCad CLI not available for .lib conversion")
                    raise ValueError("KiCad CLI not available for .lib conversion")
            else:  # .kicad_sym - still try to convert just to be sure
                if cli.exists():
                    new_path = extracted_path
                    cli.upgrade_sym_lib(str(extracted_path), str(new_path))
                    symbol_lib = SymbolLib().from_file(str(new_path))
                else:
                    logger.warning("KiCad CLI not available, loading file directly")
                    symbol_lib = SymbolLib().from_file(str(extracted_path))

            # Get the symbol name from the first symbol
            if not symbol_lib.symbols:
                logger.error("No symbols found in library")
                raise ValueError("No symbols found in library")

            symbol_name = symbol_lib.symbols[0].entryName
            return symbol_lib, symbol_name
        except Exception as e:
            logger.error(f"Failed to load symbol library: {e}")
            raise
        finally:
            shutil.rmtree(temp_dir)

    def load_footprint(
        self, footprint_path: Optional[Union[Path, zipfile.Path]]
    ) -> Optional[Footprint]:
        """
        Load a footprint from a path in a zip file

        Returns:
            Footprint object
        """
        if not footprint_path:
            return None

        footprint_file = footprint_path
        # If directory, find a .kicad_mod file in it
        if footprint_path.is_dir():
            for item in footprint_path.iterdir():
                if item.name.endswith(".kicad_mod"):
                    footprint_file = item
                    break

            if not footprint_file or footprint_file.is_dir():
                logger.warning("No .kicad_mod file found in directory")
                return None

        temp_dir, extracted_path = self.extract_file_to_temp(footprint_file)
        try:
            footprint = Footprint().from_file(str(extracted_path))
            return footprint
        except Exception as e:
            logger.error(f"Failed to load footprint: {e}")
            return None
        finally:
            shutil.rmtree(temp_dir)

    def load_model(
        self, model_path: Optional[Union[Path, zipfile.Path]]
    ) -> Tuple[Optional[Path], Optional[Path]]:
        """
        Load a 3D model from a path in a zip file

        Returns:
            Tuple of (temp_dir, extracted_model_path)
        """
        if not model_path:
            return (None, None)

        try:
            result = self.extract_file_to_temp(model_path)
            return result
        except Exception as e:
            logger.error(f"Failed to load 3D model: {e}")
            return (None, None)

    def update_footprint_with_model(
        self, footprint: Footprint, model_name: str, remote_type: REMOTE_TYPES
    ) -> Footprint:
        """
        Update a footprint with a 3D model reference

        Returns:
            Updated footprint
        """
        if not footprint or not model_name:
            return footprint

        # Create model path with proper linking
        model_path = (
            f"{self.KICAD_3RD_PARTY_LINK}/{remote_type.name}.3dshapes/{model_name}"
        )

        # Check if there's already any model
        if footprint.models:
            # Just update path of the existing model
            for existing_model in footprint.models:
                existing_model.path = model_path
        else:
            # Add new model with standard values
            new_model = Model(
                path=model_path,
                scale=Coordinate(1.0, 1.0, 1.0),
                pos=Coordinate(0.0, 0.0, 0.0),
                rotate=Coordinate(0.0, 0.0, 0.0),
            )
            footprint.models.append(new_model)

        return footprint

    def update_symbol_properties(
        self, symbol_lib: SymbolLib, footprint_name: str, remote_type: REMOTE_TYPES
    ) -> SymbolLib:
        """
        Update symbol properties, particularly the footprint reference

        Returns:
            Updated SymbolLib
        """
        if not symbol_lib or not symbol_lib.symbols:
            return symbol_lib

        for symbol in symbol_lib.symbols:
            footprint_prop = None
            # Find the footprint property
            for prop in symbol.properties:
                if prop.key == "Footprint":
                    footprint_prop = prop
                    break

            if footprint_prop:
                # Update the footprint reference with library prefix
                old_value = footprint_prop.value
                footprint_prop.value = (
                    f"{remote_type.name}:{self.cleanName(footprint_name)}"
                )
                logger.debug(
                    f"Updated footprint property: {old_value} -> {footprint_prop.value}"
                )
            else:
                # Add footprint property if it doesn't exist
                new_prop = Property(
                    key="Footprint",
                    value=f"{remote_type.name}:{self.cleanName(footprint_name)}",
                    id=0,  # Will be assigned by kiutils
                    position=Position(0, 0),
                    effects=Effects(
                        font=Font(
                            face="default",
                            height=1.27,
                            width=1.27,
                            bold=False,
                            italic=False,
                        )
                    ),
                )
                symbol.properties.append(new_prop)

        return symbol_lib

    def save_to_library(
        self,
        symbol_lib: Optional[SymbolLib],
        footprint: Optional[Footprint],
        model_path: Optional[Path],
        remote_type: REMOTE_TYPES,
        symbol_name: str,
        overwrite_if_exists: bool = True,
    ) -> bool:
        """
        Save the component to the KiCad library

        Returns:
            True if successful, False otherwise
        """
        success_items = []

        # 1. Save symbol library
        if symbol_lib:
            lib_file_path = self.DEST_PATH / f"{remote_type.name}.kicad_sym"

            # Check if symbol already exists
            if lib_file_path.exists() and not overwrite_if_exists:
                existing_lib = SymbolLib().from_file(str(lib_file_path))
                for existing_symbol in existing_lib.symbols:
                    if existing_symbol.entryName == symbol_name:
                        logger.info(f"Symbol {symbol_name} already exists, skipping")
                        self.print(
                            f"Symbol {symbol_name} already exists in library. Skipping."
                        )
                        self.lib_skipped = True
                        break
            else:
                # Merge with existing library or create new
                if lib_file_path.exists():
                    existing_lib = SymbolLib().from_file(str(lib_file_path))

                    # Remove existing symbol with same name if overwrite is enabled
                    if overwrite_if_exists:
                        existing_lib.symbols = [
                            s
                            for s in existing_lib.symbols
                            if s.entryName != symbol_name
                        ]
                        # Add the new symbols
                        existing_lib.symbols.extend(symbol_lib.symbols)
                        existing_lib.to_file(str(lib_file_path))
                        success_items.append(f"updated symbol {symbol_name}")
                        self.print(f"Updated symbol {symbol_name} in library")
                    else:
                        # Add only if not already present
                        existing_names = [s.entryName for s in existing_lib.symbols]
                        for symbol in symbol_lib.symbols:
                            if symbol.entryName not in existing_names:
                                existing_lib.symbols.append(symbol)
                        existing_lib.to_file(str(lib_file_path))
                        success_items.append(f"added symbol {symbol_name}")
                        self.print(f"Added symbol {symbol_name} to library")
                else:
                    # Create new library
                    check_file(lib_file_path)
                    symbol_lib.to_file(str(lib_file_path))
                    success_items.append(f"created symbol library with {symbol_name}")
                    self.print(f"Created new symbol library with {symbol_name}")

                modified_objects.append(lib_file_path, Modification.MODIFIED_FILE)

        # 2. Save footprint if available
        if footprint:
            footprint_dir = self.DEST_PATH / f"{remote_type.name}.pretty"
            if not footprint_dir.exists():
                footprint_dir.mkdir(parents=True, exist_ok=True)
                modified_objects.append(footprint_dir, Modification.MKDIR)

            self.footprint_name = self.cleanName(footprint.entryName)
            footprint_file = footprint_dir / f"{self.footprint_name}.kicad_mod"

            if footprint_file.exists() and not overwrite_if_exists:
                logger.info(f"Footprint {self.footprint_name} already exists, skipping")
                self.print(f"Footprint {self.footprint_name} already exists. Skipping.")
                self.footprint_skipped = True
            else:
                footprint.to_file(str(footprint_file))
                modified_objects.append(footprint_file, Modification.MODIFIED_FILE)
                success_items.append(f"saved footprint {self.footprint_name}")
                self.print(f"Saved footprint {self.footprint_name}")

        # 3. Save 3D model if available
        if model_path:
            model_dir = self.DEST_PATH / f"{remote_type.name}.3dshapes"
            if not model_dir.exists():
                model_dir.mkdir(parents=True, exist_ok=True)
                modified_objects.append(model_dir, Modification.MKDIR)

            model_file = model_dir / model_path.name

            if model_file.exists() and not overwrite_if_exists:
                logger.info(f"3D model {model_path.name} already exists, skipping")
                self.print(f"3D model {model_path.name} already exists. Skipping.")
                self.model_skipped = True
            else:
                shutil.copy2(model_path, model_file)
                modified_objects.append(model_file, Modification.EXTRACTED_FILE)
                success_items.append(f"saved 3D model {model_path.name}")
                self.print(f"Saved 3D model {model_path.name}")

        # Log summary of what was saved
        if success_items:
            logger.info(f"Saved: {', '.join(success_items)}")

        return True

    def import_all(
        self, zip_file: Path, overwrite_if_exists=True, import_old_format=True
    ):
        """Import symbols, footprints, and 3D models from a zip file"""
        logger.info(f"Importing {zip_file.name}")

        if not zipfile.is_zipfile(zip_file):
            logger.error(f"{zip_file} is not a valid zip file")
            self.print(f"Error: {zip_file} is not a valid zip file")
            return None

        self.print(f"Import: {zip_file}")

        temp_dirs = []  # Track temporary directories to clean up later

        try:
            with zipfile.ZipFile(zip_file) as zf:
                # Identify library type and locate files
                remote_type, files = self.identify_remote_type(zf)
                logger.info(f"Type: {remote_type.name}")
                self.print(f"Identified as {remote_type.name}")

                # Handle partial archives
                if remote_type == REMOTE_TYPES.Partial:
                    logger.warning(
                        "Archive contains incomplete data - partial import only"
                    )
                    self.print("Warning: Archive contains incomplete data")
                    if not files["model"]:
                        self.print("No usable content found in archive")
                        return None

                # Load symbol library
                symbol_lib = None
                symbol_name = "unknown"
                if files["symbol"]:
                    symbol_lib, symbol_name = self.load_symbol_lib(files["symbol"])
                    logger.info(f"Loaded symbol: {symbol_name}")

                # Load footprint
                footprint: Optional[Footprint] = None
                if files["footprint"]:
                    footprint = self.load_footprint(files["footprint"])
                    if footprint:
                        self.footprint_name = self.cleanName(footprint.entryName)
                        logger.info(f"Loaded footprint: {self.footprint_name}")
                    else:
                        logger.warning("Unable to load footprint")
                        self.print("Warning: Unable to load footprint")

                # Load 3D model
                model_temp_dir = None
                model_path = None
                if files["model"]:
                    model_temp_dir, model_path = self.load_model(files["model"])
                    if model_temp_dir:
                        temp_dirs.append(model_temp_dir)
                        logger.info(f"Loaded 3D model: {model_path.name}")

                    # Update footprint with model reference if we have both
                    if footprint and model_path:
                        footprint = self.update_footprint_with_model(
                            footprint, model_path.name, remote_type
                        )

                # Update symbol with footprint reference
                if symbol_lib and self.footprint_name:
                    symbol_lib = self.update_symbol_properties(
                        symbol_lib, self.footprint_name, remote_type
                    )

                # Save everything to the library
                if symbol_lib or footprint or model_path:
                    success = self.save_to_library(
                        symbol_lib=symbol_lib,
                        footprint=footprint,
                        model_path=model_path,
                        remote_type=remote_type,
                        symbol_name=symbol_name,
                        overwrite_if_exists=overwrite_if_exists,
                    )

                    if success:
                        # Check if anything was actually changed
                        if (
                            self.lib_skipped
                            and self.footprint_skipped
                            and self.model_skipped
                        ):
                            logger.info(
                                "Import completed - all files already exist"
                            )
                            self.print("Import completed")
                            return ("OK",)
                        elif (
                            self.lib_skipped
                            or self.footprint_skipped
                            or self.model_skipped
                        ):
                            logger.info("Import completed with some items skipped")
                            self.print("Import successful (some items already existed)")
                            return ("OK",)
                        else:
                            logger.info("Import completed successfully")
                            self.print("Import successful")
                            return ("OK",)
                    else:
                        logger.warning("Import failed during save")
                        self.print("Import failed during save")
                        return ("Warning",)
                else:
                    logger.warning("No content to import")
                    self.print("Warning: No content found to import")
                    return ("Warning",)

        except Exception as e:
            logger.error(f"Import failed: {str(e)}")
            self.print(f"Error during import: {str(e)}")
            logging.exception("Import error")
            return None
        finally:
            # Clean up temporary directories
            for temp_dir in temp_dirs:
                if temp_dir and temp_dir.exists():
                    shutil.rmtree(temp_dir)


def main(
    lib_file, lib_folder, overwrite=False, KICAD_3RD_PARTY_LINK="${KICAD_3RD_PARTY}"
):
    lib_folder = Path(lib_folder)
    lib_file = Path(lib_file)

    logger.info(f"Starting import: {lib_file.name} -> {lib_folder}")
    print("overwrite", overwrite)

    if not lib_folder.is_dir():
        logger.error(f"Destination folder {lib_folder} does not exist")
        print(f"Error destination folder {lib_folder} does not exist!")
        return 0

    if not lib_file.is_file():
        logger.error(f"File {lib_file} not found")
        print(f"Error file {lib_folder} to be imported was not found!")
        return 0

    impart = LibImporter()
    impart.KICAD_3RD_PARTY_LINK = KICAD_3RD_PARTY_LINK
    impart.set_DEST_PATH(lib_folder)
    try:
        result = impart.import_all(lib_file, overwrite_if_exists=overwrite)
        logger.info(f"Import result: {result}")
        print(result)
    except Exception as e:
        logger.error(f"Main import error: {e}")
        print(f"Error: {e}")
        logging.exception("Import error")


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.ERROR)

    # Example: python plugins/KiCadImport.py --lib-folder import_test --download-folder Demo/libs

    parser = argparse.ArgumentParser(
        description="Import KiCad libraries from a file or folder."
    )

    # Create mutually exclusive arguments for file or folder
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--download-folder",
        help="Path to the folder with the zip files to be imported.",
    )
    group.add_argument("--download-file", help="Path to the zip file to import.")

    group.add_argument("--easyeda", help="Import easyeda part. example: C2040")

    parser.add_argument(
        "--lib-folder",
        required=True,
        help="Destination folder for the imported KiCad files.",
    )

    parser.add_argument(
        "--overwrite-if-exists",
        action="store_true",
        help="Overwrite existing files if they already exist",
    )

    parser.add_argument(
        "--path-variable",
        help="Example: if only project-specific '${KIPRJMOD}' standard is '${KICAD_3RD_PARTY}'",
    )

    args = parser.parse_args()

    lib_folder = Path(args.lib_folder)

    if args.path_variable:
        path_variable = str(args.path_variable).strip()
    else:
        path_variable = "${KICAD_3RD_PARTY}"

    if args.download_file:
        main(
            lib_file=args.download_file,
            lib_folder=args.lib_folder,
            overwrite=args.overwrite_if_exists,
            KICAD_3RD_PARTY_LINK=path_variable,
        )
    elif args.download_folder:
        download_folder = Path(args.download_folder)
        logger.info(f"Processing folder: {download_folder}")
        if not download_folder.is_dir():
            logger.error(f"Source folder {download_folder} does not exist")
            print(f"Error Source folder {download_folder} does not exist!")
        elif not lib_folder.is_dir():
            logger.error(f"Destination folder {lib_folder} does not exist")
            print(f"Error destination folder {lib_folder} does not exist!")
        else:
            zip_files = list(download_folder.glob("*.zip"))
            logger.info(f"Found {len(zip_files)} zip files to process")
            for zip_file in zip_files:
                if (
                    zip_file.is_file() and zip_file.stat().st_size >= 1024
                ):  # Check if it's a file and at least 1 KB
                    main(
                        lib_file=zip_file,
                        lib_folder=args.lib_folder,
                        overwrite=args.overwrite_if_exists,
                        KICAD_3RD_PARTY_LINK=path_variable,
                    )
                else:
                    logger.warning(f"Skipping {zip_file}: too small or not a file")
    elif args.easyeda:
        logger.info(f"Processing EasyEDA component: {args.easyeda}")
        if not lib_folder.is_dir():
            logger.error(f"Destination folder {lib_folder} does not exist")
            print(f"Error destination folder {lib_folder} does not exist!")
        else:
            component_id = str(args.easyeda).strip()
            print("Try to import EasyEDA / LCSC Part# : ", component_id)
            from impart_easyeda import EasyEDAImporter, ImportConfig

            try:
                config = ImportConfig(
                    base_folder=lib_folder,
                    lib_name="EasyEDA",
                    overwrite=args.overwrite_if_exists,
                    lib_var=path_variable,
                )

                logger.debug(f"EasyEDA config: {config}")
                paths = EasyEDAImporter(config).import_component(component_id)
                logger.info(f"EasyEDA import completed for {component_id}")

                # Print results
                if paths.symbol_lib:
                    print(f"Library path : {paths.symbol_lib}")
                if paths.footprint_file:
                    print(f"Footprint path: {paths.footprint_file}")
                if paths.model_wrl:
                    print(f"3D model path (wrl): {paths.model_wrl}")
                if paths.model_step:
                    print(f"3D model path (step): {paths.model_step}")

            except Exception as e:
                logger.error(f"EasyEDA import failed for {component_id}: {e}")
                print(f"Error importing component: {e}")
