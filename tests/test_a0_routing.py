import uuid

from agents.a0 import orchestrator
from shared.memory.database import get_or_create_session, init_db


def test_a0_does_not_invent_group_or_time(monkeypatch):
    monkeypatch.setattr(orchestrator, "is_llm_available", lambda: False)

    profile, complete, missing, intent, routing = orchestrator.extract_or_update_request(
        "Bé 10 tuổi cao 120cm, đoàn muốn chơi 2 giờ",
        {"profile": {}},
    )

    assert intent == "plan_itinerary"
    assert complete is False
    assert profile.get("group_members") is None
    assert profile.get("start_at") is None
    assert profile.get("end_by") is None
    assert profile["pending_group_details"] == {"age_years": 10, "height_cm": 120}
    assert profile["pending_duration_hours"] == 2
    assert missing == ["thông_tin_thành_viên", "khung_giờ_tham_quan"]
    assert routing["status"] == "need_clarification"
    assert routing["completeness"] == "0/2"
    assert routing["clarification"] == {}


def test_hitl_questions_come_from_llm(monkeypatch):
    monkeypatch.setattr(orchestrator, "is_llm_available", lambda: True)
    monkeypatch.setattr(orchestrator, "classify_and_extract_intent_with_llm", lambda *_: {
        "status": "need_clarification",
        "intent": "plan_itinerary",
        "entities": {},
    })
    generated = {
        "message": "Cho mình hỏi thêm để xếp lịch vừa sức nhé.",
        "questions": [{
            "criteria_key": "travel_party_details",
            "question": "Trong đoàn có ai cần lưu ý về tuổi hoặc chiều cao không?",
            "options": ["Toàn người lớn", "Có trẻ em", "Khác/tự nhập"],
        }],
    }
    monkeypatch.setattr(orchestrator, "generate_hitl_questions_with_llm", lambda *_: generated)

    _, complete, _, _, routing = orchestrator.extract_or_update_request(
        "Lên lịch tham quan giúp mình", {"profile": {}},
    )

    assert complete is False
    assert routing["clarification"] == generated


def test_a0_stops_out_of_scope_without_options(monkeypatch):
    monkeypatch.setattr(orchestrator, "is_llm_available", lambda: False)

    _, complete, missing, intent, routing = orchestrator.extract_or_update_request(
        "Giá vàng hôm nay bao nhiêu?",
        {"profile": {}},
    )

    assert intent == "out_of_scope"
    assert complete is False
    assert missing == []
    assert routing["status"] == "out_of_scope"
    assert routing["intent"] is None
    assert routing["clarification"] == {}
    assert routing["forward_payload"] == {}


def test_partial_profile_is_saved_before_clarification(monkeypatch):
    monkeypatch.setattr(orchestrator, "is_llm_available", lambda: False)
    init_db()
    session_id = f"test_partial_{uuid.uuid4().hex}"

    response = orchestrator.run_orchestration(
        session_id=session_id,
        user_message="Bé 10 tuổi cao 120cm, đi từ 13:00-16:00",
    )
    stored = get_or_create_session(session_id)["profile"]

    assert response["status"] == "needs_input"
    assert response["memory_version"] >= 2
    assert stored["pending_group_details"] == {"age_years": 10, "height_cm": 120}
    assert stored["start_at"].endswith("T13:00:00+07:00")
    assert stored["end_by"].endswith("T16:00:00+07:00")


def test_ready_request_keeps_a2_then_a1_handoff(monkeypatch):
    monkeypatch.setattr(orchestrator, "is_llm_available", lambda: False)
    current_session = {
        "profile": {
            "group_members": [
                {"member_id": "adult_1", "age_years": 30, "height_cm": 170},
            ],
        },
    }

    profile, complete, missing, intent, routing = orchestrator.extract_or_update_request(
        "Lập lịch từ 13:00-16:00",
        current_session,
    )

    assert complete is True
    assert missing == []
    assert intent == "plan_itinerary"
    assert routing["status"] == "ready"
    assert routing["completeness"] == "2/2"
    assert routing["forward_payload"] == profile


def test_hitl_summary_is_parsed_without_llm(monkeypatch):
    monkeypatch.setattr(orchestrator, "is_llm_available", lambda: False)

    profile, complete, missing, _, _ = orchestrator.extract_or_update_request(
        "Thông tin bổ sung đã xác nhận:\n"
        "- Đoàn mình gồm những ai?: 1 người lớn và 1 trẻ em\n"
        "- Trẻ nhỏ nhất thuộc nhóm tuổi nào?: Từ 6–11 tuổi\n"
        "- Trẻ thấp nhất thuộc khoảng chiều cao nào?: Từ 105–109 cm\n"
        "- Đoàn mình muốn bắt đầu và kết thúc lúc mấy giờ?: 13:00–16:00",
        {"profile": {}},
    )

    assert complete is True
    assert missing == []
    assert profile["group_members"] == [
        {"member_id": "adult_1", "age_years": 18, "height_cm": 130},
        {"member_id": "child_1", "age_years": 6, "height_cm": 105},
    ]
