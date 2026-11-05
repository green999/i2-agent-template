import json
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def test_manifest_complete():
    m = yaml.safe_load((ROOT / "agent.yaml").read_text())
    for key in ("name", "team", "identity", "owner", "purpose", "data_class", "uses_mcp", "auth"):
        assert m.get(key), f"agent.yaml needs {key}"
    assert m["auth"] in ("off", "entra")


def test_langgraph_config_matches_auth_mode():
    m = yaml.safe_load((ROOT / "agent.yaml").read_text())
    cfg = json.loads((ROOT / "langgraph.json").read_text())
    assert cfg["dependencies"] == ["."], "the image must install this project (pyproject.toml) and ship agent.yaml"
    assert ("auth" in cfg) == (m["auth"] == "entra"), "langgraph.json auth block must match agent.yaml auth"
    graph_id = m["name"].replace("-", "_")
    assert graph_id in cfg["graphs"]


def test_prompt_present():
    text = (ROOT / "src/agent/prompt.md").read_text()
    assert len(text.strip()) > 40


def test_graph_compiles():
    from agent.graph import graph
    assert "agent" in graph.get_graph().nodes


def test_internal_packages_never_come_from_an_index():
    """platform-auth on public PyPI is an unrelated package: the identity library is installed from vendor/ only."""
    text = (ROOT / "pyproject.toml").read_text() + (ROOT / "requirements-dev.txt").read_text()
    assert '"platform-auth' not in text and '"i2-platform-auth' not in text, "remove platform-auth from dependencies"
