"""Model picker: choices are stored per job and used by the gateway; the tier rules still apply to every choice."""
import json

import pytest

from harness import config, db
from harness.gateway import Gateway
from harness.gateway.providers import Completion
from harness.gateway.settings import SelectionRefused, get_selection, set_selection


class Local:
    external, name = False, "local"

    def __init__(self, model="default-model", log=None):
        self.model, self.log = model, log if log is not None else []

    def with_model(self, m):
        return Local(m, self.log)

    def complete(self, prompt, system=None, max_tokens=0, json_mode=False):
        self.log.append(self.model)
        return Completion("ok")


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db"); db.migrate(c)
    return c


def test_default_is_the_env_model(conn):
    assert get_selection(conn, "email_triage") == ("local", config.LOCAL_MODEL)


def test_choice_is_stored_and_survives(conn):
    set_selection(conn, "email_triage", "local", "qwen3.5:9b")
    assert get_selection(conn, "email_triage") == ("local", "qwen3.5:9b")
    set_selection(conn, "email_triage", "local", "apertus1.5-8b-text:f16")
    assert get_selection(conn, "email_triage") == ("local", "apertus1.5-8b-text:f16")


@pytest.mark.parametrize("provider", ["anthropic", "infomaniak", "openrouter"])
def test_external_models_are_refused_for_confidential_email_even_if_ready(conn, provider):
    with pytest.raises(SelectionRefused, match="local models"):
        set_selection(conn, "email_triage", provider, "some-model", external_ready={provider})
    assert get_selection(conn, "email_triage") == ("local", config.LOCAL_MODEL)


def test_junk_choices_are_refused(conn):
    for args in (("nope", "local", "m"), ("email_triage", "martian", "m"), ("email_triage", "local", "")):
        with pytest.raises(SelectionRefused):
            set_selection(conn, *args)


def test_gateway_uses_the_pickers_model_for_the_job_and_logs_it(tmp_path):
    path = tmp_path / "t.db"
    c = db.connect(path); db.migrate(c); set_selection(c, "email_triage", "local", "picked-model"); c.close()
    log = []
    gw = Gateway(connect=lambda: db.connect(path), providers={"local": Local(log=log)})
    r = gw.complete("hello", source="email", purpose="t", job="email_triage")
    assert r.ok and log == ["picked-model"] and r.model == "picked-model"
    c = db.connect(path)
    assert c.execute("SELECT model, provider FROM privacy_log").fetchone()[:] == ("picked-model", "local")


def test_without_a_job_the_gateway_uses_the_provider_as_given(tmp_path):
    path = tmp_path / "t.db"
    c = db.connect(path); db.migrate(c); set_selection(c, "email_triage", "local", "picked-model"); c.close()
    log = []
    Gateway(connect=lambda: db.connect(path), providers={"local": Local("explicit", log)}).complete("hi", source="email", purpose="t")
    assert log == ["explicit"]                                   # the scoreboard relies on this


def test_api_models_and_select():
    from fastapi.testclient import TestClient
    from harness.main import app
    with TestClient(app) as cl:
        m = cl.get("/api/models").json()
        assert {"local", "jobs", "external", "spend", "cap_chf"} <= set(m)
        assert m["jobs"][0]["job"] == "email_triage" and m["jobs"][0]["local_only"] is True
        assert all(e["status"] == "not_set_up" for e in m["external"])
        assert cl.post("/api/models/select", json={"job": "email_triage", "provider": "anthropic", "model": "x"}).status_code == 422
        assert cl.post("/api/models/select", json={"job": "email_triage", "provider": "local", "model": "no-such-model"}).status_code == 422
        assert cl.post("/api/models/select", json={"job": "bogus", "provider": "local", "model": "x"}).status_code == 404
