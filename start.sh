#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Starting Science AI...${NC}\n"

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 1. Start Docker services
echo -e "${BLUE}1️⃣  Starting Docker services...${NC}"
cd "$SCRIPT_DIR"
docker-compose up -d
sleep 3

# Check if Docker started successfully
if docker ps > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Docker services running${NC}\n"
else
    echo -e "${YELLOW}⚠️  Docker daemon not running. Please start Docker Desktop.${NC}\n"
    exit 1
fi

# 2. Open new terminal for Backend
echo -e "${BLUE}2️⃣  Opening Backend terminal...${NC}"
osascript <<EOF
tell app "Terminal"
    do script "cd '$SCRIPT_DIR' && source venv/bin/activate && python -m uvicorn science_ai.main:app --reload --port 8000"
end tell
EOF
sleep 2
echo -e "${GREEN}✓ Backend terminal opened${NC}\n"

# 3. Open new terminal for Dashboard
echo -e "${BLUE}3️⃣  Opening Dashboard terminal...${NC}"
osascript <<EOF
tell app "Terminal"
    do script "cd '$SCRIPT_DIR/dashboard' && npm run dev"
end tell
EOF
sleep 2
echo -e "${GREEN}✓ Dashboard terminal opened${NC}\n"

# Print summary
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ All services started!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

echo -e "${BLUE}📍 Access the dashboard:${NC}"
echo -e "   ${GREEN}http://localhost:3000${NC}\n"

echo -e "${BLUE}📊 API Docs:${NC}"
echo -e "   ${GREEN}http://localhost:8000/docs${NC}\n"

echo -e "${BLUE}📚 Database Services:${NC}"
echo -e "   PostgreSQL: localhost:5432${NC}"
echo -e "   Redis: localhost:6379${NC}"
echo -e "   Qdrant: localhost:6333${NC}\n"

echo -e "${BLUE}To stop all services, run:${NC}"
echo -e "   ${GREEN}./stop.sh${NC}\n"

echo -e "${YELLOW}Note: Check the new terminal windows for service output${NC}\n"
