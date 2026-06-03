# JUALIN.AI — Panduan Deploy VPS

## 🚀 Quick Deploy (3 Langkah)

```bash
# 1. SSH ke VPS
ssh root@IP_VPS_KAMU

# 2. Clone & install
git clone https://github.com/romadhonardiansyah1-svg/JUALIN.AI.git /app/jualin-ai
chmod +x /app/jualin-ai/setup_vps.sh
/app/jualin-ai/setup_vps.sh

# 3. Selesai! ✅
```

Setelah install, semua dikelola pakai command `jualin`:

## 📋 Semua Command

| Command | Fungsi |
|---------|--------|
| `jualin setup` | Install lengkap (Docker, project, 9Router, seed data) |
| `jualin start` | Start semua service |
| `jualin stop` | Stop semua service |
| `jualin restart` | Restart semua |
| `jualin status` | Lihat status & health check |
| `jualin logs` | Lihat semua log |
| `jualin logs backend` | Log backend saja |
| `jualin update` | Pull latest code + rebuild |
| `jualin seed` | Seed ulang demo data |
| `jualin ssl` | Setup HTTPS (Let's Encrypt) |

### 9Router (LLM Gateway)

| Command | Fungsi |
|---------|--------|
| `jualin 9router setup` | Setup 9Router + masukkan API keys |
| `jualin 9router start` | Start 9Router |
| `jualin 9router stop` | Stop 9Router |
| `jualin 9router restart` | Restart 9Router |
| `jualin 9router logs` | Lihat log 9Router |
| `jualin 9router config` | Lihat config |
| `jualin 9router edit` | Edit config + auto restart |

## 🔑 API Keys yang Dibutuhkan

### Gemini (Gratis)
1. Buka https://aistudio.google.com/apikey
2. Klik "Create API Key"
3. Copy key → masukkan saat `jualin 9router setup`

### Groq (Gratis)
1. Buka https://console.groq.com/keys
2. Buat API key baru
3. Copy key → masukkan saat `jualin 9router setup`
4. Bisa buat 2-5 akun untuk round-robin

## 🔒 Setup Domain + HTTPS

```bash
# 1. Arahkan domain ke IP VPS (di DNS provider)
# 2. Jalankan:
jualin ssl
# 3. Masukkan domain & email
# 4. Done! ✅
```

## 📊 Spesifikasi VPS Minimum

| Spec | Minimum | Recommended |
|------|:-------:|:-----------:|
| CPU | 2 core | 4 core |
| RAM | 2 GB | 4 GB |
| Disk | 20 GB | 40 GB |
| OS | Ubuntu 22.04 | Ubuntu 24.04 |

## 🐛 Troubleshooting

### Container tidak jalan
```bash
jualin logs          # Lihat error
jualin restart       # Restart
docker compose ps    # Cek status
```

### 9Router error
```bash
jualin 9router logs    # Lihat error
jualin 9router edit    # Edit config
jualin 9router restart # Restart
```

### Reset data
```bash
jualin stop
docker volume rm jualin-ai_pgdata
jualin start
jualin seed
```

### Update code
```bash
jualin update   # Pull + rebuild + restart
```

## 🗂️ File Locations

| File | Path |
|------|------|
| Project | `/app/jualin-ai/` |
| .env | `/app/jualin-ai/.env` |
| 9Router config | `/app/9router/config.json` |
| CLI tool | `/usr/local/bin/jualin` |
| Logs | `jualin logs` |
