import uuid

from agents.a0 import orchestrator
from shared.memory.database import get_or_create_session, init_db


def test_unfeasible_reply_does_not_start_another_question_loop():
    reply = orchestrator.format_unfeasible_reply([
        "Khách cao dưới 140 cm phải có người lớn đi cùng.",
    ])

    assert "Khách cao dưới 140 cm" in reply
    assert "?" not in reply
    assert "Hãy cho mình biết" not in reply


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
        "questions": [
            {
                "criteria_key": "thong_tin_thanh_vien",
                "question": "Trong đoàn có ai cần lưu ý về tuổi hoặc chiều cao không?",
                "options": ["Toàn người lớn", "Có trẻ em", "Khác/tự nhập"],
            },
            {
                "criteria_key": "khung_gio_tham_quan",
                "question": "Bạn muốn tham quan trong khung giờ nào?",
                "options": ["09:00 - 13:00", "09:00 - 18:00", "Khác/tự nhập"],
            },
        ],
    }
    captured_missing = []

    def generate_questions(_, __, missing):
        captured_missing.extend(missing)
        return generated

    monkeypatch.setattr(orchestrator, "generate_hitl_questions_with_llm", generate_questions)

    _, complete, _, _, routing = orchestrator.extract_or_update_request(
        "Lên lịch tham quan giúp mình", {"profile": {}},
    )

    assert complete is False
    assert captured_missing == ["thông_tin_thành_viên", "khung_giờ_tham_quan"]
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


def test_group_uses_selected_safe_lower_bound(monkeypatch):
    monkeypatch.setattr(orchestrator, "is_llm_available", lambda: True)
    monkeypatch.setattr(orchestrator, "classify_and_extract_intent_with_llm", lambda *_: {
        "status": "ready",
        "intent": "plan_itinerary",
        "entities": {
            "group_size": 4,
            "age_years": 12,
            "height_cm": 130,
            "start_time": "14:00",
            "end_time": "17:00",
        },
    })

    profile, complete, missing, _, _ = orchestrator.extract_or_update_request(
        "Nhóm 4 người đều thuộc khoảng an toàn từ 12 tuổi và 130 cm, đi 14:00-17:00",
        {"profile": {}},
    )

    assert complete is True
    assert missing == []
    assert len(profile["group_members"]) == 4
    assert all(member["age_years"] == 12 for member in profile["group_members"])
    assert all(member["height_cm"] == 130 for member in profile["group_members"])
    assert profile["group_profile_ranges"]["is_safe_estimate"] is True


def test_hitl_does_not_invent_ticket_counts_from_question_or_vague_answer(monkeypatch):
    monkeypatch.setattr(orchestrator, "is_llm_available", lambda: True)
    monkeypatch.setattr(
        orchestrator,
        "classify_and_extract_intent_with_llm",
        lambda *_: (_ for _ in ()).throw(AssertionError("structured HITL must not be sent to the LLM")),
    )

    profile, complete, missing, intent, _ = orchestrator.extract_or_update_request(
        "Thông tin bổ sung đã xác nhận:\n"
        "- Bạn có thể cho mình biết cơ cấu đoàn, ví dụ bao nhiêu người lớn không?: "
        "Gia đình có cả ông bà và trẻ nhỏ\n"
        "- khung_gio_tham_quan: Cả ngày vui chơi (09:00 - 18:00)",
        {"profile": {}},
    )

    assert intent == "plan_itinerary"
    assert complete is False
    assert profile.get("ticket_groups") is None
    assert profile.get("group_members") is None
    assert profile["start_at"].endswith("T09:00:00+07:00")
    assert profile["end_by"].endswith("T18:00:00+07:00")
    assert missing == ["thông_tin_thành_viên"]


def test_hitl_ticket_ranges_create_safe_representative_profiles(monkeypatch):
    monkeypatch.setattr(orchestrator, "is_llm_available", lambda: False)

    profile, complete, missing, _, _ = orchestrator.extract_or_update_request(
        "Thông tin bổ sung đã xác nhận:\n"
        "- thong_tin_thanh_vien: 2 người lớn + 1 trẻ em + 1 bé dưới 100cm + 1 người cao tuổi\n"
        "- khung_gio_tham_quan: 09:00 - 18:00",
        {"profile": {}},
    )

    assert complete is True
    assert missing == []
    assert len(profile["group_members"]) == 5
    assert profile["ticket_groups"] == {
        "adult_140cm_plus": 2,
        "child_100_to_under_140cm": 1,
        "free_under_100cm": 1,
        "senior_60_plus": 1,
    }


def test_hitl_can_fall_back_to_selected_safe_group_range(monkeypatch):
    monkeypatch.setattr(orchestrator, "is_llm_available", lambda: False)

    profile, complete, missing, _, _ = orchestrator.extract_or_update_request(
        "Thông tin bổ sung đã xác nhận:\n"
        "- Thành viên trong đoàn: 2 người lớn – nhập tuổi và chiều cao từng thành viên: "
        "Người 1: 35 tuổi, cao 168cm\n"
        "- Khung giờ tham quan: 09:00 - 13:00",
        {"profile": {}},
    )

    assert complete is True
    assert missing == []
    assert len(profile["group_members"]) == 2


def test_hitl_uses_real_member_age_and_height_for_ticket_rules(monkeypatch):
    monkeypatch.setattr(orchestrator, "is_llm_available", lambda: False)

    profile, complete, missing, _, _ = orchestrator.extract_or_update_request(
        "Thông tin bổ sung đã xác nhận:\n"
        "- Thành viên trong đoàn: Người 1: 35 tuổi, cao 168cm; Người 2: 8 tuổi, cao 125cm\n"
        "- Khung giờ tham quan: 09:00 - 13:00",
        {"profile": {}},
    )

    assert complete is True
    assert missing == []
    assert profile["group_members"] == [
        {"member_id": "member_1", "age_years": 35, "height_cm": 168},
        {"member_id": "member_2", "age_years": 8, "height_cm": 125},
    ]
    assert profile["ticket_groups"] == {
        "adult_140cm_plus": 1,
        "child_100_to_under_140cm": 1,
    }


def test_hitl_combines_time_window_and_activity_count(monkeypatch):
    monkeypatch.setattr(orchestrator, "is_llm_available", lambda: False)
    current = {
        "profile": {
            "group_members": [{"member_id": "adult_1", "age_years": 18, "height_cm": 140}],
            "needs_activity_count": True,
        }
    }

    profile, complete, missing, _, _ = orchestrator.extract_or_update_request(
        "Thông tin bổ sung đã xác nhận:\n"
        "- Thời gian và số điểm muốn trải nghiệm: 09:00 - 13:00 · 4 điểm",
        current,
    )

    assert complete is True
    assert missing == []
    assert profile["hard_constraints"]["min_activity_count"] == 4
    assert profile["start_at"].endswith("T09:00:00+07:00")
    assert profile["end_by"].endswith("T13:00:00+07:00")
