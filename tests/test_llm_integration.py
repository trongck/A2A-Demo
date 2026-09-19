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
        assert "người bạn đồng hành du lịch" in instruction
        assert "Không lặp lại lời chào" in instruction
        assert client.get_llm_config()["model"] not in instruction


def test_hitl_safe_range_option_is_immediately_selectable(monkeypatch):
    monkeypatch.setattr(client, "is_llm_available", lambda: True)
    monkeypatch.setattr(client, "call_llm", lambda *_: '''{
        "message": "Cho mình xin thêm thông tin nhé.",
        "questions": [{
            "criteria_key": "thong_tin_thanh_vien",
            "question": "Đoàn mình gồm những ai?",
            "options": ["2 người lớn", "Khác/tự nhập"]
        }]
    }''')

    result = client.generate_hitl_questions_with_llm(
        "Lên lịch giúp mình", {}, ["thông_tin_thành_viên"]
    )

    assert result["questions"][0]["options"][0] == "2 người lớn"


def test_hitl_keeps_only_missing_criteria_and_accepts_merged_question(monkeypatch):
    monkeypatch.setattr(client, "call_llm", lambda *_: '''{
        "message": "Mình hỏi thêm nhé.",
        "questions": [
            {"criteria_key":"thong_tin_thanh_vien","question":"Đoàn gồm ai?","options":["2 người lớn","Khác/tự nhập"]},
            {"criteria_key":"thong_tin_thanh_vien","question":"Hỏi trùng","options":["Khác/tự nhập"]},
            {"criteria_key":"khung_gio_va_so_diem","question":"Đi lúc nào và bao nhiêu điểm?","options":["09:00 - 13:00 · 3 điểm","Khác/tự nhập"]},
            {"criteria_key":"noi_bo","question":"Không được hỏi","options":["Có"]}
        ]
    }''')

    result = client.generate_hitl_questions_with_llm(
        "Lên lịch", {}, ["thông_tin_thành_viên", "khung_giờ_tham_quan", "số_điểm_mong_muốn"]
    )

    assert [q["criteria_key"] for q in result["questions"]] == [
        "thong_tin_thanh_vien", "khung_gio_va_so_diem"
    ]
