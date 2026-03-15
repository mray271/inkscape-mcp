"""Shared utilities for Inkscape MCP tools."""


def _parse_inkscape_float(raw: str) -> float:
    """Parse a float from Inkscape CLI output, ignoring WARNING/INFO lines.

    Inkscape (especially with GTK extensions loaded) can print warnings such as
    ``WARNING: unknown type: svg:recraft-signature`` alongside the numeric
    result.  This helper picks the first line that looks like a number so that
    warnings do not cause a ``ValueError`` in callers.
    """
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if any(line.upper().startswith(prefix) for prefix in ("WARNING", "ERROR", "INFO", "NOTE", "DEBUG")):
            continue
        try:
            return float(line)
        except ValueError:
            continue
    raise ValueError(f"No numeric value found in Inkscape output: {raw!r}")
