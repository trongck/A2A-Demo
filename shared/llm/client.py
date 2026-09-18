"""
Universal LLM Client Adapter cho V-AI.
Hỗ trợ mọi nhà cung cấp (OpenAI, Google Gemini, OpenRouter, DeepSeek, Groq, Ollama, vLLM, LMStudio...).
Cấu hình hoàn toàn qua file .env với:
- LLM_PROVIDER (openai, gemini, openrouter, deepseek, ollama, custom...)
- LLM_API_KEY
- LLM_BASE_URL (tuỳ chọn, phục vụ OpenRouter, DeepSeek, local LLM...)
- LLM_MODEL (bất kỳ tên model nào: gpt-4o, gpt-4o-mini, gemini-2.5-flash, deepseek-chat, claude-3-5-sonnet...)
"""

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)


def get_llm_config() -> dict[str, str]:
    """Đọc cấu hình LLM từ .env với khả năng thích ứng với mọi provider."""
    load_dotenv(dotenv_path=ENV_PATH, override=True)

    # 1. Cấu hình tổng quát (Ưu tiên số 1)
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    base_url = os.environ.get("LLM_BASE_URL", "").strip()
    model = os.environ.get("LLM_MODEL", "").strip()
    provider = os.environ.get("LLM_PROVIDER", "").strip().lower()

    # 2. Cấu hình fallback theo OpenAI
    if not api_key and os.environ.get("OPENAI_API_KEY"):
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        provider = provider or "openai"
        model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()
        base_url = base_url or os.environ.get("OPENAI_BASE_URL", "").strip()

    # 3. Cấu hình fallback theo Gemini
    if not api_key and os.environ.get("GEMINI_API_KEY"):
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        provider = provider or "gemini"
        model = model or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()

    # Defaults
    if not provider:
        provider = "gemini" if "gemini" in model.lower() else "openai"
    if not model:
        model = "gemini-2.5-flash" if provider == "gemini" else "gpt-4o-mini"

    return {
        "provider": provider,
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
    }


def is_llm_available() -> bool:
    cfg = get_llm_config()
    return bool(cfg["api_key"])


def get_llm_provider() -> str:
    cfg = get_llm_config()
    return cfg["provider"] if cfg["api_key"] else "none"


def call_llm(prompt: str, system_instruction: str = "") -> str | None:
    """Gọi LLM linh hoạt: Hỗ trợ OpenAI-compatible API cho mọi provider và Google GenAI native."""
    cfg = get_llm_config()
    if not cfg["api_key"]:
        return None

    provider = cfg["provider"]
    api_key = cfg["api_key"]
    base_url = cfg["base_url"] or None
    model = cfg["model"]

    # Google GenAI Native (nếu provider là gemini và không truyền custom base_url)
    if provider == "gemini" and not base_url:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config={"system_instruction": system_instruction} if system_instruction else None,
            )
            return response.text
        except Exception as e:
            print(f"[LLM Gemini Native Error]: {e}")
            # Thử fallback qua OpenAI compatibility endpoint của Gemini
            base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"

    # Mọi nhà cung cấp khác sử dụng chuẩn OpenAI API (OpenAI, OpenRouter, DeepSeek, Groq, Ollama...)
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.3,
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"[LLM Universal Error ({model} via {base_url or 'default'})]: {e}")
        return None


def classify_and_extract_intent_with_llm(
    user_message: str,
    current_profile: dict[str, Any],
) -> dict[str, Any]:
    """Phân loại ý định của người dùng (general_chat, plan_itinerary, adjust_plan) và trích xuất thực thể."""
    if not is_llm_available():
        return {
            "intent": "plan_itinerary",
            "entities": {},
        }

    system_instruction = (
        "Bạn là bộ phân loại ý định (Intent Classifier) và trích xuất thực thể (Entity Extractor) thông minh cho VinWonders.\n"
        "Nhiệm vụ của bạn:\n"
        "1. Xác định intent của người dùng:\n"
        "   - 'plan_itinerary': Bất kỳ khi nào khách nhờ gợi ý trò chơi, gợi ý điểm tham quan, hỏi chơi gì, lên kế hoạch, lập lịch trình, tư vấn hoạt động, hoặc cung cấp thông tin đoàn khách (chiều cao, số người, thời gian chơi...).\n"
        "   - 'general_chat': CHỈ KHI khách chỉ thuần túy chào hỏi xã giao ('chào bạn', 'hello', 'hi'), hỏi bạn là ai/tên gì, hoặc hỏi giờ mở cửa/thời tiết/giá vé đơn thuần mà KHÔNG nhờ gợi ý hay tư vấn trò chơi/điểm chơi/lịch trình.\n"
        "   - 'adjust_plan': Khách đang muốn chỉnh sửa lịch trình đã có (chỉ đi trong nhà, đổi giờ, bớt trò...).\n"
        "2. Trích xuất các thực thể từ tin nhắn:\n"
        "   - height_cm: Chiều cao trẻ em (số nguyên, ví dụ 120, hoặc null)\n"
        "   - age_years: Tuổi (số nguyên hoặc null)\n"
        "   - indoor_only: true nếu chỉ muốn chơi trong nhà, false nếu ngoài trời, null nếu không nói\n"
        "   - min_activity_count: số điểm chơi tối thiểu mong muốn (số nguyên hoặc null)\n"
        "   - time_hours: số giờ dự kiến chơi (số thực/nguyên, ví dụ 2, hoặc null)\n"
        "   - start_time: giờ bắt đầu nếu có nhắc đến (ví dụ '14:00', hoặc null)\n"
        "   - end_time: giờ kết thúc nếu có nhắc đến (ví dụ '16:00', hoặc null)\n"
        "   - max_wait_minutes: thời gian chờ tối đa mỗi điểm nếu khách giới hạn (hoặc null)\n"
        "Trả về định dạng JSON thuần túy:\n"
        "{\n"
        '  "intent": "general_chat" | "plan_itinerary" | "adjust_plan",\n'
        '  "entities": {\n'
        '    "height_cm": null,\n'
        '    "age_years": null,\n'
        '    "indoor_only": null,\n'
        '    "min_activity_count": null,\n'
        '    "time_hours": null,\n'
        '    "start_time": null,\n'
        '    "end_time": null,\n'
        '    "max_wait_minutes": null\n'
        "  }\n"
        "}\n"
        "Không dùng markdown, chỉ xuất chuỗi JSON."
    )

    prompt = (
        f"Hồ sơ hiện tại của phiên: {json.dumps(current_profile, ensure_ascii=False)}\n"
        f"Tin nhắn người dùng: '{user_message}'"
    )

    raw = call_llm(prompt, system_instruction)
    if not raw:
        return {"intent": "plan_itinerary", "entities": {}}

    try:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        data = json.loads(clean)
        return {
            "intent": data.get("intent", "plan_itinerary"),
            "entities": data.get("entities", {}),
        }
    except Exception:
        return {"intent": "plan_itinerary", "entities": {}}


def extract_intent_with_llm(user_message: str, current_profile: dict[str, Any]) -> dict[str, Any] | None:
    """Tương thích ngược: Dùng LLM trích xuất các thông tin ràng buộc."""
    res = classify_and_extract_intent_with_llm(user_message, current_profile)
    entities = res.get("entities", {})
    return entities if entities else None


def answer_general_chat_with_llm(
    user_message: str,
    park_context: dict[str, Any] | None = None,
) -> str | None:
    """Agent A0 trả lời các câu hỏi chào hỏi, tư vấn thông tin chung về VinWonders bằng giọng điệu ấm áp."""
    if not is_llm_available():
        return None

    system_instruction = (
        "Bạn là Agent A0 - Hướng dẫn viên ảo kiêm Điều phối viên hệ thống V-AI tại VinWonders Nha Trang.\n"
        "Bạn có phong cách giao tiếp thông minh, ấm áp, hiếu khách và am hiểu tường tận về các phân khu VinWonders "
        "(Sea World, Fairy Land, Adventure Land, King's Garden, World Garden, Water World).\n"
        "Nhiệm vụ của bạn:\n"
        "1. Trả lời câu hỏi của khách một cách tự nhiên, lịch thiệp và hữu ích bằng tiếng Việt.\n"
        "2. Khéo léo gợi ý: Nếu quý khách muốn tối ưu hóa chuyến tham quan không phải chờ đợi lâu, "
        "hãy chia sẻ thêm chiều cao của các bé và khung giờ dự kiến tham quan để A0 kết hợp cùng Chuyên gia Mật độ (A2) "
        "và Chuyên gia Lập lịch (A1) thiết kế lộ trình riêng cho đoàn!"
    )

    ctx_str = json.dumps(park_context, ensure_ascii=False) if park_context else "Công viên VinWonders Nha Trang, mở cửa 09:00 - 20:00 hằng ngày."
    prompt = f"Thông tin bối cảnh công viên: {ctx_str}\nTin nhắn của khách: '{user_message}'"

    return call_llm(prompt, system_instruction)


def generate_unfeasible_explanation_with_llm(
    user_message: str,
    unfeasible_reasons: list[str],
    current_constraints: dict[str, Any],
) -> str | None:
    """Dùng LLM để giải thích một cách thấu cảm khi không tìm thấy lịch trình khả thi và đưa ra gợi ý nới lỏng."""
    if not is_llm_available():
        return None

    system_instruction = (
        "Bạn là Agent A0 & A1 - Chuyên gia tư vấn trải nghiệm tại VinWonders.\n"
        "Dựa trên các ràng buộc an toàn, thời gian và mật độ thực tế, hiện hệ thống chưa tìm được lịch trình thỏa mãn 100% yêu cầu của khách.\n"
        "Hãy giải thích ngắn gọn, chân thành lý do vì sao chưa khả thi và đề xuất cụ thể 2-3 giải pháp thay thế "
        "(ví dụ: tăng thời gian chơi, nới lỏng thời gian chờ tối đa, hoặc cho phép trải nghiệm thêm các điểm ngoài trời)."
    )

    prompt = (
        f"Yêu cầu của khách: '{user_message}'\n"
        f"Các lý do không khả thi từ Validator:\n" + "\n".join(f"- {r}" for r in unfeasible_reasons) + "\n"
        f"Ràng buộc hiện tại: {json.dumps(current_constraints, ensure_ascii=False)}"
    )

    return call_llm(prompt, system_instruction)



def synthesize_chat_response_with_llm(
    user_message: str,
    plans: list[dict[str, Any]],
    crowd_analysis: dict[str, Any],
) -> str | None:
    """Dùng LLM (Agent A0) để tạo lời thoại hướng dẫn viên thân thiện và hấp dẫn bằng tiếng Việt."""
    if not is_llm_available():
        return None

    system_instruction = (
        "Bạn là Agent A0 - Hướng dẫn viên ảo kiêm Điều phối viên hệ thống V-AI tại VinWonders Nha Trang. "
        "Hãy diễn đạt câu trả lời lịch thiệp, dễ hiểu, trình bày 2 phương án lịch trình "
        "(Phương án 1: Nhẹ nhàng, ít chờ; Phương án 2: Nhiều trò chơi trải nghiệm), "
        "nêu rõ lý do đề xuất từ chuyên gia A1, thời gian dự phòng trước 16:00 và gợi ý khách có thể tiếp tục chat để điều chỉnh."
    )

    prompt = (
        f"Yêu cầu của khách: '{user_message}'\n"
        f"Dữ liệu phương án đã được Validator xác thực:\n{json.dumps(plans, ensure_ascii=False, indent=2)}\n"
        f"Nhận định mật độ từ Chuyên gia A2:\n{json.dumps(crowd_analysis.get('crowd_insights', ''), ensure_ascii=False)}"
    )

    return call_llm(prompt, system_instruction)


def generate_crowd_insight_with_llm(
    items: list[dict[str, Any]],
    simulation_now: str,
    scenario_id: str = "base",
) -> str | None:
    """Dùng LLM (Agent A2) để đưa ra nhận định chuyên gia phân tích mật độ và cảnh báo nghẽn."""
    if not is_llm_available():
        return None

    system_instruction = (
        "Bạn là Agent A2 - Chuyên gia phân tích mật độ và lưu lượng tại công viên VinWonders. "
        "Dựa trên dữ liệu đếm người và hàng chờ thời gian thực, hãy đưa ra nhận định chuyên môn ngắn gọn (3-4 câu): "
        "1. Tình trạng chung về tải lưu lượng trong công viên. "
        "2. Cảnh báo cụ thể các điểm nóng có thời gian chờ cao hoặc quá tải (nếu có). "
        "3. Đề xuất nhóm điểm thông thoáng nên ưu tiên điều hướng khách tới."
    )

    summary_items = [
        {
            "name": it.get("name"),
            "wait_minutes": it.get("wait_minutes"),
            "load_category": it.get("load_category"),
            "occupancy_ratio": it.get("occupancy_ratio"),
            "operating_status": it.get("operating_status"),
            "is_stale": it.get("is_stale"),
        }
        for it in items
    ]

    prompt = (
        f"Thời điểm quan sát: {simulation_now} (Kịch bản: {scenario_id})\n"
        f"Dữ liệu mật độ từng điểm:\n{json.dumps(summary_items, ensure_ascii=False, indent=2)}"
    )

    return call_llm(prompt, system_instruction)


def generate_plan_rationale_with_llm(
    style_label: str,
    legs: list[dict[str, Any]],
    group_members: list[dict[str, Any]],
    total_wait: int,
    buffer_min: float,
    total_cost: int,
) -> str | None:
    """Dùng LLM (Agent A1) để đưa ra lời giải thích chiến lược lộ trình sâu sắc và thuyết phục."""
    if not is_llm_available():
        return None

    system_instruction = (
        "Bạn là Agent A1 - Chuyên gia lập lịch trình và tối ưu hóa trải nghiệm tại VinWonders. "
        "Hãy viết đoạn giải thích chiến lược ngắn gọn (2-3 câu) về lý do thiết kế lộ trình này: "
        "tại sao thứ tự này là tối ưu, sự an toàn và phù hợp cho các thành viên trong đoàn, "
        "và lợi thế về thời gian dự phòng để khách luôn thong thả quay về điểm đón."
    )

    legs_summary = [
        f"Chặng {l['step']}: {l['service_name']} (đến lúc {l['arrival_time']}, chơi {l['activity_duration_minutes']}p, chờ {l['wait_minutes']}p, đi bộ {l['walk_from_prev_minutes']}p)"
        for l in legs
    ]

    prompt = (
        f"Phong cách phương án: {style_label}\n"
        f"Lộ trình từng chặng:\n" + "\n".join(legs_summary) + "\n"
        f"Tổng thời gian chờ tích lũy: {total_wait} phút\n"
        f"Thời gian dự phòng cuối: {buffer_min} phút\n"
        f"Tổng chi phí: {total_cost:,} VND\n"
        f"Thành viên đoàn: {json.dumps(group_members, ensure_ascii=False)}"
    )

    return call_llm(prompt, system_instruction)


def generate_clarification_with_llm(
    user_message: str,
    missing_fields: list[str],
) -> str | None:
    """Dùng LLM (Agent A0) để tạo câu hỏi làm rõ thông tin còn thiếu một cách tự nhiên và chu đáo."""
    if not is_llm_available():
        return None

    system_instruction = (
        "Bạn là Agent A0 - Hướng dẫn viên thông minh tại VinWonders. "
        "Khách gửi yêu cầu nhưng còn thiếu thông tin an toàn/lập lịch. "
        "Hãy phản hồi bằng tiếng Việt thật tự nhiên, thân thiện và hỏi khéo các thông tin cần thiết."
    )

    prompt = (
        f"Khách nhắn: '{user_message}'\n"
        f"Thông tin cần bổ sung: {', '.join(missing_fields)}"
    )

    return call_llm(prompt, system_instruction)
