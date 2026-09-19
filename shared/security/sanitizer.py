"""
Input Sanitization cho V-AI.
Fixes: H3 — Prompt Injection, H4 — Không validate input length.
"""

import re
from shared.security.config import MAX_MESSAGE_LENGTH, MAX_SESSION_ID_LENGTH, SESSION_ID_PATTERN
from shared.security.logging import get_logger

logger = get_logger("security.sanitizer")

def sanitize_user_input(text: str) -> str:
    """Chuẩn hóa an toàn nội dung trước khi đưa vào LLM.

    - Giới hạn độ dài theo MAX_MESSAGE_LENGTH
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
