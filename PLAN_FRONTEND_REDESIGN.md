# PLAN REDESIGN FRONTEND — "Aurora Deck" (Modern / 3D / AI-vibe)

> **Untuk agen pelaksana.** Tujuan: membuat tampilan JUALIN.AI terasa **modern, 3D, dan "produk AI" premium** (gaya Linear/Vercel/OpenAI) tanpa merusak fungsi apa pun.
>
> **Strategi inti (HAFALKAN): CSS-first. JANGAN ubah logika JSX/React.** Styling proyek ini memakai **CSS Modules** yang dikunci by nama class. Jadi kita cukup **menulis ulang file CSS** (yang nama class-nya sudah dipakai di JSX) dan **menambah utility global**. React, state, fetch, routing tidak disentuh = mustahil merusak alur.
>
> Kerjakan **FASE 0 → FASE 7 berurutan**. Setelah tiap fase yang menyentuh build, jalankan `npm run build` (lihat Fase 7).

---

## ATURAN EMAS (patuhi mutlak)

1. **Hanya ubah file CSS** (`globals.css`, `*.module.css`) dan, bila disebut, sisipan kecil `className`/wrapper di JSX. **Jangan** ubah `useState`, `useEffect`, fetch, handler, atau struktur komponen.
2. **Next.js 16 punya breaking changes.** Karena kita CSS-first, kita aman. Jika TERPAKSA menyentuh komponen (mis. menambah hook tilt di Fase 6), file harus diawali `"use client";` dan tidak boleh memakai API Next yang tak kamu lihat dipakai di file existing.
3. **Append, jangan hapus, di `globals.css`.** Token & class lama masih dipakai banyak halaman dashboard. Kita **menambah** sistem baru, bukan menghapus yang lama.
4. **Reskin penuh per-halaman, bukan setengah.** Kalau menggelapkan sebuah halaman (landing/auth), seluruh elemennya harus ikut tema gelap. Jangan tinggalkan kartu putih nyangkut di background gelap.
5. **Tema gelap "Aurora" hanya untuk 3 permukaan etalase:** Landing, Auth (login/register), dan halaman AI Crew. Halaman dashboard lain tetap terang (Fase 5 opsional untuk migrasi). Ini menjaga 30+ halaman lama tetap aman.
6. **Selalu sertakan prefix `-webkit-backdrop-filter`** berdampingan dengan `backdrop-filter`.
7. **Uji `npm run build` + `npm run lint`** setelah Fase 1, 2, 3. Kalau merah, perbaiki sebelum lanjut.
8. **Hormati aksesibilitas:** blok `prefers-reduced-motion` (disediakan) wajib ada agar animasi bisa dimatikan.

---

## SPEK VISUAL — "Aurora Deck"

- **Latar:** ruang gelap dalam (`#060912` → `#0A1020`) dengan **aurora blobs** (emerald, cyan, violet) yang blur dan bergerak pelan.
- **Spektrum warna AI:** Emerald `#22C55E` (jangkar brand), Cyan `#22D3EE`, Violet `#8B5CF6`, aksen Pink `#F472B6` (hemat).
- **Material:** **glassmorphism** (kaca buram tembus cahaya) + **garis tipis** `rgba(255,255,255,.12)`.
- **Kedalaman 3D:** bayangan berlapis + glow berwarna + **tilt perspektif** saat hover + elemen melayang (float).
- **Teks judul:** font **Sora** (geometris, techy) + **gradient text**. Body tetap Inter.
- **Mikro-interaksi:** glow pulse, shimmer, gradient border, reveal saat scroll.

---

## FASE 0 — Persiapan

```powershell
cd "C:\Romadhon Data penting\Downloads\YT DON\Lomba Gemastik\jualin-ai\frontend"
npm install          # pastikan node_modules ada
npm run dev          # buka http://localhost:3000 sebagai baseline (lihat tampilan SEBELUM)
```
Catat tampilan awal landing + login + /dashboard/agent-os. **Stop dev (Ctrl+C)** sebelum mengedit, atau biarkan jalan (hot reload) untuk lihat perubahan live.

---

## FASE 1 — Fondasi global (`frontend/app/globals.css`)

### 1.1 Ganti baris `@import` font (baris 7) — tambah font **Sora**
**Cari:**
```css
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
```
**Ganti dengan:**
```css
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Sora:wght@400;500;600;700;800&display=swap');
```
> `@import` HARUS tetap berada di baris paling atas file CSS. Jangan pindahkan.

### 1.2 Tambah sistem "Aurora Deck" di AKHIR `globals.css`
Tempel blok berikut **di paling bawah** `globals.css` (setelah baris terakhir `::selection {...}`). Ini hanya **menambah**, tidak menghapus apa pun.

```css
/* ═══════════════════════════════════════════════
   AURORA DECK — Modern / 3D / AI dark layer (additive)
   ═══════════════════════════════════════════════ */
:root {
  --d-bg: #060912;
  --d-bg-2: #0A1020;
  --d-surface: rgba(255, 255, 255, 0.04);
  --d-text: #E6EDF7;
  --d-text-dim: #9AA7BD;
  --d-line: rgba(255, 255, 255, 0.10);

  --c-emerald: #22C55E;
  --c-cyan: #22D3EE;
  --c-violet: #8B5CF6;
  --c-pink: #F472B6;

  --glass: rgba(255, 255, 255, 0.05);
  --glass-2: rgba(255, 255, 255, 0.08);
  --glass-line: rgba(255, 255, 255, 0.12);

  --grad-brand: linear-gradient(100deg, #34D399 0%, #22D3EE 52%, #A78BFA 100%);
  --grad-brand-soft: linear-gradient(120deg, rgba(34,197,94,.9), rgba(34,211,238,.9), rgba(139,92,246,.9));

  --glow-emerald: 0 0 40px -8px rgba(34, 197, 94, 0.55);
  --glow-cyan: 0 0 40px -8px rgba(34, 211, 238, 0.5);
  --shadow-3d: 0 24px 60px -24px rgba(0, 0, 0, 0.75), 0 2px 8px rgba(0, 0, 0, 0.4);
  --font-display: 'Sora', 'Plus Jakarta Sans', sans-serif;
}

/* Latar aurora gelap untuk permukaan etalase */
.aurora-bg {
  position: relative;
  background:
    radial-gradient(55% 45% at 12% 8%, rgba(34, 197, 94, 0.20), transparent 60%),
    radial-gradient(50% 45% at 88% 12%, rgba(34, 211, 238, 0.18), transparent 60%),
    radial-gradient(60% 60% at 50% 108%, rgba(139, 92, 246, 0.20), transparent 60%),
    linear-gradient(180deg, var(--d-bg) 0%, var(--d-bg-2) 100%);
  color: var(--d-text);
  overflow: hidden;
}
/* lapisan grain halus */
.aurora-bg::after {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0.04;
  background-image: radial-gradient(rgba(255,255,255,0.6) 0.5px, transparent 0.5px);
  background-size: 3px 3px;
}

/* Blob aurora melayang (drop-in div: <div class="aurora-blob b1"></div>) */
.aurora-blob {
  position: absolute;
  width: 460px;
  height: 460px;
  border-radius: 50%;
  filter: blur(90px);
  opacity: 0.5;
  pointer-events: none;
  z-index: 0;
  animation: aurora-drift 18s ease-in-out infinite;
}
.aurora-blob.b1 { background: var(--c-emerald); top: -120px; left: -80px; }
.aurora-blob.b2 { background: var(--c-cyan); top: 10%; right: -120px; animation-delay: -6s; }
.aurora-blob.b3 { background: var(--c-violet); bottom: -160px; left: 30%; animation-delay: -12s; }

/* Kaca */
.glass {
  background: var(--glass);
  -webkit-backdrop-filter: blur(18px) saturate(140%);
  backdrop-filter: blur(18px) saturate(140%);
  border: 1px solid var(--glass-line);
  border-radius: 20px;
  box-shadow: var(--shadow-3d);
}
.glass-strong {
  background: var(--glass-2);
  -webkit-backdrop-filter: blur(26px) saturate(150%);
  backdrop-filter: blur(26px) saturate(150%);
  border: 1px solid var(--glass-line);
  border-radius: 24px;
  box-shadow: var(--shadow-3d);
}

/* Teks gradient */
.gradient-text {
  background: var(--grad-brand);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

/* Border gradient (tanpa animasi rumit, robust) */
.grad-border {
  border: 1px solid transparent;
  background:
    linear-gradient(var(--d-bg-2), var(--d-bg-2)) padding-box,
    var(--grad-brand-soft) border-box;
}

/* Panggung 3D + kartu tilt */
.deck-3d { perspective: 1200px; }
.card-3d {
  transform-style: preserve-3d;
  transition: transform 0.45s cubic-bezier(0.175, 0.885, 0.32, 1.275), box-shadow 0.45s ease;
  will-change: transform;
}
.deck-3d .card-3d:hover {
  transform: translateY(-8px) rotateX(5deg) rotateY(-5deg);
  box-shadow: var(--shadow-3d), var(--glow-emerald);
}

/* Tombol glow (gabungkan dgn .btn .btn-primary) */
.btn-glow {
  box-shadow: 0 10px 34px -10px rgba(34, 197, 94, 0.65), inset 0 0 0 1px rgba(255, 255, 255, 0.15);
}
.btn-glow:hover { box-shadow: 0 14px 44px -10px rgba(34, 197, 94, 0.8), inset 0 0 0 1px rgba(255, 255, 255, 0.22); }

/* Melayang & reveal */
.float-slow { animation: float-slow 6s ease-in-out infinite; }
.glow-pulse { animation: glow-pulse 3s ease-in-out infinite; }

/* Keyframes baru */
@keyframes aurora-drift {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(40px, -30px) scale(1.08); }
  66% { transform: translate(-30px, 24px) scale(0.96); }
}
@keyframes float-slow {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-12px); }
}
@keyframes glow-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.0), var(--glow-emerald); }
  50% { box-shadow: 0 0 0 6px rgba(34, 197, 94, 0.08), var(--glow-cyan); }
}
@keyframes reveal-up {
  from { opacity: 0; transform: translateY(28px); }
  to { opacity: 1; transform: translateY(0); }
}

/* Aksesibilitas: matikan animasi bila pengguna minta */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; scroll-behavior: auto !important; }
}
```

**Verifikasi 1:** `npm run build` harus sukses. Buka halaman mana pun — semua tetap normal (kita hanya menambah). Belum ada perubahan visual sampai class baru dipakai di Fase 2–4.

---

## FASE 2 — Redesign Landing Page (`frontend/app/page.module.css`)

**TINDAKAN: ganti SELURUH isi `frontend/app/page.module.css` dengan kode di bawah.**
JSX `app/page.js` **tidak perlu diubah** — semua nama class sudah cocok. (Elemen `heroGlow1/2`, `heroGrid` yang sudah ada kita ubah jadi aurora blobs.)

```css
/* JUALIN.AI — Landing (Aurora Deck) */
.landing { background: var(--d-bg); color: var(--d-text); overflow-x: hidden; }

/* ── Navbar ── */
.navbar {
  position: fixed; top: 0; left: 0; right: 0; z-index: 100;
  padding: 16px 0; transition: all 0.3s ease;
}
.navScrolled {
  background: rgba(8, 12, 22, 0.72);
  -webkit-backdrop-filter: blur(16px); backdrop-filter: blur(16px);
  border-bottom: 1px solid var(--d-line); padding: 10px 0;
}
.navContent { display: flex; align-items: center; justify-content: space-between; }
.logo { display: inline-flex; align-items: center; gap: 8px; font-family: var(--font-display); font-weight: 800; font-size: 1.25rem; color: var(--d-text); }
.logoIcon { font-size: 1.4rem; filter: drop-shadow(0 0 10px rgba(34,197,94,0.6)); }
.logoText { background: var(--grad-brand); -webkit-background-clip: text; background-clip: text; color: transparent; }
.navLinks { display: flex; gap: 28px; }
.navLinks a { color: var(--d-text-dim); font-weight: 500; font-size: 0.92rem; }
.navLinks a:hover { color: var(--d-text); }
.navActions { display: flex; gap: 10px; align-items: center; }
@media (max-width: 768px) { .navLinks { display: none; } }

/* ── Hero ── */
.hero { position: relative; padding: 150px 0 90px; }
.heroBg { position: absolute; inset: 0; overflow: hidden; z-index: 0;
  background:
    radial-gradient(50% 40% at 15% 20%, rgba(34,197,94,0.16), transparent 60%),
    radial-gradient(45% 40% at 85% 10%, rgba(34,211,238,0.14), transparent 60%),
    linear-gradient(180deg, var(--d-bg), var(--d-bg-2));
}
/* heroGlow1/2 jadi aurora blobs */
.heroGlow1 { position: absolute; width: 520px; height: 520px; border-radius: 50%;
  background: var(--c-emerald); filter: blur(110px); opacity: 0.35; top: -140px; left: -100px;
  animation: aurora-drift 20s ease-in-out infinite; }
.heroGlow2 { position: absolute; width: 480px; height: 480px; border-radius: 50%;
  background: var(--c-violet); filter: blur(120px); opacity: 0.32; top: 5%; right: -120px;
  animation: aurora-drift 24s ease-in-out infinite reverse; }
.heroGrid { position: absolute; inset: 0; opacity: 0.5;
  background-image:
    linear-gradient(rgba(255,255,255,0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.04) 1px, transparent 1px);
  background-size: 48px 48px;
  -webkit-mask-image: radial-gradient(70% 60% at 50% 35%, #000 0%, transparent 80%);
  mask-image: radial-gradient(70% 60% at 50% 35%, #000 0%, transparent 80%); }
.heroContent { position: relative; z-index: 1; display: grid; grid-template-columns: 1.05fr 0.95fr; gap: 48px; align-items: center; }
@media (max-width: 900px) { .heroContent { grid-template-columns: 1fr; } }

.heroBadge { display: inline-flex; align-items: center; gap: 8px; padding: 7px 14px;
  border-radius: 999px; font-size: 0.82rem; font-weight: 600; color: var(--d-text);
  background: var(--glass); border: 1px solid var(--glass-line);
  -webkit-backdrop-filter: blur(10px); backdrop-filter: blur(10px); }
.badgeDot { width: 8px; height: 8px; border-radius: 50%; background: var(--c-emerald); box-shadow: 0 0 10px var(--c-emerald); animation: glow-pulse 2s infinite; }
.heroTitle { font-family: var(--font-display); font-size: clamp(2.3rem, 5vw, 3.6rem); font-weight: 800; line-height: 1.08; margin: 20px 0 16px; color: #fff; letter-spacing: -0.02em; }
.heroHighlight { background: var(--grad-brand); -webkit-background-clip: text; background-clip: text; color: transparent; }
.heroDesc { color: var(--d-text-dim); font-size: 1.08rem; line-height: 1.7; max-width: 540px; }
.heroButtons { display: flex; gap: 14px; margin: 28px 0 20px; flex-wrap: wrap; }
.trustBadges { display: flex; gap: 18px; flex-wrap: wrap; color: var(--d-text-dim); font-size: 0.85rem; }

/* Visual chat (kartu kaca melayang) */
.heroVisual { position: relative; }
.chatPreview { position: relative; z-index: 2; border-radius: 22px; overflow: hidden;
  background: rgba(12, 18, 32, 0.7); border: 1px solid var(--glass-line);
  -webkit-backdrop-filter: blur(20px); backdrop-filter: blur(20px);
  box-shadow: var(--shadow-3d), var(--glow-emerald); animation: float-slow 6s ease-in-out infinite; }
.chatHeader { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; border-bottom: 1px solid var(--d-line); background: rgba(255,255,255,0.03); }
.chatHeaderInfo { display: flex; align-items: center; gap: 8px; font-size: 0.85rem; color: var(--d-text); font-weight: 600; }
.chatDot { width: 8px; height: 8px; border-radius: 50%; background: var(--c-emerald); box-shadow: 0 0 8px var(--c-emerald); }
.chatBadge { font-size: 0.72rem; font-weight: 700; padding: 3px 10px; border-radius: 999px; background: rgba(34,197,94,0.15); color: #6EE7B7; }
.chatMessages { display: flex; flex-direction: column; gap: 10px; padding: 18px; }
/* bubble global dipakai apa adanya; pastikan kontras di panel gelap */
.chatMessages :global(.chat-bubble.customer) { background: rgba(255,255,255,0.08); color: var(--d-text); }
.chatMessages :global(.chat-bubble.ai) { background: rgba(34,197,94,0.14); color: #D1FAE5; border-color: rgba(34,197,94,0.3); }
.chatInputPreview { display: flex; align-items: center; justify-content: space-between; padding: 12px 18px; border-top: 1px solid var(--d-line); color: var(--d-text-dim); font-size: 0.85rem; }
.sendIcon { color: var(--c-emerald); }
.floatingBadge1, .floatingBadge2 { position: absolute; z-index: 3; padding: 9px 14px; border-radius: 14px;
  font-size: 0.8rem; font-weight: 700; color: #fff; background: rgba(12,18,32,0.85);
  border: 1px solid var(--glass-line); box-shadow: var(--shadow-3d); }
.floatingBadge1 { top: 18%; left: -28px; animation: float-slow 5s ease-in-out infinite; }
.floatingBadge2 { bottom: 16%; right: -20px; animation: float-slow 5.5s ease-in-out infinite reverse; }
@media (max-width: 900px) { .floatingBadge1, .floatingBadge2 { display: none; } }

/* ── Stats ── */
.stats { padding: 40px 0; border-top: 1px solid var(--d-line); border-bottom: 1px solid var(--d-line); background: rgba(255,255,255,0.015); }
.statsGrid { display: flex; align-items: center; justify-content: space-around; gap: 16px; flex-wrap: wrap; }
.statItem { text-align: center; }
.statNumber { display: block; font-family: var(--font-display); font-size: 2rem; font-weight: 800; background: var(--grad-brand); -webkit-background-clip: text; background-clip: text; color: transparent; }
.statLabel { color: var(--d-text-dim); font-size: 0.85rem; }
.statDivider { width: 1px; height: 40px; background: var(--d-line); }
@media (max-width: 768px) { .statDivider { display: none; } }

/* ── Section shells ── */
.features, .howItWorks, .pricing, .faq { position: relative; padding: 90px 0; }
.howItWorks, .faq { background: rgba(255,255,255,0.015); }
.sectionHeader { text-align: center; max-width: 680px; margin: 0 auto 50px; }
.sectionBadge { display: inline-block; padding: 6px 14px; border-radius: 999px; font-size: 0.78rem; font-weight: 700; color: #6EE7B7; background: rgba(34,197,94,0.12); border: 1px solid rgba(34,197,94,0.25); margin-bottom: 14px; }
.sectionTitle { font-family: var(--font-display); font-size: clamp(1.8rem, 3.5vw, 2.6rem); font-weight: 800; color: #fff; letter-spacing: -0.02em; }
.sectionDesc { color: var(--d-text-dim); font-size: 1.02rem; margin-top: 12px; }

/* ── Feature cards (3D tilt + glass) ── */
.featuresGrid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 22px; perspective: 1200px; }
@media (max-width: 900px) { .featuresGrid { grid-template-columns: 1fr; } }
.featureCard {
  background: var(--glass); border: 1px solid var(--glass-line); border-radius: 20px; padding: 26px;
  -webkit-backdrop-filter: blur(16px); backdrop-filter: blur(16px);
  transform-style: preserve-3d;
  transition: transform 0.45s cubic-bezier(0.175,0.885,0.32,1.275), box-shadow 0.45s ease, border-color 0.3s;
  animation: reveal-up 0.6s ease both;
}
.featureCard:hover { transform: translateY(-8px) rotateX(6deg) rotateY(-6deg); box-shadow: var(--shadow-3d), var(--glow-emerald); border-color: rgba(34,197,94,0.4); }
.featureIconWrap { width: 56px; height: 56px; display: grid; place-items: center; border-radius: 16px; background: var(--grad-brand-soft); box-shadow: var(--glow-emerald); margin-bottom: 16px; transform: translateZ(40px); }
.featureIcon { font-size: 1.7rem; }
.featureCard h3 { color: #fff; font-size: 1.15rem; margin-bottom: 8px; }
.featureCard p { color: var(--d-text-dim); font-size: 0.92rem; line-height: 1.6; }

/* ── How it works ── */
.stepsGrid { display: flex; align-items: stretch; justify-content: center; gap: 16px; flex-wrap: wrap; }
.step { flex: 1; min-width: 220px; max-width: 300px; text-align: center; padding: 28px 22px; border-radius: 20px; background: var(--glass); border: 1px solid var(--glass-line); -webkit-backdrop-filter: blur(14px); backdrop-filter: blur(14px); }
.stepNum { width: 48px; height: 48px; margin: 0 auto 14px; display: grid; place-items: center; border-radius: 50%; font-family: var(--font-display); font-weight: 800; color: #fff; background: var(--grad-brand-soft); box-shadow: var(--glow-emerald); }
.step h3 { color: #fff; font-size: 1.08rem; margin-bottom: 8px; }
.step p { color: var(--d-text-dim); font-size: 0.9rem; line-height: 1.6; }
.stepArrow { display: grid; place-items: center; font-size: 1.6rem; color: var(--c-cyan); }
@media (max-width: 768px) { .stepArrow { transform: rotate(90deg); } }

/* ── Pricing ── */
.pricingGrid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 18px; perspective: 1200px; }
@media (max-width: 1024px) { .pricingGrid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 560px) { .pricingGrid { grid-template-columns: 1fr; } }
.pricingCard { display: flex; flex-direction: column; padding: 26px 22px; border-radius: 20px; background: var(--glass); border: 1px solid var(--glass-line); -webkit-backdrop-filter: blur(14px); backdrop-filter: blur(14px); transition: transform 0.4s, box-shadow 0.4s, border-color 0.3s; }
.pricingCard:hover { transform: translateY(-6px); box-shadow: var(--shadow-3d); border-color: rgba(255,255,255,0.2); }
.pricingPopular { border-color: rgba(34,197,94,0.5); box-shadow: var(--shadow-3d), var(--glow-emerald); position: relative; background: rgba(34,197,94,0.06); }
.popularBadge { position: absolute; top: -12px; left: 50%; transform: translateX(-50%); padding: 5px 14px; border-radius: 999px; font-size: 0.72rem; font-weight: 800; color: #06210F; background: var(--grad-brand); white-space: nowrap; }
.pricingName { font-family: var(--font-display); color: #fff; font-size: 1.2rem; }
.pricingPrice { margin: 8px 0; }
.priceAmount { font-family: var(--font-display); font-size: 1.9rem; font-weight: 800; color: #fff; }
.pricePeriod { color: var(--d-text-dim); font-size: 0.85rem; margin-left: 4px; }
.pricingLimit { color: var(--c-cyan); font-size: 0.82rem; font-weight: 600; }
.pricingDivider { height: 1px; background: var(--d-line); margin: 16px 0; }
.pricingFeatures { list-style: none; display: flex; flex-direction: column; gap: 10px; margin-bottom: 20px; }
.pricingFeatures li { color: var(--d-text-dim); font-size: 0.88rem; display: flex; align-items: center; gap: 8px; }
.checkIcon { color: var(--c-emerald); font-weight: 800; }

/* ── FAQ ── */
.faqList { max-width: 760px; margin: 0 auto; display: flex; flex-direction: column; gap: 12px; }
.faqItem { border-radius: 16px; background: var(--glass); border: 1px solid var(--glass-line); overflow: hidden; }
.faqQuestion { width: 100%; display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 18px 22px; background: transparent; border: none; cursor: pointer; color: #fff; font-family: var(--font-body); font-size: 0.98rem; font-weight: 600; text-align: left; }
.faqChevron { color: var(--c-emerald); font-size: 1.3rem; }
.faqAnswer { max-height: 0; overflow: hidden; transition: max-height 0.35s ease; }
.faqOpen .faqAnswer { max-height: 240px; }
.faqAnswer p { padding: 0 22px 20px; color: var(--d-text-dim); font-size: 0.92rem; line-height: 1.7; }

/* ── CTA ── */
.cta { position: relative; padding: 90px 0; overflow: hidden; }
.ctaBg { position: absolute; inset: 0; background:
    radial-gradient(50% 80% at 50% 50%, rgba(34,197,94,0.20), transparent 70%),
    linear-gradient(180deg, var(--d-bg-2), var(--d-bg)); }
.ctaTitle { font-family: var(--font-display); font-size: clamp(1.9rem, 4vw, 2.8rem); font-weight: 800; color: #fff; }
.ctaDesc { color: var(--d-text-dim); font-size: 1.05rem; margin: 12px 0 28px; }
.ctaForm { display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; }
.ctaNote { color: var(--d-text-dim); font-size: 0.88rem; margin-top: 18px; }

/* ── Footer ── */
.footer { padding: 50px 0 36px; border-top: 1px solid var(--d-line); background: var(--d-bg); }
.footerContent { display: flex; align-items: center; justify-content: space-between; gap: 24px; flex-wrap: wrap; }
.footerLinks { display: flex; gap: 22px; }
.footerLinks a { color: var(--d-text-dim); font-size: 0.9rem; }
.footerLinks a:hover { color: var(--d-text); }

/* ── Reveal on scroll (dipakai oleh sectionClass di page.js) ── */
.sectionHidden { opacity: 0; transform: translateY(34px); }
.sectionVisible { opacity: 1; transform: translateY(0); transition: opacity 0.7s ease, transform 0.7s ease; }
```

> **Penting tentang `.input` di CTA:** global `.input` masih terang. Agar kontras di bagian CTA gelap, tambahkan di AKHIR `page.module.css`:
> ```css
> .cta :global(.input) { background: rgba(255,255,255,0.06); border-color: var(--glass-line); color: #fff; }
> .cta :global(.input)::placeholder { color: var(--d-text-dim); }
> ```

**Verifikasi 2:** `npm run dev`, buka `/`. Landing harus tampil gelap + aurora + kartu 3D (hover fitur = miring + glow). `npm run build` harus sukses.

---

## FASE 3 — Redesign Auth (login + register)

`login/page.js` mengimpor `./auth.module.css` (class: authPage, authCard, authHeader, logo, logoText, authForm, errorMsg, field, fieldWithToggle, passwordToggle, authFooter).

### 3.1 Ganti SELURUH isi `frontend/app/login/auth.module.css` dengan:
```css
/* JUALIN.AI — Auth (Aurora Deck) */
.authPage {
  min-height: 100vh; display: grid; place-items: center; padding: 24px; position: relative; overflow: hidden;
  background:
    radial-gradient(45% 40% at 15% 20%, rgba(34,197,94,0.22), transparent 60%),
    radial-gradient(45% 40% at 85% 80%, rgba(139,92,246,0.22), transparent 60%),
    linear-gradient(180deg, var(--d-bg), var(--d-bg-2));
  color: var(--d-text);
}
.authPage::before {
  content: ''; position: absolute; width: 480px; height: 480px; border-radius: 50%;
  background: var(--c-cyan); filter: blur(120px); opacity: 0.25; top: -120px; right: -120px;
  animation: aurora-drift 20s ease-in-out infinite;
}
.authCard {
  position: relative; z-index: 1; width: 100%; max-width: 420px; padding: 36px 32px;
  background: rgba(12, 18, 32, 0.72); border: 1px solid var(--glass-line); border-radius: 24px;
  -webkit-backdrop-filter: blur(24px) saturate(150%); backdrop-filter: blur(24px) saturate(150%);
  box-shadow: var(--shadow-3d), var(--glow-emerald);
  animation: reveal-up 0.5s ease both;
}
.authHeader { text-align: center; margin-bottom: 24px; }
.logo { display: inline-flex; align-items: center; gap: 8px; font-family: var(--font-display); font-weight: 800; font-size: 1.3rem; margin-bottom: 16px; }
.logoText { background: var(--grad-brand); -webkit-background-clip: text; background-clip: text; color: transparent; }
.authHeader h1 { color: #fff; font-family: var(--font-display); font-size: 1.5rem; margin-bottom: 6px; }
.authHeader p { color: var(--d-text-dim); font-size: 0.9rem; }
.authForm { display: flex; flex-direction: column; gap: 16px; }
.field { display: flex; flex-direction: column; }
.field :global(.label) { color: var(--d-text); }
.field :global(.input) {
  background: rgba(255,255,255,0.06); border: 1.5px solid var(--glass-line); color: #fff;
}
.field :global(.input)::placeholder { color: var(--d-text-dim); }
.field :global(.input):focus { border-color: var(--c-emerald); box-shadow: 0 0 0 4px rgba(34,197,94,0.18); }
.fieldWithToggle { position: relative; }
.passwordToggle { position: absolute; right: 8px; top: 50%; transform: translateY(-50%); background: transparent; border: none; cursor: pointer; font-size: 1.1rem; padding: 6px; }
.errorMsg { background: rgba(239,68,68,0.12); border: 1px solid rgba(239,68,68,0.3); color: #FCA5A5; padding: 10px 14px; border-radius: 12px; font-size: 0.85rem; }
.authFooter { text-align: center; margin-top: 20px; color: var(--d-text-dim); font-size: 0.9rem; }
.authFooter a { color: var(--c-emerald); font-weight: 600; }
```

### 3.2 Samakan halaman Register
Buka `frontend/app/register/page.js`. Lihat baris `import styles from "..."`.
- Jika ia mengimpor **`../login/auth.module.css`** → otomatis ikut berubah, **tidak ada kerja lagi**.
- Jika ia mengimpor file CSS module sendiri (mis. `./register.module.css` atau `./auth.module.css` lokal) → **salin seluruh isi** dari 3.1 ke file itu (sesuaikan: jika ada class tambahan di register yang tidak ada di login, beri gaya gelap serupa: teks `#fff`, input kaca, kartu glass). **Jangan ubah JSX/logikanya.**

> Tombol submit auth memakai global `.btn .btn-primary` (sudah punya gradient emerald) — biarkan. Boleh tambahkan class `btn-glow` di JSX tombol (1 kata) untuk efek glow: `className="btn btn-primary btn-lg btn-glow"`.

**Verifikasi 3:** buka `/login` dan `/register` → kartu kaca gelap melayang di atas aurora. `npm run build` sukses.

---

## FASE 4 — Polish halaman AI Crew (`frontend/app/dashboard/agent-os/page.js`)

Halaman ini sudah dark (inline style). Cukup 3 sentuhan kecil agar selaras "Aurora Deck". **Edit `className`/style saja.**

**4.1** Wrapper terluar — beri latar aurora. Cari `return (` lalu div pembungkus pertama:
```jsx
<div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
```
Ganti menjadi (tambah className + padding):
```jsx
<div className="aurora-bg" style={{ display: "flex", flexDirection: "column", gap: 16, padding: 16, borderRadius: 20 }}>
```

**4.2** Header card — pakai gradient text. Cari judul `🤖 AI Crew — Pusat Komando Toko Otonom` di dalam `<h2 ...>`. Tambahkan `className="gradient-text"` pada elemen `<h2>` itu (biarkan style lain).

**4.3** Kartu agen — efek 3D tilt. Cari grid kartu agen (`overview?.crew || []`). Pada `<div key={c.role} style={{...}}>` tiap kartu, tambahkan `className="card-3d"` dan bungkus grid-nya dengan `className="deck-3d"` (tambahkan ke div grid pembungkus kartu). Hover kartu agen kini miring + glow.

> Tidak perlu mengubah data/fetch. Kalau ragu, cukup lakukan 4.1 + 4.2 (paling aman) dan lewati 4.3.

**Verifikasi 4:** login → menu **🤖 AI Crew** → tampilan makin "command center".

---

## FASE 5 — (OPSIONAL / Tier 2) Chrome Dashboard lebih modern

Hanya jika ingin dashboard ikut premium. **Lebih berisiko** (banyak halaman terang). Lakukan bertahap & uji tiap langkah.

Target file: `frontend/app/dashboard/dashboard.module.css` (sidebar `.sidebar`, topbar `.topBar`, dll — buka dulu untuk lihat nama class persisnya).

Rekomendasi aman (tanpa menggelapkan konten halaman):
- **Sidebar jadi kaca gelap:** pada `.sidebar` set `background: linear-gradient(180deg,#0A1020,#070B14); color: var(--d-text); border-right: 1px solid var(--d-line);` dan ubah warna item nav non-aktif ke `var(--d-text-dim)`, item aktif beri `background: rgba(34,197,94,0.12); color:#fff;` + garis kiri emerald.
- **Topbar:** `background: rgba(255,255,255,0.7); -webkit-backdrop-filter: blur(14px); backdrop-filter: blur(14px); border-bottom: 1px solid var(--border);` (tetap terang, hanya kaca).
- **Konten** dibiarkan terang agar tabel/teks tetap terbaca.

> Jangan menggelapkan area `.content`/`.mainContent` kecuali kamu siap me-restyle SEMUA halaman di dalamnya. Untuk lomba, cukup sidebar kaca gelap + landing/auth/AI Crew yang sudah wow.

---

## FASE 6 — (OPSIONAL) Interaktif 3D: tilt mengikuti mouse + reveal

Efek tilt CSS di Fase 2 sudah cukup. Jika ingin tilt **mengikuti kursor** (lebih hidup), buat komponen kecil ini. **SSR-safe** (`"use client"`, akses `window` hanya di event).

Buat `frontend/components/TiltCard.js`:
```jsx
"use client";
import { useRef } from "react";

export default function TiltCard({ children, className = "", max = 8, style }) {
  const ref = useRef(null);

  const onMove = (e) => {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width - 0.5;
    const py = (e.clientY - r.top) / r.height - 0.5;
    el.style.transform = `perspective(1000px) rotateY(${px * max}deg) rotateX(${-py * max}deg) translateY(-6px)`;
  };
  const reset = () => {
    if (ref.current) ref.current.style.transform = "";
  };

  return (
    <div
      ref={ref}
      onMouseMove={onMove}
      onMouseLeave={reset}
      className={className}
      style={{ transition: "transform 0.2s ease", transformStyle: "preserve-3d", ...style }}
    >
      {children}
    </div>
  );
}
```
Pakai dengan membungkus kartu: `import TiltCard from "@/components/TiltCard";` lalu `<TiltCard className="featureCard">...</TiltCard>`. **Opsional** — jangan dipakai kalau menambah risiko; versi CSS sudah bagus.

---

## FASE 7 — Build, QA, dan checklist

### 7.1 Build
```powershell
cd "C:\Romadhon Data penting\Downloads\YT DON\Lomba Gemastik\jualin-ai\frontend"
npm run lint
npm run build
```
Keduanya HARUS sukses (CI Anda juga menjalankan ini). Jika `npm run build` gagal, baca error: biasanya salah tanda kurung di CSS atau class JSX yang typo.

### 7.2 Checklist QA visual
- [ ] Landing gelap, aurora bergerak halus, kartu fitur **miring + glow** saat hover.
- [ ] Login & Register: kartu kaca melayang di atas aurora; input terbaca (teks putih).
- [ ] AI Crew: latar aurora + judul gradient.
- [ ] Halaman dashboard lama (Produk, Order) **tidak rusak** (masih terang & terbaca) — karena kita tidak menyentuhnya (kecuali Fase 5).
- [ ] Mobile (lebar 375px): hero menumpuk 1 kolom, grid jadi 1 kolom, tidak ada elemen meluber.
- [ ] Animasi mati saat OS di-set "reduce motion".
- [ ] Tidak ada teks gelap-di-atas-gelap atau terang-di-atas-terang.

### 7.3 Performa
- `backdrop-filter` (kaca) dipakai secukupnya pada kartu utama, bukan ratusan elemen.
- Aurora blob memakai `filter: blur()` besar — cukup 2–3 per halaman, jangan puluhan.

---

## LAMPIRAN — Jebakan umum (HINDARI)

1. **Mengubah JSX/logika.** Cukup CSS + sisipan className kecil. Jangan utak-atik `useState`/fetch.
2. **Menghapus token/class lama di `globals.css`.** Banyak halaman dashboard memakainya → bisa rusak. Hanya **append**.
3. **`@import` font tidak di baris atas.** CSS akan mengabaikannya. Biarkan baris 1 area `@import`.
4. **Lupa `-webkit-backdrop-filter`.** Efek kaca tak muncul di sebagian browser.
5. **Menggelapkan dashboard sepenuhnya** lalu tabel jadi tak terbaca. Jangan, kecuali Fase 5 dilakukan menyeluruh.
6. **Salah jumlah kurung `{}` di CSS.** Build gagal. Tempel utuh blok yang diberikan.
7. **Register page beda file CSS.** Cek importnya (Fase 3.2) agar ikut bergaya.
8. **Next 16:** karena CSS-first, aman. Jangan menambah library 3D berat (three.js) — tidak perlu dan berisiko untuk SSR.

---

*Dokumen ini berdiri sendiri. Kerjakan Fase 0→7 berurutan; build setelah Fase 1/2/3. Tema "Aurora Deck" memberi kesan produk AI modern & 3D dengan risiko break minimal karena murni lapisan CSS. Selamat mendesain. ✨*
