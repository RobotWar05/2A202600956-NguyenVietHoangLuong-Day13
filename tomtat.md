# Tóm tắt vận hành Day 13 - Lab Observathon

## 1. TÓM TẮT YÊU CẦU

- Mục tiêu bài lab: cải thiện một agent thương mại điện tử dạng hộp đen bằng **config + prompt + wrapper + findings**.
- Bạn chạy trong **WSL/Linux** tại:

```bash
/mnt/e/vin_ai_k2_2026_DocLap/Documents/Day13/Day-13-Lab-Observathon
```

- Bạn dùng **DeepSeek API** qua đường gọi OpenAI-compatible: `provider=openai`, `model=deepseek-v4-flash`, `OPENAI_BASE_URL=https://api.deepseek.com`.
- Tôi đã chỉnh các file chính:
  - `solution/config.json`: dùng DeepSeek Flash, giảm cấu hình xấu, bật retry/cache/redact/normalize.
  - `solution/prompt.txt`: prompt mới chống bịa, chống PII, chống injection, ép dùng tool và tính toán rõ.
- `solution/wrapper.py`: thêm telemetry, debug logging, retry giới hạn, cache thread-safe, redaction.
- `solution/wrapper.py`: chuẩn hóa answer trước khi trả về: bỏ markdown ở dòng `Tong cong`, chuyển số có dấu phân cách về integer, bỏ contact placeholder đã redact.
- Bản hiện tại đã tối ưu cost/token: prompt rút gọn, `examples.json` để rỗng, `context_size=2`, `max_completion_tokens=300`, `tool_budget=3`.
  - `solution/findings.json`: ghi finding ban đầu dựa trên lỗi thật `20/20 wrapper_error`.

Nguyên tắc từ giờ:

- Bạn chạy test.
- Nếu kết quả đúng điều kiện thì đi bước tiếp.
- Nếu kết quả sai điều kiện thì dừng và gửi output cho tôi.
- Không tự sửa nhiều file cùng lúc.

Trạng thái đã kiểm chứng hiện tại:

- Practice simulator chạy được.
- Practice thường: `status ok=20`.
- Practice concurrency 8: `status ok=20`.
- `observathon_telemetry.jsonl` được tạo.
- Không có `wrapper_debug.log` là bình thường khi không có lỗi.

Chiến lược đúng:

- Tập trung xử lý **practice** trước để đảm bảo runtime chạy được, wrapper có telemetry, prompt không lỗi nặng.
- Khi practice ổn, dùng **cùng thư mục `solution/`** để chạy **public sim**.
- Public sim chỉ khác binary và bộ câu hỏi; không viết lại solution từ đầu.
- Nếu practice còn `wrapper_error` hoặc không có telemetry thì chưa nên chạy public.

Bây giờ có cần chạy lại từ đầu không?

- Có. Vì các file `solution/` đã được sửa sau lần test lỗi.
- Cần chạy lại từ Bước 0 hoặc ít nhất từ Bước 1 trong đúng terminal WSL.
- Trước khi chạy lại phải xóa output cũ bằng Bước 3 để tránh đọc nhầm kết quả cũ.

## 2. PHÂN TÍCH / KIẾN TRÚC

Luồng hệ thống:

```text
question
  -> solution/wrapper.py::mitigate()
  -> call_next(question, config)
  -> black-box LLM agent
  -> wrapper ghi observathon_telemetry.jsonl
  -> nếu exception thì ghi wrapper_debug.log
  -> run_output.json
  -> scorer đọc run_output.json + solution/findings.json
```

Các file đã cải thiện:

| File | Đã sửa gì | Mục tiêu |
|---|---|---|
| `solution/config.json` | `provider=openai`, `model=deepseek-v4-flash`, `temperature=0.2`, bật retry/cache/redact/normalize, bỏ catalog override | Chạy DeepSeek qua OpenAI-compatible path, giảm cost/lỗi |
| `solution/prompt.txt` | Viết lại prompt ngắn, có luật tool-use, tính tiền, PII, injection | Tăng correctness/prompt score |
| `solution/wrapper.py` | Log telemetry, bắt exception, ghi debug, retry, cache, redact answer | Biết lỗi gốc và có evidence |
| `solution/findings.json` | Thêm finding ban đầu về `wrapper_error`, config xấu, prompt injection gap | Có chẩn đoán hợp lệ để selfcheck/score |

## 3. CÁCH CHẠY TEST TỪNG BƯỚC

### Bước 0. Vào đúng thư mục trong WSL

Chạy:

```bash
cd /mnt/e/vin_ai_k2_2026_DocLap/Documents/Day13/Day-13-Lab-Observathon
pwd
ls
```

Nếu `pwd` không đúng repo này:

- Dừng lại.
- `cd` lại đúng thư mục.

Nếu thấy `README.md`, `solution`, `harness`, `bin`:

- Đi tiếp Bước 1.

### Bước 1. Set DeepSeek API

Chạy trong đúng terminal WSL:

```bash
export OPENAI_API_KEY="YOUR_DEEPSEEK_API_KEY"
export OPENAI_BASE_URL="https://api.deepseek.com"
export LOCAL_BASE_URL="https://api.deepseek.com"
```

Không paste API key thật vào chat.

Kiểm tra:

```bash
[ -n "$OPENAI_API_KEY" ] && echo "OPENAI_API_KEY is set" || echo "OPENAI_API_KEY is empty"
echo "$LOCAL_BASE_URL"
echo "$OPENAI_BASE_URL"
```

Nếu kết quả là:

```text
OPENAI_API_KEY is set
https://api.deepseek.com
https://api.deepseek.com
```

thì đi tiếp Bước 2.

Nếu `OPENAI_API_KEY is empty`:

- Dừng lại.
- Export lại key trong đúng terminal.

Nếu `LOCAL_BASE_URL` không phải `https://api.deepseek.com`:

- Dừng lại.
- Export lại base URL.

Nếu `OPENAI_BASE_URL` không phải `https://api.deepseek.com`:

- Dừng lại.
- Export lại `OPENAI_BASE_URL`.

### Bước 2. Chạy selfcheck

Chạy:

```bash
python3 harness/selfcheck.py
```

Nếu thấy toàn PASS:

```text
[PASS] config.json
[PASS] wrapper.py
[PASS] prompt.txt
[PASS] examples.json
[PASS] findings.json (...)
```

thì đi tiếp Bước 3.

Nếu có `[FAIL]`:

- Dừng lại.
- Gửi toàn bộ output selfcheck cho tôi.
- Chưa chạy simulator.

Lưu ý:

- Selfcheck PASS chỉ nói file đúng khung.
- Selfcheck không chứng minh agent chạy đúng.

### Bước 3. Xóa log cũ trước khi chạy simulator

Chạy:

```bash
rm -f run_output.json wrapper_debug.log observathon_telemetry.jsonl
```

Mục tiêu:

- Tránh đọc nhầm log cũ.
- Lần test mới phải có output sạch.

Sau đó đi tiếp Bước 4.

### Bước 4. Chạy simulator practice

Đảm bảo binary có quyền chạy:

```bash
chmod +x ./bin/practice/observathon-sim
```

Chạy:

```bash
./bin/practice/observathon-sim \
  --config solution/config.json \
  --wrapper solution/wrapper.py \
  --out run_output.json
```

Nếu output dạng:

```text
[observathon-sim] ran 20 requests -> run_output.json  (status ok=20)
```

thì đi tiếp Bước 5A.

Nếu output dạng:

```text
status ok=0
```

hoặc số `ok` rất thấp:

- Đi Bước 5B.

Nếu simulator crash ngay, không tạo `run_output.json`:

- Dừng lại.
- Gửi nguyên output terminal cho tôi.

### Bước 5A. Khi simulator có nhiều request `ok`

Kiểm tra status:

```bash
grep -o '"status"[[:space:]]*:[[:space:]]*"[^"]*"' run_output.json | sort | uniq -c
```

Nếu thấy đa số là:

```text
"status": "ok"
```

thì xem vài answer:

```bash
python3 -m json.tool run_output.json | grep -n '"qid"\|"question"\|"answer"\|"status"' | head -n 120
```

Tiếp tục kiểm tra telemetry:

```bash
head -n 20 observathon_telemetry.jsonl
```

Nếu có log telemetry:

- Đi tiếp Bước 6.

Nếu không có `wrapper_debug.log`:

- Đây là bình thường khi tất cả request đều `ok`.
- Không cần fix lỗi debug log.

Nếu không có `observathon_telemetry.jsonl`:

- Dừng lại.
- Gửi output `ls -l` và output simulator cho tôi.

### Bước 5B. Khi vẫn bị `wrapper_error`

Kiểm tra status:

```bash
grep -o '"status"[[:space:]]*:[[:space:]]*"[^"]*"' run_output.json | sort | uniq -c
```

Xem debug log:

```bash
head -n 80 wrapper_debug.log
```

Xem config mà simulator thật sự dùng:

```bash
python3 -m json.tool run_output.json | grep -A 30 '"config_used"'
```

Nếu `wrapper_debug.log` có lỗi kiểu:

- `model not found`
- `unknown model`
- `invalid model`

thì dừng lại và gửi `wrapper_debug.log` cho tôi. Khả năng cần sửa model ID DeepSeek.

Nếu có lỗi kiểu:

- `unauthorized`
- `invalid api key`
- `authentication`

thì dừng lại. Khả năng key sai, hết quota, hoặc key không phải DeepSeek API key.

Nếu có lỗi kiểu:

- `connection`
- `404`
- `base_url`
- `unsupported endpoint`

thì dừng lại và gửi log. Khả năng simulator/provider chưa gọi đúng DeepSeek endpoint.

Nếu không có `wrapper_debug.log`:

- Dừng lại.
- Gửi output:

```bash
ls -l
python3 -m json.tool run_output.json | head -n 120
```

### Bước 6. Đánh giá nhanh chất lượng answer

Chỉ làm bước này nếu đã có nhiều `status=ok`.

Xem answer:

```bash
python3 -m json.tool run_output.json | grep -n '"qid"\|"question"\|"answer"\|"status"' | head -n 180
```

Cần kiểm tra thủ công:

- Có answer nào lặp email/số điện thoại không?
- Có answer nào bịa tổng tiền khi sản phẩm hết hàng/không hợp lệ không?
- Có answer nào không có dòng `Tong cong: ... VND` khi đơn hợp lệ không?
- Có answer nào vẫn trả `Khong the tinh tong cong.` dù đơn có vẻ hợp lệ không?

Nếu nhiều answer sai:

- Dừng lại.
- Gửi 5-10 dòng answer sai cho tôi.
- Tôi sẽ chỉnh prompt/config/wrapper tiếp.

Nếu answer nhìn tương đối ổn:

- Đi tiếp Bước 7.

### Bước 7. Xem telemetry để chuẩn bị findings

Chạy:

```bash
head -n 20 observathon_telemetry.jsonl
```

Đếm lỗi:

```bash
grep -o '"status": "[^"]*"' observathon_telemetry.jsonl | sort | uniq -c
```

Tìm PII:

```bash
grep '"pii_in_answer": [1-9]' observathon_telemetry.jsonl | head
```

Nếu có nhiều PII:

- Dừng lại.
- Gửi output dòng PII đã redact cho tôi.

Nếu status ổn, không PII rõ ràng:

- Đi tiếp Bước 8.

### Bước 8. Chạy simulator có concurrency

Chỉ chạy khi Bước 4-7 ổn.

Chạy:

```bash
rm -f run_output.json wrapper_debug.log observathon_telemetry.jsonl
./bin/practice/observathon-sim \
  --config solution/config.json \
  --wrapper solution/wrapper.py \
  --out run_output.json \
  --concurrency 8
```

Kiểm tra:

```bash
grep -o '"status"[[:space:]]*:[[:space:]]*"[^"]*"' run_output.json | sort | uniq -c
head -n 40 wrapper_debug.log
```

Nếu concurrency gây nhiều lỗi hơn:

- Dừng lại.
- Gửi status count + `wrapper_debug.log`.
- Khả năng cần chỉnh cache/retry/thread-safe.

Nếu vẫn ổn:

- Đi tiếp Bước 9.

Kiểm tra thêm loop/cost:

```bash
grep '"status": "loop"' wrapper_debug.log | wc -l
grep '"status": "loop"' wrapper_debug.log | head
```

Nếu kết quả là `0`:

- Tốt, có thể chạy public.

Nếu chỉ có 1-2 dòng loop nhưng `run_output.json` vẫn `ok=20`:

- Wrapper đã retry cứu được, nhưng vẫn nên gửi dòng loop cho tôi nếu muốn tối ưu thêm cost/latency.

Nếu có nhiều dòng loop:

- Chưa chạy public.
- Gửi `wrapper_debug.log` cho tôi để chỉnh tiếp prompt/wrapper.

Kiểm tra token/cost sau tối ưu:

```bash
python3 - <<'PY'
import json
rows=[json.loads(x) for x in open("observathon_telemetry.jsonl", encoding="utf-8") if x.strip()]
calls=[r for r in rows if r.get("event")=="AGENT_CALL"]
print("calls", len(calls))
print("status", {s:sum(1 for r in calls if r.get("status")==s) for s in sorted(set(r.get("status") for r in calls))})
print("max_tokens", max((r.get("usage") or {}).get("total_tokens",0) for r in calls))
print("sum_cost", round(sum(r.get("cost_usd",0) for r in calls), 6))
for r in sorted(calls, key=lambda x:(x.get("usage") or {}).get("total_tokens",0), reverse=True)[:5]:
    print(r["qid"], r["status"], (r.get("usage") or {}).get("total_tokens"), r.get("tools_used"))
PY
```

Mốc so sánh trước tối ưu:

```text
calls 20
status {'ok': 20}
max_tokens 19564
sum_cost 0.266214
```

Nếu sau tối ưu `ok=20`, loop=0, PII=0 và `sum_cost` giảm:

- Có thể chuyển sang public sim.

Nếu `ok` giảm hoặc answer sai:

- Dừng lại và gửi output để rollback/chỉnh lại.

### Bước 9. Chạy score nếu có binary score

Chỉ chạy khi:

- selfcheck PASS;
- simulator có nhiều `ok`;
- answer nhìn không lỗi nghiêm trọng;
- telemetry có log;
- `findings.json` không còn TODO;
- có file `observathon-score`.

Chạy:

```bash
chmod +x ./bin/practice/observathon-score
./bin/practice/observathon-score \
  --run run_output.json \
  --findings solution/findings.json \
  --team <TEAM> \
  --out score.json
```

Sau đó xem:

```bash
python3 -m json.tool score.json
```

Nếu score thấp hoặc scorer báo lỗi:

- Dừng lại.
- Gửi `score.json` và output scorer cho tôi.

Nếu score ổn:

- Lúc đó mới cân nhắc commit/push theo yêu cầu bài.

### Bước 10. Chạy public sim sau khi practice ổn

Chỉ chạy public khi:

- practice selfcheck PASS;
- practice simulator có nhiều `status=ok`;
- có `observathon_telemetry.jsonl`;
- không còn lỗi runtime lớn trong `wrapper_debug.log`;
- answer practice không có lỗi nghiêm trọng như leak PII, bịa tổng tiền, hoặc format sai hàng loạt.

Nếu chưa đạt các điều kiện trên:

- Không chạy public.
- Gửi output lỗi cho tôi để fix tiếp practice.

Khi đã đạt, chuẩn bị public binary:

```bash
chmod +x ./bin/public/observathon-sim
```

Xóa output cũ:

```bash
rm -f run_output.json wrapper_debug.log observathon_telemetry.jsonl
```

Chạy public sim:

```bash
./bin/public/observathon-sim \
  --config solution/config.json \
  --wrapper solution/wrapper.py \
  --out run_output.json \
  --concurrency 8
```

Kiểm tra status public:

```bash
grep -o '"status"[[:space:]]*:[[:space:]]*"[^"]*"' run_output.json | sort | uniq -c
head -n 80 wrapper_debug.log
head -n 20 observathon_telemetry.jsonl
```

Nếu public `ok` cao và không có lỗi nghiêm trọng:

- Giữ lại `run_output.json`.
- Chờ hoặc tải binary scorer public khi phase score được phát hành.

Nếu public lại lỗi:

- Dừng.
- Gửi tôi:

```bash
grep -o '"status"[[:space:]]*:[[:space:]]*"[^"]*"' run_output.json | sort | uniq -c
head -n 80 wrapper_debug.log
python3 -m json.tool run_output.json | head -n 160
```

### Bước 11. Chạy public score khi có scorer

Chỉ chạy score sau khi `run_output.json` được tạo từ **public sim**. Kiểm tra trước:

```bash
python3 -m json.tool run_output.json | head -n 12
```

Phải thấy:

```text
"phase": "public"
```

Nếu thấy `"phase": "practice"` thì **không được chạy public score**, vì scorer sẽ báo `0 q, 0 correct`.

Public scorer hiện nằm ở thư mục riêng:

Chạy:

```bash
chmod +x ./observathon-public-score-linux-x64/observathon-score
./observathon-public-score-linux-x64/observathon-score \
  --run run_output.json \
  --findings solution/findings.json \
  --team deepseek-observathon \
  --out score.json
```

Xem score:

```bash
python3 -m json.tool score.json
```

Nếu score thấp:

- Không push vội.
- Gửi `score.json` cho tôi để phân tích.

Nếu score ổn:

- Lúc đó mới cân nhắc commit/push theo luật bài.

## 4. KHI NÀO CẦN NHẮN TÔI FIX

Nhắn tôi ngay nếu gặp một trong các trường hợp sau:

- `selfcheck` có `[FAIL]`.
- Simulator vẫn `status ok=0`.
- `wrapper_debug.log` có lỗi model/API/base URL.
- `run_output.json` có nhiều `wrapper_error`, `max_steps`, `loop`.
- Answer lặp email/số điện thoại.
- Answer bịa tổng tiền khi phải từ chối.
- Answer không có format `Tong cong: <integer> VND` cho đơn hợp lệ.
- Telemetry không được tạo.
- Score thấp hoặc scorer lỗi.

Khi nhắn tôi, gửi đúng các output sau:

```bash
grep -o '"status"[[:space:]]*:[[:space:]]*"[^"]*"' run_output.json | sort | uniq -c
head -n 80 wrapper_debug.log
python3 -m json.tool run_output.json | head -n 160
```

Nếu đã chạy score thì gửi thêm:

```bash
python3 -m json.tool score.json
```

## 5. KHÔNG ĐƯỢC LÀM

- Không hardcode câu hỏi -> câu trả lời.
- Không hardcode bảng giá.
- Không đọc seed/instructor file.
- Không import module nội bộ simulator/scorer.
- Không sửa scorer, weights, question set, `score.json`.
- Không dùng network để exfiltrate câu hỏi.
- Không paste API key thật vào chat/log.
- Không push khi chưa xem `run_output.json` và `score.json`.
