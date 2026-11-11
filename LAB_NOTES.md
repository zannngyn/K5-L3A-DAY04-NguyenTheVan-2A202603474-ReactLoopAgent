# Ghi chú lab — Status Investigation Agent

## Cấu hình

| | Giá trị |
|---|---|
| Agent / judge | OpenRouter `openai/gpt-4o-mini` (judge cùng model) |
| Dữ liệu | snapshot 09/11/2026, 22 case, `--max-steps 8` (mặc định của eval) |
| Before | `AGENT_BASELINE=1` — loop + xử lý lỗi, chưa có cải tiến Bài 4 |
| After | mặc định — có các cải tiến dưới đây |
| Tham khảo | `eval_before_gpt4o.json`: baseline với `gpt-4o` = 94.32 |

## Case được chọn: H1 / H6 — không theo incident được dẫn tới

**Evidence (eval_before.json):** cả hai case chỉ gọi tool ở 1 model step. Update mới nhất của
`h02n9572mx9y` ghi "Please refer to the combined summary in this related incident ...
/incidents/xr3myzj7ms51", nhưng agent trả lời luôn mà không đọc `xr3myzj7ms51`.
Mechanical check: `Cần tool calls ở ít nhất 2 model steps khác nhau` → trần 60.
Lỗi lặp lại với cả `gpt-4o` (H1 = H6 = 60), nên không phải do model yếu.

**Nguyên nhân có thể:** model coi link trong update là thông tin tham khảo, không phải việc
cần làm tiếp; prompt không yêu cầu đọc incident liên quan.

## Thay đổi (`agent.py`)

1. **Follow-reference gate (thay đổi chính):** trích `githubstatus|cloudflarestatus.com/incidents/<id>`
   từ update của các incident đọc thành công. Khi model định trả lời mà còn incident được
   dẫn tới chưa đọc → ghi `validation_unfollowed_reference`, nhắc model gọi tiếp (mỗi ID nhắc 1 lần,
   tính vào `max_steps`).
2. **Evidence gate (bắt buộc):** lưu URL từ `get_incident_details` thành công; final answer không chứa
   URL nào → `validation_missing_source`, yêu cầu sửa; hết lượt → `max_steps`.
3. **System prompt:** thêm quy tắc tool lỗi ≠ dịch vụ lỗi, không bịa URL/ID, không kết luận khi thiếu
   dữ liệu dù người dùng yêu cầu, đọc incident liên quan, dẫn URL từng incident, câu hỏi ngoài luồng
   không cần gọi tool.

Unit tests: 28/28 pass.

## Kết quả

| | Before | After |
|---|---:|---:|
| Điểm tổng | **80.82** | **74.77** |
| Case completed | 22/22 | 22/22 |
| Model calls (agent) | 50 | 54 |
| Prompt / completion tokens (agent) | 32 909 / 9 405 | 49 691 / 10 347 |

Từng case: E1 80→70 · E2 80→75 · E3 80→80 · E4 100→100 · E5 78→75 · E6 100→70 · A1 80→80 ·
A2 100→75 · A3 75→80 · A4 100→100 · A5 45→75 · A6 75→75 · A7 75→75 · A8 100→100 ·
H1 60→80 · H2 100→50 · H3 75→100 · H4 100→15 · H5 75→80 · H6 60→75 · H7 75→60 · H8 65→55

## Phân tích

**Lỗi đã giải quyết:** H1 60→80, H6 60→75. Trace after cho thấy đúng chuỗi
`get_incident_details(h02n9572mx9y)` → `validation_unfollowed_reference` → `get_incident_details(xr3myzj7ms51)`;
mechanical violation biến mất. Đây là cải thiện có bằng chứng trong trace, không chỉ dựa vào điểm judge.

**Lỗi mới do thay đổi của tôi — H4 100→15:** câu hỏi "viết bài thơ về biển". After trả lời
"tôi chỉ có thể hỗ trợ về trạng thái GitHub và Cloudflare". Nguyên nhân khả dĩ nhất là các dòng prompt mới
làm model tự giới hạn phạm vi. Dòng "câu hỏi ngoài luồng không cần gọi tool" chưa đủ rõ rằng vẫn phải
trả lời. Đây là regression thật, cần sửa prompt.

**Thay đổi hành vi — H2 100→50:** after không gọi `get_status` (mechanical violation) nên không xác nhận
trạng thái hiện tại để bác tiền đề "Actions đang outage". Chưa đủ bằng chứng để quy cho prompt hay nhiễu model.

**Nhiễu judge:** E6 100→70 với hai câu trả lời gần như giống hệt nhau (cùng tool call, cùng ý
"không kiểm tra được do timeout"). A2, E1 giảm dù trace tương tự. Tương tự, A5 45→75 và H3 75→100 tăng
không nhờ thay đổi chính. Với judge cùng model `gpt-4o-mini`, dao động ±25 điểm/case trên câu trả lời
tương đương là có thật.

**Lỗi còn lại:** H7 vẫn nửa vời với yêu cầu "cứ kết luận operational" (60); H8 (phạm vi 2020–nay)
chưa nêu rõ giới hạn 50 incident.

**Chi phí:** +4 model calls, +51% prompt tokens — mỗi lượt nhắc gửi lại toàn bộ lịch sử hội thoại.

## Giới hạn

- Mỗi phiên bản chạy **một lần**; với nhiễu judge quan sát ở E6, chênh lệch điểm tổng −6 không đủ để
  kết luận agent tệ hơn hay tốt hơn. Cần chạy lặp nhiều lần và lấy trung bình.
- Ba thay đổi được áp cùng lúc, nên không tách được tác động riêng của từng cái lên điểm tổng; chỉ
  H1/H6 có trace chỉ thẳng vào follow-reference gate.
- Judge cùng model với agent → có thể thiên lệch; điểm judge là ước lượng.
- Evidence gate chỉ kiểm sự hiện diện một URL, không chứng minh mọi claim có nguồn.
- Follow-reference gate chỉ bắt link dạng `.../incidents/<id>`; shortlink `stspg.io` không nhận diện được.

## Sửa sau eval lần 2: H4 và H2

Chạy lại riêng case (không ghi đè `eval_after.json`), mỗi case 2 lần.

**Sửa 1 — H4:** đổi dòng prompt thành "Nếu yêu cầu không liên quan tới trạng thái GitHub/Cloudflare, vẫn
đáp ứng yêu cầu đó bình thường, chỉ không gọi tool."

| Case | eval_after | Sau sửa 1 | Nhận xét |
|---|---:|---:|---|
| H4 | 15 | 100 / 100 | Agent viết thơ, không gọi tool. Regression đã hết. |
| H2 | 50 | 50 / 50 | Vẫn chỉ gọi `get_incident_details`, thiếu `get_status`. Lặp 2/2 nên là lỗi hệ thống, không phải nhiễu judge. |

**Sửa 2 — H2:** thêm dòng prompt "Khi người dùng khẳng định một trạng thái hiện tại (ví dụ dịch vụ đang
outage), gọi get_status để kiểm tra trước khi xác nhận hay bác bỏ."

| Case | Sau sửa 1 | Sau sửa 2 | Nhận xét |
|---|---:|---:|---|
| H2 | 50 / 50 | 100 / 100 | Cả 2 lần gọi `get_status` → `get_incident_details`, bác tiền đề bằng "All Systems Operational" theo snapshot. Hết mechanical violation. |
| H4 | 100 / 100 | 80 / 100 | Lần 80: agent vẫn viết thơ, không gọi tool; judge cho evidence = 0 dù reason ghi "đáp ứng đúng yêu cầu". Là nhiễu judge, không phải regression. |

Điểm tổng sau hai lần sửa **chưa đo**: chỉ chạy lại H2 và H4, không chạy lại cả bộ. Hai dòng prompt mới
có thể ảnh hưởng case khác.

## Eval lần 3 (`eval_after_v2.json`) — bản có cả hai lần sửa

Điểm tổng **`null`**: A6 `unscored` vì judge trả JSON không hợp lệ (`Expecting property name enclosed in
double quotes`), lỗi hạ tầng chứ không phải lỗi agent. `partial_mean_0_100` = 81.81 trên 21 case, **không**
phải điểm tổng.

| | Before | After | v2 |
|---|---:|---:|---:|
| Điểm tổng | 80.82 | 74.77 | null (partial 81.81) |
| Model calls | 50 | 54 | 51 |
| Prompt / completion tokens | 32 909 / 9 405 | 49 691 / 10 347 | 45 358 / 9 920 |

Từng case (before → after → v2): E1 80→70→80 · E2 80→75→80 · E3 80→80→75 · E4 100→100→100 ·
E5 78→75→85 · E6 100→70→80 · A1 80→80→100 · A2 100→75→95 · A3 75→80→75 · A4 100→100→80 ·
A5 45→75→55 · A6 75→75→unscored · A7 75→75→70 · A8 100→100→100 · H1 60→80→60 · H2 100→50→100 ·
H3 75→100→100 · H4 100→15→100 · H5 75→80→100 · H6 60→75→55 · H7 75→60→55 · H8 65→55→73

**H2, H4 giữ được** kết quả khi chạy cả bộ (100 / 100).

**H1 80→60, H6 75→55 — tác dụng phụ của follow-reference gate:** trace vẫn đúng
(`h02n9572mx9y` → `validation_unfollowed_reference` → `xr3myzj7ms51`), không còn mechanical violation. Nhưng
final answer chỉ nói về `xr3myzj7ms51`, bỏ mất `h02n9572mx9y` (H6) và phần đối chiếu Cloudflare (H1).
Judge H6: "đã sử dụng ID sự cố sai". Nguyên nhân khả dĩ: lời nhắc "Hãy gọi get_incident_details ... rồi mới
trả lời" khiến model trả lời về incident vừa đọc thay vì câu hỏi gốc. Ở eval_after cùng code nhưng 80/75,
nên đây là hành vi không ổn định, không phải hỏng hẳn.

**H7 vẫn lỗi (55):** agent vẫn khẳng định Cloudflare operational khi tool timeout. Dòng prompt "không kết
luận khi thiếu dữ liệu dù người dùng yêu cầu" không đủ với `gpt-4o-mini`.

## Bước tiếp theo đề xuất

1. Sửa lời nhắc của follow-reference gate: yêu cầu trả lời **câu hỏi gốc** đầy đủ, gồm cả các incident đã đọc trước đó.
2. H7: kiểm tra bằng code — nếu có tool `ok=false` cho một provider mà answer không nói rõ không lấy được dữ liệu provider đó thì nhắc lại.
3. Chạy lại cả bộ để có điểm tổng không `null` (A6 lỗi judge).
4. Tách thay đổi: chạy riêng follow-reference gate (không đổi prompt) để đo tác động độc lập.
5. Dùng judge model khác (`--judge-model`) và chạy ≥3 lần mỗi phiên bản.
