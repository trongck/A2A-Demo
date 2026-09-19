# Kế hoạch triển khai demo V-AI: A0, A2, A1, MCP và A2A

**Mục tiêu:** khách chat với A0, A2 phân tích mật độ, A1 lập 1–2 lịch trình khả thi, A0 trả lời và tiếp tục điều chỉnh trong cùng phiên. Toàn bộ ứng dụng chạy local; không yêu cầu deploy hoặc push code.

**Giả định hiện hành:** sử dụng Python; nguồn runtime là `V-AI-Mock-Data-V2.json` dạng Google Places và được chuẩn hóa tại MCP. Các trường vận hành không có trong nguồn V2 phải giữ `null`/`unavailable`, không suy diễn thành dữ liệu thật.

## 1. Phạm vi và kết quả cần bàn giao

- Web chat tạo phiên, hiển thị `session_id`, nhận nhiều lượt hội thoại.
- A0 điều phối; A2 phân tích mật độ; A1 lập lịch. Người dùng luôn tương tác qua A0.
- Giao tiếp A0–A2 và A0–A1 qua A2A SDK; gọi công cụ dữ liệu qua MCP SDK.
- Một kho memory SQLite dùng chung, tách dữ liệu theo phiên, lưu được sau khi khởi động lại.
- Màn hình hiển thị 1–2 phương án thay thế, thời gian từng chặng, thời gian chờ, tổng chi phí và lý do đề xuất.
- Bảng sự kiện hiển thị agent đang chạy, tool được gọi, thời gian xử lý và lỗi; không hiển thị suy nghĩ nội bộ của mô hình.
- Có kịch bản baseline, tăng mật độ, đóng điểm và thiếu dữ liệu; có kiểm tra hội thoại nhiều lượt thật trong cùng phiên.
- README chạy local, file cấu hình mẫu, khóa phiên bản dependency và kiểm tra tích hợp.

## 2. Kiến trúc đề xuất

| Thành phần | Vai trò | Địa chỉ local dự kiến |
|---|---|---|
| Chat UI + backend A0 | Quản lý phiên, hiểu yêu cầu, gọi agent, lưu memory, trả lời | `127.0.0.1:8000` |
| A1 | A2A server, lập và kiểm tra lịch | `127.0.0.1:8001` |
| A2 | A2A server, phân tích mật độ | `127.0.0.1:8002` |
| MCP server | Cung cấp tool đọc catalog, mật độ, đường đi, thời tiết | `127.0.0.1:8003` |
| Shared memory | SQLite sau lớp truy cập của backend | `data/memory.sqlite` |

A0 là A2A client của hai specialist. A1 và A2 công bố Agent Card/skill tương ứng. Không cần cho A1 gọi trực tiếp A2: A0 kiểm soát thứ tự và phiên bản kết quả.

MCP SDK chính thức cung cấp client/server và Streamable HTTP; chọn transport này cho demo nhiều process. Dùng SDK để xử lý giao thức thay vì tự dựng REST rồi gọi đó là MCP. Nguồn: [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk).

A2A SDK có hướng dẫn Agent Card, executor, server/client và multi-turn. Chốt phiên bản SDK cụ thể sau smoke test, sau đó khóa dependency; không trộn code mẫu của các phiên bản giao thức khác nhau. Nguồn: [A2A Python Quickstart](https://a2a-protocol.org/latest/tutorials/python/1-introduction/).

LLM có thể dùng một model với ba vai trò/prompt riêng. A0 dùng model để hiểu và diễn đạt; A2 tính số bằng code; A1 dùng bộ lập lịch và validator xác định. Nếu model tham gia đề xuất lịch, lịch vẫn phải qua validator. Ứng dụng chạy local có thể gọi LLM API; nếu cần hoàn toàn offline thì cấu hình model local. Chế độ stub chỉ phục vụ kiểm tra kết nối, phải ghi rõ chưa phải demo chat hoàn chỉnh.

## 3. Luồng chạy bắt buộc

```mermaid
sequenceDiagram
    actor U as Khách
    participant O as A0
    participant D as A2
    participant P as A1
    participant M as MCP
    U->>O: Tạo phiên và gửi yêu cầu
    Note over O: Tạo session_id, turn_id; đọc memory
    alt Thiếu thông tin bắt buộc
        O-->>U: Hỏi bổ sung
        U->>O: Trả lời trong cùng phiên
    end
    Note over O: Lưu yêu cầu đã chuẩn hóa
    O->>D: A2A: phân tích mật độ
    D->>M: Đọc snapshot và thông số điểm
    M-->>D: Dữ liệu và thời điểm quan sát
    D-->>O: Kết quả mật độ dạng JSON
    Note over O: Kiểm tra và lưu kết quả A2
    O->>P: A2A: lập lịch từ yêu cầu và kết quả A2
    P->>M: Đọc điểm chơi, đường đi, thời tiết
    M-->>P: Dữ liệu lập lịch
    Note over P: Tạo phương án và chạy validator
    P-->>O: JSON lịch trình hoặc lý do không khả thi
    Note over O: Lưu lịch, kiểm tra phiên bản kết quả
    O-->>U: Trình bày phương án và cho phép chỉnh sửa
```

Đây là luồng thành công và nhánh hỏi lại. Nếu A2 lỗi hoặc kết quả không dùng được, A0 không gọi A1 như thể phân tích đã thành công. Cách phục hồi được quy định ở phần kiểm thử.

**Phụ thuộc khi chạy:** A1 phải đợi A0 lưu kết quả A2 hợp lệ. Trong một lượt A1, các lần đọc catalog và thời tiết độc lập có thể chạy song song; tra đường đi đợi danh sách node cần tính. Trong bản đầu, không cần tối ưu bằng cách khởi chạy A1 trước A2.

## 4. Hợp đồng JSON và trách nhiệm agent

Định nghĩa Pydantic/schema trước khi chia code. JSON dưới đây là payload nghiệp vụ của ứng dụng; envelope, message, task và artifact A2A do SDK xử lý. Không coi các tên trường nghiệp vụ này là tiêu chuẩn A2A.

| Hợp đồng | Trường bắt buộc |
|---|---|
| `NormalizedRequest` | Nhóm khách, thời gian, vị trí đầu/cuối, giới hạn bắt buộc, sở thích, số phương án |
| `AgentRequest` | `schema_version`, `session_id`, `turn_id`, `request_id`, `action`, `memory_ref`, `scenario_id`, `data_revision`, `input` |
| `AgentResult` | Các ID đối chiếu, `status`, `input_memory_version`, `data_revision`, `result`, `warnings`, `errors` |
| `CrowdAnalysis` | `analysis_id`, `simulation_now`, danh sách `service_id`, snapshot nguồn, tỷ lệ tải, mật độ, độ mới, thời gian chờ, trạng thái vận hành |
| `PlanResult` | `plan_id`, `analysis_id`, các chặng, đường đi, giờ đến/bắt đầu/kết thúc, chi phí, tổng thời gian, buffer, kiểm tra ràng buộc |

Ví dụ A0 giao A2, sau khi memory phiên bản 3 đã được lưu:

```json
{
  "schema_version": "1.0",
  "session_id": "demo_family_001",
  "turn_id": "turn_001",
  "request_id": "req_a2_001",
  "action": "analyze_crowd",
  "memory_ref": {"session_id": "demo_family_001", "version": 3},
  "scenario_id": "base",
  "data_revision": "google_places_v2",
  "input": {"scope": "all_park_services"}
}
```

A2 đọc view memory dành cho nhiệm vụ, gọi MCP, tính toán rồi trả `CrowdAnalysis`. A0 kiểm tra schema, IDs, data revision, độ mới và lưu thành `analysis_001`; memory tăng lên phiên bản 4. Chỉ sau bước này A0 mới gửi A1:

```json
{
  "schema_version": "1.0",
  "session_id": "demo_family_001",
  "turn_id": "turn_001",
  "request_id": "req_a1_001",
  "action": "create_plans",
  "memory_ref": {"session_id": "demo_family_001", "version": 4},
  "scenario_id": "base",
  "data_revision": "google_places_v2",
  "input": {
    "crowd_analysis_id": "analysis_001",
    "number_of_plans": 2
  }
}
```

Các ID và số phiên bản trên chỉ minh họa. Agent phải thực sự resolve tham chiếu qua lớp đọc memory; gửi `memory_ref` không tự khiến model biết nội dung. Agent phải báo lỗi khi không lấy được đúng phiên bản.

Trạng thái nghiệp vụ gồm `completed`, `needs_input`, `no_feasible_plan`, `failed`; ánh xạ sang trạng thái giao thức bằng adapter phù hợp SDK. Lưu riêng ánh xạ giữa ID ứng dụng và ID task/context của A2A.

## 5. MCP tools cần xây

Mọi lời gọi nhận context kịch bản/data revision đã được backend xác nhận. MCP server sở hữu quyền đọc file mock; A1/A2 không tự mở file để bỏ qua MCP.

| Tool dự kiến | Agent gọi | Input | Output tối thiểu |
|---|---|---|---|
| `get_attractions` | A1, A2 | `service_ids` hoặc toàn công viên | Điểm, lịch mở, thời lượng, điều kiện tham gia, giá, thông số vùng đếm |
| `get_crowd_snapshots` | A2 | `service_ids` | Snapshot, nguồn, chất lượng, trạng thái, `simulation_now`, ngưỡng độ mới và phân loại tải |
| `get_route_matrix` | A1 | Danh sách node cần xét | Thời gian/đường đi ngắn nhất mỗi cặp, cặp không thể tới, revision bản đồ |
| `get_weather` | A1 | Bắt đầu/kết thúc | Các cửa sổ thời tiết và thời gian không có dữ liệu |

`get_route_matrix` tính theo cạnh mở và hướng đi; không thay bằng khoảng cách đường thẳng. Có thể có cạnh 0 phút: dùng thuật toán đường đi có lưu chi phí tốt nhất để tránh lặp.

Áp dụng scenario lên bản sao baseline theo phiên. Chuyển scenario ở phiên A không được làm dữ liệu của phiên B thay đổi. Không expose `expected_plans.json` hay `example_a2_response.json` cho agent: đây là dữ liệu kiểm tra của người phát triển.

## 6. Shared memory

| Bảng | Nội dung |
|---|---|
| `sessions` | Phiên, hồ sơ/ràng buộc hiện tại, scenario, đồng hồ demo, memory version |
| `messages` | Lịch sử hội thoại theo phiên và lượt |
| `tasks` | Agent được giao, input version, request ID, A2A ID, trạng thái, thời gian |
| `agent_results` | Kết quả A2/A1 đã kiểm tra; snapshot và data revision liên quan |
| `plans` | Các phương án, phiên bản, phương án khách chọn nếu có |
| `events` | Sự kiện hiển thị tiến độ, tool call, lỗi và thời lượng |

Ba agent dùng cùng một nguồn memory. Backend A0 chịu trách nhiệm ghi theo transaction; specialist đọc view cần thiết qua lớp truy cập nội bộ và trả kết quả để A0 ghi. A2 chỉ cần phạm vi, thời gian và scenario; không cần toàn bộ thông tin cá nhân của nhóm.

- Mỗi phiên xử lý một lượt lập lịch tại một thời điểm; lượt mới được xếp hàng hoặc người dùng hủy lượt cũ.
- Kết quả của task cũ không được ghi đè lượt mới. Kiểm tra `turn_id`, input version, revision và trạng thái task.
- Memory version nghiệp vụ chỉ đổi khi context/kết quả liên quan đổi; log tiến độ không làm invalid toàn bộ nhiệm vụ đang chạy.
- Khi khách sửa yêu cầu, cập nhật đúng trường được sửa và giữ các giới hạn còn lại. Thiếu dữ liệu thì hỏi lại.
- Đổi scenario, thời gian, phạm vi hoặc dữ liệu nguồn thì vô hiệu kết quả A2 liên quan. Chỉ tái sử dụng phân tích khi còn mới và cùng phạm vi/revision.
- Đồng hồ fixture cố định; nếu cho phép tiến thời gian, phải tính lại thời gian còn lại và độ mới snapshot.

## 7. Logic nghiệp vụ cần cài

**A0:** phân loại yêu cầu → trích xuất input có schema → kiểm tra thiếu dữ liệu → lưu context → giao A2 → kiểm tra/lưu phân tích → giao A1 → nhận kết quả đã validate → lưu và diễn đạt. Các bước điều phối là state machine bằng code. Model không được tự bỏ qua bước A2 hoặc nới giới hạn bắt buộc.

**A2:** ghép snapshot với đúng điểm/vùng; kiểm tra `data_quality`, trạng thái, timestamp; tính `occupancy_ratio = current_people / comfort_capacity_people` và `density_people_per_m2 = current_people / area_m2`. Phân loại theo config: dưới 0,4 là low; 0,4 đến dưới 0,7 medium; 0,7 đến dưới 1 high; từ 1 là overloaded trong demo. Mẫu số thiếu/không dương phải báo lỗi dữ liệu; null không đổi thành 0. Snapshot cũ hơn 180 giây là stale theo config hiện tại. Phân loại tải không thay thế đánh giá an toàn thực tế.

**A1:**

1. Lấy input đã chuẩn hóa và đúng phân tích A2 được chỉ định.
2. Lọc điều kiện nhóm khách, sở thích bắt buộc, chi phí, hoạt động ngoài trời, điểm đóng/bảo trì và dữ liệu không được phép dùng.
3. Đọc catalog, thời tiết, tính đường đi; xét lịch mở tại thời điểm đến. Điểm chưa mở hiện tại không có nghĩa đóng cả ngày.
4. Tìm các tổ hợp/thứ tự khả thi bằng tìm kiếm có cắt nhánh trên tập nhỏ của demo. Số điểm tối đa và giới hạn tính toán phải cấu hình; nếu dùng giới hạn, không tuyên bố đã chứng minh vô nghiệm toàn bộ khi chỉ hết ngân sách tìm kiếm.
5. Tính `giờ đến = kết thúc chặng trước + đi bộ`; với walk-in, `bắt đầu = giờ đến + chờ`. Với show, dùng giờ suất và điều kiện check-in; tránh cộng chờ hai lần.
6. Tính cả đường quay về điểm kết thúc và buffer tối thiểu. Kiểm tra điều kiện từng thành viên, giới hạn chờ từng điểm, thời tiết cho cả thời lượng hoạt động và chi phí cả nhóm.
7. Xếp hạng hai phong cách: nhẹ nhàng/ít chờ và nhiều trò phù hợp. Cách chấm điểm là cấu hình, giới hạn bắt buộc luôn được xét trước.
8. Hai phương án phải khác lựa chọn hoạt động có ý nghĩa, không chỉ đổi thứ tự. Nếu chỉ có một phương án hợp lệ, trả một và nêu lý do.
9. Chạy validator xác định trước khi trả JSON. Nếu không khả thi, trả các ràng buộc gây khó và đề nghị khách thay đổi; không tự ý sửa yêu cầu.

Bộ mock giữ thời gian chờ hiện tại cho cả cửa sổ lập lịch để demo; phải ghi rõ đây là giả định, không phải dự báo mật độ tương lai. Khi thực thi chuyến đi hoặc đổi đồng hồ cần kiểm tra lại.

## 8. Backlog triển khai và phụ thuộc

| Mã | Đầu việc | Phụ thuộc | Đầu ra / tiêu chí hoàn thành |
|---|---|---|---|
| T1 | Chốt input, JSON schema, ID, lỗi, ownership memory | Không | Schema có mẫu hợp lệ/không hợp lệ; cả nhóm dùng chung |
| T2 | Scaffold, cấu hình, smoke test SDK A2A/MCP | T1 | A0 gọi được specialist mẫu qua A2A; specialist gọi được tool MCP; khóa phiên bản |
| T3 | MCP tools trên dataset và scenario | T1, T2 | Đọc đúng fixture; routing đúng; không lộ output tham chiếu |
| T4 | SQLite, session API, memory views, versioning | T1 | Tạo/resume phiên; cách ly hai phiên; đọc đúng version |
| T5 | Agent A2 và kết quả JSON | T3, T4 | Có phân loại tải, stale/unknown và nguồn dữ liệu; A2A trả schema đúng |
| T6 | Agent A1, bộ tìm lịch và validator | T3, T4; hoàn thiện tích hợp cần T5 | Sinh 1–2 lịch hợp lệ từ phân tích thực; không đọc expected plans |
| T7 | A0 state machine và tích hợp | T4; hoàn thiện cần T5, T6 | A2 hoàn tất và được lưu trước khi A1 nhận nhiệm vụ |
| T8 | UI chat, form preset, plan cards, event panel | T1, T4; hoàn thiện cần T7 | Chat nhiều lượt, thấy session và trạng thái; preset hiển thị input đi kèm |
| T9 | Kiểm tra tích hợp, kịch bản lỗi, hướng dẫn chạy | T3–T8 | Các ca nghiệm thu phía dưới đạt; chạy lại được từ môi trường sạch |

**Có thể làm song song khi phát triển:** sau T1, một người làm T2/T3; một người làm T4/A0; một người làm UI và skeleton A1. Sau khi schema ổn định, A1 có thể phát triển với stub CrowdAnalysis đã gắn nhãn; nghiệm thu phải thay bằng A2 thật. Điều này không thay đổi thứ tự A2 → A1 khi chạy demo.

**Ước lượng cho nhóm 3 người:**

| Ngày | Mốc chính |
|---|---|
| 1 | Chốt schema, chạy thử hai giao thức, khởi tạo memory, UI khung |
| 2 | MCP hoàn chỉnh; A2 phân tích baseline; A1 có thuật toán/validator cơ bản |
| 3 | Tích hợp A0 → A2 → A1, sinh hai lịch và hiển thị UI |
| 4 | Chat sửa yêu cầu trong cùng phiên, scenario thay đổi, timeout và lỗi dữ liệu |
| 5 | Chạy nghiệm thu, sửa lỗi còn lại, hoàn thiện README và diễn tập |

Dành thêm thời gian nếu nhóm mới học Python/API hoặc gặp khác biệt phiên bản SDK. Kế hoạch không yêu cầu framework điều phối bổ sung để hoàn thành bản đầu.

## 9. Cấu trúc module dự kiến

| Đường dẫn tương đối dự kiến | Nội dung |
|---|---|
| `apps/chat/` | UI chat, form input và plan cards |
| `agents/a0/` | Điều phối, intent extraction, final response |
| `agents/a1/` | A2A executor, planner, validator |
| `agents/a2/` | A2A executor, crowd analysis |
| `mcp_server/` | Tools, adapter fixture, scenario và routing |
| `shared/contracts/` | Schema request/result/error |
| `shared/memory/` | Repository SQLite, snapshot/version, read views |
| `shared/llm/` | Adapter model API/local, structured output |
| `data/` | Dataset và SQLite tạo lúc chạy |
| `tests/fixtures/` | Kết quả tham chiếu, không đưa vào tool runtime |
| `tests/` | Kiểm tra tính đúng nghiệp vụ và giao tiếp thật |
| `scripts/run_local.py` | Khởi động process, kiểm tra sẵn sàng, dừng gọn |
| `.env.example`, file lock, `README.md` | Cấu hình, dependency và cách chạy |

Đây là cấu trúc cần triển khai, chưa phải các file ứng dụng đã được tạo.

## 10. Tiêu chí nghiệm thu

| Ca | Thao tác | Kết quả bắt buộc |
|---|---|---|
| Nguồn V2 | Đọc `V-AI-Mock-Data-V2.json` | Có 267 Google Places; mọi kết quả runtime mang revision `google_places_v2` |
| Baseline | Gửi đủ thành viên và khung giờ | Có 2 phương án khác nhau, ít nhất 3 hoạt động/phương án và về đúng node với buffer ≥10 phút |
| Input thiếu | Chat tự do chưa cho chiều cao trẻ/thời gian | A0 hỏi đúng thông tin ảnh hưởng lựa chọn; không lén lấy hồ sơ fixture |
| Multi-turn thật | Trong cùng phiên nói “chỉ đi trong nhà, tối thiểu 2 điểm” | Giữ hồ sơ và giới hạn chưa sửa; cập nhật indoor/min_activity_count; tăng phiên bản lịch; các điểm đều trong nhà |
| Thiếu crowd | Phân tích catalog V2 | `current_people`, `wait_minutes` giữ null và tải là unknown; không suy diễn từ rating/reviews |
| Revision mismatch | Cho agent/tool trả revision khác V2 | A0/A1/A2 từ chối kết quả, không trộn dữ liệu |
| Không khả thi | Yêu cầu vượt thời gian/điều kiện nhóm | Trả `no_feasible_plan` hoặc thông báo giới hạn tìm kiếm; không tạo lịch sai |
| MCP/A2A lỗi | Tắt MCP hoặc một specialist | Có timeout và lỗi rõ; không tiếp tục bằng số bịa; UI thoát trạng thái loading |
| Hai phiên | Hai tab có scenario/input khác nhau | Memory và override không lẫn nhau |
| Khởi động lại | Dừng rồi chạy lại | Đọc lại được phiên/lịch đã lưu; task dang dở được đánh dấu gián đoạn, không tự coi đã thành công |
| Kết quả muộn | Task cũ trả sau khi bị hủy | Không ghi đè turn mới |

Timeout cấu hình riêng cho tool và agent. Chỉ retry lỗi tạm thời trong giới hạn, ví dụ tối đa một lần; giữ idempotency key và kiểm tra task đang chạy để không tạo nhiệm vụ trùng. Không retry mù lỗi input hoặc không khả thi.

Lưu ý: `indoor_followup` trong bộ dữ liệu hiện tại là một fixture độc lập. Chạy fixture đó không chứng minh đã làm đúng multi-turn; phải chạy ca cùng session ở bảng trên.

## 11. Kịch bản trình diễn 5–7 phút

1. Khởi động local; xem trạng thái sẵn sàng của A0/A1/A2/MCP.
2. Tạo phiên mới; hiển thị session_id. Chọn preset gia đình và xem đủ input trước khi gửi.
3. Gửi yêu cầu hai phương án. Theo dõi event A0 → A2, tool MCP, kết quả A2 được lưu, rồi A0 → A1.
4. Mở hai plan cards: từng điểm, giờ đến, thời gian chờ, đi bộ, chi phí và buffer.
5. Chat chỉnh “chỉ trong nhà, tối thiểu 2 điểm” trong cùng session; xem lịch mới vẫn giữ hồ sơ nhóm.
6. Mở health A0/A1/A2/MCP và xác nhận cả bốn cùng báo `google_places_v2`.
7. Mở bản ghi task/kết quả JSON để giải thích A2A là giao agent, MCP là gọi tool và shared memory là ngữ cảnh chung.

**Hoàn thành khi:** demo chạy từ hướng dẫn, khách chat được nhiều lượt qua A0, giao tiếp A2A/MCP được quan sát thực tế, lịch vượt qua validator, và không cần chép lịch mẫu vào response.
