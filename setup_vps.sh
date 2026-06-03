#!/bin/bash
# ═══════════════════════════════════════════════════════════
# JUALIN.AI — VPS Setup Script (One-Click Deploy)
# Jalankan di VPS (Ubuntu 22.04/24.04)
# 
# Cara pakai:
#   chmod +x setup_vps.sh
#   ./setup_vps.sh
# ═══════════════════════════════════════════════════════════

set -e  # Stop jika ada error

echo "╔══════════════════════════════════════════════╗"
echo "║     🚀 JUALIN.AI — VPS Setup Script         ║"
echo "║     AI Sales Assistant untuk UMKM            ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ── 1. Update sistem ──
echo "📦 [1/8] Updating system..."
sudo apt update && sudo apt upgrade -y

# ── 2. Install dependencies ──
echo "📦 [2/8] Installing dependencies..."
sudo apt install -y \
    python3 python3-pip python3-venv \
    nodejs npm \
    postgresql postgresql-contrib \
    redis-server \
    nginx \
    certbot python3-certbot-nginx \
    git curl wget ufw

# ── 3. Setup PostgreSQL + pgvector ──
echo "🗄️ [3/8] Setting up PostgreSQL + pgvector..."

# Install pgvector extension
sudo apt install -y postgresql-16-pgvector 2>/dev/null || {
    echo "Installing pgvector from source..."
    sudo apt install -y postgresql-server-dev-all build-essential
    cd /tmp
    git clone --branch v0.8.0 https://github.com/pgvector/pgvector.git
    cd pgvector
    make
    sudo make install
    cd ~
}

# Create database and user
sudo -u postgres psql -c "CREATE USER jualin WITH PASSWORD 'jualin_secure_password_2026';" 2>/dev/null || true
sudo -u postgres psql -c "CREATE DATABASE jualin_ai OWNER jualin;" 2>/dev/null || true
sudo -u postgres psql -d jualin_ai -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>/dev/null || true

echo "✅ PostgreSQL ready with pgvector"

# ── 4. Configure Redis ──
echo "📮 [4/8] Configuring Redis..."
sudo systemctl enable redis-server
sudo systemctl start redis-server
echo "✅ Redis ready"

# ── 5. Clone project from GitHub ──
echo "📂 [5/8] Cloning JUALIN.AI from GitHub..."
cd /home
sudo mkdir -p /app
sudo chown $USER:$USER /app
cd /app

if [ -d "jualin-ai" ]; then
    echo "Project exists, pulling latest..."
    cd jualin-ai
    git pull origin main
else
    echo "Cloning fresh..."
    # GANTI DENGAN URL REPO GITHUB KAMU:
    git clone https://github.com/USERNAME/jualin-ai.git
    cd jualin-ai
fi

# ── 6. Setup Backend ──
echo "🐍 [6/8] Setting up Python backend..."
cd /app/jualin-ai/backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Create .env file
cat > .env << 'EOF'
# JUALIN.AI Production Config
DEBUG=false
SECRET_KEY=GANTI_DENGAN_RANDOM_STRING_PANJANG

# Database
DATABASE_URL=postgresql+asyncpg://jualin:jualin_secure_password_2026@localhost:5432/jualin_ai

# Redis
REDIS_URL=redis://localhost:6379/0

# JWT
JWT_SECRET_KEY=GANTI_DENGAN_RANDOM_JWT_SECRET
JWT_EXPIRE_MINUTES=1440

# LLM (via 9Router)
LLM_BASE_URL=http://localhost:20128/v1
LLM_API_KEY=not-needed
LLM_MODEL=llama-3.1-8b-instant

# Gemini API (backup)
GEMINI_API_KEY=GANTI_DENGAN_GEMINI_API_KEY

# CORS (ganti dengan domain kamu)
CORS_ORIGINS=["https://jualin.ai","https://www.jualin.ai","http://localhost:3000"]
EOF

echo "⚠️  PENTING: Edit /app/jualin-ai/backend/.env dan ganti semua value yang bertanda GANTI_"

# Run seed data
python -m seed.seed_data
echo "✅ Backend ready + data seeded"

# ── 7. Setup Frontend ──
echo "🎨 [7/8] Setting up Next.js frontend..."
cd /app/jualin-ai/frontend

npm install
npm run build

echo "✅ Frontend built"

# ── 8. Setup Nginx ──
echo "🌐 [8/8] Configuring Nginx..."

sudo tee /etc/nginx/sites-available/jualin-ai << 'NGINX'
server {
    listen 80;
    server_name jualin.ai www.jualin.ai;  # GANTI DENGAN DOMAIN KAMU

    # Rate limiting (anti DDoS)
    limit_req_zone $binary_remote_addr zone=api:10m rate=30r/s;
    limit_req_zone $binary_remote_addr zone=chat:10m rate=10r/s;

    # Frontend (Next.js)
    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    # Backend API
    location /api/ {
        limit_req zone=api burst=20 nodelay;
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # Chat endpoint (stricter rate limit)
    location /api/chat/ {
        limit_req zone=chat burst=5 nodelay;
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
NGINX

sudo ln -sf /etc/nginx/sites-available/jualin-ai /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx

echo "✅ Nginx configured"

# ── Setup Firewall ──
echo "🛡️ Setting up firewall..."
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw --force enable

# ── Create systemd services ──
echo "⚙️ Creating systemd services..."

# Backend service
sudo tee /etc/systemd/system/jualin-backend.service << 'SERVICE'
[Unit]
Description=JUALIN.AI Backend (FastAPI)
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=root
WorkingDirectory=/app/jualin-ai/backend
Environment=PATH=/app/jualin-ai/backend/venv/bin:/usr/bin
ExecStart=/app/jualin-ai/backend/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

# Frontend service
sudo tee /etc/systemd/system/jualin-frontend.service << 'SERVICE'
[Unit]
Description=JUALIN.AI Frontend (Next.js)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/app/jualin-ai/frontend
ExecStart=/usr/bin/npm start
Restart=always
RestartSec=5
Environment=PORT=3000

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable jualin-backend jualin-frontend
sudo systemctl start jualin-backend jualin-frontend

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  ✅ JUALIN.AI BERHASIL DI-INSTALL!                  ║"
echo "║                                                      ║"
echo "║  Backend:  http://localhost:8000/docs                ║"
echo "║  Frontend: http://localhost:3000                     ║"
echo "║                                                      ║"
echo "║  📝 LANGKAH SELANJUTNYA:                             ║"
echo "║  1. Edit /app/jualin-ai/backend/.env                ║"
echo "║  2. Setup 9Router (npx 9router)                     ║"
echo "║  3. Arahkan domain ke IP VPS ini                    ║"
echo "║  4. Jalankan: sudo certbot --nginx (untuk HTTPS)    ║"
echo "║                                                      ║"
echo "║  Login demo:                                         ║"
echo "║  Seller: demo@jualin.ai / demo123                   ║"
echo "║  Admin:  admin@jualin.ai / admin123                 ║"
echo "╚══════════════════════════════════════════════════════╝"
