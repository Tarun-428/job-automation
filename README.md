# JobBot — Autonomous AI Job Application Platform

Production-grade autonomous AI browser agent that applies to jobs on your behalf.

---

## Architecture

```
Telegram ──→ FastAPI ──→ Temporal Workflow Engine
                              │
                    ┌─────────┴──────────┐
                    │   LangGraph DAG    │
                    │  (12 AI Agents)   │
                    └─────────┬──────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
          Playwright      AI Router       PostgreSQL
          (Browser)    Local→Cloud         + Redis
```

## Quick Start

### 1. Prerequisites

- Docker + Docker Compose
- Python 3.12+
- Ollama running locally (optional, for local AI)

### 2. Clone & Configure

```bash
cp .env.example .env
# Edit .env with your API keys
```

### 3. Pull Ollama Models (optional)

```bash
ollama pull qwen2.5vl:7b
ollama pull qwen2.5:7b
```

### 4. Start All Services

```bash
cd infra
docker-compose up -d
```

### 5. Set Telegram Webhook

```bash
curl http://localhost:8000/telegram/set_webhook
```

### 6. Run Locally (Development)

```bash
pip install -r requirements.txt
playwright install chromium

# Terminal 1: API
python main.py

# Terminal 2: Temporal Worker
python -m workflows.worker
```

---

## Project Structure

```
jobbot/
├── api/                    # FastAPI application
│   ├── main.py             # App factory, lifespan
│   ├── routes/             # telegram, workflows, health
│   └── middleware/         # auth, rate_limit
│
├── agents/                 # All 12 AI agents
│   ├── orchestrator.py     # LangGraph DAG
│   ├── browser_nav.py      # Playwright navigation
│   ├── vision.py           # Screenshot analysis
│   ├── job_parser.py       # JD extraction
│   ├── login_auth.py       # Session + credentials
│   ├── form_fill.py        # Dynamic form interaction
│   ├── resume_gen.py       # ATS resume generation
│   ├── validation.py       # Pre-submit checks
│   ├── escalation.py       # Telegram human-in-loop
│   ├── memory.py           # User profile access
│   └── workflow_recovery.py
│
├── ai/                     # AI routing layer
│   ├── router.py           # Local-first fallback chain
│   ├── confidence.py       # Scoring + classification
│   └── providers/          # ollama, gemini, openrouter, groq, anthropic
│
├── browser/                # Browser management
│   ├── context_manager.py  # Per-user isolated contexts
│   ├── stealth.py          # Anti-bot patches
│   └── screenshot.py       # Capture + storage
│
├── resume/                 # Resume generation
│   ├── ats_optimizer.py    # AI keyword optimization
│   ├── latex_renderer.py   # Jinja2 → LaTeX → PDF
│   ├── validator.py        # PDF validation
│   └── templates/          # LaTeX templates
│
├── workflows/              # Temporal workflows
│   ├── apply_workflow.py   # Main workflow
│   ├── activities/         # Activity functions
│   └── worker.py           # Worker entrypoint
│
├── telegram/               # Telegram interface
│   ├── bot.py              # Update router
│   ├── notifications.py    # Outbound messages
│   └── handlers/           # url, otp, approval, question
│
├── db/                     # Database layer
│   ├── models.py           # SQLAlchemy models
│   ├── database.py         # Engine + session factory
│   ├── repositories/       # users, applications, sessions, answers
│   └── migrations/         # Alembic
│
├── security/               # Encryption + credentials
│   ├── vault.py            # AES-256 Fernet
│   ├── credential_store.py
│   └── session_encrypt.py
│
├── config/                 # Configuration
│   ├── settings.py         # Pydantic Settings
│   └── logging.py          # Structured JSON logs
│
├── tests/                  # Pytest test suite
└── infra/                  # Docker + Kubernetes
    ├── docker-compose.yml
    ├── Dockerfile.api
    ├── Dockerfile.worker
    └── k8s/
```

---

## AI Routing

```
Request
  │
  ▼
Qwen2-VL (Ollama) — local, 8s timeout, threshold 0.75
  │ fail/low confidence
  ▼
Gemini Flash — 12s timeout
  │ fail
  ▼
Groq (Llama 3.1 70B) — 15s timeout
  │ fail
  ▼
OpenRouter — 20s timeout
  │ fail
  ▼
Claude Sonnet (premium) — 30s timeout
```

---

## Supported Platforms

| Platform | Login | Form Fill | Upload |
|---|---|---|---|
| LinkedIn | ✅ | ✅ | ✅ |
| Indeed | ✅ | ✅ | ✅ |
| Greenhouse | ✅ | ✅ | ✅ |
| Lever | ✅ | ✅ | ✅ |
| Workday | ✅ | ✅ | ✅ |
| Ashby | ✅ | ✅ | ✅ |
| Naukri | ✅ | ✅ | ✅ |
| Wellfound | ✅ | ✅ | ✅ |
| Custom ATS | ✅ | ✅ | ✅ |

---

## Database Tables

- `users` — Telegram user registry
- `user_profiles` — Full profile, skills, experience
- `resumes` — Base resume versions
- `tailored_resumes` — Per-application ATS-optimized
- `applications` — Workflow tracking
- `browser_sessions` — Encrypted persistent sessions
- `credentials` — Encrypted platform logins
- `ai_answers` — All AI-generated form answers
- `answer_history` — Reusable answer cache
- `audit_logs` — Full event trail
- `screenshots` — Step-by-step captures
- `notifications` — Telegram message log

---

## Security

- All credentials encrypted with AES-256 (Fernet)
- Browser sessions encrypted at rest
- Per-user data isolation by Telegram ID
- No plaintext secrets in database

---

## Running Tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

---

## Environment Variables

See `.env.example` for full reference. Minimum required:

```env
TELEGRAM_BOT_TOKEN=...
GEMINI_API_KEY=...        # Primary cloud fallback
DATABASE_URL=...
REDIS_URL=...
VAULT_ENCRYPTION_KEY=...  # 32+ char string
```

---

## Kubernetes Deployment

```bash
# Apply all manifests
kubectl apply -f infra/k8s/

# Scale workers
kubectl scale deployment jobbot-worker --replicas=8
```
