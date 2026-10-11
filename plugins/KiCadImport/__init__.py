#!/usr/bin/env python3
from __future__ import annotations

# Assembles local KiCad component libraries from downloaded Octopart,
# Samacsys, Ultralibrarian and Snapeda zipfiles using kiutils.
# Supports KiCad 7.0 and newer.
import gzip
import logging
import os
import shutil
import sys
import tempfile
import zipfile
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)

# Setup kiutils path using sys.path manipulation like KiCad_Settings
current_dir = Path(__file__).resolve().parent
kiutils_src = current_dir.parent / "kiutils" / "src"
if str(kiutils_src) not in sys.path:
    sys.path.insert(0, str(kiutils_src))

from kiutils.items.common import Font, Position  # noqa: E402

# Import kiutils modules directly
from kiutils.symbol import Effects, Property, SymbolLib  # noqa: E402

try:
    from .footprint_model_parser import FootprintModelParser
except ImportError:
    from footprint_model_parser import (  # type: ignore[import-not-found,no-redef]
        FootprintModelParser,
    )


try:
    from ..atomic_file import atomic_write
    from ..kicad_cli import KicadCli
except ImportError:
    from atomic_file import atomic_write  # type: ignore[import-not-found,no-redef]
    from kicad_cli import KicadCli  # type: ignore[import-not-found,no-redef]

try:
    cli: KicadCli | None = KicadCli()
    logger.info("kicad_cli initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize kicad_cli: {e}")
    cli = None


def find_in_zip(root: zipfile.Path, suffix: str) -> zipfile.Path | None:
    """
    Search under `root` for the first file whose name ends with `suffix`.
    Returns a zipfile.Path if found, otherwise None.
    """
    stack = [root]
    while stack:
        node = stack.pop()
        if node.name.endswith(suffix):
            return node
        if node.is_dir():
            # Reversed so pop() visits children in archive order.
            stack.extend(reversed(list(node.iterdir())))
    return None


class REMOTE_TYPES(Enum):
    Octopart = 0
    Samacsys = 1
    UltraLibrarian = 2
    Snapeda = 3
    Partial = 4  # For archives with incomplete data


class LibImporter:
    def print(self, txt: str) -> None:
        print("->" + txt)

    def __init__(self, lib_name: str | None = None, compress_models: bool = False):
        self.KICAD_3RD_PARTY_LINK: str = "${KICAD_3RD_PARTY}"
        self.DEST_PATH = Path.home() / "KiCad"
        self._reset_import_state()
        self.footprint_parser = FootprintModelParser()
        self.lib_name = lib_name
        self.compress_models = compress_models

    def _reset_import_state(self) -> None:
        self.lib_skipped = False
        self.footprint_skipped = False
        self.model_skipped = False

    def set_DEST_PATH(self, DEST_PATH_: str | Path = Path.home() / "KiCad") -> None:
        self.DEST_PATH = Path(DEST_PATH_)

    def get_lib_name(self, remote_type: REMOTE_TYPES) -> str:
        """Get effective library name - custom name if set, otherwise remote type name"""
        return self.lib_name if self.lib_name else remote_type.name

    # Windows device names; reserved regardless of case and extension.
    _WINDOWS_RESERVED_NAMES = frozenset(
        {"CON", "PRN", "AUX", "NUL"}
        | {f"COM{i}" for i in range(1, 10)}
        | {f"LPT{i}" for i in range(1, 10)}
    )

    def cleanName(self, name: str) -> str:
        invalid = '<>:"/\\|?* '
        name = name.strip()
        original_name = name
        for char in invalid:  # remove invalid characters
            name = name.replace(char, "_")
        # Windows forbids trailing dots; this also eliminates "." and "..".
        name = name.rstrip(".") or "_"
        if name.split(".", 1)[0].upper() in self._WINDOWS_RESERVED_NAMES:
            name = f"_{name}"
        if original_name != name:
            logger.debug(f"Cleaned name: {original_name} -> {name}")
        return name

    def identify_remote_type(
        self, zf: zipfile.ZipFile
    ) -> tuple[REMOTE_TYPES, dict[str, Path | zipfile.Path | None]]:
        """
        Identifies the source of the component library and locates key files

        Args:
            zf: The opened zipfile object

        Returns:
            Tuple with remote type and dictionary of paths to important files
        """
        root_path = zipfile.Path(zf)
        files: dict[str, Path | zipfile.Path | None] = {
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
            files["symbol"] = find_in_zip(kicad_dir, ".kicad_sym") or find_in_zip(kicad_dir, ".lib")
            files["dcm"] = find_in_zip(kicad_dir, ".dcm")
            files["footprint"] = kicad_dir  # Footprints are stored in this directory
            files["model"] = model_path
            return REMOTE_TYPES.Samacsys, files

        # Check for UltraLibrarian format
        kicad_dir = find_in_zip(root_path, "KiCAD")
        if kicad_dir and kicad_dir.is_dir():
            logger.info("Identified as UltraLibrarian format")
            files["symbol"] = find_in_zip(kicad_dir, ".kicad_sym") or find_in_zip(kicad_dir, ".lib")
            files["dcm"] = find_in_zip(kicad_dir, ".dcm")
            files["footprint"] = find_in_zip(kicad_dir, ".pretty")
            files["model"] = model_path
            return REMOTE_TYPES.UltraLibrarian, files

        # Default to Snapeda format if we have symbols and footprints
        footprint_file = find_in_zip(root_path, ".kicad_mod")
        symbol_file = find_in_zip(root_path, ".kicad_sym") or find_in_zip(root_path, ".lib")

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
            logger.warning("Archive contains only partial data: 3D model found")
            files["model"] = model_path
            return REMOTE_TYPES.Partial, files

        logger.error("Unable to identify library format - no usable files found")
        raise ValueError("Unable to identify library format. Missing essential files.")

    def extract_file_to_temp(self, file_path: Path | zipfile.Path) -> tuple[Path, Path]:
        """
        Extract a file from zipfile.Path to a temporary location

        Returns:
            Tuple of (temp_dir, extracted_file_path)
        """
        temp_dir = Path(tempfile.mkdtemp())
        extracted = temp_dir / file_path.name

        try:
            with file_path.open("rb") as src, open(extracted, "wb") as dst:
                shutil.copyfileobj(src, dst)
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise

        return temp_dir, extracted

    def load_symbol_lib(
        self,
        symbol_path: Path | zipfile.Path,
        dcm_path: Path | zipfile.Path | None = None,
    ) -> tuple[SymbolLib, str]:
        """
        Load a symbol library from a path in a zip file

        Returns:
            Tuple of (SymbolLib object, symbol name)
        """
        temp_dir, extracted_path = self.extract_file_to_temp(symbol_path)

        # Extract DCM file to same directory if available
        if dcm_path:
            try:
                with dcm_path.open("rb") as src, open(temp_dir / dcm_path.name, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            except Exception as e:
                logger.warning(f"Failed to extract DCM file: {e}")

        try:
            # Always try to convert to new format
            if extracted_path.suffix == ".lib":
                if cli is not None and cli.exists():
                    new_path = extracted_path.with_suffix(".kicad_sym")
                    cli.upgrade_sym_lib(str(extracted_path), str(new_path))
                    if new_path.exists():
                        symbol_lib = SymbolLib().from_file(str(new_path))
                    else:
                        logger.error(f"Conversion failed for {extracted_path}")
                        raise ValueError(f"Failed to convert {extracted_path} to new KiCad format")
                else:
                    logger.error("KiCad CLI not available for .lib conversion")
                    raise ValueError("KiCad CLI not available for .lib conversion")
            else:  # .kicad_sym - still try to convert just to be sure
                if cli is not None and cli.exists():
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

    def extract_footprint(self, footprint_path: Path | zipfile.Path) -> tuple[Path, Path]:
        """
        Extract and upgrade a footprint to a temporary location

        Returns:
            Tuple of (temp_dir, footprint_file) with the file named after the cleaned
            footprint name from its content
        """
        if footprint_path.is_dir():
            kicad_mod = next(
                (i for i in footprint_path.iterdir() if i.name.endswith(".kicad_mod")), None
            )
            if kicad_mod is None:
                raise ValueError("No .kicad_mod file found in directory")
            footprint_path = kicad_mod

        temp_dir, temp_file = self.extract_file_to_temp(footprint_path)
        try:
            if cli is not None and cli.exists():
                try:
                    # kicad-cli only upgrades whole .pretty libraries
                    temp_pretty = temp_dir / "temp.pretty"
                    temp_pretty.mkdir()
                    shutil.copy2(temp_file, temp_pretty / temp_file.name)
                    result = cli.upgrade_footprint_lib(pretty_folder=str(temp_pretty), force=True)

                    if result.success:
                        upgraded_file = temp_pretty / temp_file.name

                        if upgraded_file.exists():
                            temp_file = upgraded_file
                            logger.info(f"Successfully upgraded footprint: {temp_file.name}")
                        else:
                            logger.warning(f"Upgrade output not found for {temp_file.name}")
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

            footprint_file = temp_dir / f"{self.cleanName(footprint_name)}.kicad_mod"
            if temp_file != footprint_file:
                os.replace(temp_file, footprint_file)
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise

        logger.info(f"Extracted footprint: {footprint_file.stem}")
        return temp_dir, footprint_file

    def update_footprint_with_model(
        self, footprint_file: Path, model_name: str, remote_type: REMOTE_TYPES
    ) -> None:
        """Point the footprint's 3D model reference to model_name in the library's 3dshapes dir"""
        lib_name = self.get_lib_name(remote_type)
        model_path = f"{self.KICAD_3RD_PARTY_LINK}/{lib_name}.3dshapes/{model_name}"
        content = footprint_file.read_text(encoding="utf-8")
        updated_content = self.footprint_parser.update_or_add_model(content, model_path)
        footprint_file.write_text(updated_content, encoding="utf-8")

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

            lib_name = self.get_lib_name(remote_type)
            if footprint_prop:
                # Update the footprint reference with library prefix
                old_value = footprint_prop.value
                footprint_prop.value = f"{lib_name}:{footprint_name}"
                logger.debug(f"Updated footprint property: {old_value} -> {footprint_prop.value}")
            else:
                # Add footprint property if it doesn't exist
                new_prop = Property(
                    key="Footprint",
                    value=f"{lib_name}:{footprint_name}",
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

    @staticmethod
    def _prepare_target(path: Path, backups: dict[Path, Path | None]) -> None:
        """Create the parent directory and register path for rollback (None = new file)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            backups[path] = None
            return
        fd, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".backup")
        os.close(fd)
        backup_path = Path(name)
        try:
            shutil.copy2(path, backup_path)
        except BaseException:
            backup_path.unlink(missing_ok=True)
            raise
        backups[path] = backup_path

    def _compresses(self, model_path: Path) -> bool:
        return self.compress_models and model_path.suffix.lower() in (".step", ".stp")

    def _write_model(self, model_path: Path, dest: str) -> None:
        if self._compresses(model_path):
            with open(model_path, "rb") as f_in, gzip.open(dest, "wb", compresslevel=9) as f_out:
                shutil.copyfileobj(f_in, f_out)
        else:
            shutil.copyfile(model_path, dest)

    def save_to_library(
        self,
        symbol_lib: SymbolLib | None,
        footprint_path: Path | None,
        model_path: Path | None,
        remote_type: REMOTE_TYPES,
        symbol_name: str,
        overwrite_if_exists: bool = True,
    ) -> bool:
        """
        Save the component to the KiCad library; all written files are rolled back on failure

        Returns:
            True if successful, False otherwise
        """
        lib_name = self.get_lib_name(remote_type)
        success_items = []
        backups: dict[Path, Path | None] = {}

        try:
            if symbol_lib:
                lib_file_path = self.DEST_PATH / f"{lib_name}.kicad_sym"
                existing_lib = (
                    SymbolLib().from_file(str(lib_file_path))
                    if lib_file_path.exists()
                    else SymbolLib()
                )
                symbol_exists = symbol_name in [s.entryName for s in existing_lib.symbols]

                if symbol_exists and not overwrite_if_exists:
                    self.print(f"Symbol {symbol_name} already exists in library. Skipping.")
                    self.lib_skipped = True
                else:
                    existing_lib.symbols = [
                        s for s in existing_lib.symbols if s.entryName != symbol_name
                    ] + symbol_lib.symbols
                    action = "updated" if symbol_exists else "added"

                    def write_verified(tmp_path: str) -> None:
                        existing_lib.to_file(tmp_path)
                        if not SymbolLib().from_file(tmp_path).symbols:
                            raise ValueError(
                                "Library verification failed: written library is empty"
                            )

                    self._prepare_target(lib_file_path, backups)
                    atomic_write(str(lib_file_path), write_verified)

                    if cli is not None:
                        result = cli.upgrade_sym_lib(str(lib_file_path), str(lib_file_path))
                        if not result.success:
                            raise ValueError(
                                f"Updating {lib_file_path} failed: {result.message} "
                                + f"details: {result.stderr}"
                            )

                    success_items.append(f"{action} symbol {symbol_name}")
                    self.print(f"{action.capitalize()} symbol {symbol_name} in library")

            model_file: Path | None = None
            if model_path:
                compressed = self._compresses(model_path)
                model_name = model_path.name + ".gz" if compressed else model_path.name
                model_file = self.DEST_PATH / f"{lib_name}.3dshapes" / model_name

            if footprint_path:
                if model_file:
                    self.update_footprint_with_model(footprint_path, model_file.name, remote_type)

                footprint_file = self.DEST_PATH / f"{lib_name}.pretty" / footprint_path.name
                if footprint_file.exists() and not overwrite_if_exists:
                    self.print(f"Footprint {footprint_file.name} already exists. Skipping.")
                    self.footprint_skipped = True
                else:
                    self._prepare_target(footprint_file, backups)
                    atomic_write(
                        str(footprint_file), lambda tmp: shutil.copyfile(footprint_path, tmp)
                    )
                    success_items.append(f"saved footprint {footprint_file.stem}")
                    self.print(f"Saved footprint {footprint_file.stem}")

            if model_path and model_file:
                if model_file.exists() and not overwrite_if_exists:
                    self.print(f"3D model {model_file.name} already exists. Skipping.")
                    self.model_skipped = True
                else:
                    self._prepare_target(model_file, backups)
                    atomic_write(str(model_file), lambda tmp: self._write_model(model_path, tmp))

                    success_items.append(f"saved 3D model {model_file.name}")
                    self.print(f"Saved 3D model {model_file.name}")

            for backup_path in backups.values():
                if backup_path:
                    backup_path.unlink(missing_ok=True)

            if success_items:
                logger.info(f"Saved: {', '.join(success_items)}")

            return True

        except Exception as e:
            logger.error(f"Error during save_to_library: {e}")
            self.print(f"Error during save: {e}")

            for path, backup_path in backups.items():
                try:
                    if backup_path:
                        os.replace(backup_path, path)
                    else:
                        path.unlink(missing_ok=True)
                    logger.info(f"Rolled back: {path}")
                except OSError as rollback_error:
                    logger.error(f"Failed to roll back {path}: {rollback_error}")

            return False

    def import_all(
        self, zip_file: Path, overwrite_if_exists: bool = True
    ) -> tuple[str, ...] | None:
        """
        Import symbols, footprints, and 3D models from a zip file

        Returns:
            ("OK",) on success, ("Warning",) if parts could not be imported, None on failure
        """
        logger.info(f"Importing {zip_file.name}")

        self._reset_import_state()

        if not zipfile.is_zipfile(zip_file):
            logger.error(f"{zip_file} is not a valid zip file")
            self.print(f"Error: {zip_file} is not a valid zip file")
            return None

        self.print(f"Import: {zip_file}")

        temp_dirs: list[Path] = []
        failed: list[str] = []  # Parts present in the archive that could not be imported

        try:
            with zipfile.ZipFile(zip_file) as zf:
                remote_type, files = self.identify_remote_type(zf)
                logger.info(f"Type: {remote_type.name}")
                self.print(f"Identified as {remote_type.name}")

                if remote_type == REMOTE_TYPES.Partial:
                    logger.warning("Archive contains incomplete data - partial import only")
                    self.print("Warning: Archive contains incomplete data")

                symbol_lib = None
                symbol_name = "unknown"
                if files["symbol"]:
                    symbol_lib, symbol_name = self.load_symbol_lib(
                        files["symbol"], files.get("dcm")
                    )
                    logger.info(f"Loaded symbol: {symbol_name}")

                footprint_path = None
                if files["footprint"]:
                    try:
                        footprint_temp_dir, footprint_path = self.extract_footprint(
                            files["footprint"]
                        )
                    except Exception as e:
                        logger.warning(f"Failed to extract footprint: {e}")
                        self.print(f"Warning: Failed to extract footprint: {e}")
                        failed.append("footprint")
                    else:
                        temp_dirs.append(footprint_temp_dir)

                model_path = None
                if files["model"]:
                    try:
                        model_temp_dir, model_path = self.extract_file_to_temp(files["model"])
                    except Exception as e:
                        logger.warning(f"Failed to load 3D model: {e}")
                        self.print(f"Warning: Failed to load 3D model: {e}")
                        failed.append("3D model")
                    else:
                        temp_dirs.append(model_temp_dir)

                if symbol_lib and footprint_path:
                    symbol_lib = self.update_symbol_properties(
                        symbol_lib, footprint_path.stem, remote_type
                    )

                if symbol_lib or footprint_path or model_path:
                    success = self.save_to_library(
                        symbol_lib=symbol_lib,
                        footprint_path=footprint_path,
                        model_path=model_path,
                        remote_type=remote_type,
                        symbol_name=symbol_name,
                        overwrite_if_exists=overwrite_if_exists,
                    )

                    if success:
                        if failed:
                            msg = f"Import incomplete: {' and '.join(failed)} missing"
                            logger.warning(msg)
                            self.print(msg)
                            return ("Warning",)
                        if self.lib_skipped and self.footprint_skipped and self.model_skipped:
                            logger.info("Import completed - all files already exist")
                            self.print("Import completed")
                        elif self.lib_skipped or self.footprint_skipped or self.model_skipped:
                            logger.info("Import completed with some items skipped")
                            self.print("Import successful (some items already existed)")
                        else:
                            logger.info("Import completed successfully")
                            self.print("Import successful")
                        return ("OK",)
                    else:
                        logger.warning("Import failed during save")
                        self.print("Import failed during save")
                        return None
                else:
                    logger.warning("No content to import")
                    self.print("Warning: No content found to import")
                    return None

        except Exception as e:
            logger.error(f"Import failed: {str(e)}")
            self.print(f"Error during import: {str(e)}")
            logging.exception("Import error")
            return None
        finally:
            for temp_dir in temp_dirs:
                shutil.rmtree(temp_dir, ignore_errors=True)


def main(
    lib_file: str | Path,
    lib_folder: str | Path,
    overwrite: bool = False,
    KICAD_3RD_PARTY_LINK: str = "${KICAD_3RD_PARTY}",
    lib_name: str | None = None,
    compress_models: bool = False,
) -> None:
    lib_folder = Path(lib_folder)
    lib_file = Path(lib_file)

    logger.info(f"Starting import: {lib_file.name} -> {lib_folder}")

    if not lib_folder.is_dir():
        logger.error(f"Destination folder {lib_folder} does not exist")
        print(f"Error destination folder {lib_folder} does not exist!")
        return

    if not lib_file.is_file():
        logger.error(f"File {lib_file} not found")
        print(f"Error: file {lib_file} to be imported was not found!")
        return

    impart = LibImporter(lib_name=lib_name, compress_models=compress_models)
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
