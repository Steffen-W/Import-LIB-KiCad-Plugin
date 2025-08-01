#!/usr/bin/env python3
# coding: utf-8

# Assembles local KiCad component libraries from downloaded Octopart,
# Samacsys, Ultralibrarian and Snapeda zipfiles using kiutils.
# Supports KiCad 7.0 and newer.

from pathlib import Path
from .__init__ import *
import logging

logger = logging.getLogger(__name__)

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
