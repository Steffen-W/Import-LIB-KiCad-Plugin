from pathlib import Path


def find_old_lib_files(
    folder_path: str,
    libs: list[str] = ["Octopart", "Samacsys", "UltraLibrarian", "Snapeda", "EasyEDA"],
) -> list:
    folder_path = Path(folder_path)
    found_files = []

    for file in folder_path.iterdir():
        entry = {}
        for lib in libs:
            if file.is_file() and file.name.startswith(lib):
                if file.name.endswith(".lib") or file.name.endswith(
                    "_kicad_sym.kicad_sym"
                ):
                    entry["libName"] = lib
                    entry["lib"] = file

                    dcm_file = file.with_suffix(".dcm")
                    if dcm_file.exists() and dcm_file.is_file():
                        entry["dcm"] = dcm_file

                    found_files.append(entry)

    return found_files
