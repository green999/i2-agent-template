"""Release check for the agent template: generate a project for each caller-auth mode and run its tests.

Run before tagging a release (the pipeline runs it on every pull request):
    python -m venv .venv  &&  activate it
    pip install copier -e <i2-platform-auth folder>
    pip install langgraph==1.2.18 langchain-core==1.4.7 langchain-openai==1.2.2 langchain-mcp-adapters==0.3.2 mcp==1.30.0 pyyaml httpx pytest
    python check_template.py"""
import pathlib
import subprocess
import sys
import tempfile

from copier import run_copy

HERE = pathlib.Path(__file__).resolve().parent
BASE = dict(team="platform", owner="ci@i2.example", purpose="Template release check", workspace="ci",
            uses_mcp="example-mcp,other-mcp", capability="Lookup", domain="Platform")

failed = []
with tempfile.TemporaryDirectory() as tmp:
    for auth in ("off", "entra"):
        dst = pathlib.Path(tmp) / f"check-agent-{auth}"
        run_copy(str(HERE), dst, data={**BASE, "agent_auth": auth, "name": dst.name}, defaults=True, unsafe=True, quiet=True)
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests"], cwd=dst, capture_output=True, text=True)
        last = (r.stdout.strip().splitlines() or ["(no output)"])[-1]
        print(f"{'PASS' if r.returncode == 0 else 'FAIL'}  agent_auth={auth:6} {last}")
        if r.returncode:
            print(r.stdout[-3000:], r.stderr[-2000:])
            failed.append(auth)
sys.exit(1 if failed else 0)
