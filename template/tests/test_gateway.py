"""Tool loading rules: route choice, direct URLs, unique tool names."""
import asyncio
import pathlib
import sys
from types import SimpleNamespace

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agent import gateway  # noqa: E402


def test_direct_url_from_env(monkeypatch):
    monkeypatch.setenv("MCP_ROUTE", "direct")
    monkeypatch.setenv("MCP_URL_GENIE_MCP", "https://genie.internal/mcp")
    assert gateway.server_url("genie-mcp") == "https://genie.internal/mcp"


def test_direct_url_missing_is_clear(monkeypatch):
    monkeypatch.setenv("MCP_ROUTE", "direct")
    monkeypatch.delenv("MCP_URL_OTHER_MCP", raising=False)
    with pytest.raises(gateway.ConfigError, match="MCP_URL_OTHER_MCP"):
        gateway.server_url("other-mcp")


def test_gateway_url(monkeypatch):
    monkeypatch.setenv("MCP_ROUTE", "gateway")
    monkeypatch.setenv("GATEWAY_URL", "https://apim.example/")
    assert gateway.server_url("genie-mcp") == "https://apim.example/mcp/genie-mcp/mcp"


def test_bad_route(monkeypatch):
    monkeypatch.setenv("MCP_ROUTE", "sideways")
    with pytest.raises(gateway.ConfigError):
        gateway.route()


def test_gateway_route_needs_a_user(monkeypatch):
    monkeypatch.setenv("MCP_ROUTE", "gateway")
    with pytest.raises(gateway.ConfigError):
        asyncio.run(gateway.load_tools(None, ["x"]))


def test_down_server_is_skipped(monkeypatch):
    monkeypatch.setenv("MCP_ROUTE", "direct")
    monkeypatch.setenv("MCP_URL_DEAD", "http://127.0.0.1:9/mcp")   # nothing listens on port 9
    tools, down = asyncio.run(gateway.load_tools(None, ["dead"]))
    assert tools == [] and down == ["dead"]


def test_tool_name_clash_is_prefixed():
    a, b, c = SimpleNamespace(name="search"), SimpleNamespace(name="search"), SimpleNamespace(name="bad name!")
    out = gateway._unique([("one", [a]), ("two", [b, c])])
    assert [t.name for t in out] == ["search", "two__search", "bad_name_"]
