# Observathon - E-commerce Agent Optimization

## Mục tiêu Lab
Tối ưu hóa và bảo vệ một agent thương mại điện tử hộp đen thông qua config, prompt, wrapper và diagnostic findings. Hệ thống phải an toàn trước Prompt Injection, tối ưu chi phí, và báo cáo Telemetry chuẩn xác.

Điểm số: `100 × (0.32·correct + 0.16·quality + 0.13·error + 0.08·latency + 0.09·cost + 0.07·drift + 0.15·prompt) + bonus diag-F1`.

## Môi trường & Thiết lập
Chạy trên **WSL/Linux**. Export API key trước khi chạy:
```bash
export OPENAI_API_KEY="<YOUR_DEEPSEEK_API_KEY>"
export OPENAI_BASE_URL="https://api.deepseek.com"
export LOCAL_BASE_URL="https://api.deepseek.com"
```

## Cấu trúc Solution (`solution/`)
| File | Vai trò |
|---|---|
| `config.json` | Provider, model, temperature, retry, cache, redact |
| `prompt.txt` | System prompt — extraction → tool calls → tính toán → output |
| `wrapper.py` | Sanitize input, rebuild answer từ trace, telemetry, retry |
| `findings.json` | Chẩn đoán 11 fault class + root cause + evidence |
| `examples.json` | Few-shot: format đúng, refusal, coupon invalid |

## Hướng dẫn Chạy

**Practice Phase**
```bash
rm -f run_output.json score.json wrapper_debug.log observathon_telemetry.jsonl
./bin/practice/observathon-sim \
  --testset practice --config solution/config.json \
  --wrapper solution/wrapper.py --out run_output.json
```

**Public Phase**
```bash
rm -f run_output.json score.json wrapper_debug.log observathon_telemetry.jsonl
./bin/public/observathon-sim \
  --testset public --config solution/config.json \
  --wrapper solution/wrapper.py --out run_output.json --concurrency 8

./observathon-public-score-linux-x64/observathon-score \
  --run run_output.json --findings solution/findings.json \
  --team deepseek-observathon --out score.json
```

**Private Phase**
```bash
rm -f run_output.json score.json wrapper_debug.log observathon_telemetry.jsonl
./bin/private/observathon-sim \
  --testset private --config solution/config.json \
  --wrapper solution/wrapper.py --out run_output.json --concurrency 8

./observathon-private-score-linux-x64/observathon-score \
  --run run_output.json --findings solution/findings.json \
  --team deepseek-observathon --out score.json
```

> ⚠️ Không dùng lẫn `run_output.json` giữa Public và Private — scorer sẽ báo lỗi `0 q, 0 correct`.

## Kiểm tra trước khi nộp
```bash
python3 harness/selfcheck.py
```
Phải thấy `[PASS]` toàn bộ 5 mục.

## Nguyên tắc bắt buộc
- **Không hardcode** QID, câu hỏi, câu trả lời, hay bảng giá.
- **Không sửa** binary `bin/`, scorer, hoặc `run_output.json`/`score.json` bằng tay.
- **Không commit** API key thật lên git.

## Kết quả (Minh chứng)
![Public Score](image/public.png)
![Private Score](image/private.png)
