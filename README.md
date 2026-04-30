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

Images are built automatically by GitHub Actions and published to GitHub Container Registry. **No building on Unraid required.**

### Option A — Docker Compose (terminal)

```bash
# SSH into Unraid or open a terminal
mkdir -p /mnt/user/appdata/bricoprohq
cd /mnt/user/appdata/bricoprohq

# Download the compose file
curl -O https://raw.githubusercontent.com/titatom/bricoprohq/main/docker-compose.yml

# Create your env file
curl -O https://raw.githubusercontent.com/titatom/bricoprohq/main/.env.example
cp .env.example .env
nano .env   # set SECRET_KEY and ADMIN_PASSWORD

# Pull images and start
docker compose pull
docker compose up -d
```

### Option B — Unraid Docker Templates (GUI)

Four XML templates are in the `unraid/` folder. Add them one at a time in Unraid → Docker → Add Container → Advanced.

**Start order:**
1. `bricoprohq-db` (Postgres)
2. `bricoprohq-redis`
3. `bricoprohq-api`
4. `bricoprohq-web`

All four must be on the same **custom Docker network** named `bricoprohq`. Create it once:

```bash
docker network create bricoprohq
```

**Key settings to fill in:**

| Container | Setting | Value |
|-----------|---------|-------|
| db | POSTGRES_PASSWORD | your-db-password |
| api | SECRET_KEY | random 32-char hex |
| api | ADMIN_PASSWORD | your login password |
| api | DATABASE_URL | `postgresql+psycopg://bricopro:your-db-password@bricoprohq-db:5432/bricoprohq` |
| web | API_URL | `http://bricoprohq-api:8000` |

The web container reaches the API through the internal Docker network — no IP addresses needed.

### Persistent data paths

| Volume | Suggested Unraid path |
|--------|-----------------------|
| Postgres data | `/mnt/user/appdata/bricoprohq/db` |
| Redis data | `/mnt/user/appdata/bricoprohq/redis` |

### Updating to a new version

```bash
docker compose pull
docker compose up -d
```

Or in Unraid GUI: click each container → **Force Update**.

> **Tip:** If the web container logs show `Failed to proxy http://api:8000/...`
> with `ENOTFOUND api` or `ECONNREFUSED`, the web container is either running an
> outdated image or it started before the API container finished booting.
> Run `docker compose pull && docker compose up -d` (or **Force Update** the
> `bricoprohq-web` and `bricoprohq-api` containers in Unraid). The API now
> exposes a `/health` endpoint and the web container waits for it to pass
> before starting.

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
