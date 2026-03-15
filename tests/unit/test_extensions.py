"""
Unit tests for ExtensionManager and the inkscape_system list_extensions /
execute_extension operations.

All Inkscape CLI calls are mocked so these tests run without a real Inkscape
installation or a display.
"""

import asyncio
import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from inkscape_mcp.plugins.extension_manager import (
    ExtensionManager,
    InkscapeExtension,
    ExtensionParameter,
)
from inkscape_mcp.tools.system import inkscape_system


# ── shared fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def real_inkscape_config():
    from inkscape_mcp.config import InkscapeConfig
    cfg = InkscapeConfig()
    cfg.inkscape_executable = "/usr/bin/inkscape"
    cfg.process_timeout = 30
    return cfg


@pytest.fixture
def mock_cli_wrapper(real_inkscape_config):
    from inkscape_mcp.cli_wrapper import InkscapeCliWrapper
    wrapper = InkscapeCliWrapper(real_inkscape_config)
    wrapper._execute_command = AsyncMock(return_value="mock inkscape output")
    return wrapper


@pytest.fixture
def ext_dir(tmp_path):
    """Two minimal valid .inx + .py extension stubs (namespaced, like real Inkscape)."""
    inx1 = textwrap.dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <inkscape-extension xmlns="http://www.inkscape.org/namespace/inkscape/extension">
          <name>Test Render</name>
          <id>test.render.one</id>
          <param name="scale" type="float" gui-text="Scale:">1.0</param>
          <effect>
            <object-type>all</object-type>
            <effects-menu><submenu name="Render" /></effects-menu>
          </effect>
          <script><command location="inx" interpreter="python">test_render.py</command></script>
        </inkscape-extension>
    """)
    (tmp_path / "test_render.inx").write_text(inx1)
    (tmp_path / "test_render.py").write_text("# stub")

    inx2 = textwrap.dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <inkscape-extension xmlns="http://www.inkscape.org/namespace/inkscape/extension">
          <name>Test Generate</name>
          <id>test.generate.two</id>
          <param name="count" type="int" gui-text="Count:">5</param>
          <effect>
            <object-type>all</object-type>
            <effects-menu><submenu name="Generate" /></effects-menu>
          </effect>
          <script><command location="inx" interpreter="python">test_generate.py</command></script>
        </inkscape-extension>
    """)
    (tmp_path / "test_generate.inx").write_text(inx2)
    (tmp_path / "test_generate.py").write_text("# stub")

    return tmp_path


@pytest.fixture
def manager(mock_cli_wrapper, real_inkscape_config, ext_dir):
    """ExtensionManager loaded from the stub ext_dir."""
    mgr = ExtensionManager(cli_wrapper=mock_cli_wrapper, config=real_inkscape_config)
    mgr.discover_extensions(extension_dirs=[str(ext_dir)])
    return mgr


# ── ExtensionManager.discover_extensions ─────────────────────────────────────

class TestDiscoverExtensions:

    def test_discovers_both_extensions(self, manager):
        assert len(manager.extensions) == 2

    def test_extension_ids_are_registered(self, manager):
        assert "test.render.one" in manager.extensions
        assert "test.generate.two" in manager.extensions

    def test_empty_dir_produces_no_extensions(
        self, mock_cli_wrapper, real_inkscape_config, tmp_path
    ):
        mgr = ExtensionManager(cli_wrapper=mock_cli_wrapper, config=real_inkscape_config)
        mgr.discover_extensions(extension_dirs=[str(tmp_path)])
        assert len(mgr.extensions) == 0

    def test_inx_without_script_file_is_skipped(
        self, mock_cli_wrapper, real_inkscape_config, tmp_path
    ):
        """An .inx referencing a missing .py is silently skipped."""
        inx = textwrap.dedent("""\
            <?xml version="1.0" encoding="UTF-8"?>
            <inkscape-extension xmlns="http://www.inkscape.org/namespace/inkscape/extension">
              <name>Broken</name>
              <id>broken.ext</id>
              <script><command location="inx" interpreter="python">missing.py</command></script>
            </inkscape-extension>
        """)
        (tmp_path / "broken.inx").write_text(inx)
        mgr = ExtensionManager(cli_wrapper=mock_cli_wrapper, config=real_inkscape_config)
        mgr.discover_extensions(extension_dirs=[str(tmp_path)])
        assert len(mgr.extensions) == 0

    def test_namespace_stripping_allows_parsing(self, manager):
        """The namespace-strip fix must allow id/name extraction from real .inx XML."""
        ext = manager.extensions["test.render.one"]
        assert ext.name == "Test Render"
        assert ext.id == "test.render.one"


# ── ExtensionManager.list_extensions ─────────────────────────────────────────

class TestListExtensions:

    def test_returns_list(self, manager):
        assert isinstance(manager.list_extensions(), list)

    def test_returns_all_extensions(self, manager):
        assert len(manager.list_extensions()) == 2

    def test_each_entry_has_required_fields(self, manager):
        for ext in manager.list_extensions():
            assert "id" in ext
            assert "name" in ext
            assert "category" in ext

    def test_category_filter_render(self, manager):
        render = manager.list_extensions(category="render")
        assert len(render) == 1
        assert render[0]["id"] == "test.render.one"

    def test_category_filter_generate(self, manager):
        generate = manager.list_extensions(category="generate")
        assert len(generate) == 1
        assert generate[0]["id"] == "test.generate.two"

    def test_unknown_category_returns_empty(self, manager):
        assert manager.list_extensions(category="nonexistent") == []

    def test_parameter_metadata_preserved(self, manager):
        render = manager.list_extensions(category="render")[0]
        params = render.get("parameters", [])
        assert any(p["name"] == "scale" for p in params)


# ── ExtensionManager.execute_extension ───────────────────────────────────────

class TestExecuteExtension:

    @pytest.mark.asyncio
    async def test_unknown_extension_returns_error(self, manager):
        result = await manager.execute_extension("does.not.exist")
        assert result["success"] is False
        assert "not found" in result["error"].lower()
        assert "available_extensions" in result

    @pytest.mark.asyncio
    async def test_known_extension_calls_inkscape(self, manager):
        await manager.execute_extension(
            "test.render.one",
            input_file="/tmp/input.svg",
            output_file="/tmp/output.svg",
        )
        assert manager.cli_wrapper._execute_command.called
        cmd = manager.cli_wrapper._execute_command.call_args[0][0]
        assert cmd[0] == "python3"   # direct script invocation, not inkscape binary
        assert "--extension" not in cmd  # --extension flag removed in Inkscape 1.x

    @pytest.mark.asyncio
    async def test_output_file_added_to_command(self, manager):
        await manager.execute_extension("test.render.one", output_file="/tmp/out.svg")
        cmd = manager.cli_wrapper._execute_command.call_args[0][0]
        assert "--output" in cmd
        assert "/tmp/out.svg" in cmd

    @pytest.mark.asyncio
    async def test_extra_parameters_passed_as_flags(self, manager):
        await manager.execute_extension("test.render.one", parameters={"scale": "2.0"})
        cmd = manager.cli_wrapper._execute_command.call_args[0][0]
        assert "--scale" in cmd
        assert "2.0" in cmd

    @pytest.mark.asyncio
    async def test_returns_success_true_on_ok(self, manager):
        result = await manager.execute_extension("test.render.one")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_cli_error_surfaces_as_failure(self, manager):
        from inkscape_mcp.cli_wrapper import InkscapeExecutionError
        manager.cli_wrapper._execute_command.side_effect = InkscapeExecutionError("boom")
        result = await manager.execute_extension("test.render.one")
        assert result["success"] is False
        assert "boom" in result["error"]


# ── inkscape_system — list_extensions operation ───────────────────────────────
#
# We mock the ExtensionManager instance methods rather than the constructor so
# discover_extensions() never touches the filesystem.

class TestInkscapeSystemListExtensions:

    def _mock_manager(self):
        """Return a fully-mocked ExtensionManager instance."""
        mgr = MagicMock(spec=ExtensionManager)
        mgr.list_extensions.return_value = [
            {"id": "a.b.c", "name": "Ext A", "category": "render", "parameters": []},
            {"id": "x.y.z", "name": "Ext B", "category": "generate", "parameters": []},
        ]
        return mgr

    @pytest.mark.asyncio
    async def test_returns_success_true(self, mock_cli_wrapper, real_inkscape_config):
        with patch(
            "inkscape_mcp.tools.system.ExtensionManager",
            return_value=self._mock_manager(),
        ):
            result = await inkscape_system(
                operation="list_extensions",
                cli_wrapper=mock_cli_wrapper,
                config=real_inkscape_config,
            )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_data_structure(self, mock_cli_wrapper, real_inkscape_config):
        with patch(
            "inkscape_mcp.tools.system.ExtensionManager",
            return_value=self._mock_manager(),
        ):
            result = await inkscape_system(
                operation="list_extensions",
                cli_wrapper=mock_cli_wrapper,
                config=real_inkscape_config,
            )
        data = result["data"]
        assert "extensions" in data
        assert "total_count" in data
        assert "categories" in data
        assert isinstance(data["extensions"], list)

    @pytest.mark.asyncio
    async def test_total_count_matches_list_length(self, mock_cli_wrapper, real_inkscape_config):
        with patch(
            "inkscape_mcp.tools.system.ExtensionManager",
            return_value=self._mock_manager(),
        ):
            result = await inkscape_system(
                operation="list_extensions",
                cli_wrapper=mock_cli_wrapper,
                config=real_inkscape_config,
            )
        data = result["data"]
        assert data["total_count"] == len(data["extensions"])

    @pytest.mark.asyncio
    async def test_categories_are_sorted_unique(self, mock_cli_wrapper, real_inkscape_config):
        with patch(
            "inkscape_mcp.tools.system.ExtensionManager",
            return_value=self._mock_manager(),
        ):
            result = await inkscape_system(
                operation="list_extensions",
                cli_wrapper=mock_cli_wrapper,
                config=real_inkscape_config,
            )
        cats = result["data"]["categories"]
        assert cats == sorted(set(cats))


# ── inkscape_system — execute_extension operation ─────────────────────────────

class TestInkscapeSystemExecuteExtension:

    def _mock_manager(self, success=True, error=None):
        mgr = MagicMock(spec=ExtensionManager)
        payload = {"success": success, "extension_id": "a.b.c"}
        if error:
            payload["error"] = error
        mgr.execute_extension = AsyncMock(return_value=payload)
        return mgr

    @pytest.mark.asyncio
    async def test_missing_extension_id_returns_error(self, mock_cli_wrapper, real_inkscape_config):
        result = await inkscape_system(
            operation="execute_extension",
            extension_id=None,
            cli_wrapper=mock_cli_wrapper,
            config=real_inkscape_config,
        )
        assert result["success"] is False
        assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_successful_execution_returns_success_true(
        self, mock_cli_wrapper, real_inkscape_config
    ):
        with patch(
            "inkscape_mcp.tools.system.ExtensionManager",
            return_value=self._mock_manager(success=True),
        ):
            result = await inkscape_system(
                operation="execute_extension",
                extension_id="a.b.c",
                extension_params={"input_file": "/tmp/in.svg", "output_file": "/tmp/out.svg"},
                cli_wrapper=mock_cli_wrapper,
                config=real_inkscape_config,
            )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_failed_execution_propagates_failure(
        self, mock_cli_wrapper, real_inkscape_config
    ):
        with patch(
            "inkscape_mcp.tools.system.ExtensionManager",
            return_value=self._mock_manager(success=False, error="not found"),
        ):
            result = await inkscape_system(
                operation="execute_extension",
                extension_id="no.such.ext",
                cli_wrapper=mock_cli_wrapper,
                config=real_inkscape_config,
            )
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_input_output_split_from_extra_params(
        self, mock_cli_wrapper, real_inkscape_config
    ):
        """input_file and output_file must be forwarded separately, not as --flags."""
        mgr = self._mock_manager(success=True)
        with patch("inkscape_mcp.tools.system.ExtensionManager", return_value=mgr):
            await inkscape_system(
                operation="execute_extension",
                extension_id="a.b.c",
                extension_params={
                    "input_file": "/tmp/in.svg",
                    "output_file": "/tmp/out.svg",
                    "scale": "3.0",
                },
                cli_wrapper=mock_cli_wrapper,
                config=real_inkscape_config,
            )

        _, kwargs = mgr.execute_extension.call_args
        assert kwargs.get("input_file") == "/tmp/in.svg"
        assert kwargs.get("output_file") == "/tmp/out.svg"
        params = kwargs.get("parameters", {})
        assert "input_file" not in params
        assert "output_file" not in params
        assert params.get("scale") == "3.0"

    @pytest.mark.asyncio
    async def test_extension_id_forwarded_to_manager(
        self, mock_cli_wrapper, real_inkscape_config
    ):
        mgr = self._mock_manager(success=True)
        with patch("inkscape_mcp.tools.system.ExtensionManager", return_value=mgr):
            await inkscape_system(
                operation="execute_extension",
                extension_id="a.b.c",
                cli_wrapper=mock_cli_wrapper,
                config=real_inkscape_config,
            )
        mgr.execute_extension.assert_called_once()
        assert mgr.execute_extension.call_args[1]["extension_id"] == "a.b.c"
