# JUALIN.AI 🤖

**AI Sales Assistant Berbasis Katalog untuk Otomasi Layanan Chat UMKM Mikro**

> GEMASTIK DIGINEXS 2026 — Divisi III: Pengembangan Perangkat Lunak  
> Tim Digiboom

---

## 🚀 Quick Start (Development)

```bash
# 1. Clone
git clone https://github.com/romadhonardiansyah1-svg/JUALIN.AI.git
cd jualin-ai

# 2. Start databases
docker compose up -d db redis

# 3. Backend
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m seed.seed_data
uvicorn main:app --reload

# 4. Frontend (tab baru)
cd frontend
npm install
npm run dev

# 5. Buka browser
# Frontend: http://localhost:3000
# Backend:  http://localhost:8000/docs
```

## 🐳 One-Click Deploy (VPS)

```bash
# Di VPS (Ubuntu 22.04+):
git clone https://github.com/romadhonardiansyah1-svg/JUALIN.AI.git
cd jualin-ai
cp .env.example .env
# Edit .env sesuai kebutuhan
docker compose up -d

# Selesai! Buka http://IP_VPS
```

Login demo:
- **Seller:** `demo@jualin.ai` / `demo123`
- **Admin:** `admin@jualin.ai` / `admin123`

---

## 📁 Project Structure

```
jualin-ai/
├── docker-compose.yml          ← Full-stack Docker
├── setup_vps.sh                ← One-click VPS deploy
├── .env.example                ← Environment template
├── .github/workflows/          ← CI/CD auto-deploy
│
├── backend/                    ← Python FastAPI
│   ├── main.py                 ← Entry point + middleware
│   ├── config.py               ← Environment config
│   ├── cache.py                ← Redis cache + rate limiter
│   ├── middleware.py           ← Security headers + rate limit
│   ├── Dockerfile
│   ├── ai/                     ← AI Engine
│   │   ├── agent.py            ← LangGraph state machine
│   │   ├── guardrails.py       ← 7 safety rules
│   │   ├── prompts.py          ← System prompt (Bahasa ID)
│   │   ├── tools.py            ← DB tools (search, order)
│   │   ├── llm_client.py       ← 9Router LLM connection
│   │   ├── embeddings.py       ← Sentence-transformer
│   │   └── followup.py         ← Auto follow-up reminders
│   ├── api/                    ← REST API routes
│   ├── models/                 ← SQLAlchemy + pgvector
│   ├── seed/                   ← Demo data (15 produk)
│   └── tests/                  ← 30 skenario uji
│
├── frontend/                   ← Next.js 16
│   ├── Dockerfile
│   ├── app/
│   │   ├── page.js             ← Landing page
│   │   ├── login/              ← Auth pages
│   │   ├── register/
│   │   ├── chat/[slug]/        ← Public customer chat
│   │   └── dashboard/          ← Seller dashboard
│   │       ├── products/       ← CRUD katalog
│   │       ├── orders/         ← Order management
│   │       ├── chat/           ← AI chat monitor
│   │       ├── analytics/      ← Sales analytics
│   │       ├── settings/       ← AI & store config
│   │       └── admin/          ← Owner panel
│   └── lib/api.js              ← API client
│
└── nginx/                      ← Reverse proxy config
```

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, CSS Modules |
| Backend | FastAPI, SQLAlchemy, Pydantic |
| AI Engine | LangGraph, Guardrails, pgvector RAG |
| Database | PostgreSQL 16 + pgvector |
| Cache | Redis 7 |
| LLM | 9Router → Groq/Gemini (gratis) |
| Embedding | all-MiniLM-L6-v2 (lokal) |
| Deploy | Docker Compose, Nginx, GitHub Actions |

## 📊 Fitur

1. ✅ Register & Login (JWT)
2. ✅ CRUD Katalog + Auto-Embed (pgvector)
3. ✅ Chat AI (Agentic RAG, Bahasa Indonesia)
4. ✅ Order Otomatis dari Chat
5. ✅ Follow-up Pembayaran (3 reminders)
6. ✅ Dashboard Analitik
7. ✅ Riwayat Chat & Order
8. ✅ Admin Panel
9. ✅ Rate Limiting + Security Headers
10. ✅ Redis Smart Cache
11. ✅ Public Chat (`/chat/[slug]`)

## 📝 License

GEMASTIK 2026 — Tim Digiboom
