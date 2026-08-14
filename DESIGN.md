# DESIGN.md — JUALIN.AI

> Diturunkan dari token yang **sudah ada** di `frontend/app/globals.css` dan pemakaiannya
> di modul-modul frontend. Dokumen ini mendokumentasikan arah de-facto, bukan mengarang
> palet/font/arah baru. Disusun dalam mode AFTER (audit), bukan sebagai spesifikasi baru.

## Identitas

- Produk: AI sales assistant untuk UMKM Indonesia. Bahasa antarmuka: Bahasa Indonesia.
- Nada: dapat dipercaya (trustworthy), bukan flashy — halaman pembayaran dan etalase publik
  dilihat oleh pembeli akhir yang harus merasa aman bertransaksi.
- Dua "deck" visual yang sudah dipakai bersamaan:
  1. **Light deck** (emerald) — dashboard, form, tabel.
  2. **Aurora deck** (gelap, additive) — landing, login/register.

## Palet (dari `:root` di globals.css)

Core:
- `--primary: #22C55E` (emerald), `--primary-hover: #16A34A`, `--primary-dark: #15803D`
- `--secondary: #0EA5E9` (cyan), `--tertiary: #8B5CF6` (violet)
- `--stat-orange: #F97316`

Netral (tidak dihitung sebagai core per R-29):
- `--bg: #FAFBFC`, `--bg-card: #FFFFFF`, `--text: #1E293B`,
  `--text-secondary: #64748B`, `--text-muted: #94A3B8`, `--border: #E2E8F0`

Status: `--success #22C55E`, `--warning #EAB308`, `--danger #EF4444`, `--info #0EA5E9`.

Aurora deck (additive, blok kedua `:root`):
- `--d-bg: #060912`, `--d-text: #E6EDF7`, `--c-emerald/cyan/violet/pink`,
  `--grad-brand`, `--glow-*`, `--shadow-3d`.

## Tipografi (dari `app/layout.js`, self-hosted via next/font)

- Heading: Plus Jakarta Sans (`--font-jakarta` → `--font-heading`)
- Body: Inter (`--font-inter` → `--font-body`)
- Display (aurora deck): Sora (`--font-sora` → `--font-display`)

## Radius, shadow, spacing (skala sudah ada)

- Radius: `--radius-xs 4px` … `--radius-full 9999px` (skala penuh: 4/6/8/12/16/20/24/full).
- Shadow: `--shadow-xs` … `--shadow-xl`, plus `--shadow-primary`, `--shadow-card`,
  `--shadow-3d` (aurora).
- Spacing: campuran nilai `rem` langsung; utility `.mt-1/.mt-2/.mb-6` ada tapi terbatas.

## Motion (transisi & keyframes sudah ada)

- Transisi: `--transition-fast/slow/spring`.
- Keyframes: `typing`, `fadeInUp`, `fadeIn`, `shimmer`, `pulse-glow`,
  `aurora-drift`, `float-slow`, `glow-pulse`, `reveal-up`, `blink`, `pulse`, `spin`.
- `prefers-reduced-motion: reduce` sudah ada (globals.css:703) dan menonaktifkan animasi.

---

## Dial (disetujui owner)

Dial: ENERGY 2 / RHYTHM 2 / MOTION 1

Alasan usulan:
- **ENERGY 2 (Balanced)**: produk SaaS yang menjual kepercayaan (pembayaran, etalase).
  Tidak sepi seperti GOV.UK (1) karena landing memakai aurora deck yang energik; tidak
  setinggi portofolio agency (3). Titik tengah mencerminkan dua deck yang sudah ada.
- **RHYTHM 2 (consistent dengan beberapa break)**: landing sudah punya variasi section
  (hero/stats/features/steps/pricing/FAQ/CTA), dashboard relatif seragam. Angka 2 jujur
  terhadap kondisi saat ini tanpa menuntut variasi yang belum ada.
- **MOTION 1 (hover states only)**: halaman pembayaran dan chat harus tenang dan tepercaya.
  Nilai 1 sekaligus menandai animasi loop tak berujung yang saat ini ada (aurora-drift,
  float-slow, glow-pulse, blink, pulse) sebagai pelanggaran terhadap dial yang harus
  ditertibkan di fase perbaikan (R-19).
