# JUALIN.AI

JUALIN.AI adalah aplikasi full-stack untuk operasi penjualan berbasis AI. Backend menggunakan FastAPI, async SQLAlchemy, PostgreSQL dengan pgvector, Redis, ARQ, dan Alembic. Frontend menggunakan Next.js App Router dan React.

## Runtime yang didukung

- Python 3.11.15
- Node.js 20.x
- npm dengan frontend/package-lock.json
- PostgreSQL 16 dengan pgvector
- Redis 7

File .python-version dan .nvmrc adalah pin local development. Backend container dan CI memakai Python 3.11.15. Frontend container dan CI memakai Node 20.

Python 3.13 bukan runtime development project ini. Buat environment terpisah agar package global tidak memengaruhi hasil.

## Environment

- .env.example di root dipakai oleh Docker Compose.
- backend/.env.example dipakai saat backend dijalankan langsung.
- Jangan commit file .env atau credential nyata.
- Jika ENABLE_WHATSAPP=true pada production, verification token, access token, phone number ID, dan app secret wajib diisi.

## Instalasi backend bersih

Dari root repository:

    uv venv .venv --python 3.11.15
    uv pip install --python .venv/Scripts/python.exe torch==2.13.0 --index-url https://download.pytorch.org/whl/cpu
    uv pip install --python .venv/Scripts/python.exe -r backend/requirements.txt
    uv pip check --python .venv/Scripts/python.exe

Pada Linux, gunakan .venv/bin/python sebagai path interpreter.

Untuk menjalankan dependency lokal:

    docker compose up -d db redis

Siapkan schema database baru dari root repository:

    .venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head

Untuk menjalankan backend dari direktori backend:

    ..\.venv\Scripts\python.exe -m uvicorn main:app --reload

## Instalasi frontend bersih

Dari direktori frontend:

    npm ci
    npm run dev

Frontend mem-proxy path /api dan /uploads ke backend melalui konfigurasi Next.js.

## Pengujian dan validasi

Backend, dari direktori backend:

    ..\.venv\Scripts\python.exe -m unittest discover -s tests -v

Validasi tambahan dari root:

    .venv\Scripts\python.exe -m compileall backend
    .venv\Scripts\python.exe -m alembic -c alembic.ini heads
    .venv\Scripts\python.exe -m alembic -c alembic.ini check
    docker compose config --quiet

Frontend, dari direktori frontend:

    npm run lint
    npm run build
    npm audit --audit-level=high

Compileall hanya memeriksa syntax dan bukan pengganti test.

## Database dan migration

Revision Alembic membentuk satu rantai hingga head 20260706_0007. `AUTO_CREATE_TABLES` bernilai `false` secara default; Alembic adalah jalur schema normal. Pada stack baru, service Compose `migrate` menjalankan `upgrade head` satu kali sebelum backend dan worker dimulai.

Untuk menjalankan seluruh stack baru:

    docker compose up --build -d

Kode `create_all` dan patch compatibility di backend/models/database.py hanya dipertahankan untuk recovery deployment legacy yang telah diaudit. Jangan mengaktifkan `AUTO_CREATE_TABLES` pada instalasi normal.

Jangan langsung menjalankan Alembic pada database lama yang dibuat dengan create_all tetapi belum memiliki alembic_version. Database tersebut harus diaudit dan diberi baseline atau stamp yang benar lebih dahulu. Untuk database test yang benar-benar baru, validasi upgrade hingga head sebelum mengubah jalur deployment production.

Jangan menjalankan seed, setup_vps.sh, command jualin, atau migration terhadap environment yang sudah berisi data tanpa backup dan persetujuan eksplisit.

## Entry point

- Backend API: backend/main.py
- Worker: backend/worker.py
- Frontend: frontend/app
- API client frontend: frontend/lib/api.js
- Compose stack: docker-compose.yml
- CI: .github/workflows/deploy.yml

## Cakupan validasi lokal

Image backend dan frontend berhasil dibangun pada runtime yang dipin. Fresh migration hingga head, pemeriksaan drift Alembic, startup container backend/frontend, endpoint health/readiness, proxy API, serta lifecycle registrasi-login telah diuji pada PostgreSQL dan Redis disposable tanpa volume.

Browser E2E, payment, WhatsApp nyata, LLM eksternal, seed, dan migration database legacy atau production belum dijalankan. Area tersebut memerlukan staging, credential test, backup, dan persetujuan terpisah.
