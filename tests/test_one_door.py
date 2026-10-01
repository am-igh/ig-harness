"""Rule 2: every model call goes through harness/gateway/. No other harness module may import a
network or AI-provider library. (tools/ runs on the Mac for Google only and never calls an AI.)"""
import ast
from pathlib import Path

FORBIDDEN = {"anthropic", "openai", "httpx", "requests", "aiohttp", "urllib3", "socket", "http", "ollama",
             "langchain", "litellm"}
FORBIDDEN_DOTTED = {"urllib.request", "http.client"}
ROOT = Path(__file__).resolve().parent.parent / "harness"


def _imports(path: Path):
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module
            for a in node.names:
                yield f"{node.module}.{a.name}"


def test_no_module_outside_the_gateway_can_reach_a_model_or_the_network():
    offenders = []
    for py in ROOT.rglob("*.py"):
        if "gateway" in py.relative_to(ROOT).parts:
            continue
        for name in _imports(py):
            if name.split(".")[0] in FORBIDDEN or name in FORBIDDEN_DOTTED:
                offenders.append(f"{py.relative_to(ROOT)}: {name}")
    assert not offenders, offenders


def test_the_scan_itself_works():
    gw = ROOT / "gateway" / "providers.py"
    assert "urllib.request" in set(_imports(gw))      # the gateway is where the network code lives
