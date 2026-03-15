"""
Inkscape Installation Detection and Validation.

This module handles cross-platform detection of Inkscape installations,
version validation, and executable path resolution.
"""

import logging
import os
import platform
import re
import subprocess
import sys

if sys.platform == "win32":
    import winreg

from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


class InkscapeDetector:
    """
    Cross-platform Inkscape installation detector and validator.
    """

    def __init__(self):
        self.system = platform.system().lower()
        self.logger = logging.getLogger(__name__)

    def detect_inkscape_installation(self) -> Optional[str]:
        """
        Detect Inkscape installation across different platforms.

        Returns:
            Optional[str]: Path to Inkscape executable if found, None otherwise
        """
        self.logger.info(f"Detecting Inkscape installation on {self.system}")

        if self.system == "windows":
            return self._detect_windows()
        elif self.system == "darwin":  # macOS
            return self._detect_macos()
        elif self.system == "linux":
            return self._detect_linux()
        else:
            self.logger.warning(f"Unsupported platform: {self.system}")
            return None

    def _detect_windows(self) -> Optional[str]:
        """
        Detect Inkscape on Windows using registry and common paths.
        """
        registry_path = self._check_windows_registry()
        if registry_path and self._validate_executable(registry_path):
            return registry_path

        username = os.environ.get("USERNAME", "")
        common_paths = [
            r"C:\Program Files\Inkscape\bin\inkscape.exe",
            r"C:\Program Files (x86)\Inkscape\bin\inkscape.exe",
            rf"C:\Users\{username}\AppData\Local\Programs\Inkscape\bin\inkscape.exe",
            rf"C:\Users\{username}\AppData\Local\Microsoft\WindowsApps\inkscape.exe",
            rf"C:\Users\{username}\AppData\Local\Packages\25415Inkscape.Inkscape_9waqn51p1ttv2\LocalState\bin\inkscape.exe",
        ]

        for path in common_paths:
            if self._validate_executable(path):
                return path

        path_executable = self._check_path_environment(["inkscape.exe", "inkscape"])
        if path_executable:
            return path_executable

        return None

    def _check_windows_registry(self) -> Optional[str]:
        """
        Check Windows registry for Inkscape installation.
        """
        try:
            registry_keys = [
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inkscape",
                r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inkscape",
            ]

            for key_path in registry_keys:
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                        install_location, _ = winreg.QueryValueEx(key, "InstallLocation")
                        bin_dir = Path(install_location) / "bin"
                        exe_path = bin_dir / "inkscape.exe"
                        if exe_path.exists():
                            return str(exe_path)
                except (WindowsError, FileNotFoundError, OSError):
                    continue

        except ImportError:
            pass
        except Exception as e:
            self.logger.debug(f"Registry check failed: {e}")

        return None

    def _detect_macos(self) -> Optional[str]:
        """
        Detect Inkscape on macOS.
        """
        common_paths = [
            "/Applications/Inkscape.app/Contents/MacOS/inkscape",
            "/usr/local/bin/inkscape",
            "/opt/homebrew/bin/inkscape",
        ]

        for path in common_paths:
            if self._validate_executable(path):
                return path

        path_executable = self._check_path_environment(["inkscape"])
        if path_executable:
            return path_executable

        return None

    def _detect_linux(self) -> Optional[str]:
        """
        Detect Inkscape on Linux.
        """
        # Try PATH first (covers apt/snap/flatpak installs)
        path_executable = self._check_path_environment(["inkscape"])
        if path_executable:
            return path_executable

        # Try common installation paths directly
        common_paths = [
            "/usr/bin/inkscape",
            "/usr/local/bin/inkscape",
            "/snap/bin/inkscape",
            "/var/lib/flatpak/exports/bin/org.inkscape.Inkscape",
            os.path.expanduser("~/.local/bin/inkscape"),
        ]

        for path in common_paths:
            if self._validate_executable(path):
                return path

        return None

    def _check_path_environment(self, executable_names: List[str]) -> Optional[str]:
        """
        Check if Inkscape is available in PATH environment.
        """
        for exe_name in executable_names:
            try:
                cmd = "where" if self.system == "windows" else "which"
                result = subprocess.run([cmd, exe_name], capture_output=True, text=True, timeout=10)

                if result.returncode == 0 and result.stdout.strip():
                    path = result.stdout.strip().split("\n")[0]
                    if self._validate_executable(path):
                        return path

            except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                continue

        return None

    def _validate_executable(self, path: str) -> bool:
        """
        Validate that the given path is a valid Inkscape executable.
        """
        if not path:
            return False

        try:
            path_obj = Path(path)
            if not path_obj.exists() or not os.access(path, os.X_OK):
                return False

            path_str = str(path_obj).lower()
            if "inkscape" not in path_str:
                return False

            return True

        except Exception as e:
            self.logger.debug(f"Validation failed for {path}: {e}")
            return False

    def validate_inkscape_version(self, executable_path: str) -> str:
        """
        Validate Inkscape version and check compatibility.

        Args:
            executable_path: Path to Inkscape executable

        Returns:
            str: Version string

        Raises:
            RuntimeError: If version check fails or version is incompatible
        """
        try:
            result = subprocess.run(
                [executable_path, "--version"], capture_output=True, text=True, timeout=30
            )

            if result.returncode != 0:
                raise RuntimeError(f"Inkscape version check failed: {result.stderr}")

            # Inkscape outputs e.g. "Inkscape 1.3 (1:1.3+...)"
            version_match = re.search(r"Inkscape\s+(\d+\.\d+(?:\.\d+)?)", result.stdout)
            if not version_match:
                raise RuntimeError(f"Could not parse Inkscape version from: {result.stdout}")

            version = version_match.group(1)
            parts = list(map(int, version.split(".")))
            major = parts[0]
            minor = parts[1] if len(parts) > 1 else 0

            if major < 1 or (major == 1 and minor < 0):
                raise RuntimeError(
                    f"Inkscape version {version} is too old. "
                    "Please install Inkscape 1.0 or newer."
                )

            self.logger.info(f"Validated Inkscape version: {version}")
            return version

        except subprocess.TimeoutExpired:
            raise RuntimeError("Inkscape version check timed out")
        except Exception as e:
            raise RuntimeError(f"Inkscape version validation failed: {e}")

    def get_default_paths(self) -> List[str]:
        """
        Get platform-specific default installation paths.
        """
        if self.system == "windows":
            return [
                r"C:\Program Files\Inkscape\bin\inkscape.exe",
                r"C:\Program Files (x86)\Inkscape\bin\inkscape.exe",
            ]
        elif self.system == "darwin":
            return [
                "/Applications/Inkscape.app/Contents/MacOS/inkscape",
                "/usr/local/bin/inkscape",
                "/opt/homebrew/bin/inkscape",
            ]
        elif self.system == "linux":
            return [
                "/usr/bin/inkscape",
                "/usr/local/bin/inkscape",
                "/snap/bin/inkscape",
            ]
        else:
            return []
