"""
Unit tests for Inkscape detector module.
"""

import os
import platform
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock

import pytest

from inkscape_mcp.inkscape_detector import InkscapeDetector


class TestInkscapeDetector:
    """Test InkscapeDetector class functionality."""

    def test_initialization(self):
        """Test detector initializes correctly."""
        detector = InkscapeDetector()
        assert detector is not None
        assert hasattr(detector, "detect_inkscape_installation")

    @patch("platform.system")
    def test_detect_on_windows(self, mock_platform):
        """Test detection on Windows."""
        mock_platform.return_value = "Windows"
        detector = InkscapeDetector()

        with patch.object(
            detector, "_detect_windows", return_value=r"C:\Program Files\Inkscape\bin\inkscape.exe"
        ):
            result = detector.detect_inkscape_installation()
            assert result == r"C:\Program Files\Inkscape\bin\inkscape.exe"

    @patch("platform.system")
    def test_detect_on_linux(self, mock_platform):
        """Test detection on Linux."""
        mock_platform.return_value = "Linux"
        detector = InkscapeDetector()

        with patch.object(detector, "_detect_linux", return_value="/usr/bin/inkscape"):
            result = detector.detect_inkscape_installation()
            assert result == "/usr/bin/inkscape"

    @patch("platform.system")
    def test_detect_on_macos(self, mock_platform):
        """Test detection on macOS."""
        mock_platform.return_value = "Darwin"
        detector = InkscapeDetector()

        with patch.object(
            detector,
            "_detect_macos",
            return_value="/Applications/Inkscape.app/Contents/MacOS/inkscape",
        ):
            result = detector.detect_inkscape_installation()
            assert result == "/Applications/Inkscape.app/Contents/MacOS/inkscape"

    @patch("platform.system")
    def test_detect_unsupported_platform(self, mock_platform):
        """Test detection on unsupported platform."""
        mock_platform.return_value = "UnsupportedOS"
        detector = InkscapeDetector()

        result = detector.detect_inkscape_installation()
        assert result is None

    def test_windows_detection_paths(self):
        """Test Windows detection searches correct paths."""
        detector = InkscapeDetector()

        with patch.object(detector, "_validate_executable", return_value=False), \
             patch.object(detector, "_check_path_environment", return_value=None), \
             patch.object(detector, "_check_windows_registry", return_value=None):
            result = detector._detect_windows()
            assert result is None

    def test_windows_registry_search(self):
        """Test Windows registry search returns None when registry unavailable (non-Windows)."""
        detector = InkscapeDetector()
        # On Linux the registry check always returns None (no winreg)
        result = detector._check_windows_registry()
        assert result is None

    def test_windows_registry_not_found(self):
        """Test Windows registry search when Inkscape not found."""
        detector = InkscapeDetector()
        result = detector._check_windows_registry()
        assert result is None

    def test_linux_detection_paths(self):
        """Test Linux detection searches correct paths."""
        detector = InkscapeDetector()

        # Mock subprocess.run (used by _check_path_environment via 'which')
        # and Path.exists / os.access to force no match
        with patch("subprocess.run") as mock_run, \
             patch.object(Path, "exists", return_value=False), \
             patch("os.access", return_value=False):
            mock_run.return_value = Mock(returncode=1, stdout="")
            result = detector._detect_linux()
            assert result is None

        # Successful detection via 'which'
        with patch("subprocess.run") as mock_run, \
             patch.object(Path, "exists", return_value=True), \
             patch("os.access", return_value=True):
            mock_run.return_value = Mock(returncode=0, stdout="/usr/bin/inkscape\n")
            result = detector._detect_linux()
            assert result == "/usr/bin/inkscape"

    def test_macos_detection_paths(self):
        """Test macOS detection searches correct paths."""
        detector = InkscapeDetector()

        # All paths miss, PATH check returns inkscape
        with patch("subprocess.run") as mock_run, \
             patch.object(Path, "exists", return_value=False), \
             patch("os.access", return_value=False):
            mock_run.return_value = Mock(
                returncode=0, stdout="/usr/local/bin/inkscape\n"
            )
            # which returns a path containing "inkscape" but Path.exists is False
            # so _validate_executable returns False and the loop finds nothing
            mock_run.return_value = Mock(returncode=1, stdout="")
            result = detector._detect_macos()
            assert result is None

        # PATH check succeeds
        with patch("subprocess.run") as mock_run, \
             patch.object(Path, "exists", return_value=True), \
             patch("os.access", return_value=True):
            mock_run.return_value = Mock(
                returncode=0, stdout="/Applications/Inkscape.app/Contents/MacOS/inkscape\n"
            )
            result = detector._detect_macos()
            assert result == "/Applications/Inkscape.app/Contents/MacOS/inkscape"

    def test_path_environment_check(self):
        """Test PATH environment variable checking."""
        detector = InkscapeDetector()

        with patch("subprocess.run") as mock_run, \
             patch.object(Path, "exists", return_value=True), \
             patch("os.access", return_value=True):
            mock_run.return_value = Mock(returncode=0, stdout="/usr/bin/inkscape\n")
            result = detector._check_path_environment(["inkscape"])
            assert result == "/usr/bin/inkscape"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=1, stdout="")
            result = detector._check_path_environment(["inkscape"])
            assert result is None

    def test_validate_executable(self):
        """Test executable validation."""
        detector = InkscapeDetector()

        # Valid inkscape executable
        with patch.object(Path, "exists", return_value=True), \
             patch("os.access", return_value=True):
            result = detector._validate_executable("/usr/bin/inkscape")
            assert result is True

        # Path does not exist
        with patch.object(Path, "exists", return_value=False):
            result = detector._validate_executable("/nonexistent/inkscape")
            assert result is False

        # Name does not contain "inkscape"
        with patch.object(Path, "exists", return_value=True), \
             patch("os.access", return_value=True):
            result = detector._validate_executable("/usr/bin/gimp")
            assert result is False

        # Empty path
        assert detector._validate_executable("") is False

    def test_validate_executable_timeout(self):
        """Test executable validation when Path raises an exception."""
        detector = InkscapeDetector()

        with patch.object(Path, "exists", side_effect=OSError("simulated error")):
            result = detector._validate_executable("/usr/bin/inkscape")
            assert result is False

    def test_validate_executable_exception(self):
        """Test executable validation with generic exception."""
        detector = InkscapeDetector()

        with patch.object(Path, "exists", side_effect=Exception("Test error")):
            result = detector._validate_executable("/usr/bin/inkscape")
            assert result is False


class TestDetectorIntegration:
    """Integration tests for detector functionality."""

    def test_full_detection_workflow(self):
        """Test complete detection workflow."""
        detector = InkscapeDetector()

        result = detector.detect_inkscape_installation()

        # Result should be either a valid path string or None
        if result is not None:
            assert isinstance(result, str)
            assert Path(result).exists()
            assert Path(result).is_file()
        else:
            assert result is None

    def test_cross_platform_compatibility(self):
        """Test that detector works on current platform."""
        detector = InkscapeDetector()
        current_platform = platform.system()

        try:
            result = detector.detect_inkscape_installation()
            assert isinstance(result, (str, type(None)))
        except Exception as e:
            pytest.fail(f"Detection failed on {current_platform}: {e}")

    @patch.dict(os.environ, {"PATH": "/custom/bin:/usr/bin:/bin"})
    def test_custom_path_detection(self):
        """Test detection with custom PATH."""
        detector = InkscapeDetector()

        with patch("subprocess.run") as mock_run, \
             patch.object(Path, "exists", return_value=True), \
             patch("os.access", return_value=True):
            mock_run.return_value = Mock(returncode=0, stdout="/custom/bin/inkscape\n")
            result = detector._check_path_environment(["inkscape"])
            assert result == "/custom/bin/inkscape"


class TestDetectorLogging:
    """Test detector logging functionality."""

    def test_detection_logging(self, caplog):
        """Test that detection operations are logged."""
        import logging
        detector = InkscapeDetector()

        with caplog.at_level(logging.INFO, logger="inkscape_mcp.inkscape_detector"):
            with patch.object(detector, "_detect_linux", return_value=None):
                with patch("platform.system", return_value="Linux"):
                    detector.detect_inkscape_installation()

        assert any("Detecting Inkscape" in record.message for record in caplog.records)

    def test_validation_logging(self, caplog):
        """Test validation debug logging on failure."""
        import logging
        detector = InkscapeDetector()

        with caplog.at_level(logging.DEBUG, logger="inkscape_mcp.inkscape_detector"):
            with patch.object(Path, "exists", side_effect=Exception("boom")):
                detector._validate_executable("/usr/bin/inkscape")

        assert any(
            "Validation failed" in record.message for record in caplog.records
        )
