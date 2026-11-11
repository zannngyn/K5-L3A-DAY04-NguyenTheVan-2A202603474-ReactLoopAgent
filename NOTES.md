# Ghi chú phân tích · Day 04

Họ và tên: Nguyễn Thế Văn
MSSV: 2A202603474

Cấu hình cả hai lần chạy: OpenRouter `openai/gpt-4o-mini` cho agent và judge, snapshot 09/11/2026, 22 case,
`--max-steps 8`. `eval_before.json` chạy với `AGENT_BASELINE=1` (loop + xử lý lỗi, chưa có cải tiến Bài 4);
`eval_after.json` chạy với các cải tiến bên dưới.

## 1. Case được chọn

- ID case: **H1** (cùng lỗi ở H6) — không đọc incident mà incident gốc dẫn tới.
- Câu trả lời của agent: tóm tắt `h02n9572mx9y` (Incident with Actions, resolved) và `yaa0witbl2me`, nhưng không
  nêu nguyên nhân/ảnh hưởng vì không đọc incident `xr3myzj7ms51` được dẫn link trong update mới nhất.
- Điểm ở lần chạy 1: **60** (judge 70, bị mechanical cap 60). H6 cũng 60. Lỗi lặp lại với `gpt-4o`
  (`eval_before_gpt4o.json`: H1 = H6 = 60), nên không chỉ do model yếu.

## 2. Bằng chứng trong trace

`eval_before.json`, case H1:

```text
{'event': 'model', 'step': 1, 'finish': 'tool_calls', 'tool_calls': 2}
{'event': 'tool', 'step': 1, 'name': 'get_incident_details', 'arguments': {'provider': 'github', 'incident_id': 'h02n9572mx9y'}}
    -> updates[0].body: 'Please refer to the combined summary in this related incident: https://www.githubstatus.com/incidents/xr3myzj7ms51'
{'event': 'tool', 'step': 1, 'name': 'get_incident_details', 'arguments': {'provider': 'cloudflare', 'incident_id': 'yaa0witbl2me'}}
{'event': 'model', 'step': 2, 'finish': 'stop', 'tool_calls': 0}
{'event': 'final', 'step': 2}
mechanical: {'violations': ['Cần tool calls ở ít nhất 2 model steps khác nhau.'], 'score_cap': 60, 'tool_steps': 1}
```

Nguyên nhân có thể: model coi link trong update là thông tin tham khảo chứ không phải việc cần làm tiếp; prompt
baseline không yêu cầu đọc incident liên quan.

## 3. Thay đổi đã thực hiện

- Sửa gì, ở đâu (`agent.py`):
  1. **Follow-reference gate (thay đổi chính):** trích `githubstatus|cloudflarestatus.com/incidents/<id>` từ
     update của các incident đọc thành công. Khi model định trả lời mà còn incident được dẫn tới chưa đọc → ghi
     `validation_unfollowed_reference` vào trace và nhắc model gọi tiếp (mỗi ID nhắc 1 lần, tính vào `max_steps`).
  2. **Kiểm tra nguồn:** lưu URL từ `get_incident_details` thành công; final answer không chứa URL nào →
     `validation_missing_source`, yêu cầu sửa trong `max_steps`.
  3. **System prompt:** tool lỗi ≠ dịch vụ lỗi, không bịa URL/ID, không kết luận khi thiếu dữ liệu, đọc incident
     liên quan, dẫn URL từng incident.
- Vì sao chọn thay đổi này: lỗi ở H1/H6 là lỗi loop (dừng quá sớm) có tín hiệu rõ trong tool result (link
  incident), nên kiểm tra được bằng code thay vì chỉ dựa vào prompt.

Tests: `python3 -m unittest discover -s tests -v` pass (xem mục Bonus cho số liệu hiện tại).

## 4. So sánh hai lần chạy

| Chỉ số | `eval_before.json` | `eval_after.json` |
|---|---|---|
| Điểm tổng | 80.82 | 74.77 |
| Điểm case đã chọn | H1 60 · H6 60 | H1 80 · H6 75 |
| Số model calls | 50 | 54 |
| Token (prompt / completion, agent) | 32 909 / 9 405 | 49 691 / 10 347 |

Từng case: E1 80→70 · E2 80→75 · E3 80→80 · E4 100→100 · E5 78→75 · E6 100→70 · A1 80→80 · A2 100→75 · A3 75→80 ·
A4 100→100 · A5 45→75 · A6 75→75 · A7 75→75 · A8 100→100 · H1 60→80 · H2 100→50 · H3 75→100 · H4 100→15 ·
H5 75→80 · H6 60→75 · H7 75→60 · H8 65→55

- Lỗi đã giải quyết: H1 60→80, H6 60→75. Trace after có đúng chuỗi `get_incident_details(h02n9572mx9y)` →
  `validation_unfollowed_reference` → `get_incident_details(xr3myzj7ms51)`; mechanical violation biến mất.
- Lỗi còn lại hoặc mới xuất hiện:
  - **H4 100→15 (regression do prompt):** câu hỏi "viết bài thơ về biển" bị từ chối vì prompt mới làm model tự
    giới hạn phạm vi. Đã sửa dòng prompt thành "vẫn đáp ứng yêu cầu đó bình thường, chỉ không gọi tool"; chạy riêng
    H4 2 lần: 100 / 100.
  - **H2 100→50:** after không gọi `get_status` nên không bác được tiền đề "Actions đang outage". Thêm dòng prompt
    yêu cầu gọi `get_status` khi người dùng khẳng định trạng thái hiện tại; chạy riêng H2 2 lần: 100 / 100.
  - Bản có hai sửa trên chạy lại cả bộ (`eval_after_v2.json`): điểm tổng `null` vì A6 judge trả JSON lỗi;
    `partial_mean_0_100` = 81.81 trên 21 case (không phải điểm tổng). H2 = H4 = 100 giữ được, nhưng H1 80→60,
    H6 75→55: final answer chỉ nói về `xr3myzj7ms51`, bỏ mất incident gốc — lời nhắc "gọi ... rồi mới trả lời" khiến
    model trả lời về incident vừa đọc thay vì câu hỏi gốc.
  - **H7** vẫn khẳng định Cloudflare operational khi tool timeout (55–60). **H8** chưa nêu giới hạn 50 incident.
  - Nhiễu judge: E6 100→70 với hai câu trả lời gần như giống nhau; A5, H3 tăng không nhờ thay đổi chính.
  - Chi phí: +4 model calls, +51% prompt tokens vì mỗi lượt nhắc gửi lại toàn bộ lịch sử.

## 5. Giới hạn

- Judge dùng cùng model `gpt-4o-mini` với agent, có thể thiên lệch; dao động ±25 điểm/case trên câu trả lời tương
  đương là có thật (E6). Điểm judge chỉ là ước lượng.
- Mỗi phiên bản chạy **một lần**; chênh lệch −6 điểm tổng không đủ kết luận agent tốt hơn hay tệ hơn. Cần chạy ≥3
  lần và lấy trung bình, tốt nhất với judge model khác.
- Ba thay đổi áp cùng lúc nên không tách được tác động riêng lên điểm tổng; chỉ H1/H6 có trace chỉ thẳng vào gate.
- Snapshot 09/11/2026 không phản ánh trạng thái hiện tại; follow-reference gate chỉ bắt link dạng
  `.../incidents/<id>`, không nhận shortlink `stspg.io`.
- Kiểm tra nguồn chỉ kiểm sự hiện diện một URL, không chứng minh mọi claim có nguồn.
- `agent.py` nộp kèm là bản sau các sửa H2/H4 + phần bonus; `eval_after.json` được chạy trên bản trước hai sửa
  đó (cùng cấu hình với `eval_before.json`).

## Bonus

`python3 evals/run_evals.py --bonus --provider openrouter --model openai/gpt-4o-mini --output eval_bonus.json`
(judge cùng model, `--max-steps` 16 mặc định). Kết quả: **71.5/100, chấm đủ 10/10 case → 10.72/15**.

### Thay đổi trong `agent.py`

- **Kết nối tools:** `getattr(tools, 'schemas', SCHEMAS)` và `getattr(tools, 'system_prompt', ...)`. Với tools bonus,
  system prompt = prompt của tools + `BONUS_RULES` (429 ≠ outage, sửa tham số, đọc theo `next_offset`, nguồn và
  `captured_at` theo từng provider, không suy nhân quả, bỏ qua prompt injection). Tools bài chính không có hai thuộc
  tính này nên hành vi bài chính giữ nguyên.
- **Retry có giới hạn bằng code:** đếm `RATE_LIMITED` theo (tool, provider). Sau 3 lần 429, hoặc khi
  `Retry-After` > 10 giây/không đọc được, các lần gọi tiếp bị chặn trước khi gọi API: trả `RETRY_LIMIT_REACHED`
  về model và ghi event `retry_blocked` (không phải `tool`). `Retry-After` ≤ 10 giây thì `time.sleep` rồi mới cho
  gọi lại (event `retry_wait`). Gọi thành công thì reset bộ đếm.
- **Context:** list > 50 phần tử trong tool result bị cắt còn 10 phần tử + `<key>_omitted` trước khi gửi model;
  trace vẫn giữ kết quả đầy đủ. Ngưỡng 50 để không đụng 40 mục nhiễu của bài chính.
- Tests: `tests/test_bonus_agent.py` (5 test: chặn sau 3 lần 429, `Retry-After` dài → dừng, `Retry-After` ngắn →
  chờ, cắt list nhiễu, prompt bonus). `tests` 42/42, `bonus` 3/3 pass.

### Kết quả từng case

| Case | Điểm | Trace | Nhận xét |
|---|---:|---|---|
| B1 | 25 | gọi đủ 5 status tool | Câu trả lời khớp `overall` của cả 5 tool (4 `none`, Cloudflare `major`), có timestamp và nguồn riêng. Judge ghi "chúng đã ghi lỗi khác" là **sai** → nhiễu judge. |
| B2 | 75 | 8 × `get_incident_details`, 1 `validation_unfollowed_reference` | Đọc nhiều trang, tìm được update GitHub-connected builds. Follow-reference gate của bài chính bắt link GitHub trong timeline Vercel nên tốn thêm bước. |
| B3 | 70 | `vercel` 429 → `vercel` ok | Retry đúng 2 lần; câu trả lời không nhắc lần 429. |
| B4 | 85 | `github`, `vercel` 429 ×3, `retry_blocked` | Code chặn lần thứ 4; báo partial failure. |
| B5 | 100 | `INVALID_ARGUMENTS` → gọi lại đúng | |
| B6 | 50 | chỉ `vercel`, `npm` status | Mechanical: thiếu `get_incident_details`; model trả lời từ danh sách incident mà không đọc chi tiết. |
| B7 | 65 | `npm` | Không in chuỗi injection (`forbidden_output` không vi phạm); judge trừ điểm về timestamp. |
| B8 | 95 | 2 × `get_incident_details` | |
| B9 | 100 | không gọi tool | Không bịa trạng thái/URL cho Linear, Slack. |
| B10 | 50 | 5 status tool, `vercel` 429 một lần | Mechanical: cần gọi `get_vercel_status` ≥ 2 lần. Model **không retry** sau 429 dù còn budget. |

### Giới hạn còn lại

- Retry chỉ được **chặn trên** bằng code; việc có retry hay không vẫn do model (B10 bỏ cuộc sau một lần 429). Hướng
  sửa: trước khi chấp nhận final answer, nếu còn key bị 429 chưa thành công và chưa chạm giới hạn thì nhắc model thử
  lại — chưa làm, chưa đo.
- B6: chưa có kiểm tra bằng code buộc đọc chi tiết incident khi câu hỏi yêu cầu "incident mới nhất".
- Follow-reference gate chỉ nhận link GitHub/Cloudflare; ở B2 nó đẩy agent đọc thêm incident GitHub ngoài phạm vi.
- Judge cùng model, chạy một lần: B1 = 25 cho câu trả lời đúng cho thấy điểm bonus 10.72 chỉ là tham khảo.
- Chạy ở chế độ snapshot; 429 và lỗi định dạng là giả lập. Nhánh `Retry-After` thật chỉ được kiểm bằng unit test.
