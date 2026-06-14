# PLAN PENULISAN PROPOSAL GEMASTIK — JUALIN OS (Divisi III)

> **Untuk agen pelaksana.** Tugasmu: **meng-upgrade isi proposal** dari "JUALIN.AI (asisten reaktif)" menjadi **"JUALIN OS (Sistem Operasi Toko Otonom / multi-agen)"**, sesuai **persis** aturan resmi GEMASTIK DIGINEXS 2026 Divisi III (Pengembangan Perangkat Lunak), dan dioptimalkan untuk **6 kriteria penilaian babak penyisihan**.
>
> **Kabar baik:** proposal **di-generate oleh skrip** `proposal_gemastik/build_proposal.py`. Skrip itu **sudah** mengatur semua format (Times New Roman 12, spasi 1.5, A4, margin kiri 4cm / kanan-atas-bawah 3cm) dan **12 section sesuai sistematika resmi**. **Kamu HANYA mengganti teks konten**, lalu jalankan skripnya. Format mustahil salah selama kamu tidak menyentuh kode format.
>
> **Kerjakan urut FASE 0 → FASE 8. Jangan melompat. Verifikasi tiap fase.**

---

## ATURAN EMAS (baca dulu, patuhi mutlak)

1. **JANGAN sentuh kode format/layout** di `build_proposal.py` (fungsi `build_docx`, `build_pdf`, `docx_add_*`, margin `Cm(...)`, `Pt(...)`, `line_spacing`). Itu sudah benar sesuai guidebook. Mengubahnya = risiko melanggar aturan format.
2. **Ubah HANYA konten** di dalam blok `add_section(...)` (baris ±361–551), variabel `refs` (±339–352), dan label node figur bila diminta.
3. **Pertahankan grammar block apa adanya.** Tipe block yang valid: `("p", "teks")`, `("table", [[...baris...]], [lebar_kolom_cm])`, `("bullets", ["item", ...])`, `("figure", str(asset_paths[i]), "Gambar n. caption")`, `("refs", refs)`. Jumlah kolom tiap baris tabel HARUS sama dengan jumlah lebar di list lebar.
4. **Bahasa Indonesia baku, jelas, padat.** Hindari kalimat berputar, klaim tanpa dasar, dan istilah Inggris berlebihan. Setiap klaim dampak harus ada angka + sumber.
5. **JANGAN mengarang data hasil.** Untuk validasi responden, isi dari hasil GForm **asli**. Jika belum ada, tulis sebagai *target/metodologi*, bukan hasil. (Guidebook menilai "Dampak" 20% dan melarang plagiarisme/data fiktif.)
6. **Branding (konsistensi kata):** nama platform tetap **JUALIN.AI**; edisi/positioning baru = **JUALIN OS — Sistem Operasi Toko Otonom**. Di Judul tulis **"JUALIN.AI (JUALIN OS)"**, selanjutnya rujuk lapisan multi-agen sebagai **"JUALIN OS"**. Jangan campur aduk istilah lain.
7. **Setelah edit, WAJIB jalankan** `python build_proposal.py` dari folder `proposal_gemastik/` dan pastikan DOCX + PDF ter-generate tanpa error.
8. **Jangan menambah/menghapus jumlah atau urutan section.** 12 section wajib sesuai guidebook sudah pas.

---

## FASE 0 — Kepatuhan WAJIB (checklist guidebook, jangan dilanggar)

Sumber: Guidebook GEMASTIK DIGINEXS 2026, bagian **C. Pengembangan Perangkat Lunak**.

| Aturan resmi | Nilai wajib | Status di `build_proposal.py` |
|---|---|---|
| Nama file PDF | `SoftwareDevelopment_Digiboom.pdf` | ✅ sudah (`PDF_PATH`, baris 33) — **jangan ubah** |
| Font | Times New Roman **12** | ✅ sudah (baris 696, 657) |
| Spasi baris | **1.5** | ✅ sudah (baris 705, 651) |
| Kertas | **A4** (21×29.7 cm) | ✅ sudah (baris 686–687) |
| Margin | kiri **4 cm**; kanan/atas/bawah **3 cm** | ✅ sudah (baris 688–691) |
| Sistematika | **12 section** urut (Judul → … → Lampiran) | ✅ sudah (baris 361–551) |
| Daftar Pustaka | **minimal 10**, tahun **2020–2025** | ✅ ada 12 — akan di-upgrade (Fase 6) |
| Hasil uji similaritas | dilampirkan, **≤ 20%** | ⚠️ harus dikerjakan manual (Fase 7) |
| Tema | "Digital Intelligence For Smart Society" | tulis eksplisit di Section 1 |
| SDGs | kontribusi ≥1 dari 17 SDGs | sebutkan SDG 8, 9, 1, 10 (Section 1) |
| Plagiarisme/SARA | dilarang | tulis konten orisinal |

> **Catatan timeline:** sesuai guidebook, pengumpulan karya 28 Mei–11 Juni 2026, finalis 15 Juni, pitching 18 Juni. Upgrade ini memperkuat **deck final/pitching** dan **berkas delegasi nasional** (juara otomatis didelegasikan ke GEMASTIK 2026 nasional dengan pembinaan). Jika penyisihan sudah dikumpulkan, gunakan versi ini untuk final & nasional.

**Verifikasi 0:** Buka `build_proposal.py`, konfirmasi baris 686–705 (format) tidak akan kamu sentuh. Lanjut.

---

## FASE 1 — Strategi skor (PETA: kriteria → section → yang ditonjolkan)

Babak penyisihan dinilai dari **6 kriteria** (Guidebook hal. 10). Optimalkan tiap section untuk kriteria ini:

| Kriteria | Bobot | Section utama | Yang HARUS ditonjolkan |
|---|---|---|---|
| **Aspek Inovasi** | **20%** | 1, 2, 6, 7 | Lompatan **Copilot → Autopilot**: multi-agen otonom + **negosiasi aman-margin** (belum ada kompetitor). Dasar riset (ReAct/Reflexion/LLM-bargaining). |
| **Dampak yang diharapkan** | **20%** | 2, 3, 12 | **Angka + sumber** (UMKM, chat-commerce) + **kerangka pengukuran** + **target validasi**. Dampak harus terukur & dibuktikan data. |
| **Desain antarmuka** | **20%** | 8, 9, 6 | Mockup/screenshot **AI Crew command center**, chat negosiasi, dashboard; mobile-first; HITL terlihat. |
| **Proses Pengembangan** | **20%** | 5, 7 | Agile + arsitektur multi-agen + guardrail + **savepoint transaksi** + CI/CD + feature flag + testing. |
| **Kesesuaian Ide** | **10%** | 1, 2 | Selaras tema "Digital Intelligence for Smart Society" + SDG 8/9/1/10 (UMKM). |
| **Urgensi Masalah** | **10%** | 2 | Beban 6-pekerjaan-sekaligus UMKM + data chat = kanal utama. |

**Prinsip:** Inovasi + Dampak + Antarmuka + Proses = **80%**. Investasikan kualitas terbaik di Section **1, 2, 6, 7, 8, 9**.

---

## FASE 2 — Bahan baku (fakta JUALIN OS + data + sumber) — JANGAN mengarang di luar ini

### 2A. Fakta produk (yang BENAR sudah dibangun — boleh diklaim "terimplementasi")
- **JUALIN OS = tim agen AI terkoordinasi** menjalankan toko UMKM: **Orchestrator (Manajer)** + **Pramuniaga (Sales)** + **Juru Tawar (Negotiator)** + **Gudang (Inventory)** + **Marketing (Growth)** + **Keuangan (Finance)** + **Layanan (CS)**.
- **Mesin Negosiasi aman-margin** (kebaruan inti): offer-generator **deterministik** menjamin harga **tak pernah** di bawah lantai `max(modal×(1+margin_floor), harga×(1−diskon_maks))`; LLM hanya merangkai kalimat. **Tervalidasi: 0 pelanggaran lantai di semua skenario.**
- **Human-in-the-loop (HITL):** aksi berisiko (diskon di atas ambang) masuk **antrean persetujuan** seller.
- **Transparansi & audit:** setiap tindakan agen tercatat di **Activity Feed** (`agent_runs`) + `audit_logs`; keputusan menyertakan *reason code*.
- **Proaktif:** worker `arq` menjalankan siklus inventory (deteksi stok menipis) & growth (tagih pembayaran tertunda, win-back) terjadwal.
- **Laporan Harian** otomatis dari Manajer AI (rekap omzet, pending, persetujuan, stok).
- **Robustness produksi:** integrasi agen dibungkus **savepoint transaksi** (`db.begin_nested()`) → kegagalan fitur tak pernah menjatuhkan chat utama; semua di-gate flag `ENABLE_AGENT_OS`.
- **Stack:** FastAPI + SQLAlchemy async + PostgreSQL 16 + **pgvector** + Redis + arq + Next.js 16 + Docker + Nginx + GitHub Actions CI (compile + pytest + lint + build).
- **Modul baru:** `models/agent_os.py` (4 tabel: AgentPolicy, AgentRun, AgentApproval, NegotiationState), `services/agent_os/*` (orchestrator, negotiation, inventory, finance, growth, brief, cycles), `api/routes_agent_os.py` (`/api/agent-os/*`), halaman `/dashboard/agent-os` (Pusat Komando AI Crew).

### 2B. Data pasar & dampak (PAKAI angka ini + cantumkan sumbernya)
| Fakta | Angka | Sumber (untuk sitasi) |
|---|---|---|
| UMKM = mayoritas usaha Indonesia, kontribusi PDB | ±60–61% PDB, serap ±97% tenaga kerja | Kementerian Koperasi & UKM RI / Kadin |
| Pelaku e-commerce Indonesia | ±4,4 juta (2024), **mayoritas jual via instant messaging/chat** | BPS, Statistik E-Commerce 2024 |
| Penetrasi WhatsApp | ±65% pengguna ponsel | laporan industri (Infobip) |
| UMKM pakai alat digital (2025) | ±63% | riset pasar UMKM digital |
| WA sebagai kanal utama → pertumbuhan omzet | **2,4× lebih tinggi** | laporan WhatsApp Business |
| Agentic commerce → kenaikan konversi | **+20–30%**; pasar **US$50B+** pada 2030 | eMarketer / Bain (2025/2026) |

### 2C. Kerangka pengukuran dampak (untuk Section 3 & 12 — "Dampak 20%")
Metrik yang **diukur produk** (sudah ada fondasi `daily_seller_metrics`, atribusi order):
1. **Waktu operasional dihemat** (jam/hari, dari jumlah aktivitas agen otonom).
2. **Omzet di-assist AI** & **omzet diselamatkan** (pembayaran tertunda yang berhasil ditagih).
3. **Konversi chat → order** (sebelum vs sesudah).
4. **Jumlah & nilai deal nego ditutup dalam batas margin** (tanpa satu pun jual-rugi).
Target validasi (kuesioner): **minat coba rata-rata ≥4/5**, **≥70% bersedia membayar**, **SUS >75**.

---

## FASE 3 — Update Section 1 (Judul) — paste menggantikan blok baris 361–381

Ganti seluruh `add_section("1. Judul/Nama Perangkat Lunak", [...])` dengan:

```python
add_section("1. Judul/Nama Perangkat Lunak", [
    ("p", "Nama perangkat lunak yang diusulkan adalah JUALIN.AI (JUALIN OS), sebuah Sistem Operasi Toko Otonom (Autonomous Store Operating System) untuk UMKM mikro. Berbeda dari chatbot layanan yang hanya menjawab chat, JUALIN OS adalah tim agen kecerdasan buatan terspesialisasi yang menjalankan operasional toko secara otonom dan terkoordinasi: melayani percakapan, menawar harga secara aman, menjaga stok, menagih pembayaran, dan menyusun laporan harian, dengan kendali penuh tetap di tangan penjual. Produk ini dikembangkan untuk Divisi III Pengembangan Perangkat Lunak GEMASTIK DIGINEXS 2026 dengan tema Digital Intelligence For Smart Society."),
    ("table", [
        ["Aspek", "Rincian"],
        ["Nama produk", "JUALIN.AI — edisi JUALIN OS (Sistem Operasi Toko Otonom)"],
        ["Tagline", "Tim karyawan AI yang menjalankan toko UMKM: menjual, menawar, menjaga stok, menagih, dan membukukan secara otonom dan terkendali"],
        ["Target pengguna", "Pelaku UMKM mikro yang berjualan melalui WhatsApp, Instagram, storefront, atau marketplace sosial"],
        ["Kebaruan inti", "Arsitektur multi-agen (Manajer + 6 agen spesialis) dan mesin negosiasi aman-margin yang dijamin tidak pernah menjual di bawah batas untung"],
        ["Kontribusi SDGs", "SDG 8 Decent Work and Economic Growth, SDG 9 Industry Innovation and Infrastructure, SDG 1 No Poverty, SDG 10 Reduced Inequality"],
        ["Status prototipe", "Aplikasi web full-stack operasional: Next.js, FastAPI, PostgreSQL pgvector, Redis, worker arq, Docker, dengan modul multi-agen (services/agent_os) dan dashboard AI Crew"],
    ], [3.6, 9.6]),
    ("p", "Inti gagasan JUALIN OS adalah memindahkan UMKM dari AI Copilot (sekadar membantu menjawab) ke AI Autopilot (menjalankan operasi). Sebuah Orchestrator merutekan setiap peristiwa, mesin negosiasi deterministik menjaga margin, dan setiap tindakan agen tercatat serta dapat disetujui atau ditolak penjual. Dengan demikian otomasi menjadi lebih berdampak sekaligus tetap dapat dipercaya."),
    ("table", [
        ["Kriteria penyisihan", "Respons dalam proposal"],
        ["Aspek inovasi 20%", "Lompatan kategori dari chatbot reaktif menjadi sistem multi-agen otonom dengan negosiasi aman-margin; berakar pada riset ReAct, Reflexion, dan LLM bargaining."],
        ["Dampak 20%", "Dampak terukur: waktu operasional dihemat, omzet di-assist AI, omzet diselamatkan, dan deal nego tertutup tanpa jual-rugi; divalidasi melalui kuesioner 30 responden asli."],
        ["Desain antarmuka 20%", "Pusat Komando AI Crew menampilkan status tiap agen, activity feed, antrean persetujuan, dan laporan harian; mobile-first untuk seller dan chat untuk customer."],
        ["Proses pengembangan 20%", "Agile prototyping, arsitektur multi-agen modular, guardrail deterministik, savepoint transaksi, feature flag, dan CI/CD GitHub Actions."],
        ["Kesesuaian ide 10%", "Selaras tema smart society: memberdayakan jutaan UMKM dengan kecerdasan digital yang inklusif."],
        ["Urgensi masalah 10%", "Penjual mikro menanggung enam pekerjaan sekaligus di kanal chat yang tidak pernah berhenti."],
    ], [3.5, 9.7]),
])
```

---

## FASE 4 — Update Section 2 & 3 (Latar Belakang, Tujuan & Manfaat)

### 4A. Section 2 — ganti blok baris 383–395:
```python
add_section("2. Latar Belakang Ide Perangkat Lunak", [
    ("p", "UMKM adalah tulang punggung ekonomi Indonesia, menyumbang sekitar 60 persen PDB dan menyerap sekitar 97 persen tenaga kerja (Kementerian Koperasi dan UKM). Mayoritas dari sekitar 4,4 juta pelaku e-commerce nasional berjualan melalui pesan instan, bukan etalase marketplace (Badan Pusat Statistik, 2024). Artinya, medan transaksi UMKM sesungguhnya adalah kotak chat, dan di sanalah penjual mikro paling kewalahan."),
    ("p", "Seorang penjual mikro menanggung enam pekerjaan sekaligus dan sendirian: membalas chat 24 jam, melayani tawar-menawar, menagih pembayaran yang tertunda, menjaga stok agar tidak salah janji, menyapa kembali pelanggan lama, dan mencatat pembukuan. Setiap beban itu adalah pekerjaan satu orang. Akibatnya peluang closing hilang bukan karena produk tidak menarik, melainkan karena respons dan proses penjualan tidak konsisten."),
    ("table", [
        ["Beban penjual (6 pekerjaan)", "Dampak bila tak tertangani", "Agen JUALIN OS yang menangani"],
        ["Balas chat 24 jam", "Telat balas, pembeli pindah ke toko lain", "Pramuniaga (Sales) berbasis katalog"],
        ["Tawar-menawar harga", "Salah hitung, jual rugi", "Juru Tawar (Negotiator) aman-margin"],
        ["Tagih pembayaran tertunda", "Omzet menguap", "Marketing (Growth) proaktif"],
        ["Jaga stok / cegah oversell", "Janji palsu, komplain", "Gudang (Inventory)"],
        ["Pembukuan harian", "Tidak tahu performa toko", "Keuangan (Finance) + Laporan Harian"],
        ["Kendali & kepercayaan", "Takut AI salah ambil keputusan", "Manajer (Orchestrator) + persetujuan manusia"],
    ], [3.4, 4.6, 5.2]),
    ("p", "Solusi yang sudah ada di pasar (chatbot customer service dan bot open-source) bersifat reaktif: menunggu pesan lalu menjawab. Tidak ada yang berinisiatif menagih, menawar, atau menyapa kembali, dan hampir tidak ada yang berani menego harga secara otomatis karena risiko jual-rugi. Padahal tawar-menawar adalah inti budaya dagang Indonesia. Di sinilah celah JUALIN OS: agen otonom sisi penjual yang menutup seluruh siklus penjualan, termasuk negosiasi yang aman."),
    ("p", "Tren global memperkuat arah ini. Agentic commerce diproyeksikan menaikkan konversi 20 hingga 30 persen dan menjadi pasar di atas 50 miliar dolar AS pada 2030 (eMarketer, 2025), namun kapabilitasnya masih menumpuk di sisi pembeli dan bagian atas funnel. Sisi penjual dan tahap closing-bayar-retensi masih kosong, dan JUALIN OS mengisinya untuk konteks UMKM Indonesia."),
])
```

### 4B. Section 3 — ganti blok baris 397–413:
```python
add_section("3. Tujuan dan Manfaat Dikembangkan Perangkat Lunak", [
    ("p", "Tujuan utama JUALIN OS adalah memberi UMKM mikro sebuah tim agen AI yang menjalankan operasional toko secara otonom namun tetap dikendalikan penjual, sehingga penjual dapat melayani lebih banyak pembeli, menutup lebih banyak order, dan tidak kehilangan omzet karena keterbatasan waktu."),
    ("bullets", [
        "Menyediakan agen Pramuniaga yang menjawab pertanyaan customer berdasarkan katalog, harga, stok, dan kebijakan toko.",
        "Menyediakan agen Juru Tawar yang menanggapi tawar-menawar dengan penawaran yang dijamin tidak pernah di bawah batas margin penjual.",
        "Menjalankan agen Marketing dan Keuangan secara proaktif untuk menagih pembayaran tertunda, menyapa pelanggan pasif, dan menyusun laporan harian.",
        "Menjaga kepercayaan melalui human-in-the-loop, activity feed yang transparan, audit log, dan kendali kebijakan per penjual.",
        "Mengukur dampak nyata: waktu operasional dihemat, omzet di-assist AI, omzet diselamatkan, dan konversi chat ke order.",
    ]),
    ("table", [
        ["Pihak", "Manfaat"],
        ["UMKM/seller", "Beban enam pekerjaan terbantu otomatis, respons instan, negosiasi aman, penagihan tidak terlewat, dan laporan harian otomatis, tanpa menambah karyawan."],
        ["Customer", "Dilayani cepat 24 jam, mendapat penawaran tawar-menawar yang wajar, dan proses order yang jelas."],
        ["Perguruan tinggi & ekosistem", "Bukti karya software bernilai tinggi yang menerapkan AI agentik secara bertanggung jawab pada masalah ekonomi digital lokal."],
        ["Masyarakat (SDGs)", "Mendorong pertumbuhan ekonomi inklusif (SDG 8), inovasi infrastruktur digital (SDG 9), dan pengurangan ketimpangan akses teknologi (SDG 1 dan 10)."],
    ], [3.0, 10.2]),
    ("p", "Dampak ditargetkan terukur, bukan sekadar argumentasi. Indikator keberhasilan awal: penghematan waktu operasional penjual, peningkatan konversi chat ke order, nilai pembayaran tertunda yang berhasil diselamatkan, serta jumlah deal negosiasi yang tertutup tanpa satu pun transaksi di bawah batas margin."),
])
```

---

## FASE 5 — Update Section 4–7 (Batasan, Metodologi, Analisis & Desain, Implementasi)

### 5A. Section 4 (Batasan) — ganti blok baris 415–425:
```python
add_section("4. Batasan Perangkat Lunak yang Dikembangkan", [
    ("p", "Batasan dibuat agar prototipe tetap realistis, aman, dan dapat diuji dalam waktu kompetisi. JUALIN OS diposisikan sebagai tim agen operasional, bukan pengganti seluruh keputusan strategis penjual. Penjual selalu memegang kendali tertinggi."),
    ("bullets", [
        "Setiap agen hanya bertindak berdasarkan data katalog, kebijakan, dan konfigurasi penjual yang tersedia di sistem.",
        "Negosiasi dibatasi mesin deterministik: harga tidak pernah menembus lantai margin, dan diskon di atas ambang wajib disetujui penjual (human-in-the-loop).",
        "Aksi berisiko (refund, broadcast, diskon besar) tidak dieksekusi otomatis tanpa persetujuan; seluruh fitur otonom dapat dimatikan melalui kebijakan dan feature flag.",
        "Integrasi WhatsApp Cloud, Midtrans, dan Cashi.id bersifat plugin; bila credential belum ada, sistem tetap berjalan melalui chat publik demo.",
        "Prototipe tidak menangani logistik lintas ekspedisi yang kompleks; ongkir mengikuti kebijakan toko.",
        "Sistem tidak memberi nasihat hukum, medis, atau finansial di luar transaksi jual-beli toko.",
        "Validasi memakai jawaban asli dari GForm; data simulasi hanya untuk menguji format rekap, bukan sebagai bukti penelitian.",
    ]),
])
```

### 5B. Section 5 (Metodologi) — ganti blok baris 427–438:
```python
add_section("5. Metodologi Pengembangan Perangkat Lunak", [
    ("p", "Metodologi yang digunakan adalah agile prototyping dengan tahap discovery, design, build, test, dan validate. Pendekatan ini dipilih karena produk perlu cepat diuji pada skenario chat penjualan nyata, namun tetap menuntut kontrol kualitas tinggi pada keamanan, guardrail negosiasi, dan isolasi multi-tenant. Fitur berisiko dibangun di belakang feature flag dan diintegrasikan secara bertahap (evolusi, bukan penulisan ulang)."),
    ("table", [
        ["Tahap", "Aktivitas", "Output"],
        ["Discovery", "Memetakan enam beban penjual UMKM dan riset referensi agen AI serta negosiasi LLM.", "Problem statement, persona, dan metrik dampak."],
        ["Design", "Merancang arsitektur multi-agen (Orchestrator dan agen spesialis), mesin negosiasi deterministik, dan antarmuka AI Crew.", "Diagram arsitektur, desain solusi, dan mockup."],
        ["Build", "Mengembangkan modul services/agent_os, tabel agent_os, API agent-os, dashboard AI Crew, dan worker proaktif di atas basis kode existing.", "Prototipe multi-agen yang dapat dijalankan."],
        ["Test", "Menjalankan compile check, validasi mesin negosiasi (jaminan harga di atas lantai margin), dan pengujian guardrail/keamanan via CI.", "Bukti verifikasi teknis."],
        ["Validate", "Mengumpulkan respons 30 responden asli melalui GForm dan menguji demo pada calon penjual/pembeli.", "Rekap minat, keberatan, dan prioritas fitur."],
    ], [2.2, 6.1, 4.9]),
    ("p", "Verifikasi teknis yang telah dilakukan mencakup kompilasi seluruh modul backend (compileall) dan validasi matematis mesin negosiasi yang menunjukkan nol pelanggaran lantai margin pada seluruh skenario dan ronde uji. Pipeline CI GitHub Actions dikonfigurasi menjalankan pytest, audit dependensi, lint, dan build frontend pada setiap perubahan, sehingga kualitas terjaga otomatis sebelum deploy."),
])
```

### 5C. Section 6 (Analisis Kebutuhan & Desain Solusi) — ganti blok baris 440–462:
```python
add_section("6. Analisis Kebutuhan dan Desain Solusi Perangkat Lunak", [
    ("p", "Aktor utama sistem adalah seller, customer, dan admin. Yang membedakan JUALIN OS adalah lapisan agen otonom di antara mereka: sebuah Orchestrator yang merutekan setiap peristiwa (chat masuk, pembayaran, perubahan stok, dan tick terjadwal) ke agen spesialis yang tepat, lalu mencatat tindakannya untuk diaudit dan, bila berisiko, dimintakan persetujuan penjual."),
    ("table", [
        ["Agen (peran)", "Tanggung jawab otonom"],
        ["Orchestrator (Manajer)", "Merutekan peristiwa ke agen, menjaga kebijakan global, dan menyusun Laporan Harian."],
        ["Sales (Pramuniaga)", "Melayani percakapan berbasis katalog: sapa, gali kebutuhan, presentasi, dan closing."],
        ["Negotiator (Juru Tawar)", "Menanggapi tawar-menawar dengan penawaran yang dijamin tidak pernah di bawah lantai margin."],
        ["Inventory (Gudang)", "Memverifikasi stok sebelum janji/order dan mendeteksi stok menipis."],
        ["Growth (Marketing)", "Menagih pembayaran tertunda dan menyapa kembali pelanggan pasif secara proaktif."],
        ["Finance (Keuangan)", "Merekap omzet, pembayaran lunas vs tertunda, dan produk terlaris."],
    ], [3.4, 9.8]),
    ("figure", str(asset_paths[0]), "Gambar 1. Arsitektur multi-agen JUALIN OS."),
    ("figure", str(asset_paths[1]), "Gambar 2. Alur penggunaan dan dampak yang diukur."),
    ("p", "Kebaruan teknis terpenting adalah pemisahan ANGKA dari KATA pada negosiasi. Sebuah offer-generator deterministik menghitung penawaran balik memakai concession ladder yang dibatasi lantai harga, yaitu nilai terbesar antara modal dikali satu tambah margin minimum dan harga dikali satu kurang diskon maksimum. Large Language Model hanya merangkai kalimat di sekitar angka yang sudah diputuskan engine, sehingga AI tidak mungkin mengarang harga atau menjual rugi. Pendekatan ini sejalan dengan temuan riset bargaining LLM bahwa agen membutuhkan offer-generator untuk mengontrol rentang harga."),
    ("table", [
        ["Modul", "Desain solusi"],
        ["Mesin negosiasi", "Engine deterministik menjaga lantai margin; LLM hanya untuk bahasa; diskon di atas ambang masuk antrean persetujuan."],
        ["Memori dan state", "Customer memory berbasis pgvector untuk personalisasi; negotiation_states menyimpan konteks tawar berjalan."],
        ["Substrat peristiwa", "background_jobs dan worker arq untuk kerja proaktif; audit_logs dan agent_runs untuk jejak yang dapat diaudit."],
        ["Kendali manusia", "agent_policies (kill switch per agen, ambang diskon) dan agent_approvals (antrean human-in-the-loop)."],
        ["Ketahanan", "Setiap pemanggilan agen dibungkus savepoint transaksi sehingga kegagalan agen tidak menjatuhkan chat utama."],
        ["Observability", "AI trace, usage event, dan provider health untuk pengawasan operasional."],
    ], [3.0, 10.2]),
])
```

### 5D. Section 7 (Implementasi) — ganti blok baris 464–488:
> **Catatan angka:** angka endpoint/model/halaman bertambah setelah modul JUALIN OS. Untuk angka akurat, jalankan di root repo:
> `(git ls-files "backend/**/*.py").Count` dan hitung manual, atau gunakan deskripsi kualitatif. Aman memakai frasa "lebih dari".
```python
add_section("7. Implementasi Perangkat Lunak", [
    ("p", "Implementasi JUALIN OS berbentuk aplikasi web full-stack yang dapat dijalankan, dibangun secara bertahap di atas basis kode JUALIN.AI. Lapisan multi-agen ditambahkan melalui modul models/agent_os.py (empat tabel: AgentPolicy, AgentRun, AgentApproval, NegotiationState), paket services/agent_os (orchestrator, negotiation, inventory, finance, growth, brief, cycles), API routes_agent_os.py pada prefiks /api/agent-os, worker terjadwal, dan halaman dashboard AI Crew. Seluruh fitur baru di-gate oleh feature flag ENABLE_AGENT_OS sehingga aman terhadap perilaku lama."),
    ("table", [
        ["Layer", "Teknologi", "Alasan pemilihan"],
        ["Frontend", "Next.js 16, React, CSS Modules", "Cepat untuk dashboard dan chat publik, mobile-first."],
        ["Backend", "FastAPI, Pydantic, SQLAlchemy async", "API modular, validasi jelas, cocok untuk orkestrasi agen."],
        ["Database", "PostgreSQL 16 + pgvector", "Data relasional kuat plus pencarian semantik katalog pada satu basis data."],
        ["Cache/worker", "Redis 7 + arq", "Rate limit, cache, dan kerja proaktif agen yang terjadwal dan hemat."],
        ["AI", "LLM via endpoint OpenAI-compatible, embedding all-MiniLM-L6-v2, guardrails + engine deterministik", "Respons natural dengan angka harga dikontrol engine, biaya pengembangan rendah."],
        ["Deployment", "Docker Compose, Nginx, GitHub Actions CI", "Replikasi mudah pada VPS dengan pengujian otomatis sebelum deploy."],
    ], [2.4, 4.2, 6.6]),
    ("p", "Selain modul agen, codebase mencerminkan fitur autentikasi JWT, CRUD produk, chat AI dan streaming, order, payment, analytics, inbox, campaigns, workflows, billing, storefront, trust profile, growth links, referrals, knowledge base, QA review, experiments, serta admin dashboard. Lapisan JUALIN OS menyatukannya menjadi operasi toko yang otonom dan terkendali."),
    ("bullets", [
        "Keamanan: validasi keamanan produksi, rate limiting, CORS, request logging, JWT, sanitasi upload, validasi signature webhook, dan filter seller_id pada route penting.",
        "Kualitas dan keamanan AI: tujuh guardrail, untrusted data policy anti prompt-injection, mesin negosiasi deterministik aman-margin, dan trace untuk evaluasi.",
        "Keandalan: idempotency key, background job dengan retry, savepoint transaksi pada lapisan agen, dan endpoint health/readiness.",
        "Tata kelola otonomi: agent_policies untuk kebijakan per penjual, agent_approvals untuk persetujuan manusia, dan agent_runs untuk activity feed yang dapat diaudit.",
    ]),
    ("table", [
        ["Verifikasi", "Hasil"],
        ["compileall backend", "Berhasil; seluruh modul backend (termasuk services/agent_os) lolos kompilasi."],
        ["Validasi mesin negosiasi", "Nol pelanggaran lantai margin pada seluruh skenario dan ronde uji."],
        ["CI GitHub Actions", "Dikonfigurasi menjalankan pytest, audit dependensi, lint, dan build frontend pada setiap perubahan."],
    ], [5.0, 8.2]),
])
```

---

## FASE 6 — Update Section 8 & 9 (Antarmuka & Cara Penggunaan) — "Desain antarmuka 20%"

### 6A. Figur — perkuat tampilan multi-agen (pilih salah satu)

**Opsi A (DIREKOMENDASIKAN): screenshot asli dari aplikasi berjalan.** Karena guidebook menuntut produk "bisa dioperasikan", screenshot nyata lebih bernilai daripada mockup. Setelah deploy/run:
1. Tangkap layar `/dashboard/agent-os` (Pusat Komando AI Crew: kartu 7 agen, activity feed, laporan harian, antrean persetujuan).
2. Tangkap layar chat negosiasi (`/chat/<slug>`) yang menampilkan AI menawar balik.
3. Tangkap layar dashboard order/analytics.
Simpan ke `proposal_gemastik/assets/` (mis. `shot_aicrew.png`, `shot_nego.png`, `shot_dashboard.png`), lalu pada Section 8 ganti `str(asset_paths[2..4])` menjadi `str(ASSETS / "shot_aicrew.png")` dst.

**Opsi B (fallback, tanpa run): perbarui label diagram arsitektur** agar mencerminkan multi-agen. Di fungsi `create_architecture()` (sekitar baris 97–105), ganti `nodes = [...]` menjadi:
```python
    nodes = [
        (90, 190, 420, 350, "Customer", "Chat publik / WhatsApp / link katalog", BLUE),
        (520, 190, 850, 350, "Orchestrator (Manajer AI)", "Merutekan peristiwa ke agen, kebijakan, laporan harian", PURPLE),
        (950, 190, 1280, 350, "Juru Tawar (Negotiator)", "Mesin nego deterministik, lantai margin, persetujuan", ORANGE),
        (520, 460, 850, 620, "Sales / Inventory / Growth / Finance", "Pramuniaga, Gudang, Marketing, Keuangan, Layanan", GREEN),
        (90, 700, 420, 860, "PostgreSQL + pgvector", "Katalog, order, agent_runs, negotiation_states, memori", "#1D4ED8"),
        (520, 700, 850, 860, "Redis + arq worker", "Cache, rate limit, siklus proaktif terjadwal", "#DC2626"),
        (950, 700, 1280, 860, "Guardrails + HITL + Audit", "Margin floor, anti prompt-injection, approval, audit log", "#0F766E"),
    ]
```
Dan ganti judul figur baris 95 menjadi `"Arsitektur Multi-Agen JUALIN OS"`. Caption Section 6 & 8 sudah diperbarui di Fase 5/6.

### 6B. Section 8 — ganti blok baris 490–495:
```python
add_section("8. Screenshot Mockup Interface Perangkat Lunak", [
    ("p", "Antarmuka dirancang familiar untuk UMKM sekaligus menampilkan kendali atas tim agen. Pusat Komando AI Crew menampilkan status tiap agen, activity feed langsung, antrean persetujuan, dan laporan harian, sehingga penjual selalu tahu apa yang dilakukan AI dan dapat menyetujui atau menolak keputusan berisiko."),
    ("figure", str(asset_paths[2]), "Gambar 3. Mockup chat customer dengan negosiasi aman-margin."),
    ("figure", str(asset_paths[3]), "Gambar 4. Mockup Pusat Komando AI Crew (status agen, activity feed, persetujuan)."),
    ("figure", str(asset_paths[4]), "Gambar 5. Mockup laporan harian dan dashboard keuangan."),
])
```
> Jika memakai Opsi A, ganti tiga `str(asset_paths[...])` di atas dengan path screenshot asli. Jika tetap Opsi B, biarkan asset_paths apa adanya (caption sudah disesuaikan).

### 6C. Section 9 (Cara Penggunaan) — ganti blok baris 497–518:
```python
add_section("9. Dokumentasi Cara Penggunaan Perangkat Lunak", [
    ("p", "Penggunaan dibagi dua alur: penjual sebagai pemilik toko dan customer sebagai pembeli. Dokumentasi ini juga menjadi dasar video demo maksimal tiga menit pada babak final."),
    ("table", [
        ["Langkah seller", "Deskripsi"],
        ["1. Registrasi dan setup", "Membuat akun toko, mengisi katalog dan modal produk (untuk batas margin), serta memilih gaya AI."],
        ["2. Atur kebijakan agen", "Menyetel kebijakan di Pusat Komando AI Crew: diskon maksimum, margin minimum, dan ambang persetujuan."],
        ["3. Aktifkan AI Crew", "Tim agen mulai melayani chat, menawar, menjaga stok, dan menagih secara otonom."],
        ["4. Pantau activity feed", "Melihat tindakan tiap agen secara langsung beserta alasan keputusan."],
        ["5. Setujui keputusan berisiko", "Menyetujui atau menolak diskon besar dan aksi sensitif dari antrean persetujuan."],
        ["6. Baca Laporan Harian", "Menerima ringkasan omzet, pembayaran tertunda, stok menipis, dan saran tindakan."],
    ], [3.2, 10.0]),
    ("table", [
        ["Langkah customer", "Deskripsi"],
        ["1. Buka link chat", "Customer membuka chat publik toko tanpa login."],
        ["2. Tanya dan menawar", "Customer menanyakan produk, harga, atau menawar; Juru Tawar menanggapi dengan penawaran aman-margin."],
        ["3. Konfirmasi order", "Customer menyetujui detail item, jumlah, dan data pengiriman."],
        ["4. Bayar", "Customer membuka link pembayaran resmi dan memilih QRIS/VA bila gateway aktif."],
        ["5. Tindak lanjut", "Bila belum bayar, agen Marketing menindaklanjuti sesuai aturan yang diaudit."],
    ], [3.2, 10.0]),
    ("p", "Skenario demo yang disarankan: penjual mengatur kebijakan, customer menawar Dress Emerald seharga 150 ribu (di bawah margin), Juru Tawar menawar balik di harga aman, customer setuju, Pramuniaga membuat order dan link pembayaran, lalu penjual melihat jejak ketiga agen pada activity feed dan menerima laporan harian."),
])
```

---

## FASE 7 — Update Daftar Pustaka (Section 11) + Lampiran similaritas

### 7A. Ganti variabel `refs` (baris 339–352) dengan daftar berikut (≥10, semua 2020–2025):
```python
refs = [
    "Yao, S., Zhao, J., Yu, D., Du, N., Shafran, I., Narasimhan, K., & Cao, Y. (2023). ReAct: Synergizing Reasoning and Acting in Language Models. ICLR 2023. https://arxiv.org/abs/2210.03629",
    "Shinn, N., Cassano, F., Gopinath, A., Narasimhan, K., & Yao, S. (2023). Reflexion: Language Agents with Verbal Reinforcement Learning. NeurIPS 2023. https://arxiv.org/abs/2303.11366",
    "Xia, T., et al. (2024). Measuring Bargaining Abilities of Large Language Models: A Benchmark and a Buyer-Enhancement Method. ACL Findings 2024. https://arxiv.org/abs/2402.15813",
    "Bianchi, F., et al. (2024). How Well Can LLMs Negotiate? NegotiationArena Platform and Analysis. https://arxiv.org/abs/2402.05863",
    "Wang, L., et al. (2024). A Survey on Large Language Model based Autonomous Agents. Frontiers of Computer Science, 18(6). https://doi.org/10.1007/s11704-024-40231-1",
    "Lewis, P., Perez, E., Piktus, A., et al. (2020). Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. NeurIPS 2020. https://arxiv.org/abs/2005.11401",
    "Badan Pusat Statistik. (2024). Statistik E-Commerce 2024. Jakarta: BPS. https://www.bps.go.id/",
    "Google, Temasek, & Bain & Company. (2024). e-Conomy SEA 2024. https://economysea.withgoogle.com/",
    "Kementerian Koperasi dan UKM Republik Indonesia. (2023). Perkembangan Data Usaha Mikro, Kecil, dan Menengah. https://kemenkopukm.go.id/",
    "Bank Indonesia. (2024). Laporan Perkembangan Ekonomi dan Keuangan Digital serta QRIS. https://www.bi.go.id/",
    "NIST. (2023). Artificial Intelligence Risk Management Framework (AI RMF 1.0). https://www.nist.gov/itl/ai-risk-management-framework",
    "International Organization for Standardization. (2023). ISO/IEC 25010: Systems and software quality models. https://www.iso.org/standard/78176.html",
    "pgvector Contributors. (2024). pgvector: Open-source vector similarity search for PostgreSQL. https://github.com/pgvector/pgvector",
]
```
> 13 referensi, semuanya 2020–2025, mencampur dasar akademik agen AI (inovasi), data ekonomi UMKM Indonesia (urgensi/dampak), dan standar tata kelola (proses). Memenuhi syarat "minimal 10, tahun 2020–2025".

### 7B. Section 12 (Lampiran) — perbarui Lampiran C (similaritas) menjadi instruksi tindakan:
Pada blok Section 12 (baris 527–551), bagian Lampiran C, pastikan kalimatnya menyebut bahwa hasil uji Turnitin/iThenticate **≤20%** WAJIB dilampirkan sebelum submit final. Biarkan Lampiran A & B (kuesioner validasi) apa adanya, tetapi pastikan teksnya menegaskan **data harus dari responden asli**.

> **Tindakan manual di luar skrip (WAJIB sebelum submit):** jalankan proposal PDF melalui Turnitin/iThenticate; jika >20%, parafrase bagian yang tinggi (terutama definisi umum); lampirkan halaman hasil similaritas ke PDF final (bisa di-merge setelah build).

---

## FASE 8 — Build, verifikasi, dan QA akhir

### 8A. Generate ulang proposal
```powershell
cd "C:\Romadhon Data penting\Downloads\YT DON\Lomba Gemastik\jualin-ai\proposal_gemastik"
# pakai Python yang punya python-docx, reportlab, openpyxl, Pillow (cek dulu)
python -c "import docx, reportlab, openpyxl, PIL; print('deps OK')"
python build_proposal.py
```
**Output yang harus muncul** (di folder `proposal_gemastik/`):
- `SoftwareDevelopment_Digiboom.pdf`  ← berkas WAJIB submit (nama TIDAK boleh diubah)
- `Proposal_SoftwareDevelopment_Digiboom_JUALIN_AI.docx`
- `Template_Kuesioner_Validasi_JUALIN_AI.xlsx`
- figur di `assets/`

> Jika `import docx`/`reportlab` gagal: `pip install python-docx reportlab openpyxl Pillow`.

### 8B. Checklist QA akhir (centang semua sebelum submit)
- [ ] Nama file PDF **persis** `SoftwareDevelopment_Digiboom.pdf`.
- [ ] Buka PDF: font Times New Roman, terlihat spasi 1.5, ukuran A4, margin kiri lebih lebar (4cm).
- [ ] **12 section** lengkap dan **urut** sesuai guidebook (Judul → … → Lampiran).
- [ ] Daftar Pustaka **≥10** entri, **semua 2020–2025**.
- [ ] Setiap klaim dampak ada **angka + sumber**; tidak ada data hasil fiktif.
- [ ] Penyebutan produk konsisten: **"JUALIN.AI (JUALIN OS)"** lalu "JUALIN OS".
- [ ] Tema "Digital Intelligence For Smart Society" dan SDG disebut eksplisit (Section 1).
- [ ] Tidak ada tabel yang jumlah kolomnya tidak cocok dengan jumlah lebar kolom (kalau salah, skrip error saat build).
- [ ] Figur tampil benar (arsitektur multi-agen / screenshot AI Crew).
- [ ] **Hasil uji similaritas ≤20% dilampirkan** (tindakan manual, Fase 7B).
- [ ] Tidak ada unsur SARA/asusila/plagiarisme.

### 8C. Verifikasi build tidak error
Jika `python build_proposal.py` berhenti dengan error:
- **IndexError/ValueError pada tabel** → ada baris tabel yang jumlah selnya ≠ jumlah lebar kolom. Perbaiki agar konsisten.
- **Font error (TNR/times.ttf not found)** → jalankan di Windows (font Times New Roman ada di `C:\Windows\Fonts`). Skrip sudah menunjuk ke sana (baris 63–65).
- **Module not found** → install dependensi (8A).

---

## LAMPIRAN — Do's & Don'ts bahasa (struktur kata)

**DO:**
- Kalimat aktif, padat, satu gagasan per kalimat.
- Selalu sandingkan klaim dengan angka/sumber ("menyumbang sekitar 60 persen PDB (Kemenkop UKM)").
- Konsisten istilah: "agen", "Orchestrator/Manajer", "Juru Tawar/Negotiator", "lantai margin", "human-in-the-loop".
- Tonjolkan kata kunci kriteria juri: **inovasi, dampak terukur, antarmuka, proses pengembangan, kesesuaian, urgensi**.

**DON'T:**
- Jangan menulis simbol "%", ">", "<" di dalam teks paragraf `("p", ...)` yang dirender PDF bila bisa diganti kata ("persen", "lebih dari", "di bawah") — lebih aman terhadap parser dan lebih rapi. (Di dalam tabel tetap boleh.)
- Jangan klaim "sudah diuji ribuan pengguna" atau hasil yang belum ada.
- Jangan ganti nama file output atau struktur 12 section.
- Jangan menyalin definisi mentah dari internet (risiko similaritas >20%); parafrase dengan kata sendiri.
- Jangan memakai istilah Inggris bila ada padanan Indonesia yang umum.

---

*Dokumen ini melengkapi `PROPOSAL_JUALIN_OS_2026.md` (narasi) dan `PLAN_JUALIN_OS_MVP.md` (teknis). Kerjakan Fase 0→8 berurutan; format proposal sudah dijamin patuh oleh `build_proposal.py`. Selamat menulis. 🏆*
