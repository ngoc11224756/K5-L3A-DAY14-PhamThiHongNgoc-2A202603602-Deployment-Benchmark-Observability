# Benchmark & Observability Report — Day 14

> Mọi con số dưới đây được trích trực tiếp từ các file report JSON (`reports/`), CSV (`benchmark-results/`) và ảnh chụp thật (`screenshots/`).

**Họ tên:** Phạm Thị Hồng Ngọc (MSSV: 2A202603602)
**Ngày chạy:** 2026-11-25
**Môi trường:** macOS (Apple Silicon), Python 3.11.15, Docker Desktop 29.9.3 / Docker Compose v5.7.0

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | 95% người dùng nhận câu trả lời trong dưới 0,5 giây (trải nghiệm tương tác mượt với mock LLM ~150–220 ms; khớp mặc định `--slo-p95-ms 500` của `load_test.py`) |
| Error rate `/ask` | < 2 % | Cho phép error budget 2% để hấp thụ nhiễu upstream nhỏ (~1% mặc định của mock LLM) mà vẫn giữ độ tin cậy 98% (`--slo-error-rate 0.02`) |
| Accuracy trên golden dataset | ≥ 85 % (mục tiêu sau sửa KB: 100%) | Đảm bảo agent trả lời chính xác phần lớn câu hỏi kiến thức lõi và không bị regression khi deploy qua CI quality gate |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

*(300 request mỗi mức, `MOCK_SLOW_RATE=0.03`, `MOCK_ERROR_RATE=0.01`, nguồn: `reports/load_v2_c1.json` … `reports/load_v2_c100.json`)*

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.16 | 193.9 | 221.4 | 1693.6 | 1.33% | PASS |
| 10 | 41.30 | 191.7 | 221.3 | 1692.8 | 0.33% | PASS |
| 50 | 112.88 | 193.1 | 225.3 | 1697.5 | 2.00% | PASS |
| 100 | 49.27 | 731.6 | 3977.8 | 4422.0 | 0.67% | FAIL |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

- **Không tăng tuyến tính:** Từ `c=1` lên `c=10`, RPS tăng gần đúng 10 lần (`4.16 → 41.30 req/s`) với p50/p95 giữ nguyên quanh ~192–221 ms vì tác vụ chủ yếu là async I/O (`asyncio.sleep`).
- Tuy nhiên tới `c=50`, RPS chỉ tăng lên `112.88 req/s` (chỉ gấp ~2,7 lần `c=10` thay vì 5 lần), và khi đẩy lên `c=100`, hệ thống đạt ngưỡng **bão hoà (saturation)** trên 1 tiến trình uvicorn: request xếp hàng chờ event loop/socket, khiến RPS **tụt xuống còn `49.27 req/s`** trong khi p50 vọt lên `731.6 ms`, p95 vọt lên **`3977.8 ms`** (vượt xa SLO 500 ms → FAIL).

### 2.2 Tail latency

*(300 request, `concurrency=20`, nguồn: `reports/load_v2_slow_0.json`, `reports/load_v2_slow_0.03.json`, `reports/load_v2_slow_0.1.json`)*

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 187.1 | 215.8 | 223.7 |
| 0.03 (mặc định) | 233.7 | 222.1 | 1708.1 |
| 0.1 | 324.2 | 1683.2 | 1711.9 |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

- **p99 nhạy nhất** với tỷ lệ request chậm nhỏ: khi `MOCK_SLOW_RATE` tăng từ `0` lên `0.03` (chỉ 3% request chậm), `avg` chỉ tăng nhẹ `+46.6 ms` (`187.1 → 233.7 ms`) và `p95` gần như không đổi (`215.8 → 222.1 ms`), nhưng **`p99` nhảy vọt 7,6 lần** lên `1708.1 ms`. Khi `MOCK_SLOW_RATE = 0.1` (10% request chậm > ngưỡng 5%), cả **`p95` cũng vọt lên `1683.2 ms`** (vi phạm SLO 500 ms) trong khi `avg` mới là `324.2 ms` (trông vẫn có vẻ "ổn").
- **Vì sao không đặt SLO theo average?** Trung bình cộng bị kéo xuống bởi 90–97% request nhanh, nên **che giấu tail latency** — trải nghiệm thực tế rất tệ của nhóm 1–10% người dùng chịu độ trễ gần 2 giây. Đặt SLO theo **p95/p99** giúp phát hiện ngay sự xuống cấp ở đuôi phân phối.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

*(Golden dataset 23 câu hỏi; nguồn: `reports/eval_v1.json`, `reports/eval_v2.json`, `reports/eval_v2_fixed.json`)*

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 56.7 | 108.7 | 113.8 |
| Tổng cost (USD) | $0.000399 | $0.000756 | $0.000792 |
| Cost / câu đúng (USD) | $0.00039855 | $0.00003599 | $0.00003442 |
| Quality gate | FAIL (ngưỡng ≥ 80%) | PASS (≥ 80%, 0 regression) | PASS (≥ 100%, 0 regression) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry `(["jwt", "api key"], ...)` vào `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` (và đồng bộ sang `production/utils/mock_llm.py`) giải thích JWT là token có chữ ký số và thời điểm hết hạn khác với API key cố định. |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry `(["hpa", "kubernetes", "autoscal"], ...)` vào `KNOWLEDGE_BASE` giải thích Kubernetes HPA tự động scale pod dựa trên CPU, memory hoặc custom metrics. |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

- **Chất lượng:** v2 (có bước retrieval RAG) nâng accuracy từ **4.3% (1/23)** lên **91.3% (21/23)** và đạt **100.0% (23/23)** sau khi bổ sung 2 tài liệu còn thiếu vào `KNOWLEDGE_BASE` mà không gây regression câu nào.
- **Chi phí:** v2 tốn gấp ~2 lần token mỗi câu (`108.7–113.8` so với `56.7` token của v1) và tổng cost gần gấp đôi (`$0.000756–$0.000792` so với `$0.000399`), nhưng tính theo **cost / câu trả lời đúng** thì v2 sau sửa KB rẻ hơn v1 tới **11,6 lần** (`$0.00003442` vs `$0.00039855`).
- **Latency:** v2 có thêm bước `search_knowledge_base` (~20 ms) và prompt dài hơn nên `p50` tăng nhẹ (`164.9 ms → 184.0–198.7 ms`); tuy nhiên đây là đánh đổi rất xứng đáng cho mức tăng chất lượng +95,7 điểm %.
- **Quality gate trong CI (`ci/eval.yml`):** Workflow GitHub Actions khởi chạy agent v2 rồi chạy `python eval/run_eval.py --url http://localhost:8002 --min-accuracy 0.85`. Khi `accuracy < 0.85` hoặc xuất hiện bất kỳ câu nào bị regression so với `--baseline`, `run_eval.py` thoát với **exit code `1`** → làm job CI fail và **chặn merge PR** tự động:

```yaml
name: Eval Quality Gate
on: [pull_request]
jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - working-directory: 06-lab-complete/benchmark-observability/develop
        run: |
          pip install -r requirements.txt
          AGENT_VERSION=v2 MOCK_ERROR_RATE=0 PORT=8002 python app.py &
          sleep 3
          python eval/run_eval.py --url http://localhost:8002 --min-accuracy 0.85
```

---

## 4. Observability stack (production)

### 4.1 Screenshot & trả lời Exercise 7.4

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals): `screenshots/grafana-dashboard.png`
- [x] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian): `screenshots/jaeger-slow-trace.png`
- [x] Một trace lỗi trong Jaeger (có event `exception`): `screenshots/jaeger-error-trace.png`
- [x] Trang Alerts của Prometheus với ≥ 2 alert đang **firing** (`LLMCostBurnRateHigh` và `AgentInstanceDown`): `screenshots/prometheus-alert-firing.png`

**Trả lời Exercise 7.4 (số liệu đo trực tiếp trên Prometheus/Grafana khi chạy tải 30 users, cấu hình bình thường):**
1. **p95 và avg:** `p95 = 293.8 ms` (`0.2938 s`), `avg = 232.6 ms` (`0.2326 s`), `error rate = 1.27%`. Khoảng cách giữa `avg` và `p95` (cũng như `p99 ≈ 1700 ms`) phản ánh **tail latency** (~3% request chậm bất thường ~1,7s do `MOCK_SLOW_RATE=0.03`).
2. **Panel "Requests/s theo instance":** Có — Nginx (`server agent:8000 resolve` + round-robin) phân tải gần như đều cho 2 instance: `172.19.0.6:8000` nhận **`5.47 req/s`** và `172.19.0.8:8000` nhận **`6.00 req/s`**.
3. **Vì sao input tokens/s lớn hơn output tokens/s?** Đo thực tế `input = 879.6 tokens/s` so với `output = 461.0 tokens/s` (gần gấp đôi) vì agent `v2` (RAG) ghép thêm `SYSTEM_PROMPT` + tài liệu truy xuất (`context`) + câu hỏi người dùng vào prompt đầu vào, trong khi câu trả lời đầu ra ngắn gọn hơn.
4. **`curl -i http://localhost:8080/metrics` trả về gì và vì sao?** Trả về **`HTTP/1.1 404 Not Found`** (từ Nginx `nginx/1.28.3`). Lý do: `nginx.conf` chủ động chặn `location = /metrics { return 404; }` để không công khai endpoint metrics ra Internet (tránh lộ route, lưu lượng, phiên bản và thông tin hạ tầng); chỉ Prometheus bên trong mạng nội bộ `obs_net` mới scrape trực tiếp `agent:8000/metrics`.

### 4.2 Thí nghiệm "phá hệ thống"

*(Đã chạy unit test alert rules bằng `promtool test rules /p/alert_rules_test.yml` → PASS; sau đó chạy thí nghiệm fault injection thực tế với tải Locust 30 users.)*

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (`> 5%`, `for: 1m`) | **90.2 s** (`pending` ở 30.1 s với 7.83% → `firing` ở 90.2 s với 19.03%) | Golden Signals **Error rate** (đỏ) & **Requests/s theo status (5xx)** |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` (`p95 > 1s`, `for: 2m`) | **135.2 s** (`pending` ở 15.0 s với 1.32s → `firing` ở 135.2 s với 1.94s) | **p95 latency** (đỏ) & biểu đồ **Latency p50/p95/p99/avg** |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` (`> $2/giờ`, `for: 2m`) | Đang **firing** (`$2.17/giờ` trở lên, tăng mạnh ngay khi chuyển sang `mock-llm-large` có đơn giá gấp ~16,7×) | **Cost 1h** & **Cost USD/giờ** (hàng LLM) |
| D | `docker pause k5-day14-observability-agent-2` | `AgentInstanceDown` (`up == 0`, `for: 30s`) | **40.1 s** (`pending` ở 10.0 s → `firing` ở 40.1 s) | **Instances up** giảm & **Requests/s theo instance** (1 instance tụt về 0) |
| E | `AGENT_VERSION=v1` | **Không có alert nào firing** | Không firing (chỉ thấy mất retrieval hit ratio và giảm input tokens/s) | **Retrieval hit ratio** (về 0%), **Tokens/s** giảm, bảng **Instances/Version** đổi sang `v1` |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

- Observability hạ tầng (error rate, latency, CPU/RAM) vẫn hoàn toàn "xanh" khi agent trả lời sai (vì HTTP vẫn trả `200 OK`, thậm chí nhanh và rẻ hơn).
- Để phát hiện sớm trong production cần kết hợp **giám sát chất lượng**:
  1. **Chặn từ trước khi deploy (CI quality gate):** chạy `eval/run_eval.py` trên golden dataset với `--baseline` và `--min-accuracy` ở mọi PR/release.
  2. **Giám sát chất lượng online:** đo `retrieval_hit_ratio` (đặt alert nếu tụt bất thường, vd `< 50%`), lấy mẫu (sampling) traffic thật để chấm tự động bằng **LLM-as-a-Judge** định kỳ, và theo dõi phản hồi người dùng (thumbs up/down, tỷ lệ hỏi lại).
- *Ghi chú thêm về thí nghiệm D:* Lỗi `504 Gateway Timeout` phát sinh ở Nginx khi chờ instance bị pause không xuất hiện trên metric error rate của agent (vì request không được agent xử lý xong) — do đó production cần giám sát thêm metric ở tầng **load balancer (Nginx/Envoy)** và **synthetic check** từ bên ngoài.

### 4.3 Debug bằng trace

Chọn 1 trace chậm tiêu biểu trong Jaeger:

- `trace_id`: `5fe85659dea282e1f6d7f1e9f8da8833`
- Tổng thời gian (`POST /ask`): **1721.8 ms**
- Span chiếm nhiều thời gian nhất: **`chat mock-llm-small`** (**1693.9 ms**, chiếm **98.4%** tổng thời gian request; `agent.retrieve_context` chỉ mất **25.2 ms** và phần còn lại ~2.7 ms là overhead FastAPI/middleware). Điều này chứng minh nút thắt nằm ở lời gọi LLM upstream chứ không phải code xử lý của agent.
- Dòng log JSON tương ứng (`docker compose -p k5-day14-observability logs agent | grep 5fe85659dea282e1f6d7f1e9f8da8833`):

```json
{"ts": "2026-11-25T08:07:07.121641+00:00", "level": "INFO", "service": "observable-agent", "instance": "10c03eb0504d", "event": "llm_call", "trace_id": "5fe85659dea282e1f6d7f1e9f8da8833", "span_id": "f125d13d9fa1343f", "request_id": "012cbc539d9b", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 73, "output_tokens": 35, "cost_usd": 3.2e-05, "llm_ms": 1693.9}
{"ts": "2026-11-25T08:07:07.122177+00:00", "level": "INFO", "service": "observable-agent", "instance": "10c03eb0504d", "event": "http_request", "trace_id": "5fe85659dea282e1f6d7f1e9f8da8833", "span_id": "f125d13d9fa1343f", "request_id": "012cbc539d9b", "method": "POST", "route": "/ask", "status": 200, "ms": 1721.8}
```

Trace lỗi đối chiếu (`error=true` trong Jaeger):
- `trace_id`: `b2839bc3161d197cc438c54cfab0b629`
```json
{"ts": "2026-11-25T08:05:15.779037+00:00", "level": "INFO", "service": "observable-agent", "instance": "10c03eb0504d", "event": "llm_error", "trace_id": "b2839bc3161d197cc438c54cfab0b629", "span_id": "6ccff63f161ad32e", "request_id": "3778f2f58bf2", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

*(Số liệu trích chính xác từ `benchmark-results/scale_1_stats.csv` và `benchmark-results/scale_3_stats.csv`, hàng `POST /ask` — kèm số liệu `Aggregated` trong ngoặc)*

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 59.89 (Agg: 66.08) | 190 | 230 (Agg: 220) | 1700 | 93 / 7147 (1.30%) |
| 3 | 60.15 (Agg: 66.03) | 190 | 230 (Agg: 220) | 1700 | 67 / 7182 (0.93%) |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

- **Scale từ 1 lên 3 instance không làm giảm `p50` (190 ms), `p95` (230 ms) hay `p99` (1700 ms)** và RPS gần như giữ nguyên (~60 req/s cho `/ask`, ~66 req/s tổng).
- **Nút thắt nằm ở 2 điểm:**
  1. **Độ trễ LLM upstream (`chat mock-llm-small`):** Mỗi request mất ~150–220 ms (và ~3% request chậm thêm 1500 ms) chờ I/O từ LLM. Do FastAPI/uvicorn chạy bất đồng bộ (`async/await`), chỉ 1 container đã dư sức xử lý ~60 req/s mà không bị bão hoà CPU; vì vậy thêm container không rút ngắn được thời gian chờ LLM của từng request đơn lẻ.
  2. **Giới hạn tải đầu vào từ Locust:** 100 user mô phỏng có thời gian nghỉ (`wait_time`) giữa các request nên tổng lưu lượng sinh ra bị chặn quanh ~66 req/s.
- **Giá trị thực tế của việc scale 3 instance:** Tăng **tính sẵn sàng (high availability / fault tolerance)** khi 1 instance gặp sự cố và tạo **dư địa chịu tải (headroom)** khi traffic thật tăng vọt vượt ngưỡng bão hoà của 1 container (như đã thấy ở `c=100` không có wait time trong mục 2.1).

---

## 6. Kết luận

- **3 điều học được về benchmark & observability:**
  1. **Average che giấu trải nghiệm xấu (tail latency):** Luôn đo và đặt SLO dựa trên `p95`/`p99` thay vì trung bình; cùng một `avg ≈ 324 ms` nhưng `p95` có thể đã vọt lên `1683 ms`.
  2. **Hạ tầng "xanh" không đồng nghĩa agent trả lời đúng:** Metrics/alerts chỉ bắt được lỗi kỹ thuật (5xx, chậm, crash, vượt chi phí), còn lỗi giảm chất lượng (như nhầm sang `v1` hoặc thiếu kiến thức RAG) bắt buộc phải chặn bằng **eval trên golden dataset + quality gate** và theo dõi metric nghiệp vụ (`retrieval_hit_ratio`, `cost / câu đúng`).
  3. **Liên kết 3 trụ cột Metrics – Traces – Logs:** Dashboard Grafana báo bất thường → Jaeger chỉ chính xác span gây chậm (`chat mock-llm-small` chiếm 98.4%) → grep `trace_id` trong JSON logs cho ra ngữ cảnh chi tiết ngay lập tức.
- **Nếu đưa agent này lên production thật, sẽ thêm các metric / alert sau:**
  - **Nginx / Load balancer metrics** (`nginx_http_requests_total{status="504"}`, upstream response time) và **synthetic blackbox probe** bên ngoài để bắt lỗi timeout/network mà bản thân agent không nhìn thấy.
  - **LLM-specific metrics:** TTFT (Time To First Token cho streaming), tỷ lệ `retrieval_hit_ratio` (alert khi tụt dưới ngưỡng), và điểm đánh giá chất lượng online (sampling LLM-as-a-Judge / user feedback thumbs-down rate).
  - **Redis & saturation metrics:** độ trễ/tỷ lệ lỗi kết nối Redis, memory usage và tỷ lệ bị từ chối bởi rate limit (`429`) / cost guard (`402`).
