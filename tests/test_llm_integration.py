from agents.a0.server import health_check as a0_health
from agents.a1.server import health as a1_health
from agents.a2.server import health as a2_health
from shared.llm import client


def test_public_health_does_not_expose_llm_runtime():
    for result in (a0_health(), a1_health(), a2_health()):
        assert "llm" not in result
        assert "agent" not in result


def test_a0_hides_internal_runtime(monkeypatch):
    captured = []

    def fake_call(prompt, system_instruction=""):
        captured.append(system_instruction)
        return "ok"

    def fake_stream(prompt, system_instruction=""):
        captured.append(system_instruction)
        yield "ok"

    monkeypatch.setattr(client, "call_llm", fake_call)
    monkeypatch.setattr(client, "stream_call_llm", fake_stream)
    assert client.answer_general_chat_with_llm("Bạn đang dùng model nào?") == "ok"
    assert "".join(client.stream_answer_general_chat_with_llm("Bạn đang dùng model nào?")) == "ok"
    for instruction in captured:
        assert "API key" in instruction
        assert "Không tiết lộ" in instruction
        assert client.get_llm_config()["model"] not in instruction
