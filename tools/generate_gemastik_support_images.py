from __future__ import annotations

from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFont


OUT = Path("proposal_gemastik/gambar_pendukung")
W, H = 1600, 1000

BG = "#F7FAFC"
INK = "#102033"
MUTED = "#5B6B7F"
TEAL = "#0F766E"
TEAL_DARK = "#115E59"
BLUE = "#2563EB"
BLUE_DARK = "#1E3A8A"
GREEN = "#16A34A"
ORANGE = "#EA580C"
RED = "#DC2626"
YELLOW = "#F59E0B"
CARD = "#FFFFFF"
BORDER = "#D8E1EA"
LIGHT_TEAL = "#DDF7F2"
LIGHT_BLUE = "#E7F0FF"
LIGHT_GREEN = "#EAF8EF"
LIGHT_ORANGE = "#FFF1E7"
LIGHT_RED = "#FEECEC"


def font(size: int, bold: bool = False):
    candidates = [
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/calibrib.ttf" if bold else "C:/Windows/Fonts/calibri.ttf"),
    ]
    for p in candidates:
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


F_TITLE = font(48, True)
F_SUB = font(25)
F_H2 = font(30, True)
F_H3 = font(23, True)
F_BODY = font(21)
F_SMALL = font(17)
F_TINY = font(14)


def rounded(draw, xy, radius=24, fill=CARD, outline=BORDER, width=2):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def text(draw, xy, s, f=F_BODY, fill=INK, anchor=None, align="left", max_width=None, line_gap=6):
    x, y = xy
    if max_width:
        avg = max(1, f.size * 0.52)
        chars = max(8, int(max_width / avg))
        lines = []
        for para in str(s).split("\n"):
            lines.extend(wrap(para, chars) or [""])
    else:
        lines = str(s).split("\n")
    for line in lines:
        draw.text((x, y), line, font=f, fill=fill, anchor=anchor, align=align)
        y += f.size + line_gap
    return y


def arrow(draw, start, end, fill=MUTED, width=4):
    draw.line([start, end], fill=fill, width=width)
    x1, y1 = start
    x2, y2 = end
    import math
    ang = math.atan2(y2 - y1, x2 - x1)
    size = 16
    pts = [
        (x2, y2),
        (x2 - size * math.cos(ang - math.pi / 6), y2 - size * math.sin(ang - math.pi / 6)),
        (x2 - size * math.cos(ang + math.pi / 6), y2 - size * math.sin(ang + math.pi / 6)),
    ]
    draw.polygon(pts, fill=fill)


def header(draw, title, subtitle):
    text(draw, (70, 50), title, F_TITLE, INK)
    text(draw, (74, 112), subtitle, F_SUB, MUTED, max_width=1280)
    draw.line([(70, 162), (1530, 162)], fill=BORDER, width=3)


def save(img, name):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    img.save(path, quality=96)
    print(path.resolve())


def img_problem_map():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    header(d, "Peta Masalah UMKM Chat-Commerce", "Mengapa JUALIN OS relevan untuk Digital Intelligence for Smart Society")

    problems = [
        ("Respons terlambat", "Calon pembeli pindah toko ketika chat tidak segera dibalas."),
        ("Nego berisiko rugi", "Penjual harus hitung margin cepat saat pelanggan menawar."),
        ("Order belum dibayar", "Link pembayaran dikirim, tetapi tidak ada follow-up otomatis."),
        ("Stok tidak sinkron", "Janji ready saat stok habis menurunkan kepercayaan."),
        ("Retensi lemah", "Pelanggan lama tidak pernah disapa ulang secara sistematis."),
        ("Rekap manual", "Omzet, pending, dan produk laris sering diketahui terlambat."),
    ]
    agents = [
        ("Pramuniaga", "Balas & closing chat"),
        ("Juru Tawar", "Nego aman-margin"),
        ("Marketing", "Follow-up & win-back"),
        ("Gudang", "Cek stok & restock alert"),
        ("Layanan", "Keluhan & eskalasi"),
        ("Keuangan", "Rekap harian otomatis"),
    ]

    left_x, right_x = 90, 940
    y0, gap = 215, 112
    for i, (p, desc) in enumerate(problems):
        y = y0 + i * gap
        rounded(d, (left_x, y, left_x + 570, y + 82), 18, "#FFFFFF", BORDER)
        d.ellipse((left_x + 22, y + 24, left_x + 54, y + 56), fill=RED if i in (1, 2) else ORANGE)
        text(d, (left_x + 72, y + 13), p, F_H3, INK)
        text(d, (left_x + 72, y + 43), desc, F_SMALL, MUTED, max_width=450, line_gap=2)

        rounded(d, (right_x, y, right_x + 500, y + 82), 18, [LIGHT_BLUE, LIGHT_TEAL, LIGHT_GREEN, LIGHT_TEAL, LIGHT_ORANGE, LIGHT_GREEN][i], BORDER)
        text(d, (right_x + 30, y + 14), agents[i][0], F_H3, TEAL_DARK if i != 1 else BLUE_DARK)
        text(d, (right_x + 30, y + 46), agents[i][1], F_SMALL, MUTED, max_width=380, line_gap=2)
        arrow(d, (left_x + 600, y + 41), (right_x - 24, y + 41), TEAL if i != 1 else BLUE, 5)

    rounded(d, (365, 875, 1235, 945), 22, INK, INK)
    text(d, (410, 894), "Inti gagasan: bukan chatbot tunggal, tetapi tim agen AI yang menjalankan operasi toko.", F_H3, "#FFFFFF", max_width=800)
    save(img, "01_peta_masalah_umkm_chat_commerce.png")


def img_architecture():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    header(d, "Arsitektur JUALIN OS", "Lapisan multi-agen di atas JUALIN.AI untuk menjalankan toko secara semi-otonom")

    # Main row: events -> orchestrator -> controls
    rounded(d, (535, 235, 1065, 345), 26, INK, INK)
    text(d, (590, 254), "ORCHESTRATOR", F_H2, "#FFFFFF")
    text(d, (590, 294), "routing agen, policy, audit, daily brief", F_SMALL, "#CFE8FF")

    events = [("Chat masuk", 120, 215), ("Payment", 120, 300), ("Cron worker", 120, 385), ("Stok berubah", 120, 470)]
    for label, x, y in events:
        rounded(d, (x, y, x + 260, y + 56), 16, LIGHT_BLUE, "#B7CCEF")
        text(d, (x + 24, y + 16), label, F_BODY, BLUE_DARK)
    arrow(d, (390, 330), (515, 290), BLUE, 5)
    text(d, (120, 555), "Peristiwa bisnis", F_H3, INK)
    text(d, (120, 587), "Semua sinyal operasional masuk ke satu pengarah utama.", F_SMALL, MUTED, max_width=320)

    controls = [
        ("Policy Engine", "diskon maks, margin floor, otonomi", 1215, 215, LIGHT_TEAL),
        ("Human Approval", "approve/reject aksi berisiko", 1215, 315, LIGHT_GREEN),
        ("Audit Log", "jejak semua tindakan agen", 1215, 415, "#F3E8FF"),
    ]
    for title, sub, x, y, fill in controls:
        rounded(d, (x, y, x + 280, y + 74), 18, fill, BORDER)
        text(d, (x + 22, y + 13), title, F_H3, INK)
        text(d, (x + 22, y + 45), sub, F_TINY, MUTED, max_width=230, line_gap=1)
    arrow(d, (1085, 290), (1192, 250), TEAL, 5)
    arrow(d, (1085, 305), (1192, 352), GREEN, 5)

    # Agent specialists
    text(d, (120, 650), "Agen spesialis yang dikoordinasikan", F_H2, INK)
    agents = [
        ("Pramuniaga", "sales", 120, 700, LIGHT_BLUE),
        ("Juru Tawar", "negotiator", 360, 700, LIGHT_TEAL),
        ("Gudang", "inventory", 600, 700, LIGHT_GREEN),
        ("Marketing", "growth", 840, 700, LIGHT_ORANGE),
        ("Keuangan", "finance", 1080, 700, "#FFF7D6"),
        ("Layanan", "cs", 1320, 700, LIGHT_RED),
    ]
    for title, role, x, y, fill in agents:
        rounded(d, (x, y, x + 190, y + 105), 20, fill, BORDER)
        text(d, (x + 20, y + 22), title, F_H3, INK, max_width=150)
        text(d, (x + 20, y + 58), role, F_SMALL, MUTED)
    arrow(d, (800, 350), (800, 675), TEAL, 5)

    # Shared state row
    stores = [
        ("PostgreSQL + pgvector", "produk, order, memori pelanggan", 470, 485, LIGHT_BLUE),
        ("Redis + arq", "job proaktif dan cron cycle", 790, 485, LIGHT_ORANGE),
        ("Negotiation State", "ronde, floor price, offer terakhir", 1110, 515, LIGHT_GREEN),
    ]
    for title, sub, x, y, fill in stores:
        rounded(d, (x, y, x + 285, y + 78), 18, fill, BORDER)
        text(d, (x + 22, y + 12), title, F_BODY, INK, max_width=240)
        text(d, (x + 22, y + 45), sub, F_TINY, MUTED, max_width=230, line_gap=1)
    arrow(d, (800, 350), (620, 475), MUTED, 3)
    arrow(d, (800, 350), (930, 475), MUTED, 3)

    rounded(d, (80, 865, 1520, 940), 22, "#FFFFFF", BORDER)
    text(d, (110, 885), "Prinsip desain: LLM menyusun bahasa; keputusan bisnis kritis dikontrol policy engine, margin guardrail, approval penjual, dan audit.", F_H3, INK, max_width=1360)
    save(img, "02_arsitektur_jualin_os_multi_agen.png")


def img_negotiation():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    header(d, "Alur Negosiasi Aman-Margin", "Angka dikontrol engine deterministik; LLM hanya menarasikan kalimat ke pelanggan")

    steps = [
        ("1", "Pesan pelanggan", '"Kak boleh 150 ribu?"'),
        ("2", "Deteksi intent nego", "Regex + konteks percakapan"),
        ("3", "Cari produk fokus", "Semantic search katalog seller"),
        ("4", "Hitung lantai harga", "max(modal x margin, harga x diskon maks)"),
        ("5", "Putuskan offer", "Concession ladder per ronde"),
        ("6", "Approval jika perlu", "Diskon melewati ambang -> penjual approve"),
        ("7", "Balasan natural", "LLM memakai angka engine persis"),
    ]
    positions = [
        (90, 230), (465, 230), (840, 230), (1215, 230),
        (278, 410), (653, 410), (1028, 410),
    ]
    box_w, box_h = 300, 120
    for i, (num, title, desc) in enumerate(steps):
        x, y = positions[i]
        fill = LIGHT_TEAL if i in (3, 4, 5) else "#FFFFFF"
        rounded(d, (x, y, x + box_w, y + box_h), 22, fill, BORDER)
        d.ellipse((x + 18, y + 18, x + 54, y + 54), fill=TEAL if i in (3, 4, 5) else BLUE)
        text(d, (x + 30, y + 24), num, F_SMALL, "#FFFFFF", anchor="mm")
        text(d, (x + 72, y + 18), title, F_H3, INK, max_width=205, line_gap=2)
        text(d, (x + 24, y + 72), desc, F_SMALL, MUTED, max_width=250, line_gap=2)
    for a, b in [(0, 1), (1, 2), (2, 3), (4, 5), (5, 6)]:
        sx, sy = positions[a]
        ex, ey = positions[b]
        arrow(d, (sx + box_w, sy + box_h // 2), (ex - 18, ey + box_h // 2), TEAL if a >= 2 else BLUE, 4)

    # Wrap connector from the last top-row step to the first second-row step.
    sx, sy = positions[3]
    ex, ey = positions[4]
    wrap_points = [
        (sx + box_w // 2, sy + box_h),
        (sx + box_w // 2, 382),
        (ex + box_w // 2, 382),
    ]
    d.line(wrap_points, fill=TEAL, width=4)
    arrow(d, (ex + box_w // 2, 382), (ex + box_w // 2, ey - 8), TEAL, 4)

    rounded(d, (130, 590, 1470, 715), 28, "#FFFFFF", BORDER)
    text(d, (170, 614), "Contoh perhitungan guardrail", F_H2, INK)
    formula = "Harga list Rp189.000 | modal Rp113.400 | diskon maks 15% | margin minimum 10%"
    text(d, (170, 660), formula, F_BODY, MUTED)
    text(d, (170, 688), "Lantai harga = max(189.000 x 85%, 113.400 x 110%) = max(160.650, 124.740) = Rp160.650", F_BODY, TEAL_DARK)

    rounded(d, (130, 770, 1470, 905), 28, INK, INK)
    text(d, (175, 795), "Implikasi untuk juri", F_H2, "#FFFFFF")
    text(d, (175, 842), "AI tidak bisa menjual di bawah batas aman. Jika pelanggan menawar Rp150.000, sistem menolak halus dan menawarkan harga yang tetap menjaga margin.", F_BODY, "#DDF7F2", max_width=1220)
    save(img, "03_alur_negosiasi_aman_margin.png")


def img_dashboard_mock():
    img = Image.new("RGB", (W, H), "#0B1220")
    d = ImageDraw.Draw(img)
    text(d, (70, 45), "Mockup Pusat Komando AI Crew", F_TITLE, "#FFFFFF")
    text(d, (74, 108), "Visual pendukung proposal: satu layar untuk memantau agen, approval, dan dampak operasional", F_SUB, "#AFC2D9", max_width=1250)

    # sidebar
    rounded(d, (60, 175, 310, 930), 26, "#111827", "#1F2937")
    text(d, (95, 215), "JUALIN.AI", F_H2, "#FFFFFF")
    nav = ["Overview", "AI Crew", "Produk", "Order", "Inbox", "Campaign", "Analitik", "Settings"]
    for i, item in enumerate(nav):
        y = 285 + i * 65
        fill = TEAL if item == "AI Crew" else "#111827"
        rounded(d, (92, y, 278, y + 44), 14, fill, fill if item == "AI Crew" else "#273449")
        text(d, (116, y + 12), item, F_SMALL, "#FFFFFF" if item == "AI Crew" else "#B8C3D3")

    # top cards
    content_x = 350
    text(d, (content_x, 188), "AI Crew - Toko Otonom", F_H2, "#FFFFFF")
    kpis = [
        ("Omzet hari ini", "Rp 612.000", "+18% vs kemarin", GREEN),
        ("Pending bayar", "3 order", "Rp 214.000", YELLOW),
        ("Approval", "1 item", "diskon besar", ORANGE),
        ("Produk terlaris", "Dress Emerald", "8 unit", BLUE),
    ]
    for i, (label, val, sub, color) in enumerate(kpis):
        x = content_x + i * 295
        rounded(d, (x, 245, x + 265, 360), 20, "#111827", "#243244")
        text(d, (x + 22, 267), label, F_SMALL, "#AFC2D9")
        text(d, (x + 22, 298), val, F_H2, "#FFFFFF")
        text(d, (x + 22, 334), sub, F_TINY, color)

    # crew cards
    roles = [("Manajer", "aktif"), ("Pramuniaga", "12 aksi"), ("Juru Tawar", "2 nego"), ("Gudang", "3 alert"), ("Marketing", "4 follow-up"), ("Keuangan", "brief")]
    for i, (role, status) in enumerate(roles):
        x = content_x + (i % 3) * 265
        y = 405 + (i // 3) * 130
        rounded(d, (x, y, x + 235, y + 100), 18, "#111827", "#243244")
        d.ellipse((x + 22, y + 24, x + 58, y + 60), fill=TEAL if i != 2 else BLUE)
        text(d, (x + 76, y + 22), role, F_H3, "#FFFFFF")
        text(d, (x + 76, y + 58), status, F_SMALL, "#AFC2D9")

    # approval/activity
    rounded(d, (1160, 405, 1510, 635), 20, "#111827", "#243244")
    text(d, (1190, 430), "Approval Queue", F_H3, "#FFFFFF")
    text(d, (1190, 472), "Diskon 14.8% untuk Dress Emerald", F_SMALL, "#FDE68A", max_width=270)
    rounded(d, (1190, 535, 1328, 580), 14, GREEN, GREEN)
    text(d, (1225, 548), "Setujui", F_SMALL, "#06130A")
    rounded(d, (1342, 535, 1475, 580), 14, "#334155", "#334155")
    text(d, (1385, 548), "Tolak", F_SMALL, "#FFFFFF")

    rounded(d, (350, 680, 1510, 930), 20, "#111827", "#243244")
    text(d, (380, 705), "Live Activity Feed", F_H3, "#FFFFFF")
    feed = [
        ("Juru Tawar", "Menolak tawaran Rp150.000, menawarkan Rp170.000 sesuai floor margin."),
        ("Gudang", "Stok Dress Emerald aman: 8 unit tersedia."),
        ("Marketing", "Menandai 3 pembayaran tertunda untuk follow-up."),
        ("Keuangan", "Menyusun ringkasan omzet harian otomatis."),
    ]
    for i, (agent, line) in enumerate(feed):
        y = 752 + i * 42
        d.ellipse((382, y + 4, 402, y + 24), fill=TEAL)
        text(d, (418, y), f"{agent}: {line}", F_SMALL, "#DDE7F3", max_width=980)
    save(img, "04_mockup_dashboard_ai_crew.png")


def img_validation_template():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    header(d, "Template Visual Validasi Responden", "Gunakan sebagai placeholder desain; ganti angka setelah Google Form asli terkumpul")

    # watermark
    d.text((805, 512), "SIMULASI", font=font(120, True), fill="#E5E7EB", anchor="mm")

    rounded(d, (80, 210, 550, 850), 28, "#FFFFFF", BORDER)
    text(d, (120, 245), "Instrumen GForm", F_H2, INK)
    questions = [
        "Profil responden: jenis usaha, kanal jualan, volume chat.",
        "Masalah utama: lambat balas, nego, stok, follow-up, rekap.",
        "Persepsi manfaat JUALIN OS.",
        "Kepercayaan pada kontrol approval.",
        "Niat menggunakan dan membayar.",
    ]
    y = 305
    for i, q in enumerate(questions, 1):
        d.ellipse((120, y + 5, 144, y + 29), fill=TEAL)
        text(d, (132, y + 8), str(i), F_TINY, "#FFFFFF", anchor="mm")
        y = text(d, (160, y), q, F_BODY, INK, max_width=335, line_gap=3) + 12

    rounded(d, (620, 210, 1490, 850), 28, "#FFFFFF", BORDER)
    text(d, (660, 245), "Contoh grafik yang bisa dipakai setelah data asli masuk", F_H2, INK, max_width=760)
    labels = ["Butuh\nbalas cepat", "Butuh\nnego aman", "Percaya\napproval", "Berminat\npakai", "Bersedia\nbayar"]
    values = [0.90, 0.83, 0.87, 0.80, 0.67]
    colors = [TEAL, BLUE, GREEN, ORANGE, YELLOW]
    chart_x, chart_y = 720, 385
    max_h = 310
    bar_w = 95
    for i, (lab, val, col) in enumerate(zip(labels, values, colors)):
        x = chart_x + i * 145
        h = int(max_h * val)
        d.rounded_rectangle((x, chart_y + max_h - h, x + bar_w, chart_y + max_h), radius=18, fill=col)
        text(d, (x + bar_w / 2, chart_y + max_h - h - 35), f"{int(val*100)}%", F_H3, INK, anchor="mm")
        text(d, (x + bar_w / 2, chart_y + max_h + 22), lab, F_SMALL, MUTED, anchor="mm", align="center")
    d.line((690, chart_y + max_h, 1445, chart_y + max_h), fill=BORDER, width=3)
    rounded(d, (660, 775, 1450, 825), 16, LIGHT_RED, "#F9B4B4")
    text(d, (685, 789), "Catatan etis: angka di grafik ini simulasi desain, bukan hasil survei. Pakai hanya setelah diganti data GForm asli.", F_SMALL, RED, max_width=720, line_gap=1)
    save(img, "05_template_validasi_responden_simulasi.png")


def img_roadmap_impact():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    header(d, "Roadmap dan Metrik Dampak", "Membuktikan solusi bukan hanya argumentasi, tetapi produk yang bisa diukur")

    stages = [
        ("MVP Lomba", "AI Crew core: nego, stok, brief, dashboard", TEAL),
        ("Pilot UMKM", "10-30 toko uji: chat, order, approval, feedback", BLUE),
        ("Integrasi WA", "Follow-up otomatis, template pesan, payment link", GREEN),
        ("Scale-up", "Playbook toko, A/B eksperimen, multi-channel", ORANGE),
    ]
    y = 245
    for i, (title, desc, col) in enumerate(stages):
        x = 105 + i * 370
        d.ellipse((x, y, x + 84, y + 84), fill=col)
        text(d, (x + 42, y + 23), str(i + 1), F_H2, "#FFFFFF", anchor="mm")
        rounded(d, (x - 30, y + 115, x + 260, y + 270), 22, "#FFFFFF", BORDER)
        text(d, (x, y + 138), title, F_H3, INK, max_width=235)
        text(d, (x, y + 178), desc, F_SMALL, MUTED, max_width=230, line_gap=3)
        if i < len(stages) - 1:
            arrow(d, (x + 95, y + 42), (x + 340, y + 42), MUTED, 4)

    rounded(d, (115, 620, 1485, 900), 28, "#FFFFFF", BORDER)
    text(d, (155, 650), "Metrik produk yang disiapkan untuk pembuktian dampak", F_H2, INK)
    metrics = [
        ("Response time", "waktu dari chat masuk ke balasan AI"),
        ("Conversion rate", "chat yang berubah menjadi order"),
        ("AI-assisted revenue", "nilai order yang dibantu agen"),
        ("Saved revenue", "pending payment yang berhasil ditagih"),
        ("Safe negotiation", "deal nego yang tetap di atas floor margin"),
    ]
    for i, (m, desc) in enumerate(metrics):
        x = 155 + (i % 3) * 430
        yy = 720 + (i // 3) * 80
        rounded(d, (x, yy, x + 375, yy + 58), 16, [LIGHT_BLUE, LIGHT_TEAL, LIGHT_GREEN, LIGHT_ORANGE, "#FFF7D6"][i], BORDER)
        text(d, (x + 20, yy + 10), m, F_H3, INK)
        text(d, (x + 20, yy + 38), desc, F_TINY, MUTED, max_width=330, line_gap=1)
    save(img, "06_roadmap_dan_metrik_dampak.png")


if __name__ == "__main__":
    img_problem_map()
    img_architecture()
    img_negotiation()
    img_dashboard_mock()
    img_validation_template()
    img_roadmap_impact()
