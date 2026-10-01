"""Model providers. Only this package may talk to a model (rule 2).

Phase 2: only the local Ollama is real. Infomaniak and Claude API arrive in Phase 6; until then
they exist as disabled stubs so the policy and tests already cover them."""
import json
import urllib.request
from dataclasses import dataclass

from harness import config


class ProviderUnavailable(Exception):
    pass


@dataclass
class Completion:
    text: str
    cost_chf: float = 0.0


class OllamaProvider:
    name = "local"
    external = False

    def __init__(self, url: str | None = None, model: str | None = None, timeout: int = 300):
        self.url, self.model, self.timeout = (url or config.OLLAMA_URL).rstrip("/"), model or config.LOCAL_MODEL, timeout

    def complete(self, prompt: str, system: str | None = None, max_tokens: int = 1024, json_mode: bool = False) -> Completion:
        msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        body = {"model": self.model, "messages": msgs, "stream": False, "think": False,
                "options": {"temperature": 0.2, "num_predict": max_tokens}}
        if json_mode:
            body["format"] = "json"
        req = urllib.request.Request(f"{self.url}/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return Completion(json.load(r)["message"]["content"])
        except Exception as e:  # network down, model missing, timeout
            raise ProviderUnavailable(f"local model: {type(e).__name__}: {e}") from e

    def with_model(self, model: str) -> "OllamaProvider":
        return OllamaProvider(self.url, model, self.timeout)

    def status(self) -> dict:
        try:
            with urllib.request.urlopen(f"{self.url}/api/tags", timeout=4) as r:
                tags = json.load(r).get("models", [])
            names = [m["name"] for m in tags]
            return {"up": True, "model": self.model, "model_installed": self.model in names, "installed": names,
                    "models": [{"name": m["name"], "size_gb": round(m.get("size", 0) / 1e9, 1)} for m in tags]}
        except Exception:
            return {"up": False, "model": self.model, "model_installed": False, "installed": [], "models": []}


class DisabledProvider:
    """Placeholder for external providers not yet switched on (Phase 6)."""
    external = True

    def __init__(self, name: str):
        self.name = name

    def complete(self, *a, **k) -> Completion:
        raise ProviderUnavailable(f"{self.name} is not enabled yet")


def default_providers() -> dict:
    return {"local": OllamaProvider(), "infomaniak": DisabledProvider("infomaniak"),
            "anthropic": DisabledProvider("anthropic"), "openrouter": DisabledProvider("openrouter")}
