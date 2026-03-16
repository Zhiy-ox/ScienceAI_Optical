# Quick Start Scripts

Automated scripts to start and stop all Science AI services.

## Prerequisites

✅ Python 3.11+ with virtual environment activated
✅ Docker Desktop installed and running
✅ Node.js and npm installed
✅ Dependencies installed (`pip install -e ".[dev]"`, `npm install` in dashboard)

## Usage

### Start All Services

```bash
./start.sh
```

This will:
1. ✓ Start Docker services (PostgreSQL, Redis, Qdrant)
2. ✓ Open a new terminal window for FastAPI backend
3. ✓ Open a new terminal window for Next.js dashboard

### Stop All Services

```bash
./stop.sh
```

This will:
1. ✓ Stop Docker services
2. ✓ Kill backend and dashboard processes

---

## What Each Script Does

### `start.sh` (Advanced - Opens New Terminals)

**Advantages:**
- Each service runs in its own terminal window
- Easy to see logs for each service separately
- Can close individual windows independently
- Clean separation of concerns

**Services started:**
- `docker-compose up -d` → PostgreSQL, Redis, Qdrant in background
- FastAPI backend → http://localhost:8000
- Next.js dashboard → http://localhost:3000

### `stop.sh`

Cleanly stops all services:
- Stops Docker containers
- Kills backend process (`uvicorn`)
- Kills dashboard process (`npm run dev`)

---

## Access Points

Once started, you can access:

| Service | URL |
|---------|-----|
| **Dashboard** | http://localhost:3000 |
| **API Docs** | http://localhost:8000/docs |
| **PostgreSQL** | localhost:5432 |
| **Redis** | localhost:6379 |
| **Qdrant** | localhost:6333 |

---

## Troubleshooting

**"Docker daemon not running"**
- Open Docker Desktop app from Applications

**"Permission denied: ./start.sh"**
- Run: `chmod +x start.sh stop.sh`

**"Port 3000 already in use"**
- Run: `kill -9 $(lsof -ti:3000)` then `./start.sh`

**"Port 8000 already in use"**
- Run: `kill -9 $(lsof -ti:8000)` then `./start.sh`

---

## Manual Alternative

If scripts don't work, start manually:

```bash
# Terminal 1: Docker
docker-compose up -d

# Terminal 2: Backend
source venv/bin/activate
python -m uvicorn science_ai.main:app --reload --port 8000

# Terminal 3: Dashboard
cd dashboard
npm run dev
```

Then open: http://localhost:3000

---

## Environment Setup

Before using scripts, ensure:

```bash
# Activate virtual environment
source venv/bin/activate

# Install Python dependencies
pip install -e ".[dev]"

# Install Node dependencies
cd dashboard
npm install
cd ..
```

Done! Now you can use `./start.sh` 🚀
