from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


if "mcp.server.fastmcp" not in sys.modules:
    mcp_mod = ModuleType("mcp")
    mcp_server_mod = ModuleType("mcp.server")
    mcp_fastmcp_mod = ModuleType("mcp.server.fastmcp")

    class _FastMCP:
        def __init__(self, name: str):
            self.name = name

        def tool(self, name: str):
            def _decorator(fn):
                return fn

            return _decorator

        def run(self, transport: str):
            return None

    mcp_fastmcp_mod.FastMCP = _FastMCP
    mcp_server_mod.fastmcp = mcp_fastmcp_mod
    mcp_mod.server = mcp_server_mod
    sys.modules["mcp"] = mcp_mod
    sys.modules["mcp.server"] = mcp_server_mod
    sys.modules["mcp.server.fastmcp"] = mcp_fastmcp_mod


if "saleae" not in sys.modules:
    saleae_mod = ModuleType("saleae")
    saleae_mod.automation = SimpleNamespace()
    sys.modules["saleae"] = saleae_mod
