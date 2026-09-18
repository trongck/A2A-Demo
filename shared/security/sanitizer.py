"""
Input Sanitization cho V-AI.
Fixes: H3 — Prompt Injection, H4 — Không validate input length.
"""

import re
from shared.security.config import MAX_MESSAGE_LENGTH, MAX_SESSION_ID_LENGTH, SESSION_ID_PATTERN
from shared.security.logging import get_logger

logger = get_logger("security.sanitizer")

# Các pattern prompt injection phổ biến (case-insensitive)
_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE) for p in [
        r"ignore\s+(all\s+)?(previous|above|prior|earlier)\s+(instructions?|prompts?|rules?|guidelines?)",
        r"disregard\s+(all\s+)?(previous|above|prior)\s+(instructions?|prompts?|context)",
        r"forget\s+(all\s+)?(previous|above|your)\s+(instructions?|prompts?|rules?)",
        r"you\s+are\s+now\s+(a|an|my)",
        r"act\s+as\s+(a|an|if)\b",
        r"new\s+instructions?:",
        r"system\s*:\s*",
        r"<\s*\|?(system|im_start|im_end)\|?\s*>",
        r"reveal\s+(your|the)\s+(system\s+)?(instructions?|prompts?|keys?|secrets?|config)",
        r"show\s+(me\s+)?(your\s+)?(system\s+)?(prompt|instructions?|config)",
        r"what\s+(is|are)\s+your\s+(system\s+)?(prompt|instructions?|rules?)",
        r"print\s+(your\s+)?(system\s+)?(prompt|instructions?)",
        r"output\s+(your\s+)?(system\s+)?(prompt|instructions?)",
        r"repeat\s+(your|the)\s+(system\s+)?(prompt|instructions?)\s+(back|verbatim|exactly)",
    ]
]


def sanitize_user_input(text: str) -> str:
    """Lọc nội dung user input trước khi đưa vào LLM.

    - Giới hạn độ dài theo MAX_MESSAGE_LENGTH
    - Phát hiện và vô hiệu hóa prompt injection patterns
    - Loại bỏ ký tự điều khiển nguy hiểm

    Returns:
        Chuỗi đã được sanitize.
    """
    if not text:
        return ""

    # 1. Giới hạn độ dài
    original_len = len(text)
    text = text[:MAX_MESSAGE_LENGTH]
    if original_len > MAX_MESSAGE_LENGTH:
        logger.warning(
            "SECURITY: Input bị cắt từ %d xuống %d ký tự",
            original_len, MAX_MESSAGE_LENGTH,
        )

    # 2. Loại bỏ ký tự điều khiển (null bytes, backspace, v.v.) nhưng giữ newline và tab
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # 3. Phát hiện prompt injection
    for pattern in _INJECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            logger.warning(
                "SECURITY: Prompt injection detected — pattern='%s', matched='%s'",
                pattern.pattern[:60], match.group()[:80],
            )
            # Thay thế bằng chuỗi vô hại thay vì block hoàn toàn
            text = pattern.sub("[nội dung không hợp lệ]", text)

    return text.strip()


def validate_session_id(session_id: str) -> bool:
    """Kiểm tra session_id có hợp lệ không."""
    if not session_id or len(session_id) > MAX_SESSION_ID_LENGTH:
        return False
    return bool(re.match(SESSION_ID_PATTERN, session_id))


def validate_message(message: str) -> tuple[bool, str]:
    """Kiểm tra tính hợp lệ của message trước khi xử lý.

    Returns:
        (is_valid, error_message)
    """
    if not message or not message.strip():
        return False, "Tin nhắn không được để trống."
    if len(message) > MAX_MESSAGE_LENGTH:
        return False, f"Tin nhắn quá dài ({len(message)} ký tự). Tối đa {MAX_MESSAGE_LENGTH} ký tự."
    return True, ""
