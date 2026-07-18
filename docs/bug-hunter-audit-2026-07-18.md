# Audit Bug Hunter — 18 Juli 2026

## Ringkasan

Audit enam pass menemukan defect nyata pada otorisasi, pembayaran, inventori, kuota, streaming chat, inbox, referral, workflow, dan storefront. Semua temuan **Critical/High** di bawah telah diperbaiki dan memiliki regression coverage terfokus. Tidak ada Critical/High terbuka yang terbukti pada review kode final.

Status rilis tetap **NO-GO** sampai bukti PostgreSQL/Redis nyata, browser Chromium nyata, rehearsal migrasi/rollback, serta keputusan manusia tersedia. Audit ini membuktikan perilaku melalui unit/component tests dan pemeriksaan statis; audit ini bukan bukti produksi.

## Critical — dikonfirmasi dan diperbaiki

| # | File:line final | Bug dan skenario kegagalan | Dampak | Perbaikan |
|---|---|---|---|---|
| C1 | `backend/services/payments/factory.py:461-768` | Webhook paid dapat memakai amount yang tidak terverifikasi, attempt lama, atau invoice fallback yang salah. Payload/attempt salah → order ditandai paid. | Underpayment diterima dan status pembayaran lintas-attempt rusak. | Cocokkan provider+invoice current attempt, Decimal amount, seller, dan tolak amount hilang/mismatch/stale. |
| C2 | `backend/services/payments/cashi_gateway.py:306-380` | Cashi webhook amount berasal dari payload dan lookup provider yang gagal terlihat sebagai pending valid. Payload dipalsukan/outage → fakta pembayaran dipercaya. | Order salah paid/pending dan webhook tidak dapat diretry dengan jujur. | Amount/status wajib berasal dari status API terverifikasi; lookup gagal menghasilkan `verified=False` dan webhook fail closed. |
| C3 | `backend/services/payments/factory.py:564-768` | Webhook bersamaan, late-paid, cancel, dan refund mengubah order/stock tanpa lifecycle monotonic dan lock lengkap. | Double restore, stok negatif/phantom, paid turun status, atau refund tidak tercatat. | Lock order+produk, paid-lineage monotonic, exact late-paid consumption ledger, refund reversal, dan stock conservation. |
| C4 | `backend/services/job_handlers.py:677-897` | Reconciliation melaporkan sukses tetapi hanya menangani paid; refund/cancel/late-paid tidak menyelaraskan stock dan recovery ledger. | Provider dan database berbeda walaupun job sukses. | Exact current-attempt validation, row locks, amount validation, lifecycle parity, audit, recovery outcome, dan retry pada status unverifiable. |
| C5 | `backend/api/routes_public_payments.py:124-297`; `backend/services/payment_capability.py:106-221` | Bootstrap capability dapat direplay dan session anak tetap dipakai setelah parent revoked/expired atau attempt berubah. | Akses publik pembayaran melampaui otorisasi yang diberikan. | Single-use row lock, parent/attempt revalidation, audience/purpose binding, expiry/revocation checks. |

## High — otorisasi, auth, dan referral

| # | File:line final | Trigger → failure → impact | Perbaikan |
|---|---|---|---|
| H1 | `backend/api/routes_templates.py:60-147` | Seller meminta template private milik tenant lain → query hanya berdasarkan ID → konfigurasi private bocor/terduplikasi. | Query mengizinkan hanya template public atau milik seller. |
| H2 | `backend/api/routes_auth.py:587-630`; `frontend/components/AuthProvider.js` | Access token kedaluwarsa saat logout → route bergantung access token/frontend menelan error → refresh session tetap aktif. | Logout berbasis refresh cookie, revoke fail closed, dan frontend menampilkan kegagalan. |
| H3 | `backend/api/routes_auth.py:362-464`; `frontend/app/register/page.js` | Referral URL tidak diteruskan atau kode sudah melewati expiry → signup tidak teratribusi/atribusi kedaluwarsa diterima. | Referral dikirim end-to-end, row-locked, expiry-aware, dan conversion event disimpan atomik. |
| H4 | `backend/api/routes_auth.py:362-464` | Signup referral membuat reward bernilai nol tanpa kebijakan materialisasi → record reward menyesatkan. | Simpan conversion fact saja sampai kebijakan reward nyata tersedia. |
## High — pembayaran, order, dan inventori

| # | File:line final | Trigger → failure → impact | Perbaikan |
|---|---|---|---|
| H5 | `backend/services/payments/factory.py:264-458` | Dua request create-payment bersamaan atau retry VA tanpa URL → dua invoice/attempt dapat dibuat. | Lock order, deterministic invoice ID, durable provider+invoice identity, dan reuse invoice meski URL kosong. |
| H6 | `backend/services/payments/factory.py:264-458` | Invoice provider tersimpan tetapi capability setup gagal → retry selalu mengembalikan invoice tanpa capability. | Repair capability dari status provider terverifikasi tanpa membuat invoice baru; Cashi wajib `amount >= total`, provider lain exact match. |
| H7 | `backend/services/payments/cashi_gateway.py:32-380`; `backend/services/payments/midtrans_gateway.py:31-304` | Provider mengembalikan amount berbeda/QRIS unique suffix/partial refund → amount lokal salah atau partial refund dianggap full. | Simpan amount provider, bedakan `PARTIALLY_REFUNDED`, dan jangan melakukan full stock/reversal untuk partial refund. |
| H8 | `backend/services/payments/factory.py:461-768`; `backend/api/routes_orders.py:343-417` | Seller cancel setelah paid lalu provider refund → refund fact diabaikan atau stock direstore dua kali. | Cancelled→refunded mencatat reversal tanpa double restore. |
| H9 | `backend/services/payments/factory.py:189-263,564-768`; `backend/api/routes_orders.py:77-91` | Late payment saat stok tidak cukup, termasuk duplicate product lines → stock negatif atau refund membuat/menghilangkan stok. | Catat jumlah yang benar-benar dikonsumsi per produk pada immutable status history dan restore jumlah itu saja. |
| H10 | `backend/ai/followup.py:103-148` | Dua worker auto-cancel order yang sama → keduanya restore stock. | Lock pending orders dengan `FOR UPDATE SKIP LOCKED` dan lock produk seller-scoped. |
| H11 | `backend/api/routes_orders.py:343-417` | Seller status update bersamaan webhook → stale status dan double stock mutation. | Lock order dan setiap produk sebelum transition/restore. |

## High — produk, import, workflow, inbox, dan chat

| # | File:line final | Trigger → failure → impact | Perbaikan |
|---|---|---|---|
| H12 | `backend/api/routes_marketplace.py:30-235` | CSV berisi NaN/Infinity/negatif/stok pecahan → nilai invalid menjadi nol atau masuk katalog. | Reject nonfinite/negative price dan stok non-integer; preview menyimpan error per baris. |
| H13 | `backend/api/routes_marketplace.py:139-235` | Preview token dieksekusi paralel → batch diimport lebih dari sekali. | Row-lock batch sebelum one-shot status check. |
| H14 | `backend/core/quota.py:31-35`; `backend/api/routes_products.py:142-278`; `backend/api/routes_marketplace.py:139-235` | Create/activate/import paralel membaca count sama → tier quota terlampaui. | Semua quota writer diserialisasi pada seller row; count mencakup semua active rows. |
| H15 | `backend/api/routes_products.py:208-278` | Draft tidak bisa diaktifkan atau aktivasi melewati quota. | Expose `is_active`, tampilkan draft pada seller list, lock dan cek quota saat aktivasi. |
| H16 | `backend/services/workflow_runner.py:218-232` | Workflow action tidak didukung dianggap berhasil/no-op. | Unsupported action gagal secara eksplisit/fail closed. |
| H17 | `backend/api/routes_inbox.py:145-206` | Provider inbox unsupported menyimpan reply seolah terkirim. | Tolak provider unsupported sebelum persist; kegagalan provider disimpan failed dan dikembalikan 502. |
| H18 | `frontend/app/dashboard/inbox/page.js:11-155` | Detail/note/reply/mode request thread A selesai setelah user pindah ke B → state/draft A muncul atau terkirim di B. | Request sequencing, active-thread guards, dan clear draft saat selection berubah. |
| H19 | `backend/api/routes_chat_stream.py:74-407`; `frontend/app/chat/[slug]/page.js` | SSE gagal persist tetapi mengirim `done`, atau frontend fallback REST menduplikasi turn. | Persist assistant/negotiation sebelum `done`; kirim terminal SSE error; hapus duplicate REST fallback. |
| H20 | `backend/api/routes_chat_stream.py:38-41` | Public chat menerima input tak terbatas → memory/token/resource abuse. | Batas message 1–4000 dan session/slug maksimal 255. |
## High — storefront dan frontend contract

| # | File:line final | Trigger → failure → impact | Perbaikan |
|---|---|---|---|
| H21 | `frontend/app/store/[slug]/page.js:7-151` | `/store/{slug}` tidak ada atau Next.js 16 `params` dibaca sinkron → published storefront 404/runtime failure. | Tambah server page dan await async `params`. |
| H22 | `frontend/app/store/[slug]/page.js:18-151` | Configured sections diabaikan/direka ulang atau semua section hidden tetapi produk tetap ditampilkan. | Render hero/products/categories/testimonials/CTA dalam urutan API; empty section list tidak mengekspos produk. |
| H23 | `frontend/app/store/[slug]/page.js:18-151` | CTA seller menunjuk URL eksternal → public storefront menjadi open redirect/link injection. | CTA dibatasi ke `/chat/{store.slug}`. |
| H24 | `frontend/app/store/[slug]/page.js:41-50` | Storefront tidak menghasilkan metadata kontrak SEO. | Export metadata title/description dari published storefront response. |

## Medium — tidak diubah otomatis

1. `backend/api/routes_payments.py:141-231` — `_sync_payment_status` tidak memiliki reference terdeteksi oleh Serena dan mempertahankan legacy transition logic yang lebih lemah. Diklasifikasikan dead legacy code; jangan dihapus tanpa konfirmasi pemilik.
2. `frontend/app/store/[slug]/page.js:109-130` — payload testimonial malformed seperti `items: [null]` masih perlu schema boundary/defensive filtering agar satu section tidak menjatuhkan halaman.
3. Route-registration regression menguji local router, bukan final mounted FastAPI app.
4. Canonical/OpenGraph/sitemap/robots storefront belum memiliki coverage.

## Needs verification

- **Ambiguous provider create timeout:** deterministic Midtrans/Cashi invoice IDs mengurangi duplikasi, tetapi recovery checkout token/URL setelah provider menerima request lalu response timeout bergantung kontrak/API provider. Tidak diklaim selesai.
- **Real PostgreSQL concurrency:** lock SQL dan state behavior diuji dengan mocks; belum ada eksekusi concurrent transaction pada PostgreSQL disposable.
- **Real browser:** tidak ada Chromium runtime, network, console, responsive, atau visual verification.
- **Real stack:** PostgreSQL/Redis/Docker startup dan disposable full-stack rehearsal belum dijalankan karena environment sebelumnya tidak tersedia; tidak dicoba ulang membabi buta.
- **Mutation testing:** Stryker/mutmut tidak dikonfigurasi dan tidak dijalankan.
- **Partial refund accounting:** partial refund kini dipertahankan sebagai fakta terpisah dan tidak lagi melakukan full refund/stock restore, tetapi partial monetary reversal membutuhkan model/kebijakan bisnis khusus.

## Enam pass yang dijalankan

1. **Contract:** route/schema/model/frontend producer-consumer, referral URL, payment payload, Next.js async params, storefront section contract.
2. **Async & concurrency:** row locks order/product/import/capability/quota, retries, current attempt, stale frontend requests, SSE persistence order.
3. **Error handling:** logout revocation, unsupported workflow/provider, gateway lookup outage, SSE persistence failure, CSV validation.
4. **Security:** template ownership, capability audience/purpose/revocation, origin allowlist, webhook verification, tenant scoping, public-chat bounds.
5. **Edge cases:** zero/NaN/Infinity, duplicate imports, VA tanpa URL, unique QRIS suffix, late paid, refund after cancellation, duplicate product lines, hidden sections.
6. **State & lifecycle:** paid-lineage monotonicity, stock conservation, reconciliation parity, inbox request ordering, streamed completion lifecycle.

## Coverage dan batasan test quality

Reviewed area mencakup route/service/worker/payment gateway utama di `backend/`, frontend auth/chat/inbox/storefront consumers, serta regression files baru. Generated `.next`, caches, uploads, `__pycache__`, migrations, `.env`, dan user-owned `.agents/` tidak diaudit sebagai source change.

Regression tests memakai `unittest`/`AsyncMock` dan Vitest/jsdom. Assertions fokus observable status, stock, amount, capability, calls ke recovery bridge, dan rendered UI. Keterbatasan utama: banyak backend tests adalah isolated mock tests, tidak membuktikan PostgreSQL lock scheduling; frontend tests bukan real browser; mutation score tidak tersedia.

## Verdict

**Critical/High code findings: CLOSED dalam scope yang diuji.**

**Public beta/production: NO-GO** sampai item Needs verification dan release gate di `docs/release-go-no-go.md` diselesaikan dengan evidence exact-SHA serta persetujuan manusia.
