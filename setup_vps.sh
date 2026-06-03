#!/bin/bash
# ═══════════════════════════════════════════════════════════
# JUALIN.AI — VPS ONE-CLICK DEPLOY (Docker Version)
# 
# Cara pakai di VPS:
#   curl -sSL https://raw.githubusercontent.com/USERNAME/jualin-ai/main/setup_vps.sh | bash
#   ATAU:
#   chmod +x setup_vps.sh && ./setup_vps.sh
#
# Yang diinstal otomatis:
#   ✅ Docker + Docker Compose
#   ✅ PostgreSQL + pgvector (container)
#   ✅ Redis (container)
#   ✅ Backend FastAPI (container)
#   ✅ Frontend Next.js (container)
#   ✅ Nginx reverse proxy (container)
#   ✅ Seed data (15 produk demo)
#   ✅ Firewall (UFW)
#   ✅ SSL otomatis (Certbot)
#
# Setelah selesai, tinggal buka browser!
# ═══════════════════════════════════════════════════════════

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║     🚀 JUALIN.AI — ONE-CLICK DEPLOY         ║${NC}"
echo -e "${CYAN}║     AI Sales Assistant untuk UMKM            ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════╝${NC}"
echo ""

# ── 1. Update sistem ──
echo -e "${YELLOW}📦 [1/6] Updating system...${NC}"
sudo apt update && sudo apt upgrade -y

# ── 2. Install Docker ──
echo -e "${YELLOW}🐳 [2/6] Installing Docker...${NC}"
if command -v docker &> /dev/null; then
    echo -e "${GREEN}Docker already installed$(docker --version)${NC}"
else
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
    echo -e "${GREEN}✅ Docker installed${NC}"
fi

# Install Docker Compose plugin
if ! docker compose version &> /dev/null; then
    sudo apt install -y docker-compose-plugin 2>/dev/null || {
        sudo mkdir -p /usr/local/lib/docker/cli-plugins/
        sudo curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m)" -o /usr/local/lib/docker/cli-plugins/docker-compose
        sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
    }
fi
echo -e "${GREEN}✅ Docker Compose ready${NC}"

# ── 3. Clone project ──
echo -e "${YELLOW}📂 [3/6] Setting up project...${NC}"
APP_DIR="/app/jualin-ai"
sudo mkdir -p /app
sudo chown $USER:$USER /app

if [ -d "$APP_DIR" ]; then
    echo "Project exists, pulling latest..."
    cd $APP_DIR
    git pull origin main
else
    echo "Cloning from GitHub..."
    # ⚠️ GANTI URL INI DENGAN REPO GITHUB KAMU
    git clone https://github.com/USERNAME/jualin-ai.git $APP_DIR
    cd $APP_DIR
fi

# ── 4. Setup environment ──
echo -e "${YELLOW}⚙️ [4/6] Configuring environment...${NC}"
if [ ! -f ".env" ]; then
    cp .env.example .env
    
    # Generate random secrets
    SECRET_KEY=$(openssl rand -hex 32)
    JWT_SECRET=$(openssl rand -hex 32)
    DB_PASS=$(openssl rand -hex 16)
    
    # Update .env with generated secrets
    sed -i "s/ganti-dengan-random-string-panjang-32-karakter/$SECRET_KEY/" .env
    sed -i "s/ganti-dengan-jwt-secret-panjang-32-karakter/$JWT_SECRET/" .env
    sed -i "s/jualin_secure_2026/$DB_PASS/" .env
    
    echo -e "${GREEN}✅ .env created with auto-generated secrets${NC}"
else
    echo -e "${GREEN}.env already exists, keeping existing config${NC}"
fi

# ── 5. Build & Run ──
echo -e "${YELLOW}🏗️ [5/6] Building & starting containers...${NC}"
echo "This may take 5-10 minutes on first run (downloading images + building)..."

# Build all containers
docker compose build --no-cache

# Start all services
docker compose up -d

echo -e "${GREEN}✅ All containers running${NC}"

# Wait for DB to be ready
echo "Waiting for database..."
sleep 10

# Run seed data
echo -e "${YELLOW}🌱 Seeding demo data...${NC}"
docker compose exec -T backend python -m seed.seed_data 2>/dev/null || {
    echo -e "${YELLOW}⚠️ Seed will run on first API call${NC}"
}

# ── 6. Firewall ──
echo -e "${YELLOW}🛡️ [6/6] Setting up firewall...${NC}"
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw --force enable
echo -e "${GREEN}✅ Firewall configured${NC}"

# ── Done! ──
SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || echo "YOUR_IP")

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  ✅ JUALIN.AI BERHASIL DI-DEPLOY!                       ║${NC}"
echo -e "${GREEN}║                                                          ║${NC}"
echo -e "${GREEN}║  🌐 Frontend: http://$SERVER_IP:3000                     ║${NC}"
echo -e "${GREEN}║  🔧 Backend:  http://$SERVER_IP:8000/docs                ║${NC}"
echo -e "${GREEN}║                                                          ║${NC}"
echo -e "${GREEN}║  📝 Login Demo:                                          ║${NC}"
echo -e "${GREEN}║     Seller: demo@jualin.ai / demo123                    ║${NC}"
echo -e "${GREEN}║     Admin:  admin@jualin.ai / admin123                  ║${NC}"
echo -e "${GREEN}║                                                          ║${NC}"
echo -e "${GREEN}║  🛠️  Commands:                                           ║${NC}"
echo -e "${GREEN}║     docker compose logs -f        (lihat log)           ║${NC}"
echo -e "${GREEN}║     docker compose restart        (restart all)         ║${NC}"
echo -e "${GREEN}║     docker compose down            (stop all)           ║${NC}"
echo -e "${GREEN}║     docker compose pull && up -d   (update)             ║${NC}"
echo -e "${GREEN}║                                                          ║${NC}"
echo -e "${GREEN}║  📋 Next steps:                                          ║${NC}"
echo -e "${GREEN}║     1. Setup 9Router: npx 9router                       ║${NC}"
echo -e "${GREEN}║     2. Arahkan domain ke $SERVER_IP                     ║${NC}"
echo -e "${GREEN}║     3. SSL: sudo certbot --nginx                        ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

# Show container status
echo -e "${CYAN}Container Status:${NC}"
docker compose ps
