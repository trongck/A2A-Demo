# Hệ Thống Đa Tác Tử V-AI (VinWonders Intelligent Guide)

Dự án triển khai hệ thống Multi-Agent cục bộ (local) phục vụ gợi ý và lập lịch trình vui chơi VinWonders, tuân thủ nghiêm ngặt 100% tài liệu [V-AI-Implementation-Plan.md](V-AI-Implementation-Plan.md).

---

## 1. Kiến trúc Hệ thống & Cổng Dịch vụ

| Thành phần | Vai trò | Cổng / Đường dẫn | Công nghệ |
|---|---|---|---|
| **Chat UI + Backend A0** | Quản lý phiên, giao diện chat, điều phối state machine, tổng hợp câu trả lời | `http://127.0.0.1:8000` | FastAPI, Next.js, Tailwind CSS |
| **Agent A1 (Planner)** | Lập lịch trình, thuật toán tìm kiếm cắt nhánh, bộ Validator xác định | `http://127.0.0.1:8001` | A2A Protocol (`a2a-sdk`), Dijkstra Graph |
| **Agent A2 (Crowd Specialist)** | Phân tích trạng thái vận hành và mật độ mock ổn định theo từng POI | `http://127.0.0.1:8002` | A2A Protocol (`a2a-sdk`), Analytics |
| **MCP Server** | Chuẩn hóa Google Places V2, cung cấp catalog, trạng thái, đường đi và thời tiết | `http://127.0.0.1:8003` | Model Context Protocol (`mcp` SDK) |
| **Shared Memory** | SQLite lưu trữ tập trung dữ liệu phiên, hội thoại, kết quả, sự kiện | `data/memory.sqlite` | SQLite WAL Mode, Transactional |

---

## 2. Hướng dẫn Khởi động Nhanh

### Bước 1: Khởi động toàn bộ 4 tiến trình với một lệnh duy nhất
```bash
python scripts/run_local.py
```
Lệnh này sẽ tự động khởi chạy cả 4 tiến trình, kiểm tra sức khỏe (`health check`) và mở trình duyệt tại:
👉 **`http://127.0.0.1:8000`**

### Bước 2: Dừng hệ thống
Nhấn `Ctrl + C` tại cửa sổ dòng lệnh để tắt đồng thời cả 4 tiến trình một cách an toàn (Clean Shutdown).

---

## 3. Dữ liệu và kiểm thử

Nguồn runtime duy nhất là `data/V-AI-Mock-Data-V2.json` (267 Google Places). MCP chuẩn hóa `placeId`, tọa độ, loại hình, giờ mở cửa, rating/reviews và trạng thái đóng cửa. Mỗi POI có thêm `mockCrowd` ổn định để demo mật độ, hàng chờ và sức chứa; có thể tái tạo bằng `python scripts/seed_mock_crowd.py`. Giá vé dùng chính sách riêng, còn điều kiện từng trò chơi vẫn được giữ `null`/`unavailable` khi nguồn không cung cấp.

Chạy kiểm thử contract V2 xuyên suốt MCP → A2 → A1:
```bash
python -m pytest tests/test_all_criteria.py -v
```

Các ca kiểm tra bao gồm nguồn V2, chuẩn hóa MCP, lọc category, routing từ tọa độ, mật độ mock, lập lịch A1, khung giờ bất khả thi, HITL và cô lập session.

---

## 4. Kiểm chứng Tương tác trên Giao diện Web

1. **Thử lập lịch 2 phương án**: Cung cấp thành viên và khung giờ; hệ thống sẽ hiển thị 2 thẻ lịch trình:
   - **Phương án 1 (Gentle)**: Nhẹ nhàng, ít chờ, thời gian dự phòng cao.
   - **Phương án 2 (More Rides)**: Nhiều trò chơi trải nghiệm hơn, khác biệt ít nhất 1 điểm hoạt động.
2. **Thử Multi-turn trong cùng phiên**: Nhấn nút **🏛️ Chỉ đi trong nhà** hoặc gõ tin nhắn *"Chỉ đi trong nhà, tối thiểu 2 điểm"*. Lịch trình mới sẽ cập nhật chỉ gồm các điểm trong nhà và giữ nguyên cấu hình gia đình.
3. **Kiểm chứng Nhật ký Trao đổi Agent (Audit Log)**: Xem payload A0 ➔ A2 ➔ A1; `data_revision` phải là `google_places_v2` và các trường crowd không có dữ liệu phải là `null`.
"# A2A-Demo" 
