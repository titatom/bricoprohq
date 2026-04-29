# Bricopro HQ

Self-hosted business command center for Bricopro.

## Overview

Bricopro HQ is a unified internal dashboard that centralizes daily business information, pending AI/document/image queues, quick-access links to external tools, and an AI-powered social media management workflow.

**What it is:** A command center that sits above existing tools (Jobber, Immich, Paperless-ngx, Google Calendar) and helps you answer:
- What needs my attention today?
- What photos and documents need review?
- What content should I post next?
- What tools do I need quick access to?

**What it is not:** A replacement for Jobber, Immich, Paperless-ngx, Google Calendar, Meta, or any other specialist platform.

---

## Modules

| Module | Purpose |
|--------|---------|
| **Dashboard** | Live overview: integrations, widgets, quick links |
| **Processing Queues** | Review pending photos (Immich) and documents (Paperless) |
| **AI Social Studio** | Generate platform-specific social content from job info |
| **Publishing Queue** | Kanban / calendar / list view for content drafts |
| **Campaigns** | Seasonal and service-based marketing campaigns |
| **Settings** | Integration credentials, AI provider config |

---

## Quick Start

### Prerequisites

- Docker and Docker Compose
- 2 GB RAM minimum

### 1. Clone and configure

```bash
git clone <repo-url> bricopro-hq
cd bricopro-hq
cp .env.example .env
# Edit .env — at minimum set SECRET_KEY, ADMIN_EMAIL, ADMIN_PASSWORD
```

### 2. Start

```bash
docker compose up -d
```

The app will be available at:
- **Frontend:** http://localhost:3000
- **API:** http://localhost:8000
- **API docs:** http://localhost:8000/docs

Default login: `admin@bricopro.local` / `admin1234` (change after first login)

---

## Environment Variables

Create a `.env` file in the project root:

```dotenv
# Required — change these before deploying
SECRET_KEY=your-random-secret-key-here
ADMIN_EMAIL=admin@bricopro.local
ADMIN_PASSWORD=your-secure-password

# Optional
POSTGRES_PASSWORD=bricopro
APP_ENV=production
NEXT_PUBLIC_API_URL=http://localhost:8000
```

For Unraid, set these in the Docker template environment fields.

---

## Configuring Integrations

Once logged in, go to **Settings** to configure each integration.

### Google Calendar

1. Create a Google API key at https://console.cloud.google.com
2. Enable the Calendar API
3. In Settings → Google Calendar:
   - **Base URL:** leave blank (uses Google's API directly)
   - **API Key:** your Google API key
   - In `config_json` add: `{"calendar_id": "your-calendar-id@gmail.com"}`

### Jobber

1. Generate an API key in Jobber Settings → Connected Apps
2. In Settings → Jobber:
   - **Base URL:** `https://api.getjobber.com/api/graphql`
   - **API Key:** your Jobber bearer token

### Immich

1. Generate an API key in Immich → Account Settings → API Keys
2. In Settings → Immich:
   - **Base URL:** `http://immich.local:2283` (or your Immich URL)
   - **API Key:** your Immich API key

### Paperless-ngx

1. Generate a token in Paperless → Admin → Auth Token
2. In Settings → Paperless:
   - **Base URL:** `http://paperless.local:8000` (or your Paperless URL)
   - **API Key:** your Paperless token

### AI Provider

In Settings → AI Provider, select:
- **openai** — enter your OpenAI API key
- **openrouter** — enter your OpenRouter key and base URL
- **ollama** — enter your Ollama base URL (e.g. `http://ollama.local:11434`)

---

## Development

### Backend (FastAPI)

```bash
cd backend
pip install -r requirements.txt
DATABASE_URL=sqlite+pysqlite:///./dev.db uvicorn app.main:app --reload
```

Run tests:

```bash
cd backend
python3 -m pytest tests/ -v
```

### Frontend (Next.js + Tailwind)

```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

### Database Migrations (Alembic)

```bash
cd backend
# Generate migration after model changes:
alembic revision --autogenerate -m "describe_change"
# Apply migrations:
alembic upgrade head
```

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 14, React 18, Tailwind CSS 3 |
| Backend | FastAPI, SQLAlchemy 2, Alembic |
| Database | PostgreSQL 16 |
| Cache / Queue | Redis 7 |
| Auth | JWT (python-jose), bcrypt |
| HTTP client | httpx |
| Deployment | Docker Compose |

---

## Data Philosophy

Bricopro HQ **stores:**
- User settings and integration credentials (encrypted in env)
- Dashboard cache (short TTL, refreshed on demand)
- Quick links
- Content drafts, publishing queue, campaigns
- Queue asset status overrides and notes

Bricopro HQ **does not duplicate:**
- Original photos (Immich)
- Original documents (Paperless-ngx)
- CRM records, quotes, invoices (Jobber)
- Calendar events (Google Calendar)

It stores references (IDs / URLs) to source systems.

---

## Security Notes

- Change `SECRET_KEY`, `ADMIN_EMAIL`, and `ADMIN_PASSWORD` before exposing to any network
- API keys are stored in the database — use a strong `SECRET_KEY` and restrict DB access
- The app requires login — no public endpoints (except `/health`)
- Do not commit `.env` to version control

---

## Unraid Deployment

```bash
cd /mnt/user/appdata
git clone <repo-url> bricoprohq
cd bricoprohq

cp .env.example .env
nano .env   # set SECRET_KEY, ADMIN_PASSWORD, NEXT_PUBLIC_API_URL

docker compose up -d --build
```

Set `NEXT_PUBLIC_API_URL` to your Unraid server's LAN IP **before building**:

```dotenv
NEXT_PUBLIC_API_URL=http://192.168.1.100:8000
```

### Fix: `compose build requires buildx 0.17 or later`

The `.env.example` already includes:

```dotenv
DOCKER_BUILDKIT=0
COMPOSE_DOCKER_CLI_BUILD=0
```

Copy it to `.env` and those are picked up automatically. Alternatively:

```bash
./start.sh up --build -d
```

`start.sh` exports the same two variables before calling `docker compose`.

### Persistent volumes

- `db_data` → `/mnt/user/appdata/bricoprohq/db`
- `redis_data` → `/mnt/user/appdata/bricoprohq/redis`

### Local development (hot-reload)

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

---

## MVP Acceptance Checklist

- [x] Runs self-hosted in Docker
- [x] Shows a useful main business dashboard
- [x] Displays upcoming calendar/job information (via configurable connectors)
- [x] Displays pending Immich/Paperless queues
- [x] Provides editable quick links to important tools
- [x] Generates AI social content packs
- [x] Saves generated content as drafts
- [x] Organizes drafts in a publishing queue (kanban + calendar + list)
- [x] Shows a content calendar
- [x] Supports basic seasonal campaigns
- [x] User can log in / log out
- [x] Integration failures show clear errors (not app crashes)
