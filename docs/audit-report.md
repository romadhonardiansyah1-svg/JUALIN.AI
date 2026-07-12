# JUALIN.AI Audit Report

Tanggal audit: 2026-07-11 sampai 2026-07-12

## Ringkasan arsitektur

- Backend FastAPI dengan async SQLAlchemy, PostgreSQL dan pgvector, Redis, ARQ worker, Alembic, payment gateway, WhatsApp Cloud, dan integrasi LLM.
- Frontend Next.js App Router dengan React dan API client terpusat.
- Docker Compose menjalankan database, Redis, backend, worker, frontend, dan Nginx.
- CI memvalidasi backend pada Python 3.11.15 dan frontend pada Node 20.

## Temuan dan status

| ID | Risiko | Akar masalah | Status dan solusi |
|---|---|---|---|
| AUD-001 | High | Starlette 1.0.1 memiliki empat advisory 2026 | Selesai: upgrade ke 1.3.1; clean install, import, OpenAPI, test, dan audit lulus |
| AUD-002 | High | python-jose menarik ecdsa dengan advisory tanpa fix | Selesai: satu call site dimigrasikan ke PyJWT dan cryptography menjadi dependency langsung |
| AUD-003 | High | Signature WhatsApp dianggap valid saat app secret kosong | Selesai: verifikasi fail closed dan production config mewajibkan credential saat fitur aktif |
| AUD-004 | High | Runtime lokal 3.13 berbeda dari Docker dan CI 3.11 | Selesai: Python 3.11.15 dipin untuk local, CI, dan container |
| AUD-005 | Medium | Torch CPU di-install tanpa versi | Selesai: Torch 2.13.0 dipin di requirements, Docker, dan CI |
| AUD-006 | High | Test backend dan test gate CI telah dihapus | Selesai sebagian: 13 regression test baru dan CI gate aktif; test lama tidak dipulihkan tanpa review |
| AUD-007 | High | Readiness gagal tetap mengembalikan HTTP 200, membocorkan exception, dan menganggap Redis `None` sehat | Selesai: HTTP 503 untuk database/Redis gagal, body generik, detail tetap tercatat di server log |
| AUD-008 | High | Schema dikelola oleh Alembic sekaligus create_all dan patch runtime; Compose tidak menjalankan migration | Selesai untuk instalasi baru: default create_all dimatikan dan service `migrate` menjadi gate backend/worker. Production lama tetap memerlukan backup, audit, baseline atau stamp |
| AUD-009 | Medium | Node lokal 24 berbeda dari CI dan Docker Node 20 | Selesai: .nvmrc dan package engines menetapkan Node 20 |
| AUD-010 | Low | Method getProviderHealth didefinisikan dua kali | Selesai: definisi duplikat dihapus setelah call-site diperiksa |
| AUD-011 | Medium | Refresh auth dashboard menelan error dan dapat menampilkan layar kosong | Root, login, proxy, dan lifecycle auth container lulus; perilaku dashboard masih belum diverifikasi dengan browser |
| AUD-012 | High | JWT browser disimpan di localStorage | Belum diubah; migrasi cookie httpOnly mengubah kontrak auth dan memerlukan keputusan desain tersendiri |
| AUD-013 | Medium | Environment Compose dan direct backend tidak dijelaskan | Selesai: README menjelaskan kedua template dan backend example mendapat default production yang aman |
| AUD-014 | Medium | CI mengabaikan CVE lama tetapi gagal pada vulnerability lain | Selesai: dependency diperbaiki dan pengecualian audit dihapus |
| AUD-015 | Medium | Enam indeks performa migration tidak terdaftar pada metadata ORM sehingga `alembic check` menyarankan penghapusan | Selesai: metadata model diselaraskan; fresh upgrade dan `alembic check` lulus tanpa operasi baru |
| AUD-016 | High | Rewrite frontend dibake ke localhost karena URL backend hanya diberikan saat runtime container | Selesai: URL internal menjadi build argument; proxy container mengembalikan respons backend 401, bukan 500 |

## Bukti pengujian

- Clean Python 3.11.15 install: 78 package kompatibel, termasuk Torch 2.13.0 CPU.
- Backend unit test: 13 lulus.
- Backend import: 194 route; OpenAPI menghasilkan 170 path.
- Worker import: konfigurasi ARQ terbaca.
- Alembic: satu head 20260706_0007, history linear, fresh upgrade menghasilkan 81 tabel, dan `alembic check` tidak menemukan drift.
- Backend compileall: lulus.
- Backend pip-audit: tidak ada vulnerability yang diketahui.
- Frontend clean npm install: lulus dari package-lock.
- Frontend lint pada Node 20.20.2: lulus untuk app, components, lib, Next config, dan ESLint config.
- Frontend production build pada Node 20.20.2: 39 route berhasil dibuat.
- npm audit high: tidak ada vulnerability.
- Docker Compose config: valid.
- Backend dan frontend Docker image: build lulus pada Python 3.11.15 dan Node 20.
- Container smoke terisolasi: backend root, health, readiness, dan OpenAPI HTTP 200; frontend root dan login HTTP 200.
- Proxy frontend: endpoint auth tanpa token HTTP 401; error localhost/HTTP 500 telah hilang.
- Lifecycle auth melalui proxy: registrasi 200, login salah 401, login benar 200, `/auth/me` tanpa token 401 dan dengan JWT 200; schema JSON serta header `nosniff` tervalidasi.
- Command dan bind-mount service migration Compose berhasil dijalankan terhadap database audit disposable.

## Masalah yang masih belum terverifikasi

- Database legacy/production yang mungkin dibuat dengan `create_all` tidak dimigrasikan atau diubah. Stack pengguna yang sedang aktif tidak disentuh.
- Browser E2E untuk form, navigasi dashboard, refresh auth, dan UI error state belum dijalankan.
- Payment, WhatsApp nyata, LLM, marketplace, worker job nyata, seed, dan integrasi ber-credential belum diuji.
- JWT frontend masih disimpan di `localStorage`; migrasi ke cookie httpOnly memerlukan perubahan kontrak auth tersendiri.

Sebelum deployment production:

1. Backup database.
2. Audit keberadaan alembic_version dan kesesuaian schema dengan revision.
3. Uji upgrade Alembic pada salinan database atau database baru.
4. Jalankan browser E2E dan alur payment, webhook, worker, serta dashboard di staging.
5. Putuskan secara terpisah apakah token browser dimigrasikan dari localStorage ke cookie httpOnly.
