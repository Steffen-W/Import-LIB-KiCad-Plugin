import subprocess
import sys
import platform
import importlib
import os
import shutil
import json
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Union, TYPE_CHECKING
import logging

# Handle pkg_resources import with proper type checking
try:
    import pkg_resources

    HAS_PKG_RESOURCES = True
except ImportError:
    HAS_PKG_RESOURCES = False
    if TYPE_CHECKING:
        import pkg_resources  # type: ignore
    else:
        pkg_resources = None


class PipManager:
    """Cross-platform Python package manager for Windows, Linux, and macOS."""

    def __init__(self, python_executable: Optional[str] = None):
        self.platform = platform.system().lower()
        self.python_executable = python_executable or self._find_python_executable()
        self.logger = self._setup_logger()

        # Validate Python executable
        if not self._is_valid_python_executable(self.python_executable):
            self.logger.warning(
                f"Python executable may not be valid: {self.python_executable}"
            )

        # Log system info at initialization
        self.logger.debug(f"Platform: {self.platform}")
        self.logger.debug(f"Python executable: {self.python_executable}")
        self.logger.debug(f"Python version: {platform.python_version()}")
        self.logger.debug(f"pkg_resources available: {HAS_PKG_RESOURCES}")

    def _find_python_executable(self) -> str:
        """Find the appropriate Python executable for the current platform."""
        candidates = [sys.executable]

        current_platform = platform.system().lower()

        try:
            if current_platform == "windows":
                candidates.extend(
                    [
                        "python.exe",
                        "python3.exe",
                        "py.exe",
                    ]
                )
                for cmd in ["python", "python3", "py"]:
                    which_result = shutil.which(cmd)
                    if which_result:
                        candidates.append(which_result)

            elif current_platform == "darwin":
                candidates.extend(
                    [
                        "python3",
                        "python",
                        "/usr/bin/python3",
                        "/usr/local/bin/python3",
                        "/opt/homebrew/bin/python3",
                        "/usr/local/opt/python/bin/python3",
                    ]
                )
                for cmd in ["python3", "python"]:
                    which_result = shutil.which(cmd)
                    if which_result:
                        candidates.append(which_result)

            elif current_platform == "linux":
                candidates.extend(
                    [
                        "python3",
                        "python",
                        "/usr/bin/python3",
                        "/usr/local/bin/python3",
                        "/bin/python3",
                        "/usr/bin/python",
                        "/usr/local/bin/python",
                    ]
                )
                for cmd in ["python3", "python"]:
                    which_result = shutil.which(cmd)
                    if which_result:
                        candidates.append(which_result)

            else:
                candidates.extend(
                    [
                        "python3",
                        "python",
                        "/usr/local/bin/python3",
                        "/usr/pkg/bin/python3",
                        "/opt/local/bin/python3",
                    ]
                )
                for cmd in ["python3", "python"]:
                    which_result = shutil.which(cmd)
                    if which_result:
                        candidates.append(which_result)

        except Exception as e:
            self.logger.debug(f"Error finding Python executables: {e}")

        # Test candidates in order
        for candidate in candidates:
            if candidate and self._is_valid_python_executable(candidate):
                return candidate

        return sys.executable

    def _is_valid_python_executable(self, executable_path: str) -> bool:
        """Check if the given path is a valid Python executable."""
        try:
            path = Path(executable_path)
            if not path.exists() or not path.is_file():
                return False
            creation_flags = (
                subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )

            result = subprocess.run(
                [str(path), "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
                creationflags=creation_flags,
            )
            return result.returncode == 0 and "python" in result.stdout.lower()

        except (
            subprocess.TimeoutExpired,
            subprocess.CalledProcessError,
            OSError,
            FileNotFoundError,
        ):
            return False
        except Exception as e:
            self.logger.debug(
                f"Error validating Python executable {executable_path}: {e}"
            )
            return False

    def _setup_logger(self) -> logging.Logger:
        logger = logging.getLogger(self.__class__.__name__)
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger

    def _run_pip_command(
        self, args: List[str], check: bool = True, timeout: int = 300
    ) -> subprocess.CompletedProcess:
        """Execute pip command with platform-specific handling."""
        cmd = [self.python_executable, "-m", "pip"] + args

        kwargs = {
            "capture_output": True,
            "text": True,
            "check": check,
            "timeout": timeout,
        }

        if self.platform == "windows":
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUNBUFFERED"] = "1"
            kwargs["env"] = env

        self.logger.debug(f"Executing command: {' '.join(cmd)}")

        try:
            if sys.platform == "win32":
                kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)

            return subprocess.run(cmd, **kwargs)
        except subprocess.TimeoutExpired as e:
            self.logger.error(f"Pip command timed out after {timeout} seconds")
            raise
        except FileNotFoundError as e:
            self.logger.error(f"Python executable not found: {self.python_executable}")
            raise
        except Exception as e:
            self.logger.error(f"Error executing pip command: {e}")
            raise

    def is_package_installed(self, package_name: str) -> bool:
        """Check if package is installed."""
        clean_package_name = self._extract_package_name_from_git_url(package_name)

        # Method 1: Try importing the module
        try:
            importlib.import_module(clean_package_name)
            return True
        except ImportError:
            pass

        # Method 2: Try pkg_resources if available
        if HAS_PKG_RESOURCES and pkg_resources is not None:
            try:
                pkg_resources.get_distribution(clean_package_name)
                return True
            except Exception:  # Catch all pkg_resources exceptions
                pass

        # Method 3: Use pip list as fallback
        try:
            result = self._run_pip_command(
                ["list", "--format=json"], check=False, timeout=30
            )
            if result.returncode == 0:
                packages = json.loads(result.stdout)
                installed_names = {pkg["name"].lower() for pkg in packages}
                return clean_package_name.lower() in installed_names
        except (json.JSONDecodeError, Exception) as e:
            self.logger.debug(f"Error checking installed packages via pip list: {e}")

        return False

    def get_package_version(self, package_name: str) -> Optional[str]:
        """Get version of installed package."""
        clean_package_name = self._extract_package_name_from_git_url(package_name)

        # Method 1: Try pkg_resources if available
        if HAS_PKG_RESOURCES and pkg_resources is not None:
            try:
                return pkg_resources.get_distribution(clean_package_name).version
            except Exception:  # Catch all pkg_resources exceptions
                pass

        # Method 2: Use pip list as fallback
        try:
            result = self._run_pip_command(
                ["list", "--format=json"], check=False, timeout=30
            )
            if result.returncode == 0:
                packages = json.loads(result.stdout)
                for pkg in packages:
                    if pkg["name"].lower() == clean_package_name.lower():
                        return pkg["version"]
        except (json.JSONDecodeError, Exception) as e:
            self.logger.debug(f"Error getting package version via pip list: {e}")

        return None

    def _extract_package_name_from_git_url(self, package_spec: str) -> str:
        """Extract package name from Git URL or package specification."""
        package_spec = package_spec.strip()

        if package_spec.startswith("git+"):
            # Handle Git URLs
            patterns = [
                r"git\+https://[^/]+/[^/]+/([^@/#\s]+)",  # github.com/user/repo
                r"git\+ssh://[^/]+/[^/]+/([^@/#\s]+)",  # ssh format
                r"git\+[^/]+://[^/]+/([^@/#\s]+)",  # generic git+protocol
            ]

            for pattern in patterns:
                match = re.search(pattern, package_spec)
                if match:
                    return match.group(1)

            # Fallback: extract from URL end
            parts = package_spec.replace("git+", "").split("/")
            if len(parts) >= 1:
                repo_name = parts[-1].split("@")[0].split("#")[0].strip()
                if repo_name:
                    return repo_name

        return self._extract_package_name(package_spec)

    def _extract_package_name(self, package_spec: str) -> str:
        """Extract package name from package specification."""
        package_spec = package_spec.strip()

        # Handle URLs
        if any(
            package_spec.startswith(prefix)
            for prefix in ["http://", "https://", "git+", "file://"]
        ):
            return self._extract_package_name_from_git_url(package_spec)

        # Handle regular package specifications
        for sep in ["==", ">=", "<=", ">", "<", "~=", "!=", "["]:
            if sep in package_spec:
                return package_spec.split(sep)[0].strip()

        return package_spec.strip()

    def check_package_requirements(
        self, package_name: str, required_version: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Check if package meets version requirements."""
        clean_package_name = self._extract_package_name_from_git_url(package_name)

        if not self.is_package_installed(clean_package_name):
            return False, f"Package '{clean_package_name}' not installed"

        if required_version:
            current_version = self.get_package_version(clean_package_name)
            if current_version != required_version:
                return (
                    False,
                    f"Package '{clean_package_name}' version {current_version} found, {required_version} required",
                )

        version = self.get_package_version(clean_package_name)
        return True, f"Package '{clean_package_name}' version {version} installed"

    def install_package(
        self,
        package_name: str,
        upgrade: bool = False,
        user: bool = False,
        no_deps: bool = False,
    ) -> bool:
        """Install single package with pip."""
        try:
            args = ["install"]

            if upgrade:
                args.append("--upgrade")

            if user:
                args.append("--user")

            if no_deps:
                args.append("--no-deps")

            args.append(package_name)

            self.logger.info(f"Installing package: {package_name}")
            result = self._run_pip_command(args, timeout=600)  # 10 minutes for installs

            self.logger.info(f"Package '{package_name}' installed successfully")
            return True

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to install '{package_name}': {e}")
            if e.stderr:
                self.logger.error(f"Stderr: {e.stderr}")
            return False
        except subprocess.TimeoutExpired:
            self.logger.error(f"Installation of '{package_name}' timed out")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error installing '{package_name}': {e}")
            return False

    def uninstall_package(self, package_name: str) -> bool:
        """Uninstall package."""
        try:
            args = ["uninstall", package_name, "-y"]
            self.logger.info(f"Uninstalling package: {package_name}")
            self._run_pip_command(args)

            self.logger.info(f"Package '{package_name}' uninstalled successfully")
            return True

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to uninstall '{package_name}': {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error uninstalling '{package_name}': {e}")
            return False

    def parse_requirements_file(self, requirements_path: Union[str, Path]) -> List[str]:
        """Parse requirements.txt file."""
        requirements = []
        try:
            path = Path(requirements_path)
            if not path.exists():
                self.logger.warning(f"Requirements file not found: {requirements_path}")
                return requirements

            with open(path, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()

                    # Skip empty lines and comments
                    if not line or line.startswith("#"):
                        continue

                    # Skip pip options
                    if line.startswith("-"):
                        continue

                    # Remove inline comments
                    package = line.split("#")[0].strip()
                    if package:
                        requirements.append(package)

            self.logger.info(f"Read {len(requirements)} packages from requirements.txt")
            return requirements

        except UnicodeDecodeError as e:
            self.logger.error(f"Encoding error reading requirements.txt: {e}")
            return []
        except Exception as e:
            self.logger.error(f"Error reading requirements.txt: {e}")
            return []

    def install_from_requirements(
        self,
        requirements_path: Union[str, Path],
        upgrade: bool = False,
        user: bool = False,
    ) -> Dict[str, bool]:
        """Install packages from requirements.txt file."""
        try:
            args = ["install", "-r", str(requirements_path)]

            if upgrade:
                args.append("--upgrade")

            if user:
                args.append("--user")

            self.logger.info(f"Installing packages from: {requirements_path}")
            self._run_pip_command(args, timeout=1200)  # 20 minutes for requirements

            packages = self.parse_requirements_file(requirements_path)
            return {self._extract_package_name(pkg): True for pkg in packages}

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to install from requirements.txt: {e}")
            if e.stderr:
                self.logger.error(f"Stderr: {e.stderr}")
            packages = self.parse_requirements_file(requirements_path)
            return {self._extract_package_name(pkg): False for pkg in packages}
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            return {}

    def check_and_install_missing(
        self,
        required_packages: List[str],
        auto_install: bool = True,
        user: bool = False,
    ) -> Dict[str, str]:
        """Check package list and install missing packages."""
        results = {}

        for package in required_packages:
            try:
                # For Git URLs, check the actual package name but install the full spec
                if package.strip().startswith("git+"):
                    package_name = self._extract_package_name_from_git_url(package)
                    install_spec = package
                else:
                    package_name = self._extract_package_name(package)
                    install_spec = package

                if self.is_package_installed(package_name):
                    version = self.get_package_version(package_name)
                    results[package_name] = (
                        f"✓ Installed (Version {version or 'unknown'})"
                    )
                    self.logger.info(f"Package '{package_name}' already installed")
                else:
                    if auto_install:
                        self.logger.info(
                            f"Package '{package_name}' missing - attempting installation..."
                        )
                        if self.install_package(install_spec, user=user):
                            results[package_name] = "✓ Successfully installed"
                        else:
                            results[package_name] = "✗ Installation failed"
                    else:
                        results[package_name] = "✗ Not installed"

            except Exception as e:
                self.logger.error(f"Error processing package '{package}': {e}")
                results[package] = f"✗ Error: {str(e)}"

        return results

    def check_and_install_from_requirements(
        self,
        requirements_path: Union[str, Path],
        auto_install: bool = True,
        user: bool = False,
    ) -> Dict[str, str]:
        """Check and install packages from requirements.txt file."""
        try:
            path = Path(requirements_path)
            if not path.exists():
                self.logger.error(f"Requirements file not found: {requirements_path}")
                return {}

            packages = self.parse_requirements_file(requirements_path)
            if not packages:
                self.logger.warning("No packages found in requirements.txt")
                return {}

            return self.check_and_install_missing(packages, auto_install, user)

        except Exception as e:
            self.logger.error(f"Error processing requirements file: {e}")
            return {}

    def get_installed_packages(self) -> Dict[str, str]:
        """Get all installed packages with versions."""
        try:
            result = self._run_pip_command(["list", "--format=json"], timeout=60)
            packages = json.loads(result.stdout)
            return {pkg["name"]: pkg["version"] for pkg in packages}

        except (json.JSONDecodeError, subprocess.CalledProcessError) as e:
            self.logger.error(f"Error getting installed packages: {e}")
            return {}
        except Exception as e:
            self.logger.error(f"Unexpected error getting installed packages: {e}")
            return {}

    def upgrade_package(self, package_name: str, user: bool = False) -> bool:
        """Upgrade specific package."""
        return self.install_package(package_name, upgrade=True, user=user)

    def upgrade_all_packages(self, user: bool = False) -> Dict[str, bool]:
        """Upgrade all outdated packages."""
        results = {}

        try:
            result = self._run_pip_command(
                ["list", "--outdated", "--format=json"], timeout=60
            )
            outdated = json.loads(result.stdout)

            for pkg in outdated:
                package_name = pkg["name"]
                self.logger.info(
                    f"Upgrading {package_name} from {pkg['version']} to {pkg['latest_version']}"
                )
                results[package_name] = self.upgrade_package(package_name, user=user)

            return results

        except (json.JSONDecodeError, subprocess.CalledProcessError) as e:
            self.logger.error(f"Error upgrading packages: {e}")
            return {}
        except Exception as e:
            self.logger.error(f"Unexpected error upgrading packages: {e}")
            return {}

    def get_pip_version(self) -> Optional[str]:
        """Get pip version."""
        try:
            result = self._run_pip_command(["--version"], timeout=30)
            version_line = result.stdout.strip()
            # Extract version from "pip X.Y.Z from ..."
            parts = version_line.split()
            if len(parts) >= 2:
                return parts[1]
            return version_line
        except Exception as e:
            self.logger.debug(f"Error getting pip version: {e}")
            return None

    def get_system_info(self) -> Dict[str, str]:
        """Get comprehensive system information."""
        info = {
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor() or "unknown",
            "architecture": platform.architecture()[0],
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "python_executable": self.python_executable,
            "pip_version": self.get_pip_version() or "unknown",
            "working_directory": os.getcwd(),
            "pkg_resources_available": str(HAS_PKG_RESOURCES),
        }

        # Add virtual environment info
        try:
            if hasattr(sys, "real_prefix") or (
                hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
            ):
                info["virtual_env"] = (
                    f"Active - Base: {getattr(sys, 'base_prefix', 'unknown')}, Current: {sys.prefix}"
                )
            elif os.environ.get("VIRTUAL_ENV"):
                info["virtual_env"] = (
                    f"Active via VIRTUAL_ENV: {os.environ.get('VIRTUAL_ENV')}"
                )
            elif os.environ.get("CONDA_DEFAULT_ENV"):
                info["virtual_env"] = (
                    f"Conda environment: {os.environ.get('CONDA_DEFAULT_ENV')}"
                )
            else:
                info["virtual_env"] = "Not detected"
        except Exception:
            info["virtual_env"] = "Error detecting"

        return info


if __name__ == "__main__":
    pip_manager = PipManager()

    print("=== System Information ===")
    system_info = pip_manager.get_system_info()
    for key, value in system_info.items():
        print(f"{key}: {value}")

    print("\n=== Single Package Check ===")
    packages_to_check = ["requests", "numpy"]

    for package in packages_to_check:
        is_installed = pip_manager.is_package_installed(package)
        version = pip_manager.get_package_version(package)
        print(
            f"{package}: {'✓' if is_installed else '✗'} - Version: {version or 'Not installed'}"
        )

    print("\n=== Auto Install Missing Packages ===")
    required_packages = ["requests", "colorama"]
    results = pip_manager.check_and_install_missing(
        required_packages, auto_install=False
    )

    for package, status in results.items():
        print(f"{package}: {status}")
