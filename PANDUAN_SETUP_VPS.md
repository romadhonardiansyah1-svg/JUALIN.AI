# 🚀 JUALIN.AI — Panduan Setup VPS Lengkap

## Alur Kerja

```
LAPTOP KAMU                    GITHUB                     VPS
──────────                    ────────                   ─────
Nulis kode ──► git push ──► Repository ──► git pull ──► Install semua
                                                        Jalankan semua
                                                        Bisa diakses online
```

---

## LANGKAH 1: Siapkan VPS

### Buat VPS Oracle Cloud (Gratis Selamanya)
1. Buka https://cloud.oracle.com → Sign up (gratis)
2. Buat **Compute Instance**:
   - Shape: **VM.Standard.A1.Flex** (ARM)
   - OCPU: **4** | RAM: **24GB**
   - OS: **Ubuntu 22.04** atau **24.04**
   - Simpan **SSH private key** (download .pem file)
3. Catat **IP Public** VPS kamu

### Akses VPS via SSH
```bash
# Dari laptop kamu (PowerShell/Terminal):
ssh -i path/to/key.pem ubuntu@IP_VPS_KAMU
```

---

## LANGKAH 2: Push Code ke GitHub

### Di laptop kamu:
```bash
cd "c:\Romadhon Data penting\Downloads\YT DON\Lomba Gemastik\jualin-ai"

# Buat repo di github.com → klik "New Repository" → nama: jualin-ai

# Hubungkan ke GitHub:
git remote add origin https://github.com/USERNAME_KAMU/jualin-ai.git
git push -u origin main
```

---

## LANGKAH 3: Install di VPS (Otomatis)

### SSH ke VPS, lalu jalankan:
```bash
# Download setup script
cd ~
wget https://raw.githubusercontent.com/USERNAME_KAMU/jualin-ai/main/setup_vps.sh

# Atau copy manual dari repo:
nano setup_vps.sh
# (paste isi setup_vps.sh)

# Jalankan
chmod +x setup_vps.sh
./setup_vps.sh
```

Script ini akan **otomatis install**:
- ✅ PostgreSQL + pgvector
- ✅ Redis
- ✅ Python + virtual environment + semua library
- ✅ Node.js + npm + build frontend
- ✅ Nginx (reverse proxy + rate limiting)
- ✅ Firewall (UFW)
- ✅ Systemd services (auto-start saat VPS reboot)
- ✅ Seed data (15 produk demo)

---

## LANGKAH 4: Konfigurasi

### Edit file .env:
```bash
nano /app/jualin-ai/backend/.env
```

Ganti semua value yang bertanda `GANTI_`:
```env
SECRET_KEY=buat_random_string_32_karakter
JWT_SECRET_KEY=buat_random_string_lain_32_karakter
GEMINI_API_KEY=paste_api_key_dari_aistudio.google.dev
```

Generate random string:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### Restart setelah edit .env:
```bash
sudo systemctl restart jualin-backend
```

---

## LANGKAH 5: Setup 9Router

```bash
# Install 9Router
npx 9router

# Buka dashboard: http://IP_VPS:20128
# Masukkan API keys:
# - Groq API Key 1
# - Groq API Key 2
# - Groq API Key 3
# - Gemini API Key
# Set round-robin + fallback
```

---

## LANGKAH 6: Domain + HTTPS

### Arahkan domain ke VPS:
1. Beli domain (misal: jualin.id)
2. Di DNS setting, tambah A record:
   ```
   A    @       → IP_VPS_KAMU
   A    www     → IP_VPS_KAMU
   ```
3. Tunggu 5-30 menit propagasi DNS

### Aktifkan HTTPS (gratis):
```bash
sudo certbot --nginx -d jualin.ai -d www.jualin.ai
# Ikuti instruksi → pilih redirect HTTP ke HTTPS
```

---

## LANGKAH 7: Verifikasi

### Cek semua service jalan:
```bash
# Cek status
sudo systemctl status jualin-backend
sudo systemctl status jualin-frontend
sudo systemctl status postgresql
sudo systemctl status redis

# Cek log
sudo journalctl -u jualin-backend -f    # Log backend real-time
sudo journalctl -u jualin-frontend -f   # Log frontend real-time

# Test API
curl http://localhost:8000/health
curl http://localhost:8000/docs
```

### Buka di browser:
- **Landing page**: https://jualin.ai
- **API docs**: https://jualin.ai/api/docs
- **Login**: demo@jualin.ai / demo123

---

## UPDATE CODE (Setelah Install)

### Setiap kali kamu push update dari laptop:

```bash
# Di VPS:
cd /app/jualin-ai
git pull origin main

# Rebuild backend
cd backend
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart jualin-backend

# Rebuild frontend (jika ada perubahan)
cd ../frontend
npm install
npm run build
sudo systemctl restart jualin-frontend
```

### Atau pakai script update cepat:
```bash
# Buat file /app/update.sh
cat > /app/update.sh << 'EOF'
#!/bin/bash
cd /app/jualin-ai
git pull origin main
cd backend && source venv/bin/activate && pip install -r requirements.txt
cd ../frontend && npm install && npm run build
sudo systemctl restart jualin-backend jualin-frontend
echo "✅ Updated!"
EOF
chmod +x /app/update.sh

# Setiap mau update, tinggal:
/app/update.sh
```

---

## MONITORING

### Cek apakah web kamu online:
```bash
# Setup Uptime Robot (gratis):
# 1. Buka uptimerobot.com
# 2. Tambah monitor: https://jualin.ai
# 3. Akan dapat notifikasi email jika web down
```

### Backup database otomatis:
```bash
# Buat cron job backup harian
crontab -e
# Tambah baris:
0 2 * * * pg_dump -U jualin jualin_ai > /app/backups/jualin_$(date +\%Y\%m\%d).sql
```

---

## TROUBLESHOOTING

| Masalah | Solusi |
|---------|--------|
| Backend error 502 | `sudo systemctl restart jualin-backend` |
| Frontend error 502 | `sudo systemctl restart jualin-frontend` |
| Database connection error | `sudo systemctl restart postgresql` |
| Port 80/443 blocked | `sudo ufw allow 80/tcp; sudo ufw allow 443/tcp` |
| Disk penuh | `sudo apt autoremove; sudo journalctl --vacuum-size=100M` |
| AI tidak respon | Cek 9Router running + API keys valid |
| SSH tidak bisa masuk | Cek firewall: `sudo ufw allow 22/tcp` |
