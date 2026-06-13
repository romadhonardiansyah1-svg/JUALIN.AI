# JUALIN OS — Sistem Operasi Toko Otonom untuk UMKM Mikro

### Dari "AI yang menjawab chat" → menjadi "tim AI yang menjalankan toko"

> **GEMASTIK DIGINEXS 2026 — Divisi III: Pengembangan Perangkat Lunak**
> **Tim Digiboom**
> Tagline: *"Setiap UMKM berhak punya tim karyawan AI yang tak pernah tidur."*

---

## 1. Ringkasan Eksekutif

JUALIN.AI versi awal sudah menjawab satu masalah: membalas chat pelanggan secara otomatis. Tetapi pasar sudah ramai dengan **chatbot reaktif** — Qiscus, Kata.ai, dan puluhan bot open-source semuanya melakukan hal yang sama: *menunggu pesan, lalu menjawab*. Itu **AI Copilot**.

**JUALIN OS adalah lompatan kategori berikutnya: AI Autopilot.** Bukan satu bot yang menjawab, melainkan **satu tim agen AI terspesialisasi** yang **menjalankan seluruh operasional toko secara otonom** — menjual, **menawar (nego)**, menjaga stok, menagih pembayaran, memenangkan kembali pelanggan, dan menyusun laporan harian — sambil tetap berada **di bawah kendali penjual** lewat persetujuan untuk keputusan berisiko dan transparansi penuh.

Tiga kebaruan inti yang belum dimiliki kompetitor mana pun di Indonesia:

1. **Arsitektur Multi-Agen (Business OS).** Sebuah *Orchestrator* mengoordinasikan 6 agen spesialis (Pramuniaga, Juru Tawar, Gudang, Marketing, Keuangan, Layanan) yang bekerja proaktif 24/7 — bukan sekadar menjawab.
2. **Mesin Negosiasi Ber-Guardrail (Nego Cerdas).** Tawar-menawar adalah DNA dagang Indonesia, tetapi **tidak ada** AI komersial yang berani melakukannya secara otonom karena risiko jual rugi. JUALIN OS memecahkannya dengan **offer-generator deterministik** yang menjamin harga **tidak pernah** menembus batas margin penjual — sementara LLM hanya merangkai kalimatnya secara natural. Pendekatan ini langsung diturunkan dari riset *LLM bargaining* terbaru.
3. **Otonomi yang Bertanggung Jawab (Responsible Autonomy).** Setiap tindakan agen tercatat, dapat dijelaskan (*explainable*), dan keputusan berisiko (diskon besar, refund, broadcast) masuk **antrean persetujuan manusia** (*human-in-the-loop*). Penjual tetap pegang kemudi.

**Dampak yang ditargetkan:** memangkas waktu operasional penjual hingga **60–80%**, menaikkan konversi chat lewat respons & nego instan, serta **menyelamatkan omzet** yang biasanya hilang dari pembayaran tertunda dan pelanggan yang menghilang.

---

## 2. Latar Belakang & Masalah

### 2.1 UMKM Indonesia hidup di dalam chat

- Sekitar **63% UMKM Indonesia** sudah memakai alat digital pada 2025; WhatsApp memimpin dengan **±65% penetrasi**.
- Menurut **BPS**, ada **±4,4 juta** pelaku e-commerce di Indonesia (2024), dan **mayoritas berjualan lewat *instant messaging*** — chat, bukan marketplace.
- Bisnis yang menjadikan WhatsApp kanal penjualan utama mencatat pertumbuhan omzet **2,4× lebih tinggi** dibanding yang tidak.

Artinya, **medan pertempuran UMKM bukan etalase, melainkan kotak chat.** Dan di kotak chat itulah penjual mikro kewalahan.

### 2.2 Rasa sakit yang nyata (dan mahal)

Seorang penjual baju rumahan menghadapi semua ini **sendirian, setiap hari**:

| Beban | Realita di lapangan |
|---|---|
| **Balas chat 24 jam** | Calon pembeli bertanya jam 1 malam. Telat balas 10 menit = pembeli kabur ke toko sebelah. |
| **Tawar-menawar** | "Kak, 75 ribu boleh ya?" — penjual harus hitung cepat: masih untung atau rugi? Sering salah, sering rugi. |
| **Tagih yang belum bayar** | Order dibuat, link dikirim, lalu senyap. Tanpa follow-up, omzet menguap. |
| **Jaga stok** | Janji "ready kak!" padahal sudah habis → komplain & rugi reputasi. |
| **Menangkan kembali pelanggan** | Pembeli bulan lalu lupa. Tidak ada yang menyapa mereka lagi. |
| **Pembukuan** | Akhir hari: berapa masuk, berapa pending, produk apa yang laku? Tidak pernah sempat dihitung. |

Setiap beban di atas adalah **pekerjaan satu orang**. Penjual mikro mengerjakan **enam pekerjaan sekaligus** — dan kalah lelah sebelum kalah saing.

---

## 3. Keterbatasan Solusi Saat Ini

Pasar AI customer service Indonesia (Qiscus, Kata.ai) dan ekosistem open-source (mis. *langgraph-sales-agent*, *Cosmo*, *Multi-Agent-Enterprise-CRM*) memiliki pola yang sama:

- **Reaktif, bukan proaktif.** Mereka menunggu pesan masuk lalu menjawab. Tidak ada yang **berinisiatif** menagih, menawar, atau menyapa balik.
- **Satu otak, satu peran.** Sebuah bot tunggal "menjawab pertanyaan". Tidak ada pembagian peran layaknya tim — tidak ada yang khusus mengurus stok, keuangan, atau retensi.
- **Menghindari uang & risiko.** Tidak ada yang berani **menego harga** secara otomatis karena bahaya jual-rugi. Padahal nego adalah inti transaksi UMKM Indonesia.
- **Kotak hitam.** Penjual tidak bisa melihat *mengapa* AI mengambil keputusan tertentu, dan tidak punya rem untuk keputusan berisiko.

Riset pasar mengonfirmasi celah ini: kapabilitas *agentic commerce* 2026 menumpuk di **sisi pembeli** (asisten belanja) dan di **atas funnel** (discovery). **Sisi penjual dan deep-funnel (nego → closing → bayar → retensi) masih kosong.** Di sanalah JUALIN OS bermain.

> **Tesis kami:** Kategori berikutnya bukan "chatbot yang lebih pintar menjawab", melainkan **"karyawan AI yang menjalankan toko".**

---

## 4. Gagasan: JUALIN OS — Multi-Agent Business OS

Bayangkan penjual UMKM **merekrut 6 karyawan AI** sekaligus, masing-masing ahli di bidangnya, dikoordinasikan oleh seorang "Manajer AI", dan semuanya bekerja tanpa lelah:

| Agen (Karyawan AI) | Peran | Yang dilakukan secara otonom |
|---|---|---|
| 🧭 **Manajer Toko** (*Orchestrator*) | Mengoordinasi & memutuskan agen mana yang bertindak; menyusun **Laporan Harian** | Membaca setiap peristiwa (chat masuk, pembayaran, stok), mendelegasikan ke spesialis, dan menyusun *standup* harian untuk penjual |
| 🛍️ **Pramuniaga** (*Sales*) | Melayani percakapan: sapa → gali kebutuhan → presentasi → closing | Menjawab pertanyaan produk berbasis katalog, merekomendasi, membuat order |
| 🤝 **Juru Tawar** (*Negotiator*) | **Tawar-menawar aman-margin** | Menanggapi "boleh kurang?" dengan penawaran yang dijamin **tidak pernah di bawah batas untung** |
| 📦 **Gudang** (*Inventory*) | Menjaga stok & cegah *oversell* | Memverifikasi stok sebelum janji/order, mendeteksi stok menipis, memberi peringatan restock |
| 📣 **Marketing** (*Growth*) | Proaktif menumbuhkan omzet | Menagih pembayaran tertunda, *win-back* pelanggan pasif, usul *upsell*/reorder |
| 💰 **Keuangan** (*Finance*) | Pembukuan otomatis | Rekap omzet harian, paid vs pending, produk terlaris, bandingkan dengan kemarin |
| 🎧 **Layanan** (*CS*) | Tangani kebijakan & keluhan | Jawab COD/ongkir/retur, empati pada komplain, eskalasi ke penjual saat perlu |

Mereka tidak bekerja sendiri-sendiri. Sebuah **substrat peristiwa bersama** (event bus) menghubungkan mereka: ketika Pramuniaga akan menjanjikan stok, Gudang memverifikasi dulu; ketika Juru Tawar memberi diskon di atas ambang, Manajer menahannya untuk **persetujuan penjual**; ketika order dibuat tapi tak dibayar, Marketing mengambil alih menagih. Setelah hari berakhir, Manajer menyusun **Laporan Harian**: *"Hari ini tim AI Anda melayani 23 chat, menutup 4 order (Rp 612.000), menego 2 deal dalam batas margin, dan menyelamatkan 1 pembayaran tertunda. 1 keputusan menunggu persetujuan Anda."*

Inilah **Sistem Operasi Toko**: bukan fitur, melainkan **lapisan operasional otonom** di atas toko UMKM.

---

## 5. Pembeda & Kebaruan (Novelty)

### 5.1 Autopilot, bukan Copilot
Kompetitor = **copilot** (bantu manusia menjawab). JUALIN OS = **autopilot** (menjalankan operasi). Perbedaan ini bukan kosmetik — ia mengubah unit nilai dari *"hemat waktu mengetik"* menjadi *"gantikan beban 6 pekerjaan"*.

### 5.2 Negosiasi kultural ber-guardrail — fitur yang "ditakuti" semua kompetitor
Tawar-menawar adalah ritual dagang Indonesia, tetapi mematikan jika diserahkan ke LLM mentah (LLM mengarang harga, bisa jual rugi). **Solusi kami memisahkan ANGKA dari KATA:**

- **Offer-generator deterministik** menghitung penawaran balik memakai *concession ladder* (tangga konsesi) yang dibatasi **lantai harga** = `max(modal × (1 + margin_floor), harga × (1 − diskon_maks))`. Harga **secara matematis mustahil** menembus batas untung.
- **LLM hanya merangkai kalimat** di sekitar angka yang sudah diputuskan engine — natural, sopan, sesuai gaya toko, tetapi **tanpa kuasa mengubah angka**.
- Diskon di atas ambang → **persetujuan penjual** otomatis.

Pendekatan "engine yang mengontrol rentang harga, LLM yang menarasikan" ini **persis** rekomendasi riset *Measuring Bargaining Abilities of LLMs* (mekanisme *OG-Narrator / offer generator*). Inilah jembatan antara **kebaruan akademik** dan **kebutuhan pasar nyata**.

### 5.3 Otonomi yang bertanggung jawab (Responsible AI)
- **Transparan:** setiap tindakan agen tercatat di *Activity Feed* — penjual melihat siapa melakukan apa dan mengapa.
- **Dapat dijelaskan:** setiap keputusan menyertakan *reason code* (mis. "diskon 8% — masih di atas margin 22%").
- **Human-in-the-loop:** tindakan berisiko (diskon besar, refund, broadcast massal) tidak dieksekusi tanpa persetujuan.
- **Anti prompt-injection:** data pelanggan/katalog diperlakukan *untrusted*; instruksi berbahaya diblokir & diaudit (sudah ada di basis kode).

Kombinasi *otonomi + kendali + transparansi* adalah narasi "AI yang bisa dipercaya" yang sangat kuat di mata juri dan regulator.

### 5.4 Ringkasan posisi
| Dimensi | Chatbot CS (Qiscus/Kata.ai) | Bot open-source | **JUALIN OS** |
|---|---|---|---|
| Mode | Reaktif | Reaktif | **Proaktif + reaktif** |
| Struktur | 1 bot | 1 bot | **Multi-agen terkoordinasi** |
| Negosiasi | ❌ | ❌ | ✅ **aman-margin** |
| Proaktif (tagih/win-back) | ❌ | terbatas | ✅ |
| Pembukuan otomatis | ❌ | ❌ | ✅ |
| Kendali manusia + audit | sebagian | ❌ | ✅ **HITL penuh** |
| Konteks UMKM Indonesia | sebagian | ❌ | ✅ **kultural** |

---

## 6. Arsitektur Sistem

```
                         ┌──────────────────────────────────────────────┐
   Peristiwa masuk  ──▶  │            ORCHESTRATOR (Manajer AI)          │
   (chat / bayar /       │  Routing • Goal state • Refleksi • Daily Brief │
    stok / cron)         └───────────┬──────────────────────────────────┘
                                     │ delegasi (event substrate)
        ┌───────────────┬────────────┼────────────┬───────────────┬──────────────┐
        ▼               ▼            ▼            ▼               ▼              ▼
   🛍️ Pramuniaga   🤝 Juru Tawar  📦 Gudang   📣 Marketing   💰 Keuangan    🎧 Layanan
   (Sales)         (Negotiator)   (Inventory) (Growth)       (Finance)      (CS)
        │               │            │            │               │              │
        └───────────────┴────────────┴────────────┴───────────────┴──────────────┘
                                     │
            ┌────────────────────────┼─────────────────────────────┐
            ▼                        ▼                             ▼
   GUARDRAILS & GLOBAL POLICY   MEMORY & STATE                HUMAN-IN-THE-LOOP
   • Margin floor / diskon maks • Customer memory (pgvector)  • Antrean persetujuan
   • Anti prompt-injection      • Negotiation deal state      • Approve / reject
   • Audit setiap aksi          • Reflection log (lessons)    • Override penjual
```

**Lapisan & teknologi (semua sudah ada di basis kode, tinggal dievolusikan):**

- **Orkestrasi:** layanan Python async yang merutekan tiap *turn* chat dan tiap *tick* cron ke agen yang tepat. Loop **Plan → Act → Observe → Reflect** terinspirasi **ReAct** dan **Reflexion**.
- **Substrat peristiwa:** tabel `background_jobs` + worker **arq** (sudah ada) untuk kerja proaktif terjadwal; `audit_logs` + `customer_events` untuk jejak.
- **Memori:** `customer_memories` (pgvector) untuk personalisasi lintas sesi; `negotiation_state` untuk konteks tawar berjalan; *reflection log* untuk pembelajaran tanpa fine-tune (gaya *verbal reinforcement learning* Reflexion).
- **Guardrails:** mesin negosiasi deterministik + kebijakan global per penjava (`agent_policies`) + filter prompt-injection (sudah ada).
- **LLM:** via 9Router (OpenAI-compatible) — `llama-3.1-8b-instant` (gratis/murah), embedding lokal `all-MiniLM-L6-v2`.
- **Stack:** FastAPI · SQLAlchemy async · PostgreSQL 16 + pgvector · Redis · arq · Next.js 16 · Docker.

---

## 7. Fitur Unggulan (MVP) & Alur Demo

Untuk GEMASTIK, kami membangun **"JUALIN OS Core"** — irisan paling berdampak yang **bisa didemokan end-to-end**:

**Yang dibangun di MVP:**
1. **Orchestrator** yang merutekan tiap chat ke agen yang tepat & mencatat aktivitas.
2. **Juru Tawar (Negotiator)** lengkap dengan mesin nego aman-margin + persetujuan.
3. **Gudang (Inventory)** sebagai penjaga stok + pemindai stok menipis.
4. **Marketing (Growth)** proaktif: tagih pembayaran tertunda + win-back.
5. **Keuangan (Finance)** + **Laporan Harian** otomatis.
6. **Pusat Komando "AI Crew"** — satu halaman dashboard: kartu status tiap agen, *live activity feed*, laporan harian, antrean persetujuan, pengaturan kebijakan, dan *viewer* negosiasi.

**Skenario demo 90 detik (yang membuat juri "wow"):**

> 1. Pengunjung chat ke toko: *"Kak, Dress Emerald-nya ada? Boleh 150 ribu?"* (harga list 189.000).
> 2. **Gudang** memverifikasi stok (8 tersedia) → **Juru Tawar** menghitung: lantai harga 170.000, tawar balik **175.000** dengan kalimat ramah — **bukan** 150.000 yang akan rugi.
> 3. Pembeli setuju → **Pramuniaga** membuat order + link pembayaran.
> 4. Buka **Pusat Komando AI Crew**: *activity feed* menampilkan jejak ke-3 agen secara real-time; **Laporan Harian** terisi; bila pembeli minta diskon ekstrem, muncul **kartu persetujuan** yang harus di-*approve* penjual.
> 5. Tunjukkan **Keuangan**: omzet hari ini, pending, produk terlaris — terhitung otomatis.

Satu layar, satu menit — juri **melihat** sebuah toko yang dijalankan oleh tim AI, bukan sekadar kotak chat.

---

## 8. Dasar Ilmiah & Referensi

Kebaruan JUALIN OS bersandar pada literatur mutakhir, bukan klaim kosong:

1. **Arsitektur agen — ReAct** (*Reasoning + Acting*): interleaving penalaran dan aksi-tool untuk pengambilan keputusan dinamis. → Pola loop Orchestrator kami.
2. **Pembelajaran dari pengalaman — Reflexion**: refleksi verbal disimpan di memori episodik ("*verbal reinforcement learning*"), agen memperbaiki diri tanpa pelatihan ulang. → *Reflection log* kami.
3. **Negosiasi LLM — Measuring Bargaining Abilities of LLMs (arXiv:2402.15813)**: memformalkan tawar sebagai *asymmetric incomplete-information game*; menunjukkan LLM butuh **offer generator** untuk mengontrol rentang harga. → Inti mesin Nego Cerdas kami.
4. **NegotiationArena (arXiv:2402.05863)** & **LLM Agents for Bargaining with Utility-based Feedback (arXiv:2505.22998)**: evaluasi & peningkatan kapabilitas tawar LLM. → Rancangan *concession ladder* berbasis utilitas.
5. **Survei memori & perencanaan agen LLM (2024–2025)**: modul memori jangka pendek/panjang & pemisahan *planning/execution* untuk menekan *hallucination* dan *error compounding*. → Pemisahan angka (engine) vs kata (LLM).
6. **Laporan pasar** (eMarketer, Bain, Mordor Intelligence): *agentic commerce* memampatkan funnel & menaikkan konversi 20–30%; pasar US$50B+ pada 2030; namun **sisi penjual/deep-funnel masih kosong**. → Validasi peluang.
7. **Statistik Indonesia** (BPS, Infobip, Ken Research): chat = kanal e-commerce utama; WhatsApp dominan; UMKM digital tumbuh cepat. → Validasi pasar lokal.

> Tautan riset utama: arXiv [2402.15813](https://arxiv.org/abs/2402.15813), [2402.05863](https://arxiv.org/abs/2402.05863), [2505.22998](https://arxiv.org/pdf/2505.22998).

---

## 9. Dampak & Validasi

### 9.1 Metrik dampak yang diukur dalam produk
JUALIN OS mengukur nilainya sendiri (sudah ada fondasi `daily_seller_metrics`, atribusi order, `ai_assisted_revenue`):

- **Waktu operasional dihemat** (estimasi jam/hari dari aktivitas agen otonom).
- **Omzet di-assist AI** & **omzet diselamatkan** (pembayaran tertunda yang berhasil ditagih).
- **Konversi chat → order** sebelum vs sesudah.
- **Deal nego ditutup dalam batas margin** (jumlah & nilai), tanpa satu pun jual-rugi.

### 9.2 Rencana validasi (kuesioner)
Memakai *Template Kuesioner Validasi* yang sudah disiapkan tim: uji terhadap penjual UMKM riil (skala kemudahan, kepercayaan terhadap otonomi, persepsi nilai nego otomatis, niat pakai/bayar). Target: **SUS > 75** dan **≥ 70%** penjual menyatakan bersedia membayar.

---

## 10. Model Bisnis & Skalabilitas

- **Freemium berbasis kuota & otonomi:** Free (reaktif), Starter/Pro/Bisnis (membuka agen proaktif, nego, multi-channel, otonomi penuh). Tier sudah ada di basis kode (`QUOTA_*`, `PRODUCT_LIMIT_*`).
- **Monetisasi nilai, bukan pesan:** harga ditambatkan ke **omzet yang diselamatkan/dihasilkan** agen, bukan jumlah pesan — selaras dengan nilai yang dirasakan UMKM.
- **Moat (parit pertahanan):** (a) data nego & memori pelanggan per-penjual yang makin personal; (b) *reflection log* yang membuat tiap toko makin pintar seiring waktu; (c) integrasi mendalam (WhatsApp, payment, storefront) yang sudah berjalan.
- **Skala teknis:** arsitektur async + worker terdistribusi + idempotensi + rate-limit + secrets terenkripsi sudah disiapkan untuk multi-tenant.

---

## 11. Peta Jalan (Roadmap)

| Tahap | Fokus | Isi |
|---|---|---|
| **MVP (lomba)** | *JUALIN OS Core* | Orchestrator + Negotiator + Inventory + Growth + Finance + Pusat Komando + HITL + Laporan Harian |
| **Fase 2** | Crew lengkap & multimodal | Agen Layanan penuh, *voice note* & gambar (multimodal WA-native), auto-restock |
| **Fase 3** | Pembelajaran mandiri | *Reflection-driven tuning* + integrasi penuh modul Experiment (A/B otomatis taktik nego & pesan) |
| **Fase 4** | Ekosistem | *Marketplace playbook* antar-penjual, agen pengadaan/supplier, analitik lintas-toko |

---

## 12. Keunggulan Kompetitif, Risiko & Mitigasi

| Risiko | Mitigasi |
|---|---|
| LLM mengarang harga / jual rugi | **Angka dikontrol engine deterministik**, bukan LLM. Lantai margin tak bisa ditembus. |
| Otonomi salah ambil keputusan | **Human-in-the-loop** untuk aksi berisiko + audit + *kill switch* per agen (`agent_policies`). |
| Prompt-injection via chat/katalog | Data *untrusted* difilter & diaudit (sudah ada). |
| Biaya LLM | Model gratis/murah via 9Router; LLM hanya dipanggil saat perlu; embedding lokal. |
| Kompleksitas eksekusi | MVP dibangun **di atas infrastruktur yang sudah ada** (actions, jobs, worker, memory) — evolusi bertahap, bukan tulis ulang. |

---

## 13. Penutup

UMKM Indonesia tidak butuh chatbot yang sedikit lebih pintar menjawab. Mereka butuh **tenaga kerja** — yang menjual, menawar, menagih, menjaga stok, dan membukukan, tanpa lelah dan tanpa gaji bulanan. **JUALIN OS memberi setiap penjual mikro sebuah tim karyawan AI yang menjalankan tokonya** — dengan kendali penuh tetap di tangan manusia.

Kami tidak membangun fitur. Kami membangun **kategori**: *the operating system for autonomous micro-commerce*. Dan kami membangunnya di atas fondasi yang sudah berjalan, dengan kebaruan yang berakar pada riset, untuk pasar yang sudah terbukti besar.

**Tim Digiboom — JUALIN OS. Toko yang menjalankan dirinya sendiri.**

---

*Lampiran teknis (untuk implementasi): lihat `PLAN_JUALIN_OS_MVP.md` di root repositori — blueprint langkah-demi-langkah pembangunan MVP.*
