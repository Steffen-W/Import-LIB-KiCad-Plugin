#!/usr/bin/env python3
import os
import shutil
import subprocess
import zipfile
import json
from datetime import datetime
import tempfile


def clean_pycache_files(directory):
    """Remove all __pycache__ directories and .pyc files"""
    print("Cleaning __pycache__ and .pyc files...")
    for root, dirs, files in os.walk(directory, topdown=True):
        # Remove __pycache__ directories
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for d in list(dirs):
            if d == "__pycache__":
                pycache_path = os.path.join(root, d)
                print(f"Removing {pycache_path}")
                shutil.rmtree(pycache_path, ignore_errors=True)

        # Remove .pyc files
        for file in files:
            if file.endswith(".pyc"):
                pyc_path = os.path.join(root, file)
                print(f"Removing {pyc_path}")
                os.remove(pyc_path)


def clone_git_dependency(repo_url, branch_or_tag, subdirectory, target_dir):
    """Clone a specific subdirectory from a git repository"""
    print(f"Cloning {repo_url}@{branch_or_tag} subdirectory: {subdirectory}")

    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # Clone the repository
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    "--branch",
                    branch_or_tag,
                    repo_url,
                    temp_dir,
                ],
                check=True,
                capture_output=True,
            )

            # Copy the specific subdirectory
            source_path = os.path.join(temp_dir, subdirectory)
            if os.path.exists(source_path):
                # Get the final directory name (e.g., "kiutils" from "src/kiutils")
                target_name = os.path.basename(subdirectory)
                target_path = os.path.join(target_dir, target_name)

                # Remove existing directory if it exists
                if os.path.exists(target_path):
                    shutil.rmtree(target_path)

                shutil.copytree(source_path, target_path)
                print(f"✓ Successfully cloned {target_name} from {repo_url}")
                return True
            else:
                print(f"✗ Subdirectory {subdirectory} not found in {repo_url}")
                return False

        except subprocess.CalledProcessError as e:
            print(f"✗ Failed to clone {repo_url}: {e}")
            return False
        except Exception as e:
            print(f"✗ Error processing git dependency: {e}")
            return False


def check_git_available():
    """Check if git is available"""
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def install_dependencies_properly(target_dir):
    """Install dependencies with proper structure"""
    print("Installing dependencies to proper site-packages structure...")

    # Create site-packages directory
    site_packages = os.path.join(target_dir, "site-packages")
    os.makedirs(site_packages, exist_ok=True)

    # Regular pip dependencies
    pip_dependencies = [
        "easyeda2kicad>=0.6.5",
        # kicad-python wird oft von KiCad selbst bereitgestellt
    ]

    # Git dependencies
    git_dependencies = [
        {
            "url": "https://github.com/Steffen-W/kiutils.git",
            "branch": "v1.4.9",
            "subdirectory": "src/kiutils",
        }
    ]

    # Install pip dependencies
    for dep in pip_dependencies:
        try:
            print(f"Installing {dep}...")
            result = subprocess.run(
                [
                    "pip",
                    "install",
                    "--target",
                    site_packages,
                    "--no-deps",
                    "--disable-pip-version-check",
                    "--upgrade",
                    dep,
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            print(f"✓ Successfully installed {dep}")

        except subprocess.CalledProcessError as e:
            print(f"⚠ Failed to install {dep}: {e.stderr}")

            # Try alternative: download source and extract manually
            try:
                print(f"Trying alternative installation for {dep}...")
                download_source_package(dep, site_packages)
            except Exception as e2:
                print(f"✗ Alternative installation also failed: {e2}")

    # Install git dependencies
    if check_git_available():
        for git_dep in git_dependencies:
            success = clone_git_dependency(
                git_dep["url"],
                git_dep["branch"],
                git_dep["subdirectory"],
                site_packages,
            )
            if not success:
                print(f"⚠ Failed to install git dependency from {git_dep['url']}")
                # Try fallback: use existing manual kiutils if present
                existing_kiutils = os.path.join("plugins", "kiutils")
                if os.path.exists(existing_kiutils):
                    print("📁 Found existing manual kiutils, copying...")
                    target_kiutils = os.path.join(site_packages, "kiutils")
                    if os.path.exists(target_kiutils):
                        shutil.rmtree(target_kiutils)
                    shutil.copytree(existing_kiutils, target_kiutils)
                    print("✓ Copied existing kiutils to site-packages")
    else:
        print("⚠ Git not available, trying fallback for git dependencies...")
        # Use existing manual kiutils if present
        existing_kiutils = os.path.join("plugins", "kiutils")
        if os.path.exists(existing_kiutils):
            print("📁 Found existing manual kiutils, copying...")
            target_kiutils = os.path.join(site_packages, "kiutils")
            if os.path.exists(target_kiutils):
                shutil.rmtree(target_kiutils)
            shutil.copytree(existing_kiutils, target_kiutils)
            print("✓ Copied existing kiutils to site-packages")
        else:
            print("✗ Git not available and no existing kiutils found")
            print("  Please install git or manually add kiutils to plugins/kiutils/")


def download_source_package(package_spec, target_dir):
    """Download and extract source package manually"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Download source
        subprocess.run(
            [
                "pip",
                "download",
                "--no-binary",
                ":all:",
                "--no-deps",
                "--dest",
                temp_dir,
                package_spec,
            ],
            check=True,
        )

        # Find and extract downloaded file
        for file in os.listdir(temp_dir):
            if file.endswith((".tar.gz", ".zip")):
                # Extract and copy Python files
                import tarfile

                archive_path = os.path.join(temp_dir, file)
                extract_dir = os.path.join(temp_dir, "extracted")

                if file.endswith(".tar.gz"):
                    with tarfile.open(archive_path, "r:gz") as tar:
                        tar.extractall(extract_dir)

                # Find the actual package directory
                for root, dirs, files in os.walk(extract_dir):
                    for dir_name in dirs:
                        if not dir_name.startswith(".") and any(
                            f.endswith(".py")
                            for f in os.listdir(os.path.join(root, dir_name))
                        ):
                            package_source = os.path.join(root, dir_name)
                            package_dest = os.path.join(target_dir, dir_name)
                            if os.path.exists(package_source):
                                shutil.copytree(
                                    package_source, package_dest, dirs_exist_ok=True
                                )
                                print(f"✓ Manually installed {dir_name}")
                                return


def create_proper_bootstrap(plugins_dir):
    """Create proper bootstrap code for dependency loading"""
    bootstrap_code = '''# KiCad Plugin Bootstrap - Enhanced Version
import sys
import os

def setup_dependencies():
    """Setup dependency paths for KiCad plugin"""
    
    # Get the plugin directory
    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    lib_dir = os.path.join(plugin_dir, 'lib')
    
    # Add multiple possible dependency paths
    dependency_paths = [
        os.path.join(lib_dir, 'site-packages'),  # Standard pip --target location
        lib_dir,  # Direct lib directory
    ]
    
    # Add all existing paths to sys.path
    added_paths = []
    for path in dependency_paths:
        if os.path.exists(path) and path not in sys.path:
            sys.path.insert(0, path)
            added_paths.append(path)
    
    if added_paths:
        print(f"KiCad Plugin: Added dependency paths: {added_paths}")
    
    # Try to import and verify critical dependencies
    try:
        import easyeda2kicad
        print("✓ easyeda2kicad loaded successfully")
    except ImportError as e:
        print(f"⚠ easyeda2kicad import failed: {e}")
        try_auto_install('easyeda2kicad>=0.6.5')
    
    try:
        import kiutils
        print("✓ kiutils loaded successfully")
    except ImportError as e:
        print(f"⚠ kiutils import failed: {e}")
        # kiutils is custom, so try git installation
        try_auto_install_git('https://github.com/Steffen-W/kiutils.git', 'v1.4.9', 'src/kiutils')

def try_auto_install_git(repo_url, branch_tag, subdirectory):
    """Try to auto-install git dependency"""
    try:
        import subprocess
        import tempfile
        
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        target_dir = os.path.join(plugin_dir, 'lib', 'site-packages')
        
        print(f"Attempting auto-install from git: {repo_url}")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Clone repository
            subprocess.check_call([
                'git', 'clone', '--depth', '1', '--branch', branch_tag,
                repo_url, temp_dir
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Copy subdirectory
            source_path = os.path.join(temp_dir, subdirectory)
            if os.path.exists(source_path):
                target_name = os.path.basename(subdirectory)
                target_path = os.path.join(target_dir, target_name)
                
                if os.path.exists(target_path):
                    shutil.rmtree(target_path)
                
                shutil.copytree(source_path, target_path)
                
                # Add to path immediately
                if target_dir not in sys.path:
                    sys.path.insert(0, target_dir)
                
                print(f"✓ Auto-installed {target_name} from git")
                return True
        
        return False
    except Exception as e:
        print(f"✗ Git auto-install failed: {e}")
        return False

def try_auto_install(package):
    """Try to auto-install missing package"""
    try:
        import subprocess
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        target_dir = os.path.join(plugin_dir, 'lib', 'site-packages')
        
        print(f"Attempting auto-install of {package}...")
        subprocess.check_call([
            sys.executable, '-m', 'pip', 'install',
            '--target', target_dir, '--no-deps', package
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Add to path immediately
        if target_dir not in sys.path:
            sys.path.insert(0, target_dir)
        
        print(f"✓ Auto-installed {package}")
        return True
    except Exception as e:
        print(f"✗ Auto-install failed: {e}")
        return False

# Execute setup immediately when imported
setup_dependencies()

# Note: wxPython is provided by KiCad - no separate import needed
'''

    # Find and modify the main plugin file
    main_files = ["__main__.py", "__init__.py"]

    for main_file in main_files:
        main_path = os.path.join(plugins_dir, main_file)
        if os.path.exists(main_path):
            with open(main_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Only add bootstrap if not already present
            if "setup_dependencies()" not in content:
                with open(main_path, "w", encoding="utf-8") as f:
                    f.write(bootstrap_code + "\n\n" + content)
                print(f"✓ Added bootstrap to {main_file}")
                break
    else:
        # Create __init__.py if none exists
        init_path = os.path.join(plugins_dir, "__init__.py")
        with open(init_path, "w", encoding="utf-8") as f:
            f.write(bootstrap_code)
        print("✓ Created __init__.py with bootstrap code")


def create_clean_zip_package():
    """Create a clean, optimized ZIP package"""

    print("🧹 Creating clean KiCad plugin package...")

    # Cleanup
    if os.path.exists("Import-LIB-KiCad-Plugin.zip"):
        os.remove("Import-LIB-KiCad-Plugin.zip")

    with tempfile.TemporaryDirectory() as temp_dir:
        build_dir = os.path.join(temp_dir, "build")
        os.makedirs(build_dir)

        print("📁 Copying plugin files...")

        # Copy main directories, excluding __pycache__
        def copy_without_pycache(src, dst):
            def ignore_pycache(dir, files):
                return ["__pycache__"] + [f for f in files if f.endswith(".pyc")]

            shutil.copytree(src, dst, ignore=ignore_pycache)

        copy_without_pycache("plugins", os.path.join(build_dir, "plugins"))
        copy_without_pycache("resources", os.path.join(build_dir, "resources"))

        # Update metadata
        with open("metadata.json", "r") as f:
            metadata = json.load(f)

        today = datetime.now().strftime("%Y.%m.%d")
        metadata["versions"][0]["version"] = today

        with open(os.path.join(build_dir, "metadata.json"), "w") as f:
            json.dump(metadata, f, indent=2)

        # Setup dependencies
        lib_dir = os.path.join(build_dir, "plugins", "lib")
        os.makedirs(lib_dir, exist_ok=True)

        # Install dependencies properly
        install_dependencies_properly(lib_dir)

        # Clean any remaining pycache
        clean_pycache_files(build_dir)

        # Create enhanced bootstrap
        create_proper_bootstrap(os.path.join(build_dir, "plugins"))

        # Create user installation script
        install_script = '''#!/usr/bin/env python3
"""
KiCad Plugin Dependency Installer
Run this if the plugin reports missing dependencies
"""
import subprocess
import sys
import os

def main():
    print("🔧 KiCad Plugin Dependency Installer")
    print("=" * 40)
    
    # Find plugin directory
    plugin_dir = os.path.join(os.path.dirname(__file__), 'plugins')
    lib_dir = os.path.join(plugin_dir, 'lib', 'site-packages')
    
    os.makedirs(lib_dir, exist_ok=True)
    
    dependencies = [
        'easyeda2kicad>=0.6.5',
        # Note: kicad-python usually provided by KiCad
        # Note: wxPython provided by KiCad
    ]
    
    print(f"Installing to: {lib_dir}")
    print()
    
    success_count = 0
    total_deps = len(dependencies) + len(git_dependencies)
    
    # Install pip dependencies
    for dep in dependencies:
        print(f"Installing {dep}...")
        try:
            subprocess.check_call([
                sys.executable, '-m', 'pip', 'install',
                '--target', lib_dir, '--upgrade', dep
            ])
            print(f"✅ {dep} - SUCCESS")
            success_count += 1
        except subprocess.CalledProcessError as e:
            print(f"❌ {dep} - FAILED: {e}")
    
    # Install git dependencies
    for git_dep in git_dependencies:
        print(f"Installing {git_dep['name']} from git...")
        try:
            # Try to clone and install git dependency
            with tempfile.TemporaryDirectory() as temp_dir:
                subprocess.check_call([
                    'git', 'clone', '--depth', '1', '--branch', git_dep['branch'],
                    git_dep['url'], temp_dir
                ])
                
                source_path = os.path.join(temp_dir, git_dep['subdirectory'])
                target_path = os.path.join(lib_dir, git_dep['name'])
                
                if os.path.exists(target_path):
                    import shutil
                    shutil.rmtree(target_path)
                
                shutil.copytree(source_path, target_path)
                print(f"✅ {git_dep['name']} - SUCCESS")
                success_count += 1
        except Exception as e:
            print(f"❌ {git_dep['name']} - FAILED: {e}")
            print(f"   You may need to install git or check network connection")
    
    print()
    print(f"Installation complete: {success_count}/{total_deps} successful")
    
    if success_count == total_deps:
        print("🎉 All dependencies installed successfully!")
        print("You can now restart KiCad and use the plugin.")
    else:
        print("⚠️  Some dependencies failed to install.")
        print("Try installing them manually with pip.")

if __name__ == '__main__':
    main()
'''

        with open(os.path.join(build_dir, "install_dependencies.py"), "w") as f:
            f.write(install_script)

        # Create README
        readme_content = """# KiCad Import Plugin

## Installation
1. Extract this ZIP to your KiCad plugins directory
2. Restart KiCad
3. If you get import errors, run: `python install_dependencies.py`

## Dependencies Structure
- `plugins/lib/site-packages/` - Embedded dependencies
- Dependencies are automatically loaded via bootstrap code
- wxPython is provided by KiCad (no separate installation needed)

## Included Dependencies
- ✅ easyeda2kicad - Embedded in plugins/lib/site-packages/
- ✅ kiutils (custom) - Cloned from https://github.com/Steffen-W/kiutils@v1.4.9
- ✅ Auto-installer for missing dependencies
- ✅ Python version independent (3.6+)

## Troubleshooting
- Check `plugins/plugin.log` for errors
- Run `install_dependencies.py` for manual installation
- Plugin includes auto-installation fallbacks
"""

        with open(os.path.join(build_dir, "README.md"), "w") as f:
            f.write(readme_content)

        # Create final ZIP
        print("📦 Creating optimized ZIP file...")
        with zipfile.ZipFile(
            "Import-LIB-KiCad-Plugin.zip", "w", zipfile.ZIP_DEFLATED, compresslevel=6
        ) as zipf:
            for root, dirs, files in os.walk(build_dir):
                # Skip __pycache__ directories
                dirs[:] = [d for d in dirs if d != "__pycache__"]

                for file in files:
                    if not file.endswith(".pyc"):  # Skip .pyc files
                        file_path = os.path.join(root, file)
                        arc_path = os.path.relpath(file_path, build_dir)
                        zipf.write(file_path, arc_path)

        print(f"✅ Clean ZIP created: {os.path.abspath('Import-LIB-KiCad-Plugin.zip')}")

        # Show structure
        with zipfile.ZipFile("Import-LIB-KiCad-Plugin.zip", "r") as zipf:
            file_count = len(zipf.namelist())
            size_mb = os.path.getsize("Import-LIB-KiCad-Plugin.zip") / (1024 * 1024)
            print(f"📊 ZIP contains {file_count} files, {size_mb:.1f} MB")

            # Show dependency structure
            deps = [
                name for name in zipf.namelist() if "plugins/lib/site-packages/" in name
            ]
            if deps:
                print(f"🔗 Dependencies embedded: {len(deps)} files in site-packages/")


if __name__ == "__main__":
    create_clean_zip_package()
