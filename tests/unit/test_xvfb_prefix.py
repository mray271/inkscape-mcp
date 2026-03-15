"""
Unit tests for the _xvfb_prefix helper and its integration with _execute_command.

These tests verify that Inkscape is transparently wrapped with xvfb-run when
running headlessly (no $DISPLAY), enabling GTK-dependent extensions to work in
Docker and CI environments.
"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from inkscape_mcp.cli_wrapper import _xvfb_prefix, InkscapeCliWrapper, InkscapeExecutionError


# ── _xvfb_prefix() unit tests ────────────────────────────────────────────────

class TestXvfbPrefix:
    """Tests for the _xvfb_prefix() helper function."""

    def test_returns_empty_when_display_is_set(self):
        """When $DISPLAY is set (desktop/CI with a real display), no wrapper needed."""
        with patch.dict(os.environ, {"DISPLAY": ":0"}):
            assert _xvfb_prefix() == []

    def test_returns_xvfb_run_when_headless_and_available(self):
        """Headless + xvfb-run on PATH → prefix should be ['xvfb-run', '-a']."""
        env = {k: v for k, v in os.environ.items() if k != "DISPLAY"}
        with patch.dict(os.environ, env, clear=True):
            with patch("shutil.which", return_value="/usr/bin/xvfb-run"):
                assert _xvfb_prefix() == ["xvfb-run", "-a"]

    def test_returns_empty_when_headless_but_xvfb_unavailable(self):
        """Headless but xvfb-run not installed → fall through without wrapping."""
        env = {k: v for k, v in os.environ.items() if k != "DISPLAY"}
        with patch.dict(os.environ, env, clear=True):
            with patch("shutil.which", return_value=None):
                assert _xvfb_prefix() == []

    def test_display_set_takes_priority_over_xvfb(self):
        """$DISPLAY beats xvfb-run availability — don't double-wrap."""
        with patch.dict(os.environ, {"DISPLAY": ":1"}):
            with patch("shutil.which", return_value="/usr/bin/xvfb-run"):
                assert _xvfb_prefix() == []


# ── _execute_command xvfb integration ────────────────────────────────────────

@pytest.fixture
def real_inkscape_config():
    """Config pointing at the real system Inkscape (Linux path)."""
    from inkscape_mcp.config import InkscapeConfig
    cfg = InkscapeConfig()
    cfg.inkscape_executable = "/usr/bin/inkscape"
    cfg.process_timeout = 30
    return cfg


@pytest.fixture
def wrapper(real_inkscape_config):
    return InkscapeCliWrapper(real_inkscape_config)


class TestExecuteCommandXvfbIntegration:
    """Tests that _execute_command prepends xvfb-run correctly."""

    @pytest.mark.asyncio
    async def test_prepends_xvfb_run_when_headless(self, wrapper):
        """When headless and xvfb-run is available, xvfb-run is prepended."""
        captured = {}

        async def fake_exec(*args, stdout, stderr, env):
            captured["cmd"] = args
            proc = MagicMock()
            proc.returncode = 0
            future_out = asyncio.get_event_loop().create_future()
            future_out.set_result((b"ok", b""))
            proc.communicate = AsyncMock(return_value=(b"ok", b""))
            return proc

        env = {k: v for k, v in os.environ.items() if k != "DISPLAY"}
        with patch.dict(os.environ, env, clear=True):
            with patch("shutil.which", return_value="/usr/bin/xvfb-run"):
                with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
                    await wrapper._execute_command(["/usr/bin/inkscape", "--version"], 10)

        assert captured["cmd"][0] == "xvfb-run", (
            f"Expected 'xvfb-run' as first arg, got: {captured['cmd'][0]}"
        )
        assert captured["cmd"][1] == "-a"
        assert captured["cmd"][2] == "/usr/bin/inkscape"

    @pytest.mark.asyncio
    async def test_no_xvfb_run_when_display_present(self, wrapper):
        """When $DISPLAY is set, inkscape is called directly without xvfb-run."""
        captured = {}

        async def fake_exec(*args, stdout, stderr, env):
            captured["cmd"] = args
            proc = MagicMock()
            proc.returncode = 0
            proc.communicate = AsyncMock(return_value=(b"ok", b""))
            return proc

        with patch.dict(os.environ, {"DISPLAY": ":0"}):
            with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
                await wrapper._execute_command(["/usr/bin/inkscape", "--version"], 10)

        assert captured["cmd"][0] == "/usr/bin/inkscape", (
            f"Expected inkscape as first arg, got: {captured['cmd'][0]}"
        )
