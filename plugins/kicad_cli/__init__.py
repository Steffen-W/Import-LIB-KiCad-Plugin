import subprocess


class kicad_cli:
    def run_kicad_cli(self, command):
        try:
            result = subprocess.run(
                ["kicad-cli"] + command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            # print(result.stdout.strip())
            return True
        except subprocess.CalledProcessError as e:
            print(" ".join(["kicad-cli"] + command))
            print(f"Error: {e.stderr}")
            return None

    def exists(self):

        def version_to_tuple(version_str):
            try:
                return tuple(map(int, version_str.split("-")[0].split(".")))
            except (ValueError, AttributeError) as e:
                print(f"Version extractions error '{version_str}': {e}")
                return None

        try:
            result = subprocess.run(
                ["kicad-cli", "--version"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            version = result.stdout.strip()
            minVersion = "8.0.4"
            KiCadVers = version_to_tuple(version)
            if not KiCadVers or KiCadVers < version_to_tuple(minVersion):
                print("KiCad Version", version)
                print("Minimum required KiCad version is", minVersion)
                return False
            else:
                return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("kicad-cli does not exist")
            return False

    def upgrade_sym_lib(self, input_file, output_file):
        return self.run_kicad_cli(["sym", "upgrade", input_file, "-o", output_file])

    def upgrade_footprint_lib(self, pretty_folder):
        return self.run_kicad_cli(["fp", "upgrade", pretty_folder])


if __name__ == "__main__":
    cli = kicad_cli()
    if cli.exists():
        input_file = "UltraLibrarian_kicad_sym.kicad_sym"
        output_file = "UltraLibrarian.kicad_sym"

        cli.upgrade_sym_lib(input_file, output_file)
        cli.upgrade_footprint_lib("test.pretty")
