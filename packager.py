#!/usr/bin/env python3
"""
KiCad Plugin Packager
Creates clean ZIP package with embedded dependencies for old API and requirements.txt for new API
"""

import os
import shutil
import subprocess
import zipfile
import json
from datetime import datetime
import tempfile
from pathlib import Path


def check_git_available():
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def clean_pycache_files(directory):
    print("Cleaning cache files...")
    removed_count = 0

    for root, dirs, files in os.walk(directory, topdown=True):
        for d in list(dirs):
            if d == "__pycache__":
                pycache_path = os.path.join(root, d)
                shutil.rmtree(pycache_path, ignore_errors=True)
                dirs.remove(d)
                removed_count += 1

        for file in files:
            if file.endswith(".pyc"):
                pyc_path = os.path.join(root, file)
                os.remove(pyc_path)
                removed_count += 1

    if removed_count > 0:
        print(f"  Removed {removed_count} cache files")


def install_pip_dependencies(target_dir):
    print("Installing pip dependencies...")

    site_packages = target_dir / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)

    pip_dependencies = ["easyeda2kicad>=0.6.5"]

    success_count = 0
    for dep in pip_dependencies:
        try:
            subprocess.run(
                [
                    "pip",
                    "install",
                    "--target",
                    str(site_packages),
                    "--no-deps",
                    "--disable-pip-version-check",
                    "--upgrade",
                    dep,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            print(f"  ✓ {dep}")
            success_count += 1
        except subprocess.CalledProcessError:
            print(f"  ✗ {dep}")

    return success_count


def install_git_dependencies(target_dir):
    if not check_git_available():
        return handle_git_fallback(target_dir)

    print("Installing git dependencies...")

    site_packages = target_dir / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)

    git_dependencies = [
        {
            "name": "kiutils",
            "url": "https://github.com/Steffen-W/kiutils.git",
            "branch": "v1.4.9",
            "subdirectory": "src/kiutils",
        }
    ]

    success_count = 0
    for git_dep in git_dependencies:
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                subprocess.run(
                    [
                        "git",
                        "clone",
                        "--depth",
                        "1",
                        "--branch",
                        git_dep["branch"],
                        git_dep["url"],
                        temp_dir,
                    ],
                    check=True,
                    capture_output=True,
                )

                source_path = Path(temp_dir) / git_dep["subdirectory"]
                target_path = site_packages / git_dep["name"]

                if source_path.exists():
                    if target_path.exists():
                        shutil.rmtree(target_path)

                    shutil.copytree(source_path, target_path)
                    print(f"  ✓ {git_dep['name']}")
                    success_count += 1
        except subprocess.CalledProcessError:
            print(f"  ✗ {git_dep['name']}")

    return success_count


def handle_git_fallback(target_dir):
    site_packages = target_dir / "site-packages"
    existing_kiutils = Path("plugins/kiutils")

    if existing_kiutils.exists() and existing_kiutils.is_dir():
        print("Using existing kiutils...")
        target_kiutils = site_packages / "kiutils"

        if target_kiutils.exists():
            shutil.rmtree(target_kiutils)

        shutil.copytree(existing_kiutils, target_kiutils)
        print("  ✓ kiutils (from existing)")
        return 1
    else:
        print("  ✗ kiutils (git unavailable, no existing found)")
        return 0


def cleanup_dependencies(site_packages_dir):
    print("Cleaning dependencies...")

    cleanup_patterns = [
        "*.dist-info",
        "*.egg-info",
        "tests",
        "test",
        "__pycache__",
        "*.pyc",
        "*.pyo",
        "example*",
        "demo*",
        "doc*",
        "*.md",
        "LICENSE*",
        "CHANGELOG*",
        "README*",
    ]

    removed_count = 0
    for root, dirs, files in os.walk(site_packages_dir):
        for d in list(dirs):
            for pattern in cleanup_patterns:
                if pattern.endswith("*"):
                    if d.startswith(pattern[:-1]):
                        shutil.rmtree(os.path.join(root, d), ignore_errors=True)
                        dirs.remove(d)
                        removed_count += 1
                        break
                elif d == pattern:
                    shutil.rmtree(os.path.join(root, d), ignore_errors=True)
                    dirs.remove(d)
                    removed_count += 1
                    break

        for f in files:
            for pattern in cleanup_patterns:
                if pattern.endswith("*"):
                    if f.startswith(pattern[:-1]):
                        os.remove(os.path.join(root, f))
                        removed_count += 1
                        break
                elif f.endswith(pattern.replace("*", "")):
                    os.remove(os.path.join(root, f))
                    removed_count += 1
                    break

    if removed_count > 0:
        print(f"  Cleaned {removed_count} files")


def create_requirements_txt(build_dir):
    print("Creating requirements.txt...")

    requirements_content = """# KiCad Plugin Requirements (New Plugin Manager API)
kicad-python>=0.3.0
easyeda2kicad>=0.6.5
git+https://github.com/Steffen-W/kiutils@v1.4.9
"""

    requirements_path = build_dir / "plugins" / "requirements.txt"
    with open(requirements_path, "w", encoding="utf-8") as f:
        f.write(requirements_content)


def update_metadata(build_dir):
    print("Updating metadata...")

    metadata_path = build_dir / "metadata.json"

    try:
        with open("metadata.json", "r", encoding="utf-8") as f:
            metadata = json.load(f)

        today = datetime.now().strftime("%Y.%m.%d")
        if "versions" in metadata and len(metadata["versions"]) > 0:
            metadata["versions"][0]["version"] = today

        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

    except Exception:
        if os.path.exists("metadata.json"):
            shutil.copy2("metadata.json", metadata_path)


def create_installation_script(build_dir):
    print("Creating installation script...")

    install_script = '''#!/usr/bin/env python3
"""
KiCad Plugin Dependency Installer
Installs missing dependencies for old plugin API
"""

import subprocess
import sys
import os
from pathlib import Path

def main():
    print("KiCad Plugin Dependency Installer")
    print("=" * 40)
    
    script_dir = Path(__file__).resolve().parent
    plugin_dir = script_dir / 'plugins'
    lib_dir = plugin_dir / 'lib' / 'site-packages'
    
    if not plugin_dir.exists():
        print("Error: Plugin directory not found!")
        return
    
    lib_dir.mkdir(parents=True, exist_ok=True)
    print(f"Installing to: {lib_dir}")
    
    pip_dependencies = ['easyeda2kicad>=0.6.5']
    git_dependencies = [{
        'name': 'kiutils',
        'url': 'https://github.com/Steffen-W/kiutils.git',
        'branch': 'v1.4.9',
        'path': 'src/kiutils'
    }]
    
    success_count = 0
    total_count = len(pip_dependencies) + len(git_dependencies)
    
    # Install pip dependencies
    for dep in pip_dependencies:
        print(f"Installing {dep}...")
        try:
            subprocess.check_call([
                sys.executable, '-m', 'pip', 'install',
                '--target', str(lib_dir), '--upgrade', dep
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("  ✓ SUCCESS")
            success_count += 1
        except subprocess.CalledProcessError:
            print("  ✗ FAILED")
    
    # Install git dependencies
    for git_dep in git_dependencies:
        print(f"Installing {git_dep['name']} from git...")
        try:
            import tempfile
            import shutil
            
            with tempfile.TemporaryDirectory() as temp_dir:
                subprocess.check_call([
                    'git', 'clone', '--depth', '1', '--branch', git_dep['branch'],
                    git_dep['url'], temp_dir
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                source_path = Path(temp_dir) / git_dep['path']
                target_path = lib_dir / git_dep['name']
                
                if target_path.exists():
                    shutil.rmtree(target_path)
                
                shutil.copytree(source_path, target_path)
                print("  ✓ SUCCESS")
                success_count += 1
                
        except Exception:
            print("  ✗ FAILED")
    
    print(f"\\nInstallation complete: {success_count}/{total_count} successful")
    
    if success_count == total_count:
        print("All dependencies installed successfully!")
    else:
        print("Some dependencies failed to install.")

if __name__ == '__main__':
    main()
'''

    install_script_path = build_dir / "install_dependencies.py"
    with open(install_script_path, "w", encoding="utf-8") as f:
        f.write(install_script)


def copy_plugin_files(build_dir):
    print("Copying plugin files...")

    def ignore_function(dir, files):
        ignore_patterns = [
            "__pycache__",
            ".pyc",
            ".pyo",
            ".git",
            ".gitignore",
            "build",
            "dist",
            "*.egg-info",
            "venv",
            "env",
        ]

        ignored = []
        for file in files:
            for pattern in ignore_patterns:
                if pattern.startswith(".") and file.endswith(pattern):
                    ignored.append(file)
                    break
                elif file == pattern or (
                    pattern.startswith("*") and file.endswith(pattern[1:])
                ):
                    ignored.append(file)
                    break

        return ignored

    for src_dir in ["plugins", "resources"]:
        if os.path.exists(src_dir):
            dst_dir = build_dir / src_dir
            shutil.copytree(src_dir, dst_dir, ignore=ignore_function)

    files_to_copy = ["metadata.json"]
    for file in files_to_copy:
        if os.path.exists(file):
            shutil.copy2(file, build_dir / file)


def create_zip_package(build_dir, zip_name="Import-LIB-KiCad-Plugin.zip"):
    print("Creating ZIP package...")

    if os.path.exists(zip_name):
        os.remove(zip_name)

    with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
        file_count = 0

        for root, dirs, files in os.walk(build_dir):
            dirs[:] = [d for d in dirs if d != "__pycache__"]

            for file in files:
                if not file.endswith((".pyc", ".pyo")):
                    file_path = os.path.join(root, file)
                    arc_path = os.path.relpath(file_path, build_dir)
                    zipf.write(file_path, arc_path)
                    file_count += 1

    zip_size_mb = os.path.getsize(zip_name) / (1024 * 1024)
    print(f"  Created {zip_name} ({file_count} files, {zip_size_mb:.1f} MB)")

    return zip_name


def main():
    print("KiCad Plugin Packager")
    print("=" * 30)

    required_dirs = ["plugins", "resources"]
    missing_dirs = [d for d in required_dirs if not os.path.exists(d)]

    if missing_dirs:
        print(f"Error: Missing directories: {missing_dirs}")
        return False

    with tempfile.TemporaryDirectory() as temp_dir:
        build_dir = Path(temp_dir) / "build"
        build_dir.mkdir()

        try:
            copy_plugin_files(build_dir)
            clean_pycache_files(build_dir)

            lib_dir = build_dir / "plugins" / "lib"
            lib_dir.mkdir(exist_ok=True)

            pip_success = install_pip_dependencies(lib_dir)
            git_success = install_git_dependencies(lib_dir)

            if pip_success > 0 or git_success > 0:
                cleanup_dependencies(lib_dir / "site-packages")

            create_requirements_txt(build_dir)
            update_metadata(build_dir)
            create_installation_script(build_dir)

            zip_name = create_zip_package(build_dir)

            print(f"\nPackage created successfully: {os.path.abspath(zip_name)}")
            return True

        except Exception as e:
            print(f"Error: {e}")
            return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
