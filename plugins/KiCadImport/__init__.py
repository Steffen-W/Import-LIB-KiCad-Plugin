#!/usr/bin/env python3
# coding: utf-8

# Assembles local KiCad component libraries from downloaded Octopart,
# Samacsys, Ultralibrarian and Snapeda zipfiles using kiutils.
# Supports KiCad 7.0 and newer.

import zipfile
import tempfile
import shutil
import sys
import logging
from enum import Enum
from typing import Tuple, Union, List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Setup kiutils path using sys.path manipulation like KiCad_Settings
current_dir = Path(__file__).resolve().parent
kiutils_src = current_dir.parent / "kiutils" / "src"
if str(kiutils_src) not in sys.path:
    sys.path.insert(0, str(kiutils_src))

# Import kiutils modules directly
from kiutils.symbol import SymbolLib, Property, Effects
from kiutils.items.common import Position, Font

try:
    from .footprint_model_parser import FootprintModelParser
except ImportError:
    from footprint_model_parser import FootprintModelParser

try:
    from ..kicad_cli import kicad_cli
except ImportError:
    from kicad_cli import kicad_cli

try:
    cli = kicad_cli()
    logger.info("✓ kicad_cli initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize kicad_cli: {e}")
    cli = None


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
        self.footprint_parser = FootprintModelParser()

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
            files["symbol"] = find_in_zip(kicad_dir, ".kicad_sym") or find_in_zip(
                kicad_dir, ".lib"
            )
            files["dcm"] = find_in_zip(kicad_dir, ".dcm")
            files["footprint"] = kicad_dir  # Footprints are stored in this directory
            files["model"] = model_path
            return REMOTE_TYPES.Samacsys, files

        # Check for UltraLibrarian format
        kicad_dir = find_in_zip(root_path, "KiCAD")
        if kicad_dir and kicad_dir.is_dir():
            logger.info("Identified as UltraLibrarian format")
            files["symbol"] = find_in_zip(kicad_dir, ".kicad_sym") or find_in_zip(
                kicad_dir, ".lib"
            )
            files["dcm"] = find_in_zip(kicad_dir, ".dcm")
            files["footprint"] = find_in_zip(kicad_dir, ".pretty")
            files["model"] = model_path
            return REMOTE_TYPES.UltraLibrarian, files

        # Default to Snapeda format if we have symbols and footprints
        footprint_file = find_in_zip(root_path, ".kicad_mod")
        symbol_file = find_in_zip(root_path, ".kicad_sym") or find_in_zip(
            root_path, ".lib"
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
        self,
        symbol_path: Optional[Union[Path, zipfile.Path]],
        dcm_path: Optional[Union[Path, zipfile.Path]] = None,
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

        # Extract DCM file to same directory if available
        if dcm_path:
            try:
                _, dcm_extracted_path = self.extract_file_to_temp(dcm_path)
                dcm_target = temp_dir / dcm_path.name
                if dcm_extracted_path != dcm_target:
                    shutil.copy2(dcm_extracted_path, dcm_target)
            except Exception as e:
                logger.warning(f"Failed to extract DCM file: {e}")

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
                            f"Failed to convert {extracted_path} to new KiCad format"
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

    def extract_footprint_to_file(
        self, footprint_path: Optional[Union[Path, zipfile.Path]], dest_file: Path
    ) -> Optional[str]:
        """Extract footprint to destination file with upgrade and return footprint name"""
        if not footprint_path:
            return None

        footprint_file = footprint_path
        if footprint_path.is_dir():
            for item in footprint_path.iterdir():
                if item.name.endswith(".kicad_mod"):
                    footprint_file = item
                    break

            if not footprint_file or footprint_file.is_dir():
                logger.warning("No .kicad_mod file found in directory")
                return None

        temp_dir = Path(tempfile.mkdtemp())
        try:
            # Extract to temporary file
            temp_file = temp_dir / footprint_file.name
            with footprint_file.open("rb") as src, open(temp_file, "wb") as dst:
                shutil.copyfileobj(src, dst)

            # Upgrade footprint using CLI if available
            if cli.exists():
                try:
                    # Create temporary .pretty directory for upgrade
                    temp_pretty = temp_dir / "temp.pretty"
                    temp_pretty.mkdir()

                    # Copy footprint to .pretty structure
                    pretty_footprint = temp_pretty / temp_file.name
                    shutil.copy2(temp_file, pretty_footprint)

                    # Upgrade in-place (no output folder)
                    result = cli.upgrade_footprint_lib(
                        pretty_folder=str(temp_pretty), force=True
                    )

                    if result.success:
                        # Use upgraded file from same directory
                        upgraded_file = temp_pretty / temp_file.name

                        if upgraded_file.exists():
                            temp_file = upgraded_file
                            logger.info(
                                f"Successfully upgraded footprint: {temp_file.name}"
                            )
                        else:
                            logger.warning(
                                f"Upgrade output not found for {temp_file.name}"
                            )
                    else:
                        logger.warning(f"Footprint upgrade failed: {result.message}")

                except Exception as upgrade_error:
                    logger.warning(f"Footprint upgrade failed: {upgrade_error}")
            else:
                logger.debug("KiCad CLI not available - skipping footprint upgrade")

            content = temp_file.read_text(encoding="utf-8")
            footprint_name = self.footprint_parser.extract_footprint_name(content)

            if not footprint_name:
                raise ValueError("Could not extract valid footprint name")

            # Copy to final destination
            shutil.copy2(temp_file, dest_file)

            logger.info(f"Successfully extracted footprint: {footprint_name}")
            return footprint_name

        except Exception as e:
            logger.error(f"Failed to extract footprint: {e}")
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
        self, footprint_file: Path, model_name: str, remote_type: REMOTE_TYPES
    ) -> bool:
        """Update footprint file with model using string manipulation"""
        if not footprint_file.exists():
            return False

        model_path = (
            f"{self.KICAD_3RD_PARTY_LINK}/{remote_type.name}.3dshapes/{model_name}"
        )

        try:
            content = footprint_file.read_text(encoding="utf-8")
            updated_content = self.footprint_parser.update_or_add_model(
                content, model_path
            )
            footprint_file.write_text(updated_content, encoding="utf-8")
            return True
        except Exception as e:
            logger.error(f"Failed to update footprint model: {e}")
            return False

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
        footprint_file_path: Optional[Path],
        model_path: Optional[Path],
        remote_type: REMOTE_TYPES,
        symbol_name: str,
        overwrite_if_exists: bool = True,
    ) -> bool:
        """
        Save the component to the KiCad library with backup protection

        Returns:
            True if successful, False otherwise
        """
        success_items = []
        backup_files = {}  # Track backup files for rollback

        try:
            # 1. Save symbol library with atomic write
            if symbol_lib:
                lib_file_path = self.DEST_PATH / f"{remote_type.name}.kicad_sym"

                # Create backup if file exists
                backup_path = None
                if lib_file_path.exists():
                    backup_path = lib_file_path.with_suffix(".kicad_sym.backup")
                    shutil.copy2(lib_file_path, backup_path)
                    backup_files[lib_file_path] = backup_path
                    existing_lib = SymbolLib().from_file(str(lib_file_path))
                else:
                    existing_lib = SymbolLib()
                    check_file(lib_file_path)

                # Check if symbol already exists
                existing_names = [s.entryName for s in existing_lib.symbols]
                symbol_exists = symbol_name in existing_names

                # Decide what to do
                if symbol_exists and not overwrite_if_exists:
                    self.print(
                        f"Symbol {symbol_name} already exists in library. Skipping."
                    )
                    self.lib_skipped = True
                else:
                    # Single place for symbol insertion/update
                    if symbol_exists and overwrite_if_exists:
                        # Remove existing symbol
                        existing_lib.symbols = [
                            s
                            for s in existing_lib.symbols
                            if s.entryName != symbol_name
                        ]
                        action = "updated"
                    else:
                        action = "added" if symbol_exists == False else "created"

                    # Add new symbols
                    existing_lib.symbols.extend(symbol_lib.symbols)

                    # Atomic write: Save to temporary file first
                    temp_lib_path = lib_file_path.with_suffix(".tmp")
                    existing_lib.to_file(str(temp_lib_path))

                    # Verify the written file
                    try:
                        test_lib = SymbolLib().from_file(str(temp_lib_path))
                        if not test_lib.symbols:
                            raise ValueError("Written library is empty")
                    except Exception as e:
                        if temp_lib_path.exists():
                            temp_lib_path.unlink()
                        raise ValueError(f"Library verification failed: {e}")

                    # Replace original with temp file (atomic on most filesystems)
                    if lib_file_path.exists():
                        lib_file_path.unlink()
                    temp_lib_path.rename(lib_file_path)

                    result = cli.upgrade_sym_lib(str(lib_file_path), str(lib_file_path))
                    if not result.success:
                        raise ValueError(
                            f"Updating {lib_file_path} failed: {result.message} "
                            + f"details: {result.stderr}"
                        )

                    modified_objects.append(lib_file_path, Modification.MODIFIED_FILE)

                    # Output message
                    if action == "created":
                        success_items.append(
                            f"created symbol library with {symbol_name}"
                        )
                        self.print(f"Created new symbol library with {symbol_name}")
                    elif action == "updated":
                        success_items.append(f"updated symbol {symbol_name}")
                        self.print(f"Updated symbol {symbol_name} in library")
                    else:  # added
                        success_items.append(f"added symbol {symbol_name}")
                        self.print(f"Added symbol {symbol_name} to library")

            # 2. Handle footprint (already extracted to destination)
            if footprint_file_path and footprint_file_path.exists():
                if not overwrite_if_exists and footprint_file_path.exists():
                    self.print(
                        f"Footprint {footprint_file_path.name} already exists. Skipping."
                    )
                    self.footprint_skipped = True
                else:
                    modified_objects.append(
                        footprint_file_path, Modification.MODIFIED_FILE
                    )
                    success_items.append(f"saved footprint {footprint_file_path.stem}")
                    self.print(f"Saved footprint {footprint_file_path.stem}")

            # 3. Save 3D model
            if model_path:
                model_dir = self.DEST_PATH / f"{remote_type.name}.3dshapes"
                if not model_dir.exists():
                    model_dir.mkdir(parents=True, exist_ok=True)
                    modified_objects.append(model_dir, Modification.MKDIR)

                model_file = model_dir / model_path.name

                if model_file.exists() and not overwrite_if_exists:
                    self.print(f"3D model {model_path.name} already exists. Skipping.")
                    self.model_skipped = True
                else:
                    # Create backup if file exists
                    if model_file.exists():
                        backup_path = model_file.with_suffix(
                            f"{model_file.suffix}.backup"
                        )
                        shutil.copy2(model_file, backup_path)
                        backup_files[model_file] = backup_path

                    # Copy model file
                    shutil.copy2(model_path, model_file)
                    modified_objects.append(model_file, Modification.EXTRACTED_FILE)
                    success_items.append(f"saved 3D model {model_path.name}")
                    self.print(f"Saved 3D model {model_path.name}")

                    # Update footprint with model reference
                    if footprint_file_path and footprint_file_path.exists():
                        model_update_success = self.update_footprint_with_model(
                            footprint_file_path, model_path.name, remote_type
                        )
                        if not model_update_success:
                            logger.warning(
                                "Failed to update footprint with model reference"
                            )

            # Success - clean up backup files
            for backup_path in backup_files.values():
                if backup_path and backup_path.exists():
                    backup_path.unlink()

            # Log summary of what was saved
            if success_items:
                logger.info(f"Saved: {', '.join(success_items)}")

            return True

        except Exception as e:
            logger.error(f"Error during save_to_library: {e}")
            self.print(f"Error during save: {e}")

            # Rollback: Restore original files from backups
            for original_path, backup_path in backup_files.items():
                if backup_path and backup_path.exists():
                    try:
                        if original_path.exists():
                            original_path.unlink()
                        shutil.move(backup_path, original_path)
                        logger.info(f"Restored backup for: {original_path}")
                    except Exception as restore_error:
                        logger.error(
                            f"Failed to restore backup {backup_path}: {restore_error}"
                        )

            # Clean up any remaining temporary files
            for pattern in [f"{remote_type.name}.kicad_sym.tmp", "*.tmp"]:
                for temp_file in self.DEST_PATH.glob(pattern):
                    if temp_file.exists():
                        temp_file.unlink(missing_ok=True)

            return False

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
                    symbol_lib, symbol_name = self.load_symbol_lib(
                        files["symbol"], files.get("dcm")
                    )
                    logger.info(f"Loaded symbol: {symbol_name}")

                # Handle footprint - extract directly to destination
                footprint_file_path = None
                if files["footprint"]:
                    footprint_dir = self.DEST_PATH / f"{remote_type.name}.pretty"
                    if not footprint_dir.exists():
                        footprint_dir.mkdir(parents=True, exist_ok=True)
                        modified_objects.append(footprint_dir, Modification.MKDIR)

                    # Generate initial footprint filename
                    temp_footprint_name = None
                    if files["footprint"].is_dir():
                        for item in files["footprint"].iterdir():
                            if item.name.endswith(".kicad_mod"):
                                temp_footprint_name = self.cleanName(item.name[:-10])
                                break
                    else:
                        temp_footprint_name = self.cleanName(
                            files["footprint"].name[:-10]
                        )

                    if temp_footprint_name:
                        footprint_file_path = (
                            footprint_dir / f"{temp_footprint_name}.kicad_mod"
                        )

                        # Extract footprint with upgrade
                        extracted_name = self.extract_footprint_to_file(
                            files["footprint"], footprint_file_path
                        )

                        if extracted_name:
                            self.footprint_name = extracted_name
                            # Rename file if name changed after parsing
                            if extracted_name != temp_footprint_name:
                                new_footprint_path = (
                                    footprint_dir / f"{extracted_name}.kicad_mod"
                                )
                                if footprint_file_path.exists():
                                    footprint_file_path.rename(new_footprint_path)
                                    footprint_file_path = new_footprint_path

                            logger.info(
                                f"Successfully processed footprint: {self.footprint_name}"
                            )
                        else:
                            logger.warning("Failed to extract footprint")
                            self.print("Warning: Failed to extract footprint")
                            footprint_file_path = None

                # Load 3D model
                model_temp_dir = None
                model_path = None
                if files["model"]:
                    model_temp_dir, model_path = self.load_model(files["model"])
                    if model_temp_dir:
                        temp_dirs.append(model_temp_dir)
                        if model_path:
                            logger.info(f"Loaded 3D model: {model_path.name}")

                # Update symbol with footprint reference
                if symbol_lib and self.footprint_name:
                    symbol_lib = self.update_symbol_properties(
                        symbol_lib, self.footprint_name, remote_type
                    )

                # Save everything to the library
                if symbol_lib or footprint_file_path or model_path:
                    success = self.save_to_library(
                        symbol_lib=symbol_lib,
                        footprint_file_path=footprint_file_path,
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
                            logger.info("Import completed - all files already exist")
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
