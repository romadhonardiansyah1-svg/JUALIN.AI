#!/bin/bash
# ═══════════════════════════════════════════════════════════
# JUALIN.AI — VPS Quick Install
#
# Cara pakai:
#   curl -sSL https://raw.githubusercontent.com/USERNAME/jualin-ai/main/setup_vps.sh | bash
#
# Atau kalau sudah clone:
#   chmod +x setup_vps.sh && ./setup_vps.sh
#
# Setelah install, gunakan command: jualin
# ═══════════════════════════════════════════════════════════

set -e

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║     🚀 JUALIN.AI — Quick Install             ║"
echo "║     AI Sales Assistant untuk UMKM            ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

APP_DIR="/app/jualin-ai"

# Jika belum ada project, clone dulu
if [ ! -d "$APP_DIR" ]; then
    sudo apt update
    sudo apt install -y git curl
    sudo mkdir -p /app
    sudo chown $USER:$USER /app

    echo "📂 Masukkan URL repo GitHub:"
    read -p "GitHub URL (atau tekan Enter untuk default): " REPO_URL
    REPO_URL=${REPO_URL:-"https://github.com/USERNAME/jualin-ai.git"}

    git clone "$REPO_URL" $APP_DIR
fi

# Install jualin CLI
echo "📦 Installing jualin CLI..."
sudo cp "$APP_DIR/jualin" /usr/local/bin/jualin
sudo chmod +x /usr/local/bin/jualin
echo "✅ jualin CLI installed!"
echo ""

# Run full setup
jualin setup
