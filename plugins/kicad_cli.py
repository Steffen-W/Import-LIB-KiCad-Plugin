import subprocess


def run_kicad_cli(command):
    try:
        result = subprocess.run(
            ["kicad-cli"] + command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(" ".join(["kicad-cli"] + command))
        print(f"Error: {e.stderr}")
        return None


def check_kicad_cli_exists():
    try:
        subprocess.run(
            ["kicad-cli", "--version"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("kicad-cli does not exist")
        return False


def upgrade_sym_lib(input_file, output_file):
    res = run_kicad_cli(["sym", "upgrade", input_file, "-o", output_file])
    if res:
        return True
    return False


def upgrade_footprint_lib(pretty_folder):
    res = run_kicad_cli(["fp", "upgrade", pretty_folder])
    if res:
        return True
    return False


if __name__ == "__main__":
    check_kicad_cli_exists()
    input_file = "UltraLibrarian_kicad_sym.kicad_sym"
    output_file = "UltraLibrarian.kicad_sym2"

    upgrade_sym_lib(input_file, output_file)
    upgrade_footprint_lib("test.pretty")
