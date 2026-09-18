# Hệ Thống Đa Tác Tử V-AI (VinWonders Intelligent Guide)

Dự án triển khai hệ thống Multi-Agent cục bộ (local) phục vụ gợi ý và lập lịch trình vui chơi VinWonders, tuân thủ nghiêm ngặt 100% tài liệu [V-AI-Implementation-Plan.md](V-AI-Implementation-Plan.md).

---

## 1. Kiến trúc Hệ thống & Cổng Dịch vụ

| Thành phần | Vai trò | Cổng / Đường dẫn | Công nghệ |
|---|---|---|---|
| **Chat UI + Backend A0** | Quản lý phiên, giao diện chat, điều phối state machine, tổng hợp câu trả lời | `http://127.0.0.1:8000` | FastAPI, HTML5 Semantic, Vanilla CSS |
| **Agent A1 (Planner)** | Lập lịch trình, thuật toán tìm kiếm cắt nhánh, bộ Validator xác định | `http://127.0.0.1:8001` | A2A Protocol (`a2a-sdk`), Dijkstra Graph |
| **Agent A2 (Crowd Specialist)** | Phân tích mật độ, tính tỷ lệ tải, kiểm tra độ mới stale 180s | `http://127.0.0.1:8002` | A2A Protocol (`a2a-sdk`), Analytics |
| **MCP Server** | Cung cấp 4 công cụ đọc catalog, mật độ, đường đi, thời tiết | `http://127.0.0.1:8003` | Model Context Protocol (`mcp` SDK) |
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

## 3. Chạy Kiểm Thử Tự Động (10 Ca Nghiệm Thu)
Chạy toàn bộ 10 ca kiểm thử nghiệm thu bám sát mục 10 của kế hoạch:
```bash
python -m pytest tests/test_all_criteria.py -v
```

Các ca kiểm tra bao gồm:
1. `test_acceptance_baseline`: Nạp preset gia đình sinh đúng 2 phương án hợp lệ, buffer ≥ 10 phút.
2. `test_acceptance_missing_input`: Khách chat tự do thiếu chiều cao/thời gian thì A0 hỏi lại, không tự ý bịa dữ liệu.
3. `test_acceptance_multiturn_same_session`: Chat đa lượt "chỉ đi trong nhà, tối thiểu 2 điểm" giữ nguyên hồ sơ nhóm và sinh lịch trình 100% trong nhà.
4. `test_acceptance_aquarium_crowded`: Thủy cung quá tải 35 phút (>20p) bị loại khỏi lịch trình.
5. `test_acceptance_alpine_closed`: Điểm Alpine đóng cửa đột xuất bị loại khỏi lịch trình.
6. `test_acceptance_stale_data`: Dữ liệu cũ (>180s) được đánh dấu stale chính xác.
7. `test_acceptance_missing_data_no_zero_coercion`: Thiếu dữ liệu giữ nguyên `null`, không ép thành `0`.
8. `test_acceptance_no_feasible_plan`: Yêu cầu bất khả thi trả về `no_feasible_plan` và lý do nghẽn.
9. `test_acceptance_session_isolation`: Hai session độc lập không làm nhiễm dữ liệu của nhau.
10. `test_acceptance_event_audit_trail`: Chuỗi sự kiện A0, A2, A1 được ghi nhận đầy đủ vào SQLite.

---

## 4. Kiểm chứng Tương tác trên Giao diện Web

1. **Thử Preset Gia Đình 2 Phương Án**: Nhấn nút **👨‍👩‍👧 Gia đình 2 phương án** bên góc trái. Hệ thống sẽ hiển thị 2 thẻ lịch trình:
   - **Phương án 1 (Gentle)**: Nhẹ nhàng, ít chờ, thời gian dự phòng cao.
   - **Phương án 2 (More Rides)**: Nhiều trò chơi trải nghiệm hơn, khác biệt ít nhất 1 điểm hoạt động.
2. **Thử Multi-turn trong cùng phiên**: Nhấn nút **🏛️ Chỉ đi trong nhà** hoặc gõ tin nhắn *"Chỉ đi trong nhà, tối thiểu 2 điểm"*. Lịch trình mới sẽ cập nhật chỉ gồm các điểm trong nhà và giữ nguyên cấu hình gia đình.
3. **Thử Đổi Kịch Bản**: Chuyển dropdown sang *"2. Thủy cung quá tải (35 phút chờ)"* rồi yêu cầu lập lịch để quan sát A2 phát hiện hàng chờ 35 phút và A1 tự động thay thế bằng điểm khác.
4. **Kiểm chứng Nhật ký Trao đổi Agent (Audit Log)**: Nhấn vào tab **🔬 Nhật ký Trao đổi Agent (A2A & MCP Audit)** để xem toàn bộ danh sách lời gọi A0 ➔ A2, A0 ➔ A1, MCP Tool Calls. Bấm nút **🔍 Xem JSON** tại từng dòng để kiểm tra trực tiếp raw payload trao đổi giữa các Agent.
"# A2A-Demo" 
