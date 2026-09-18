from agents.a0.server import health_check as a0_health
from agents.a1.server import health as a1_health
from agents.a2.server import health as a2_health
from shared.llm import client


def test_all_agents_report_the_same_llm_runtime():
    expected = client.get_llm_status()
    assert set(expected) == {"enabled", "provider", "model"}
    assert a0_health()["llm"] == expected
    assert a1_health()["llm"] == expected
    assert a2_health()["llm"] == expected


def test_a0_knows_the_runtime_model(monkeypatch):
    captured = {}

    def fake_call(prompt, system_instruction=""):
        captured["system_instruction"] = system_instruction
        return "ok"

    monkeypatch.setattr(client, "call_llm", fake_call)
    assert client.answer_general_chat_with_llm("Bạn đang dùng model nào?") == "ok"
    runtime = client.get_llm_status()
    assert runtime["provider"] in captured["system_instruction"]
    assert runtime["model"] in captured["system_instruction"]
