# Deployment Information

## Public URL
https://k5-l3a-day14-phamthihongngoc-2a202603602-deploym-production.up.railway.app

## Platform
Railway (Docker — Root Directory: `06-lab-complete`, config: `06-lab-complete/railway.toml` + Railway Redis service)

## Test Commands

### 1. Bộ 4 lệnh tự kiểm tra chuẩn CP6 (không lộ API key)
```bash
export BASE="https://k5-l3a-day14-phamthihongngoc-2a202603602-deploym-production.up.railway.app"
export AGENT_API_KEY="YOUR_KEY"

curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"     # Expected: 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"      # Expected: 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"Hello"}'   # Expected: 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'   # Expected: 200
```

### 2. Health & Readiness Check
```bash
curl https://k5-l3a-day14-phamthihongngoc-2a202603602-deploym-production.up.railway.app/health
# Expected: {"status":"ok","environment":"production","uptime_seconds":...}

curl https://k5-l3a-day14-phamthihongngoc-2a202603602-deploym-production.up.railway.app/ready
# Expected: {"status":"ready","redis":"ok"}
```

### 3. API Test (with authentication)
```bash
curl -X POST https://k5-l3a-day14-phamthihongngoc-2a202603602-deploym-production.up.railway.app/ask \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "Hello"}'
```

## Environment Variables Set (trên Railway Dashboard — không commit giá trị thật)
- `PORT` (Railway cấp tự động)
- `REDIS_URL` (`${{Redis.REDIS_URL}}` — trỏ tới service Redis trên Railway)
- `AGENT_API_KEY` (đặt bí mật trên Railway Variables)
- `ENVIRONMENT` (`production`)
- `RATE_LIMIT_PER_MINUTE` (`10`)
- `DAILY_BUDGET_USD` (`1.0`)

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
