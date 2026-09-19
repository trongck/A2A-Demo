"""Gắn dữ liệu mật độ giả lập ổn định vào mọi POI của dataset V2."""

import hashlib
import json
from pathlib import Path


DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "V-AI-Mock-Data-V2.json"
OBSERVED_AT = "2026-09-19T09:00:00+07:00"


def main() -> None:
    places = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    for place in places:
        digest = hashlib.sha256(place["placeId"].encode()).digest()
        capacity = 80 + int.from_bytes(digest[:2], "big") % 321
        occupancy_ratio = 0.15 + digest[2] / 255 * 0.75
        current_people = round(capacity * occupancy_ratio)
        queue_people = round(current_people * (0.04 + digest[3] / 255 * 0.16))
        place["mockCrowd"] = {
            "observedAt": OBSERVED_AT,
            "areaM2": 300 + int.from_bytes(digest[4:6], "big") % 2701,
            "comfortCapacityPeople": capacity,
            "currentPeople": current_people,
            "queuePeople": queue_people,
            "waitMinutes": 3 + digest[6] % 28,
        }
    # Giữ đúng layout gốc: các object cấp cao không thụt vào trong mảng.
    serialized = "[" + ",\n".join(json.dumps(place, ensure_ascii=False, indent=2) for place in places) + "]\n"
    DATA_PATH.write_text(serialized, encoding="utf-8")
    print(f"Seeded mock crowd for {len(places)} POIs")


if __name__ == "__main__":
    main()
