#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${RED}🛑 Stopping Science AI...${NC}\n"

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# 1. Stop Docker services
echo -e "${RED}1️⃣  Stopping Docker services...${NC}"
docker-compose down
echo -e "${GREEN}✓ Docker services stopped${NC}\n"

# 2. Kill backend process
echo -e "${RED}2️⃣  Stopping FastAPI backend...${NC}"
pkill -f "uvicorn science_ai.main"
echo -e "${GREEN}✓ Backend stopped${NC}\n"

# 3. Kill dashboard process
echo -e "${RED}3️⃣  Stopping Next.js dashboard...${NC}"
pkill -f "npm run dev"
echo -e "${GREEN}✓ Dashboard stopped${NC}\n"

# 4. Kill any remaining Node processes in dashboard folder
pkill -f "node.*dashboard"

echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ All services stopped!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

echo -e "${BLUE}You can now close the terminal windows or run:${NC}"
echo -e "   ${GREEN}./start.sh${NC}\n"
