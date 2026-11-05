"""Load MCP tools for THIS request. Template code - do not change.

Two routes, chosen by MCP_ROUTE (default: gateway when the agent has Entra auth, else direct):
  gateway -> {GATEWAY_URL}/mcp/<server>/mcp (APIM). Needs a signed-in user: each call carries an
             On-Behalf-Of token for the server's audience (src/agent/mcp_audiences.json, from `make resolve`):
               shared-data servers -> one token for the gateway audience, reused for all of them
               OBO servers         -> a token for that server's own app registration
  direct  -> MCP_URL_<SERVER> (e.g. MCP_URL_GENIE_MCP=https://genie-mcp.internal.../mcp). Migration only.
             Sends the same OBO token when a user is signed in; otherwise no token (the server must allow it).

A server that is down or refuses the call is skipped (and reported), so one bad server never breaks the agent.
Tool names must be unique across servers: a clash is resolved by prefixing the server name."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import pathlib
import re

import yaml
from langchain_mcp_adapters.client import MultiServerMCPClient

from platform_auth import InteractionRequired, obo_token

log = logging.getLogger("agent.gateway")
_HERE = pathlib.Path(__file__).resolve()
_MANIFEST = yaml.safe_load((_HERE.parents[2] / "agent.yaml").read_text())
SERVERS: list[str] = [s for s in (_MANIFEST.get("uses_mcp") or []) if s]
_AUDIENCES_FILE = _HERE.with_name("mcp_audiences.json")
AUDIENCES: dict[str, str] = json.loads(_AUDIENCES_FILE.read_text()) if _AUDIENCES_FILE.exists() else {}
_VALID_TOOL_NAME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")   # what the chat model APIs accept


class ConfigError(RuntimeError):
    pass


def route() -> str:
    default = "gateway" if _MANIFEST.get("auth") == "entra" else "direct"
    r = os.getenv("MCP_ROUTE", default).strip().lower()
    if r not in ("gateway", "direct"):
        raise ConfigError(f"MCP_ROUTE must be gateway or direct, not {r!r}")
    return r


def gateway_url() -> str:
    return os.getenv("GATEWAY_URL", "http://127.0.0.1:8080").rstrip("/")


def server_url(server: str) -> str:
    if route() == "gateway":
        return f"{gateway_url()}/mcp/{server}/mcp"
    key = "MCP_URL_" + re.sub(r"[^A-Z0-9]", "_", server.upper())
    url = os.getenv(key)
    if not url:
        raise ConfigError(f"MCP_ROUTE=direct needs {key}")
    return url


def audience_of(server: str) -> str:
    return AUDIENCES.get(server, os.getenv("MCP_GATEWAY_AUDIENCE", "api://mcp-gateway"))


async def _server_tools(server: str, token: str | None):
    conn = {"transport": "streamable_http", "url": server_url(server)}
    if token:
        conn["headers"] = {"Authorization": f"Bearer {token}"}
    return await MultiServerMCPClient({server: conn}).get_tools()


async def _tokens(user_token: str, servers: list[str]) -> dict:
    audiences = sorted({audience_of(s) for s in servers})          # usually: the gateway + a few OBO servers
    exchanged = await asyncio.gather(*[asyncio.to_thread(obo_token, user_token, f"{a}/.default") for a in audiences],
                                     return_exceptions=True)
    for t in exchanged:
        if isinstance(t, InteractionRequired):
            raise t
    return dict(zip(audiences, exchanged))


def _unique(tools_by_server: list[tuple[str, list]]) -> list:
    """Keep tool names unique and valid; on a clash, prefix the server name."""
    seen: dict[str, str] = {}
    out = []
    for server, tools in tools_by_server:
        for t in tools:
            name = t.name if _VALID_TOOL_NAME.match(t.name) else re.sub(r"[^A-Za-z0-9_-]", "_", t.name)[:64]
            if name in seen:
                name = re.sub(r"[^A-Za-z0-9_-]", "_", f"{server}__{name}")[:64]
                log.warning("tool %s from %s clashes with %s; exposed as %s", t.name, server, seen.get(t.name), name)
            seen[name] = server
            if name != t.name:
                t.name = name
            out.append(t)
    return out


async def load_tools(user_token: str | None, servers: list[str] | None = None) -> tuple[list, list[str]]:
    """Returns (tools, unavailable_servers)."""
    servers = servers or SERVERS
    if route() == "gateway" and not user_token:
        raise ConfigError("MCP_ROUTE=gateway needs a signed-in user (agent_auth=entra)")
    tokens = await _tokens(user_token, servers) if user_token else {}

    down, pending = [], []
    for s in servers:
        tok = tokens.get(audience_of(s))
        if isinstance(tok, BaseException):
            log.warning("token exchange for %s failed: %s", s, tok)
            down.append(s)
        else:
            pending.append(s)
    results = await asyncio.gather(*[_server_tools(s, tokens.get(audience_of(s))) for s in pending],
                                   return_exceptions=True)
    loaded = []
    for server, res in zip(pending, results):
        if isinstance(res, BaseException):
            log.warning("MCP server %s unavailable: %s", server, res)
            down.append(server)
        else:
            loaded.append((server, res))
    return _unique(loaded), down
