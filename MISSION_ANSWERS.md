# Day 14 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found (`01-localhost-vs-production/develop/app.py`)

Các anti-pattern phát hiện trong `01-localhost-vs-production/develop/app.py`:

1. **Hardcode secrets trong source code (dòng 17–18):**
   - `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`.
   - *Rủi ro:* Khi push lên Git (đặc biệt repo Public), secret bị lộ ngay lập tức và còn nằm lại trong git history kể cả khi xoá sau đó.
   - *Cách `production` đã sửa:* Đọc toàn bộ từ biến môi trường qua `os.getenv(...)` trong `production/config.py` (dòng 17–35) và kiểm tra fail-fast ở `Settings.validate()` (dòng 37–46).
2. **Không quản lý cấu hình tập trung, hardcode `DEBUG = True` và `MAX_TOKENS = 500` (dòng 21–22):**
   - Không thể thay đổi cấu hình giữa các môi trường `dev / staging / production` mà không sửa code và build lại.
   - *Cách `production` đã sửa:* Gom vào dataclass `Settings` trong `production/config.py`, đọc từ env vars.
3. **Dùng `print()` thay cho structured logging và in trực tiếp secret ra log (dòng 33–38):**
   - `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` (dòng 34) làm lộ API key vào log; `print()` không có timestamp, log level hay format JSON để hệ thống gom log (Loki, Datadog…) phân tích.
   - *Cách `production` đã sửa:* Dùng `logging` với định dạng JSON trong `production/app.py` (dòng 28–32, 111–122) và chỉ log metadata (`question_length`, `client_ip`, `response_length`), tuyệt đối không log secret.
4. **Thiếu endpoint kiểm tra sức khoẻ (`/health` và `/ready`) (dòng 42–43):**
   - Cloud platform và load balancer không biết process còn sống hay đã sẵn sàng nhận traffic hay chưa để tự restart hoặc định tuyến.
   - *Cách `production` đã sửa:* Bổ sung `GET /health` (liveness, dòng 135–149) và `GET /ready` (readiness trả 503 khi chưa sẵn sàng, dòng 152–161).
5. **Bind cứng `host="localhost"`, cố định `port=8000` và bật `reload=True` (dòng 49–54):**
   - `host="localhost"` khiến container/cloud không nhận được traffic từ bên ngoài; `port=8000` không tương thích với `PORT` mà Railway/Render inject; `reload=True` tốn tài nguyên và gây không ổn định ở production.
   - *Cách `production` đã sửa:* `host=settings.host` (mặc định `0.0.0.0`), `port=settings.port` (từ `PORT`), `reload=settings.debug` (mặc định `False`) ở `production/app.py` (dòng 194–199).
6. **Không có graceful shutdown & lifecycle management:**
   - Khi container nhận `SIGTERM`, tiến trình bị dừng đột ngột, dễ cắt ngang request đang xử lý.
   - *Cách `production` đã sửa:* Dùng `lifespan` (dòng 39–68) để quản lý startup/shutdown và đăng ký `signal.signal(signal.SIGTERM, handle_sigterm)` (dòng 180–189).
7. **Endpoint `/ask` nhận `question` qua query param thay vì JSON body và không có input validation rõ ràng (dòng 30–31):**
   - Dễ bị lộ câu hỏi trên URL/access log và giới hạn độ dài URL.
   - *Cách `production` đã sửa:* Nhận JSON body và trả `422` khi thiếu `question` (dòng 102–108), đồng thời cấu hình `CORSMiddleware` (dòng 77–82).

### Exercise 1.2: Kết quả chạy bản `develop`

*(Lưu ý: cổng `8000` trên máy đang có tiến trình Python khác sử dụng, nên test bản `develop` trên cổng `8010` và truyền `question` qua query string theo lưu ý K5.)*

Lệnh kiểm tra:
```bash
curl -i -sS -X POST "http://127.0.0.1:8010/ask?question=Hello"
```

Kết quả thực tế:
```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 07:29:22 GMT
server: uvicorn
content-length: 95
content-type: application/json

{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

Log sinh ra phía server cho thấy rõ anti-pattern in secret ra stdout:
```text
[DEBUG] Got question: Hello
[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this
[DEBUG] Response: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.
```

Kết quả kiểm tra nhanh bản `production` (`PORT=8010`):
- `GET /health` → `200 OK`: `{"status":"ok","uptime_seconds":1.8,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T07:29:25.233252+00:00"}`
- `GET /ready` → `200 OK`: `{"ready":true}`
- `POST /ask` (`{"question": "Hello"}`) → `200 OK`: `{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","model":"gpt-4o-mini"}`

### Exercise 1.3: Comparison table (Develop vs Production)

| Feature | Develop (`develop/app.py`) | Production (`production/app.py` & `config.py`) | Tại sao quan trọng? |
| --- | --- | --- | --- |
| **Config & Secrets** | Hardcode `OPENAI_API_KEY`, `DATABASE_URL`, `DEBUG`, `MAX_TOKENS` trực tiếp trong code | Đọc toàn bộ từ biến môi trường qua `Settings` (`os.getenv`), có `validate()` fail-fast khi thiếu `AGENT_API_KEY` ở production | Tránh lộ secret lên Git; dùng chung 1 artifact/codebase cho nhiều môi trường (`dev`, `staging`, `prod`) theo 12-Factor App |
| **Network binding & Port** | Cố định `host="localhost"`, `port=8000`, `reload=True` | `host="0.0.0.0"`, `port` từ env `PORT`, `reload` chỉ bật khi `DEBUG=true` | Container và cloud (Railway/Render) cần bind `0.0.0.0` và lắng nghe đúng cổng được inject qua `PORT`; tắt reload để ổn định và tiết kiệm CPU/RAM |
| **Health & Readiness checks** | Không có `/health` và `/ready` | Có `GET /health` (liveness: uptime, version, status) và `GET /ready` (readiness: trả `503` khi chưa sẵn sàng) | Giúp orchestrator/cloud tự restart container khi process treo (liveness) và chỉ route traffic khi app sẵn sàng (readiness) |
| **Logging** | `print()` tự do, in cả `OPENAI_API_KEY` ra terminal | `logging` xuất JSON có cấu trúc (`time`, `level`, `msg`, `event`, metadata), không log secret | Log JSON dễ thu thập, tìm kiếm, cảnh báo tự động trên hệ thống tập trung (Loki/ELK/Datadog) và không làm rò rỉ thông tin nhạy cảm |
| **Lifecycle & Shutdown** | Tắt đột ngột, không bắt `SIGTERM` | Có `lifespan` (startup/shutdown) và đăng ký handler `SIGTERM` | Khi rolling deploy hoặc scale down, app đặt `is_ready = False`, hoàn thành nốt request đang xử lý và đóng kết nối sạch sẽ, tránh lỗi 5xx cho user |
| **API Design & CORS** | Nhận `question` qua query param, không cấu hình CORS | Nhận JSON body, trả `422` khi thiếu `question`, cấu hình `CORSMiddleware` theo `ALLOWED_ORIGINS` | Tránh lộ dữ liệu người dùng trên URL/log, kiểm soát nguồn gọi hợp lệ từ frontend và validate input chuẩn REST |

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions (`02-docker/develop/Dockerfile`)

1. **Base image là gì?**
   - `python:3.11` (dòng 8) — bản phân phối Python 3.11 đầy đủ (kèm nhiều công cụ hệ thống và trình biên dịch nên dung lượng lớn, ~1 GB+).
2. **Working directory là gì?**
   - `/app` (dòng 11: `WORKDIR /app`) — mọi lệnh `COPY`, `RUN`, `CMD` phía sau đều chạy tương đối trong thư mục này.
3. **Tại sao `COPY requirements.txt` phải đứng trước `COPY . .` (hoặc copy code)?**
   - Để tận dụng **Docker layer cache**: thư viện phụ thuộc ít thay đổi hơn mã nguồn. Khi chỉ sửa `app.py`, Docker tái sử dụng lại layer đã chạy `pip install -r requirements.txt` nên build lại chỉ mất vài giây thay vì tải và cài lại toàn bộ thư viện từ đầu.
4. **`CMD` vs `ENTRYPOINT` khác nhau thế nào?**
   - `ENTRYPOINT` định nghĩa tiến trình thực thi cố định của container (khó bị ghi đè trừ khi truyền cờ `--entrypoint`).
   - `CMD` định nghĩa lệnh mặc định (hoặc tham số mặc định cho `ENTRYPOINT`) và **dễ dàng bị ghi đè** khi người dùng truyền lệnh ở cuối `docker run <image> <cmd>`.

### Exercise 2.2: Build và chạy container `my-agent:develop`

Build từ gốc repo theo lưu ý K5:
```bash
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker run -d --name k5-p2-dev -p 127.0.0.1:8012:8000 my-agent:develop
```

Kết quả kiểm tra (`GET /health` và `POST /ask?question=...`):
```http
HTTP/1.1 200 OK
content-type: application/json

{"status":"ok","uptime_seconds":3.0,"container":true}
```
```http
HTTP/1.1 200 OK
content-type: application/json

{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

### Exercise 2.3: Multi-stage build & so sánh dung lượng image

**Phân tích `02-docker/production/Dockerfile`:**
- **Stage 1 (`builder`):** Dùng `python:3.11-slim`, cài công cụ biên dịch (`gcc`, `libpq-dev`) và cài Python packages bằng `pip install --no-cache-dir --user -r requirements.txt` vào `/root/.local`. Image stage này không được dùng để deploy.
- **Stage 2 (`runtime`):** Bắt đầu mới từ `python:3.11-slim`, tạo non-root user `appuser`, chỉ `COPY --from=builder /root/.local /home/appuser/.local` kèm mã nguồn (`main.py`, `utils/mock_llm.py`), thêm `HEALTHCHECK` và chạy `uvicorn` bằng `USER appuser`.
- **Vì sao image nhỏ hơn?** Loại bỏ hoàn toàn base image đầy đủ (`python:3.11`), trình biên dịch (`gcc`, `libpq-dev`), cache apt/pip và các file thừa ở stage builder — image cuối chỉ còn Python slim runtime và thư viện đã biên dịch.

**Kích thước đo thực tế bằng `docker images my-agent` và `docker image inspect`:**
```text
IMAGE               ID             DISK USAGE   CONTENT SIZE
my-agent:advanced   a3ab4c3f7f46        265MB         57.5MB
my-agent:develop    95da23e09741       1.67GB          415MB
```
- **Develop (`my-agent:develop`):** `1,672,153,255 bytes` ≈ **1,594.7 MB (1.67 GB)**
- **Production (`my-agent:advanced`):** `265,493,177 bytes` ≈ **253.2 MB (265 MB)**
- **Chênh lệch:** giảm **84.1%** dung lượng (nhỏ hơn nhiều ngưỡng 500 MB).

### Exercise 2.4: Docker Compose stack (`02-docker/production/docker-compose.yml`)

**Sơ đồ kiến trúc các service (network nội bộ `internal`):**
```text
                     ┌─────────────────────────────────────────┐
                     │          Docker Network: internal        │
                     │                                         │
Client ──(:80)──▶ [ nginx (nginx:alpine) ]                     │
                     │  (reverse proxy, rate limit 10r/s,      │
                     │   security headers)                     │
                     ▼  (:8000)                                │
                  [ agent (my-agent:advanced, uvicorn x2) ]    │
                     ├──(:6379)──▶ [ redis (redis:7-alpine) ]  │
                     │              (volume: redis_data)       │
                     └──(:6333)──▶ [ qdrant (v1.9.0) ]         │
                                    (volume: qdrant_data)      │
                     └─────────────────────────────────────────┘
```
- Chỉ `nginx` mở cổng ra ngoài (`80:80`, `443:443`); `agent`, `redis`, `qdrant` hoàn toàn cô lập trong mạng `internal`.
- `agent` khai báo `depends_on` với điều kiện `service_healthy` cho `redis` và `qdrant`.

**Kết quả test thực tế qua Nginx (`docker compose -p k5-day14-docker up -d --build`):**
```http
# GET http://127.0.0.1/health
HTTP/1.1 200 OK
Server: nginx
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"status":"ok","uptime_seconds":1.7,"version":"2.0.0","timestamp":"2026-11-25T07:38:50.420484"}
```
```http
# POST http://127.0.0.1/ask -d '{"question": "Explain microservices"}'
HTTP/1.1 200 OK
Server: nginx
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```
*(Đã dọn sạch stack bằng `docker compose -p k5-day14-docker down -v` sau khi test.)*

---

## Part 3: Cloud Deployment

### Exercise 3.1 / 3.2: Deploy Agent Part 6 (`06-lab-complete/`)

- **Platform:** *(Điền Railway hoặc Render sau khi deploy xong CP6)*
- **Public URL:** *(Điền URL công khai sau khi deploy xong CP6)*
- **Screenshots:** `screenshots/dashboard.png`, `screenshots/running.png`, `screenshots/test.png` (chi tiết xem [DEPLOYMENT.md](DEPLOYMENT.md))

### So sánh `railway.toml` và `render.yaml`

| Tiêu chí | `railway.toml` (Railway) | `render.yaml` (Render Blueprint) |
| --- | --- | --- |
| **Định dạng & phạm vi** | TOML, thường cấu hình cho **1 service** (build & deploy policy của service hiện tại). | YAML (Infrastructure-as-Code Blueprint), có thể khai báo **nhiều services & database/Redis** trong cùng 1 file dưới mảng `services:`. |
| **Cách build** | `[build]` với `builder = "DOCKERFILE"`, `dockerfilePath = "Dockerfile"`. | `runtime: docker` và `dockerfilePath: ./Dockerfile` cho từng service. |
| **Health check & restart** | `[deploy]` dùng `healthcheckPath = "/health"`, `healthcheckTimeout`, `restartPolicyType = "ON_FAILURE"`, `restartPolicyMaxRetries`. | Khai báo `healthCheckPath: /health` ngay trong định nghĩa service; Render tự quản lý zero-downtime deploy và restart. |
| **Quản lý biến môi trường & secret** | Thường set qua CLI (`railway variables set`) hoặc Dashboard; không định nghĩa danh sách env var trực tiếp trong `railway.toml`. | Khai báo trực tiếp mục `envVars:` trong `render.yaml`; hỗ trợ `generateValue: true` (tự sinh secret ngẫu nhiên) và `sync: false` (nhắc người dùng nhập trên Dashboard, không lưu secret trong Git). |
| **Lý do khác nhau** | Railway hướng tới trải nghiệm CLI/Dashboard nhanh cho từng service và gắn plugin Redis bằng giao diện kéo-thả. | Render Blueprint hướng tới khai báo toàn bộ hạ tầng dạng mã (IaC) theo GitOps để tái tạo đồng bộ từ GitHub repo. |

### Exercise 3.3: GCP Cloud Run CI/CD Pipeline (`03-cloud-deployment/production-cloud-run/`)

Đọc `cloudbuild.yaml` và `service.yaml` cho thấy pipeline CI/CD trên Google Cloud gồm 4 bước tuần tự khi push lên `main`:
1. **Test (`test`):** Dùng container `python:3.11-slim` cài `requirements.txt` và `pytest`, chạy `pytest tests/` để chặn sớm code lỗi.
2. **Build (`build`):** Build Docker image gắn cả tag `$COMMIT_SHA` lẫn `latest` và dùng `--cache-from` để tận dụng layer cache.
3. **Push (`push`):** Đẩy toàn bộ tag image lên Google Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
4. **Deploy (`deploy`):** Gọi `gcloud run deploy` triển khai image vừa build lên Cloud Run (`asia-southeast1`), cấu hình tài nguyên (`512Mi`, `1 CPU`, `min-instances=1` tránh cold start, `max-instances=10`, concurrency `80`), nạp secret an toàn từ Google Secret Manager (`secretKeyRef`) và bật `livenessProbe` (`/health`) + `startupProbe` (`/ready`) như mô tả trong `service.yaml`.

---

## Part 4: API Security

### Exercise 4.1: API Key Authentication (`04-api-gateway/develop/app.py`)

- **API key được kiểm tra ở đâu?** Tại dependency `verify_api_key` (dòng 39–54) dùng `APIKeyHeader(name="X-API-Key", auto_error=False)`, được inject vào endpoint `/ask` qua `Depends(verify_api_key)` (dòng 70). `/health` và `/` để public cho platform giám sát.
- **Điều gì xảy ra nếu thiếu hoặc sai key?** Thiếu header `X-API-Key` → trả `401 Unauthorized`; sai key → trả `403 Forbidden` (ở Part 6 theo hợp đồng sẽ chuẩn hoá cả thiếu và sai key về `401`).
- **Cách rotate key:** Thay giá trị biến môi trường `AGENT_API_KEY` trên nền tảng triển khai và khởi động lại/rolling deploy (ở quy mô lớn hơn có thể hỗ trợ đồng thời 2 key cũ/mới trong thời gian chuyển tiếp để không làm gián đoạn client).

**Kết quả test thực tế (`AGENT_API_KEY=secret-key-123`):**

Không có key (`401`):
```http
HTTP/1.1 401 Unauthorized
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```

Sai key (`403`):
```http
HTTP/1.1 403 Forbidden
content-type: application/json

{"detail":"Invalid API key."}
```

Có key hợp lệ (`200`):
```http
HTTP/1.1 200 OK
content-type: application/json

{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

### Exercise 4.2 & 4.3: JWT Authentication & Rate Limiting (`04-api-gateway/production/`)

- **JWT flow (`auth.py`):** Client gọi `POST /auth/token` với `{"username": "student", "password": "demo123"}` → server ký JWT bằng thuật toán `HS256` chứa `sub`, `role`, `iat`, `exp` (60 phút) → các request tới `POST /ask` gửi kèm `Authorization: Bearer <REDACTED_TOKEN>` → `verify_token` giải mã và xác thực chữ ký không cần tra DB.
- **Rate limiter (`rate_limiter.py`):**
  - **Thuật toán:** **Sliding Window** (dùng `deque` lưu timestamp các request của từng user, loại bỏ các timestamp cũ hơn `now - window_seconds` rồi kiểm tra `len(window) >= max_requests`).
  - **Giới hạn:** `rate_limiter_user` = **10 requests/phút** (tài khoản `student`, role `user`); `rate_limiter_admin` = **100 requests/phút** (tài khoản `teacher`, role `admin`).
  - **Bypass / nâng giới hạn cho admin:** Trong `app.py` (dòng 141), kiểm tra `role == "admin"` để chọn limiter có ngưỡng cao hơn (`rate_limiter_admin`), hoặc có thể bỏ qua bước gọi `limiter.check()` nếu muốn bypass hoàn toàn cho role `admin`.

**Kết quả test thực tế (`curl -i`, đã che token):**

Gọi `/ask` không có token (`401`):
```http
HTTP/1.1 401 Unauthorized
www-authenticate: Bearer
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY

{"detail":"Authentication required. Include: Authorization: Bearer <token>"}
```

Gọi `/ask` với JWT hợp lệ (`Authorization: Bearer <REDACTED_TOKEN>` → `200`):
```http
HTTP/1.1 200 OK
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY

{"question":"Explain JWT","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","usage":{"requests_remaining":9,"budget_remaining_usd":1.6e-05}}
```

Vòng lặp gọi liên tiếp để chạm ngưỡng 10 req/phút của `student`:
```text
Request #1  -> HTTP 200 (remaining: 9)
Request #2  -> HTTP 200
...
Request #10 -> HTTP 200
Request #11 -> HTTP 429
```

Response chi tiết khi vượt rate limit (`429`):
```http
HTTP/1.1 429 Too Many Requests
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795592452
retry-after: 59
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

### Exercise 4.4: Cost Guard Implementation & vì sao cần cả Rate Limit lẫn Cost Guard

- **Cách hoạt động của Cost Guard (`cost_guard.py` + thiết kế Redis production):**
  1. Trước khi gọi LLM (`check_budget`): đọc tổng chi phí đã chi trong chu kỳ hiện tại từ Redis (key theo ngày `cost:YYYY-MM-DD` hoặc theo tháng `budget:{user_id}:YYYY-MM`). Nếu tổng chi phí hiện tại `>= budget` (hoặc `current + estimated_cost > budget`) → từ chối ngay với **HTTP `402 Payment Required`** (hoặc `503` nếu chạm ngưỡng global budget). Nếu vượt 80% ngân sách thì ghi log cảnh báo.
  2. Sau khi gọi LLM (`record_cost` / `record_usage`): tính chi phí thực tế từ `input_tokens` và `output_tokens` theo đơn giá model (`input/1000 * 0.00015 + output/1000 * 0.0006`), cộng dồn bằng lệnh nguyên tử `INCRBYFLOAT` trên Redis và đặt TTL (`EXPIRE`, ví dụ 2 ngày cho daily budget hoặc 32 ngày cho monthly budget) để tự động reset sang chu kỳ mới.
- **Vì sao phải có cả Rate Limit lẫn Cost Guard?**
  - **Rate limit bảo vệ tốc độ & tài nguyên hạ tầng:** chặn spam/DDoS theo số request/phút, tránh quá tải CPU/worker/API quota tức thời.
  - **Cost guard bảo vệ ngân sách (tiền):** một người dùng vẫn có thể gọi dưới ngưỡng rate limit (ví dụ 5 req/phút liên tục cả ngày, hoặc mỗi request gửi prompt cực dài tốn hàng chục nghìn token) khiến hóa đơn LLM tăng vọt. Do đó cần cả hai lớp bảo vệ bổ trợ nhau.

---

## Part 5: Scaling & Reliability

### Exercise 5.1 & 5.2: Health checks (`/health`, `/ready`) và Graceful Shutdown (`05-scaling-reliability/develop/app.py`)

- **Phân biệt Liveness (`/health`) và Readiness (`/ready`):**
  - **`GET /health` (Liveness probe):** Trả lời câu hỏi *"Process còn sống không?"*. Luôn trả `200` khi process hoạt động (kể cả khi Redis tạm mất kết nối). Nếu trả non-200/timeout, platform sẽ restart container.
  - **`GET /ready` (Readiness probe):** Trả lời câu hỏi *"Instance đã sẵn sàng nhận traffic chưa?"*. Trả `503` khi đang khởi động, đang shutdown (`_is_ready = False`), hoặc dependency quan trọng (như Redis) mất kết nối — khi đó load balancer sẽ ngừng chuyển traffic mới vào instance này mà không vội kill container.
- **Kết quả chạy thực tế & gửi `SIGTERM` (`kill -TERM <pid>`):**
  - `GET /health` → `200 OK`: `{"status":"ok","uptime_seconds":1.7,"version":"1.0.0","environment":"development",...,"checks":{"memory":{"status":"ok","used_percent":82.7}}}`
  - `GET /ready` → `200 OK`: `{"ready":true,"in_flight_requests":1}`
  - Log khi nhận `SIGTERM` (signal 15):
    ```text
    INFO:     Shutting down
    INFO:     Waiting for application shutdown.
    2026-11-25 14:40:49,677 INFO 🔄 Graceful shutdown initiated...
    2026-11-25 14:40:49,678 INFO ✅ Shutdown complete
    INFO:     Application shutdown complete.
    INFO:     Finished server process [23881]
    2026-11-25 14:40:49,678 INFO Received signal 15 — uvicorn will handle graceful shutdown
    ```
  - Khi nhận `SIGTERM`, app chuyển `_is_ready = False`, chờ `_in_flight_requests` xử lý xong (tối đa `timeout_graceful_shutdown=30s`) rồi mới thoát sạch sẽ thay vì cắt ngang request.

### Exercise 5.3–5.5: Stateless Design, Load Balancing (`scale=3`) & `test_stateless.py`

- **Vì sao state trong RAM bị hỏng khi chạy nhiều instance?**
  - Mỗi container/instance có bộ nhớ RAM riêng biệt. Nếu lưu session/conversation history/rate limit trong dict ở RAM, request 1 của user vào `instance A`, request 2 bị Nginx định tuyến sang `instance B` sẽ không thấy dữ liệu trước đó → mất ngữ cảnh hoặc sai bộ đếm.
  - **Giải pháp:** Chuyển toàn bộ state ra bộ nhớ dùng chung ngoài process như **Redis** (`save_session`/`load_session` qua `setex`/`get` với TTL), để mọi instance hoàn toàn stateless và thay thế lẫn nhau được.

- **Kết quả chạy thực tế `docker compose -p k5-day14-scaling up -d --build --scale agent=3` và `python test_stateless.py` (cổng `8080`, endpoint `POST /chat`):**
  ```text
  ============================================================
  Stateless Scaling Demo
  ============================================================

  Session ID: ab300337-5b64-4d4c-a148-a1a8d6523765

  Request 1: [instance-632ac8]  Q: What is Docker?
  Request 2: [instance-d3d5d6]  Q: Why do we need containers?
  Request 3: [instance-632ac8]  Q: What is Kubernetes?
  Request 4: [instance-3aac33]  Q: How does load balancing work?
  Request 5: [instance-d3d5d6]  Q: What is Redis used for?

  ------------------------------------------------------------
  Total requests: 5
  Instances used: {'instance-632ac8', 'instance-d3d5d6', 'instance-3aac33'}
  ✅ All requests served despite different instances!

  --- Conversation History ---
  Total messages: 10
  ✅ Session history preserved across all instances via Redis!
  ```
- **Giải thích kết quả:** 5 câu hỏi trong cùng một `session_id` được Nginx phân tán qua cả **3 instance khác nhau** (`instance-632ac8`, `instance-d3d5d6`, `instance-3aac33`), nhưng khi gọi `GET /chat/{session_id}/history` vẫn nhận đủ toàn bộ **10 messages** (5 user + 5 assistant) nhờ toàn bộ lịch sử được lưu tập trung trong Redis. *(Đã chạy `docker compose -p k5-day14-scaling down -v` sau khi test.)*

---

## Part 6: Final Project — Kết quả `check_production_ready.py`

Chạy đầy đủ (có Docker, không dùng `--static-only` hay `--skip-docker`) trong `06-lab-complete/`:

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

Một số chỉ số đo thực tế từ script:
- Docker image size: **321 MB** (< 500 MB), build multi-stage `python:3.11-slim`, user non-root `appuser`.
- Rate limit: `429` sau 5 request (`RATE_LIMIT_PER_MINUTE=5`), sau khi restart agent vẫn trả `429` (state lưu Redis).
- Cost guard: `402` ở request thứ 1 khi `DAILY_BUDGET_USD=0.000001`.
- Readiness: `/ready` trả `503` khi Redis mất kết nối trong khi `/health` vẫn trả `200`.
- Structured logging: `17` dòng JSON hợp lệ.
- Graceful shutdown: `SIGTERM` lúc đang có request trả `200`, thoát `exit code 0`; `docker stop` tắt êm `exit code 0` trong `0.5s` (< 10s).

---

## AI Log

- **CP0 & CP1:** Hỏi AI hướng dẫn đọc cấu trúc yêu cầu K5 và chạy kiểm thử `01-localhost-vs-production/develop` và `production`. Đã đối chiếu trực tiếp mã nguồn `develop/app.py`, `production/app.py`, `production/config.py`, tự chạy server thật trên máy (cổng 8010) để thu output `curl` và kiểm tra lại bảng so sánh cũng như các số dòng trích dẫn.
- **CP2:** Dùng AI chạy build Docker (`my-agent:develop`, `my-agent:advanced`) từ gốc repo, kiểm tra container `develop` và stack Compose (`-p k5-day14-docker`) theo lưu ý K5. Mọi kích thước image (`1.67GB` vs `265MB`) và output HTTP đều lấy từ kết quả chạy thật trên Docker Desktop của máy.
- **CP3:** Dùng AI chạy kiểm thử `04-api-gateway/develop` và `04-api-gateway/production` theo lưu ý K5 (API key, JWT `/auth/token` với `student/demo123`, burst loop tới 429) và tổng hợp câu trả lời Part 4. Đã kiểm tra lại các mã phản hồi thực tế (`401`, `403`, `200`, `429`), che token và đối chiếu trực tiếp `auth.py`, `rate_limiter.py`, `cost_guard.py`.
- **CP4:** Dùng AI chạy kiểm thử `05-scaling-reliability/develop` (`/health`, `/ready`, `SIGTERM`) và `05-scaling-reliability/production` (`-p k5-day14-scaling --scale agent=3`, `test_stateless.py`), rồi dọn sạch stack. Đã đối chiếu trực tiếp output phân tải 3 instance và 10 messages trong Redis.
- **CP5:** Dùng AI hỗ trợ viết code hoàn thiện các `TODO` trong `06-lab-complete/` (`config.py`, `redis_client.py`, `auth.py`, `rate_limiter.py`, `cost_guard.py`, `main.py`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `railway.toml`, `render.yaml`). Đã chạy kiểm chứng đầy đủ bằng `python check_production_ready.py` (không sửa script chấm) và đạt `PASS 12/12` (43/43 checks passed).
- **CP7 & CP8:** Dùng AI hỗ trợ thêm metric `agent_question_length_chars`, tạo `ci/eval.yml`, bổ sung 2 mục `hpa`/`jwt` vào `KNOWLEDGE_BASE` trong `mock_llm.py` (không sửa `golden_dataset.jsonl`), sửa thiếu `PYTHONUSERBASE` trong `benchmark-observability/production/Dockerfile` để stack Docker chạy được, rồi chạy toàn bộ load test (`reports/`), Locust headless (`benchmark-results/`), thí nghiệm kích hoạt 4 alert firing và điền `BENCHMARK_REPORT.md` khớp 100% với số liệu JSON/CSV thực đo.
