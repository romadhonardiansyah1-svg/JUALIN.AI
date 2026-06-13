from pathlib import Path
import html

from PIL import Image, ImageDraw, ImageFont
from docx import Document
from docx.shared import Cm, Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle,
    Image as RLImage, KeepTogether, ListFlowable, ListItem
)


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "proposal_gemastik"
ASSETS = OUT / "assets"
ASSETS.mkdir(exist_ok=True)

PDF_PATH = OUT / "SoftwareDevelopment_Digiboom.pdf"
DOCX_PATH = OUT / "Proposal_SoftwareDevelopment_Digiboom_JUALIN_AI.docx"
XLSX_PATH = OUT / "Template_Kuesioner_Validasi_JUALIN_AI.xlsx"
NOTES_PATH = OUT / "Catatan_Finalisasi_Submission.txt"
TODAY = "11 Juni 2026"

GREEN = "#16A34A"
BLUE = "#0EA5E9"
PURPLE = "#7C3AED"
ORANGE = "#F97316"
DARK = "#0F172A"
MUTED = "#64748B"
BORDER = "#D9E2EC"
BG = "#F8FAFC"


def font(name="arial.ttf", size=24):
    path = Path(r"C:\Windows\Fonts") / name
    if path.exists():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


F_REG = font("arial.ttf", 22)
F_SMALL = font("arial.ttf", 18)
F_SMALL_BOLD = font("arialbd.ttf", 18)
F_BOLD = font("arialbd.ttf", 24)
F_TITLE = font("arialbd.ttf", 36)
F_SUB = font("arial.ttf", 22)

pdfmetrics.registerFont(TTFont("TNR", r"C:\Windows\Fonts\times.ttf"))
pdfmetrics.registerFont(TTFont("TNR-Bold", r"C:\Windows\Fonts\timesbd.ttf"))
pdfmetrics.registerFont(TTFont("TNR-Italic", r"C:\Windows\Fonts\timesi.ttf"))


def draw_round(draw, xy, r=18, fill="white", outline=BORDER, width=2):
    draw.rounded_rectangle(xy, radius=r, fill=fill, outline=outline, width=width)


def draw_text_wrap(draw, text, xy, max_width, font_obj, fill=DARK, line_gap=6):
    words = text.split()
    lines, cur = [], ""
    for word in words:
        trial = (cur + " " + word).strip()
        if draw.textbbox((0, 0), trial, font=font_obj)[2] <= max_width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    x, y = xy
    for line in lines:
        draw.text((x, y), line, font=font_obj, fill=fill)
        y += font_obj.size + line_gap
    return y


def create_architecture():
    img = Image.new("RGB", (1600, 980), BG)
    d = ImageDraw.Draw(img)
    d.text((70, 50), "Arsitektur JUALIN.AI", font=F_TITLE, fill=DARK)
    d.text((72, 96), "Alur dari kanal customer sampai aksi penjualan yang bisa diaudit", font=F_SUB, fill=MUTED)
    nodes = [
        (90, 190, 420, 350, "Customer", "Chat publik / WhatsApp / link katalog", BLUE),
        (520, 190, 850, 350, "Frontend Next.js", "Landing, dashboard seller, storefront, halaman pembayaran", GREEN),
        (950, 190, 1280, 350, "API FastAPI", "Auth, produk, order, analytics, billing, admin", PURPLE),
        (520, 460, 850, 620, "AI Sales Agent", "Intent detection, RAG katalog, guardrails, structured actions", ORANGE),
        (90, 700, 420, 860, "PostgreSQL + pgvector", "Data seller, katalog, order, embeddings, trace AI", "#1D4ED8"),
        (520, 700, 850, 860, "Redis", "Cache katalog, rate limit, worker queue ringan", "#DC2626"),
        (950, 700, 1280, 860, "Payment & Integrasi", "Midtrans/Cashi, webhook, growth link, WhatsApp template", "#0F766E"),
    ]
    for x1, y1, x2, y2, title, desc, color in nodes:
        draw_round(d, (x1, y1, x2, y2), r=24, fill="white", outline="#E2E8F0", width=3)
        d.rounded_rectangle((x1, y1, x1 + 16, y2), radius=8, fill=color)
        d.text((x1 + 36, y1 + 28), title, font=F_BOLD, fill=DARK)
        draw_text_wrap(d, desc, (x1 + 36, y1 + 72), x2 - x1 - 64, F_SMALL, fill=MUTED)
    arrows = [
        ((420, 270), (520, 270)), ((850, 270), (950, 270)), ((1115, 350), (1115, 700)),
        ((950, 540), (850, 540)), ((685, 620), (685, 700)), ((520, 780), (420, 780)),
        ((950, 780), (850, 780)), ((685, 350), (685, 460)), ((950, 270), (820, 460)),
    ]
    for (x1, y1), (x2, y2) in arrows:
        d.line((x1, y1, x2, y2), fill="#94A3B8", width=4)
        if x2 > x1:
            pts = [(x2, y2), (x2 - 14, y2 - 9), (x2 - 14, y2 + 9)]
        elif x2 < x1:
            pts = [(x2, y2), (x2 + 14, y2 - 9), (x2 + 14, y2 + 9)]
        elif y2 > y1:
            pts = [(x2, y2), (x2 - 9, y2 - 14), (x2 + 9, y2 - 14)]
        else:
            pts = [(x2, y2), (x2 - 9, y2 + 14), (x2 + 9, y2 + 14)]
        d.polygon(pts, fill="#94A3B8")
    d.text((70, 915), "Kontrol utama: tenant isolation, rate limiting, idempotency, audit log, dan human takeover.", font=F_SMALL_BOLD, fill=DARK)
    path = ASSETS / "fig01_arsitektur_jualin_ai.png"
    img.save(path, quality=95)
    return path


def create_user_flow():
    img = Image.new("RGB", (1600, 900), BG)
    d = ImageDraw.Draw(img)
    d.text((70, 48), "Alur Penggunaan dan Dampak yang Diukur", font=F_TITLE, fill=DARK)
    d.text((72, 94), "Fokus: seller melihat manfaat dalam 10 menit, customer mendapat respons cepat, order tercatat.", font=F_SUB, fill=MUTED)
    steps = [
        ("1", "Seller daftar", "Input profil toko dan tujuan jualan"),
        ("2", "Input katalog", "Produk, harga, stok, foto, kategori"),
        ("3", "Share link", "Chat publik / WhatsApp / storefront"),
        ("4", "AI melayani", "Jawab produk, rekomendasi, konfirmasi order"),
        ("5", "Order & bayar", "Payment link, follow-up, status order"),
        ("6", "Dashboard", "Revenue, AI assisted order, conversion funnel"),
    ]
    x0, y = 80, 210
    box_w, box_h, gap = 220, 170, 28
    cols = [GREEN, BLUE, PURPLE, ORANGE, "#0F766E", "#334155"]
    for i, (num, title, desc) in enumerate(steps):
        x = x0 + i * (box_w + gap)
        draw_round(d, (x, y, x + box_w, y + box_h), r=22, fill="white", outline="#E2E8F0", width=3)
        d.ellipse((x + 18, y + 18, x + 60, y + 60), fill=cols[i])
        d.text((x + 39, y + 39), num, font=F_SMALL_BOLD, fill="white", anchor="mm")
        d.text((x + 24, y + 82), title, font=F_SMALL_BOLD, fill=DARK)
        draw_text_wrap(d, desc, (x + 24, y + 112), box_w - 48, font("arial.ttf", 17), fill=MUTED)
        if i < len(steps) - 1:
            d.line((x + box_w + 4, y + 85, x + box_w + gap - 6, y + 85), fill="#94A3B8", width=4)
            d.polygon([(x + box_w + gap - 6, y + 85), (x + box_w + gap - 20, y + 76), (x + box_w + gap - 20, y + 94)], fill="#94A3B8")
    d.text((90, 500), "Metrik evaluasi", font=F_BOLD, fill=DARK)
    metrics = [
        ("Respons", "Waktu balas rata-rata, target detik"),
        ("Konversi", "Chat yang berujung order"),
        ("Kepercayaan", "Kebijakan toko dan payment jelas"),
        ("Kontrol", "Manual takeover dan approval action"),
    ]
    for i, (m, desc) in enumerate(metrics):
        x = 90 + i * 360
        draw_round(d, (x, 555, x + 310, 720), r=18, fill="#FFFFFF", outline="#DCE6F2", width=2)
        d.text((x + 22, 580), m, font=F_BOLD, fill=GREEN)
        draw_text_wrap(d, desc, (x + 22, 626), 260, F_SMALL, fill=MUTED)
    d.text((90, 792), "Validasi primer: kuesioner 30 responden asli dari GForm, dilengkapi uji skenario prototipe.", font=F_SMALL_BOLD, fill=DARK)
    path = ASSETS / "fig02_alur_pengguna_dampak.png"
    img.save(path, quality=95)
    return path


def bubble_lines(draw, text, maxw, fnt):
    lines, cur = [], ""
    for w in text.split():
        trial = (cur + " " + w).strip()
        if draw.textbbox((0, 0), trial, font=fnt)[2] <= maxw:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def create_chat_mockup():
    img = Image.new("RGB", (1500, 980), "#ECFDF5")
    d = ImageDraw.Draw(img)
    d.text((70, 50), "Mockup Interface: Customer Chat", font=F_TITLE, fill=DARK)
    d.text((72, 96), "Percakapan dibuat ringkas, katalog-aware, dan selalu mengarah ke konfirmasi order.", font=F_SUB, fill=MUTED)
    px, py, pw, ph = 160, 170, 470, 710
    draw_round(d, (px, py, px + pw, py + ph), r=42, fill="white", outline="#BBF7D0", width=4)
    d.rounded_rectangle((px + 20, py + 20, px + pw - 20, py + 88), radius=24, fill="#DCFCE7")
    d.ellipse((px + 42, py + 38, px + 76, py + 72), fill=GREEN)
    d.text((px + 92, py + 37), "Toko Sari Fashion", font=F_SMALL_BOLD, fill=DARK)
    d.text((px + 92, py + 62), "Online - dibantu JUALIN.AI", font=font("arial.ttf", 14), fill=MUTED)
    fnt = font("arial.ttf", 18)
    bubbles = [
        ("left", "Kak, ada baju buat kondangan warna soft?"),
        ("right", "Ada kak. Rekomendasi paling cocok: Baju Pink Satin Rp 89.000, stok M dan L ready. Bahannya ringan dan rapi untuk acara."),
        ("left", "Ukuran M ready? mau order 1."),
        ("right", "Ready kak. Saya konfirmasi dulu: Baju Pink Satin ukuran M, qty 1, total Rp 89.000. Mau lanjut dibuatkan pesanan?"),
    ]
    y = py + 120
    for side, text in bubbles:
        maxw = 330
        lines = bubble_lines(d, text, maxw, fnt)
        h = 32 + len(lines) * 25
        x = px + 36 if side == "left" else px + pw - 36 - maxw - 24
        fill = "#F1F5F9" if side == "left" else "#DCFCE7"
        outline = "#E2E8F0" if side == "left" else "#86EFAC"
        draw_round(d, (x, y, x + maxw + 24, y + h), r=22, fill=fill, outline=outline, width=2)
        ty = y + 17
        for line in lines:
            d.text((x + 14, ty), line, font=fnt, fill=DARK)
            ty += 25
        y += h + 18
    d.rounded_rectangle((px + 28, py + ph - 72, px + pw - 28, py + ph - 28), radius=22, fill="#F8FAFC", outline="#E2E8F0")
    d.text((px + 52, py + ph - 60), "Tulis pesan...", font=font("arial.ttf", 17), fill="#94A3B8")
    d.ellipse((px + pw - 76, py + ph - 67, px + pw - 36, py + ph - 27), fill=GREEN)
    d.polygon([(px + pw - 60, py + ph - 57), (px + pw - 46, py + ph - 47), (px + pw - 60, py + ph - 37)], fill="white")
    x = 720
    d.text((x, 180), "Elemen interface yang ditonjolkan", font=F_BOLD, fill=DARK)
    cards = [
        ("Jawaban berbasis katalog", "AI tidak mengarang harga/stok; semua merujuk produk seller."),
        ("Konfirmasi sebelum order", "Pesanan baru dibuat setelah customer menyetujui detail item."),
        ("Tone lokal dan natural", "Bahasa singkat, sopan, cocok untuk chat jual-beli UMKM."),
        ("Fallback aman", "Jika LLM gagal atau data tidak lengkap, sistem meminta admin mengecek manual."),
    ]
    yy = 240
    for title, desc in cards:
        draw_round(d, (x, yy, 1370, yy + 130), r=20, fill="white", outline="#BBF7D0", width=2)
        d.text((x + 28, yy + 24), title, font=F_SMALL_BOLD, fill=GREEN)
        draw_text_wrap(d, desc, (x + 28, yy + 58), 570, F_SMALL, fill=MUTED)
        yy += 155
    path = ASSETS / "mockup01_customer_chat.png"
    img.save(path, quality=95)
    return path


def create_dashboard_mockup():
    img = Image.new("RGB", (1600, 1000), BG)
    d = ImageDraw.Draw(img)
    d.text((70, 50), "Mockup Interface: Seller Dashboard", font=F_TITLE, fill=DARK)
    d.text((72, 96), "Dashboard fokus pada uang, order, stok, dan chat yang perlu tindakan.", font=F_SUB, fill=MUTED)
    sx, sy, sw, sh = 80, 170, 1440, 730
    draw_round(d, (sx, sy, sx + sw, sy + sh), r=28, fill="white", outline="#E2E8F0", width=3)
    d.rounded_rectangle((sx, sy, sx + 250, sy + sh), radius=28, fill="#0F172A")
    d.text((sx + 32, sy + 34), "JUALIN.AI", font=F_BOLD, fill="white")
    nav = ["Overview", "Inbox", "Produk", "Order", "Analytics", "Campaign", "Settings"]
    for i, n in enumerate(nav):
        y = sy + 100 + i * 54
        fill = GREEN if i == 0 else "#1E293B"
        d.rounded_rectangle((sx + 24, y, sx + 226, y + 40), radius=12, fill=fill)
        d.text((sx + 48, y + 10), n, font=font("arial.ttf", 17), fill="white")
    cx = sx + 290
    d.text((cx, sy + 38), "Selamat datang, Seller", font=F_BOLD, fill=DARK)
    d.text((cx, sy + 72), "Ringkasan performa toko hari ini", font=F_SMALL, fill=MUTED)
    stats = [
        ("AI Bantu Closing", "Rp 1,8 Jt", GREEN),
        ("Order Dibantu AI", "23", BLUE),
        ("Payment Pending", "Rp 420 rb", ORANGE),
        ("Avg Respons", "3 dtk", PURPLE),
    ]
    for i, (label, val, color) in enumerate(stats):
        x = cx + i * 285
        draw_round(d, (x, sy + 125, x + 255, sy + 250), r=18, fill=BG, outline="#E2E8F0", width=2)
        d.rectangle((x, sy + 125, x + 8, sy + 250), fill=color)
        d.text((x + 26, sy + 150), label, font=font("arial.ttf", 16), fill=MUTED)
        d.text((x + 26, sy + 182), val, font=font("arialbd.ttf", 28), fill=DARK)
    draw_round(d, (cx, sy + 300, cx + 720, sy + 650), r=18, fill="white", outline="#E2E8F0", width=2)
    d.text((cx + 28, sy + 326), "Order 7 Hari Terakhir", font=F_SMALL_BOLD, fill=DARK)
    bars = [90, 130, 80, 180, 220, 160, 250]
    for i, b in enumerate(bars):
        x = cx + 70 + i * 82
        d.rounded_rectangle((x, sy + 610 - b, x + 42, sy + 610), radius=12, fill=GREEN)
        d.text((x + 8, sy + 622), ["Min", "Sen", "Sel", "Rab", "Kam", "Jum", "Sab"][i], font=font("arial.ttf", 14), fill=MUTED)
    draw_round(d, (cx + 760, sy + 300, sx + sw - 40, sy + 650), r=18, fill="#F0FDF4", outline="#BBF7D0", width=2)
    d.text((cx + 790, sy + 328), "Tindakan Prioritas", font=F_SMALL_BOLD, fill=DARK)
    tasks = ["Follow-up 8 order pending", "Upload foto 5 produk", "Cek 3 chat perlu admin", "Publish storefront minggu ini"]
    yy = sy + 380
    for task in tasks:
        d.rounded_rectangle((cx + 790, yy, sx + sw - 80, yy + 50), radius=12, fill="white", outline="#BBF7D0")
        d.ellipse((cx + 812, yy + 16, cx + 830, yy + 34), fill=GREEN)
        d.text((cx + 846, yy + 14), task, font=font("arial.ttf", 17), fill=DARK)
        yy += 66
    path = ASSETS / "mockup02_seller_dashboard.png"
    img.save(path, quality=95)
    return path


def create_onboarding_mockup():
    img = Image.new("RGB", (1500, 900), BG)
    d = ImageDraw.Draw(img)
    d.text((70, 50), "Mockup Interface: Quick Start 10 Menit", font=F_TITLE, fill=DARK)
    d.text((72, 96), "Onboarding mobile-first agar UMKM tidak perlu memahami konfigurasi teknis.", font=F_SUB, fill=MUTED)
    steps = ["Toko", "Produk", "AI", "Preview", "Go Live"]
    x0, y0 = 110, 190
    for i, step in enumerate(steps):
        x = x0 + i * 260
        color = GREEN if i <= 2 else "#CBD5E1"
        d.ellipse((x, y0, x + 54, y0 + 54), fill=color)
        d.text((x + 27, y0 + 27), str(i + 1), font=F_SMALL_BOLD, fill="white", anchor="mm")
        d.text((x - 8, y0 + 70), step, font=F_SMALL_BOLD, fill=DARK)
        if i < len(steps) - 1:
            d.line((x + 64, y0 + 27, x + 250, y0 + 27), fill="#CBD5E1", width=4)
    cards = [
        ("Profil Toko", "Nama toko, kategori usaha, jam layanan, gaya bahasa."),
        ("Produk Cepat", "Tambah 3-5 produk pertama dari HP, bisa draft dulu."),
        ("Simulasi Chat", "Seller mengetes pertanyaan customer sebelum link dibagikan."),
    ]
    for i, (title, desc) in enumerate(cards):
        x = 130 + i * 430
        draw_round(d, (x, 360, x + 360, 665), r=26, fill="white", outline="#E2E8F0", width=3)
        d.rounded_rectangle((x + 26, 390, x + 110, 474), radius=20, fill="#DCFCE7")
        d.text((x + 52, 414), str(i + 1), font=F_TITLE, fill=GREEN)
        d.text((x + 26, 510), title, font=F_BOLD, fill=DARK)
        draw_text_wrap(d, desc, (x + 26, 552), 305, F_SMALL, fill=MUTED)
    d.rounded_rectangle((130, 735, 1370, 805), radius=22, fill="#0F172A")
    d.text((170, 756), "Output onboarding: link katalog, halaman chat demo, dan checklist siap jual.", font=F_SMALL_BOLD, fill="white")
    path = ASSETS / "mockup03_onboarding_quick_start.png"
    img.save(path, quality=95)
    return path


asset_paths = [
    create_architecture(),
    create_user_flow(),
    create_chat_mockup(),
    create_dashboard_mockup(),
    create_onboarding_mockup(),
]

refs = [
    "Badan Pusat Statistik. (2024). Statistik E-Commerce 2024. Jakarta: BPS. https://www.bps.go.id/",
    "Bank Indonesia. (2025). Kanal edukasi dan publikasi QRIS Bank Indonesia. https://www.bi.go.id/QRIS/default.aspx",
    "Google, Temasek, & Bain & Company. (2025). e-Conomy SEA 2025. https://economysea.withgoogle.com/",
    "Kadin Indonesia. (2024). Data dan statistik UMKM Indonesia. https://kadin.id/data-dan-statistik/umkm-indonesia/",
    "Lewis, P., Perez, E., Piktus, A., et al. (2020). Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. NeurIPS. https://arxiv.org/abs/2005.11401",
    "NIST. (2023). Artificial Intelligence Risk Management Framework (AI RMF 1.0). https://www.nist.gov/itl/ai-risk-management-framework",
    "OWASP Foundation. (2023). OWASP API Security Top 10. https://owasp.org/API-Security/editions/2023/en/0x00-header/",
    "International Organization for Standardization. (2023). ISO/IEC 25010 software quality model. https://www.iso.org/standard/78176.html",
    "PostgreSQL Global Development Group. (2023). PostgreSQL 16 Documentation. https://www.postgresql.org/docs/16/",
    "pgvector Contributors. (2024). pgvector: Open-source vector similarity search for PostgreSQL. https://github.com/pgvector/pgvector",
    "FastAPI. (2024). FastAPI Documentation. https://fastapi.tiangolo.com/",
    "Vercel. (2024). Next.js App Router Documentation. https://nextjs.org/docs/app",
]

sections = []


def add_section(title, blocks):
    sections.append((title, blocks))


add_section("1. Judul/Nama Perangkat Lunak", [
    ("p", "Nama perangkat lunak yang diusulkan adalah JUALIN.AI, yaitu platform asisten penjualan berbasis katalog untuk membantu UMKM mikro melayani chat customer, membuat pesanan, memantau pembayaran, dan membaca performa penjualan dari satu dashboard. Produk ini dikembangkan untuk Divisi III Pengembangan Perangkat Lunak GEMASTIK DIGINEXS 2026 dengan tema Digital Intelligence For Smart Society."),
    ("table", [
        ["Aspek", "Rincian"],
        ["Nama produk", "JUALIN.AI"],
        ["Tagline", "AI sales assistant berbasis katalog untuk otomasi layanan chat UMKM mikro"],
        ["Target pengguna", "Pelaku UMKM mikro yang menjual produk melalui WhatsApp, Instagram, storefront sederhana, atau marketplace sosial"],
        ["Kontribusi SDGs", "SDG 8 Decent Work and Economic Growth, SDG 9 Industry Innovation and Infrastructure, SDG 10 Reduced Inequality, SDG 12 Responsible Consumption and Production"],
        ["Status prototipe", "Full-stack web application: Next.js frontend, FastAPI backend, PostgreSQL pgvector, Redis, Docker Compose, dan modul AI guardrails"],
    ], [3.6, 9.6]),
    ("p", "Inti gagasan JUALIN.AI adalah mengubah chat penjualan yang selama ini manual menjadi alur layanan yang terstruktur: customer bertanya, AI memahami katalog, sistem menawarkan produk yang tersedia, order hanya dibuat setelah konfirmasi, pembayaran dilacak, dan seller melihat dampaknya dalam metrik bisnis."),
    ("table", [
        ["Kriteria penyisihan", "Respons dalam proposal"],
        ["Aspek inovasi 20%", "AI tidak berdiri sendiri sebagai chatbot generik, tetapi terikat pada katalog, stok, harga, guardrails, order, payment link, dan audit log."],
        ["Dampak 20%", "Dampak diukur dari waktu respons, chat terlayani, order dibantu AI, follow-up pembayaran, dan adopsi seller; validasi primer disiapkan untuk 30 responden asli."],
        ["Desain antarmuka 20%", "Interface dibuat mobile-first untuk seller UMKM dan customer chat, dengan onboarding 10 menit, dashboard uang, dan halaman chat publik."],
        ["Proses pengembangan 20%", "Metodologi agile, prototyping, API modular, pengujian guardrail/security, Docker deployment, dan feature flag untuk fitur berisiko."],
        ["Kesesuaian ide 10%", "Sesuai tema smart society karena memperluas akses otomasi digital untuk pelaku usaha kecil."],
        ["Urgensi masalah 10%", "Masalah slow response, katalog tidak rapi, dan follow-up pembayaran muncul langsung pada pola jualan berbasis chat UMKM."],
    ], [3.5, 9.7]),
])

add_section("2. Latar Belakang Ide Perangkat Lunak", [
    ("p", "UMKM mikro banyak mengandalkan chat sebagai kanal utama transaksi. Di sisi customer, proses tanya harga, stok, ukuran, ongkir, dan cara bayar sering terjadi berulang. Di sisi seller, chat masuk pada jam yang tidak menentu, stok berubah, dan follow-up pembayaran mudah terlewat. Situasi ini membuat kesempatan closing hilang bukan karena produknya tidak menarik, tetapi karena respons dan proses penjualan tidak konsisten."),
    ("p", "Data sekunder memperlihatkan bahwa perdagangan digital dan pembayaran digital terus menjadi bagian penting dari perilaku belanja Indonesia. Publikasi BPS tentang e-commerce, publikasi QRIS Bank Indonesia, dan laporan e-Conomy SEA menunjukkan pergeseran transaksi ke kanal digital serta pentingnya infrastruktur pembayaran yang mudah diakses. Di sisi lain, pelaku UMKM tetap membutuhkan solusi yang murah, ringan, dan tidak menambah beban operasional."),
    ("table", [
        ["Sumber masalah", "Dampak pada UMKM", "Peluang solusi"],
        ["Chat customer tidak pernah berhenti", "Seller lambat membalas, customer pindah ke toko lain", "Asisten chat 24/7 yang hanya menjawab berdasarkan katalog seller"],
        ["Katalog tersebar di chat, spreadsheet, atau foto", "Harga/stok salah jawab, rekomendasi tidak konsisten", "Katalog terstruktur dengan semantic search dan ringkasan produk"],
        ["Order dibuat manual", "Salah catat alamat, item, atau jumlah", "Konfirmasi order dari chat dengan validasi data produk"],
        ["Pembayaran perlu diingatkan", "Pending payment menumpuk", "Payment link dan follow-up otomatis yang tetap bisa diaudit"],
        ["AI dianggap berisiko", "Seller takut AI mengarang diskon, stok, atau kebijakan", "Guardrails, manual takeover, QA review, dan batasan aksi sensitif"],
    ], [3.0, 4.8, 5.4]),
    ("p", "JUALIN.AI berangkat dari hipotesis sederhana: UMKM tidak perlu memulai digitalisasi dari sistem ERP yang kompleks. Mereka cukup membutuhkan asisten jualan yang paham produk, bisa dipakai dari HP, dan memberi dampak yang terlihat dalam waktu singkat. Karena itu, produk difokuskan pada conversational commerce, bukan sekadar dashboard administrasi."),
])

add_section("3. Tujuan dan Manfaat Dikembangkan Perangkat Lunak", [
    ("p", "Tujuan utama JUALIN.AI adalah menyediakan perangkat lunak yang membantu UMKM mikro meningkatkan kecepatan respons, konsistensi informasi produk, dan peluang konversi order melalui otomasi chat yang tetap aman dikendalikan seller."),
    ("bullets", [
        "Menyediakan AI sales assistant yang menjawab pertanyaan customer berdasarkan katalog, harga, stok, dan kebijakan toko.",
        "Membuat alur chat-to-order sehingga percakapan dapat berakhir pada order yang tercatat, bukan berhenti pada tanya jawab.",
        "Memudahkan seller baru melakukan setup dalam sesi singkat melalui onboarding quick start dan template niche UMKM.",
        "Memberikan dashboard dampak bisnis seperti AI assisted order, revenue assisted by AI, pending payment, dan conversion funnel.",
        "Menjaga kepercayaan dengan guardrails, tenant isolation, rate limiting, audit log, dan human takeover.",
    ]),
    ("table", [
        ["Pihak", "Manfaat"],
        ["UMKM/seller", "Respons lebih cepat, katalog lebih rapi, pesanan lebih mudah dilacak, follow-up pembayaran tidak terlewat, dan insight penjualan lebih mudah dipahami."],
        ["Customer", "Mendapat jawaban stok/harga lebih cepat, rekomendasi produk lebih relevan, dan proses order lebih jelas."],
        ["Perguruan tinggi", "Menunjukkan karya software yang menyentuh persoalan ekonomi digital lokal dan dapat dikembangkan menjadi produk nyata."],
        ["Ekosistem digital", "Mendorong adopsi AI yang terukur, aman, dan sesuai kebutuhan pelaku usaha kecil."],
    ], [3.0, 10.2]),
])

add_section("4. Batasan Perangkat Lunak yang Dikembangkan", [
    ("p", "Batasan dibuat agar prototipe tetap realistis, aman, dan dapat diuji dalam waktu kompetisi. JUALIN.AI tidak diposisikan sebagai AI yang menggantikan seluruh keputusan bisnis seller, tetapi sebagai asisten operasional yang mengurangi beban chat dan administrasi order."),
    ("bullets", [
        "AI hanya boleh menjawab berdasarkan data katalog, kebijakan, dan konfigurasi seller yang tersedia di sistem.",
        "Aksi berdampak uang seperti diskon, broadcast campaign, dan perubahan order sensitif memerlukan approval atau konfigurasi eksplisit dari seller.",
        "Integrasi WhatsApp Cloud, Midtrans, dan Cashi.id disiapkan sebagai plugin/konfigurasi; jika credential belum tersedia, sistem tetap berjalan melalui public chat demo.",
        "Prototipe tidak menangani logistik kompleks lintas ekspedisi; v1 menggunakan shipping cost manual dan kebijakan toko.",
        "Sistem tidak memberi nasihat hukum, medis, finansial, atau topik di luar transaksi jual-beli toko.",
        "Validasi responden harus menggunakan jawaban asli dari GForm; data simulasi hanya boleh dipakai untuk uji format rekap, bukan sebagai bukti penelitian.",
    ]),
])

add_section("5. Metodologi Pengembangan Perangkat Lunak", [
    ("p", "Metodologi yang digunakan adalah agile prototyping dengan tahap discovery, design, build, test, dan validate. Pilihan ini cocok karena produk perlu cepat diuji pada skenario nyata chat penjualan, tetapi tetap membutuhkan kontrol kualitas pada security, guardrails, dan multi-tenant isolation."),
    ("table", [
        ["Tahap", "Aktivitas", "Output"],
        ["Discovery", "Mengidentifikasi pain point UMKM chat-selling, memetakan kanal penjualan, dan menyusun metrik dampak.", "Problem statement, user persona, dan instrumen validasi."],
        ["Design", "Merancang flow customer chat, dashboard seller, onboarding, arsitektur data, dan guardrails AI.", "Flow, mockup, kebutuhan fungsional, dan desain solusi."],
        ["Build", "Mengembangkan frontend Next.js, backend FastAPI, PostgreSQL pgvector, Redis, payment, dan API modular.", "Prototipe web full-stack yang dapat dijalankan."],
        ["Test", "Melakukan syntax check, compose validation, test guardrails, test security route, dan skenario chat-to-order.", "Checklist verifikasi teknis dan daftar perbaikan."],
        ["Validate", "Mengumpulkan respons 30 responden asli melalui GForm dan menguji demo pada calon seller/customer.", "Rekap kebutuhan, minat mencoba, keberatan, dan prioritas fitur."],
    ], [2.2, 6.1, 4.9]),
    ("p", "Pada saat penyusunan proposal, verifikasi teknis yang sudah berhasil dilakukan adalah python compileall pada folder backend dan docker compose config --quiet. Pengujian unit dengan pytest disiapkan di repository, tetapi belum dijalankan pada runtime ini karena modul pytest tidak tersedia."),
])

add_section("6. Analisis Kebutuhan dan Desain Solusi Perangkat Lunak", [
    ("p", "Aktor utama sistem adalah seller, customer, dan admin. Seller mengelola katalog, melihat chat, memproses order, mengatur AI, dan membaca analytics. Customer menggunakan halaman chat atau WhatsApp untuk bertanya dan membeli. Admin memantau kesehatan sistem, retry job, audit log, seller, dan konfigurasi operasional."),
    ("table", [
        ["Kategori", "Kebutuhan"],
        ["Fungsional seller", "Registrasi/login, CRUD produk, upload gambar, AI enrich produk, dashboard analytics, order management, inbox/manual takeover, campaign draft, template niche, onboarding, storefront, billing/quota."],
        ["Fungsional customer", "Chat publik toko, riwayat sesi, rekomendasi produk, konfirmasi order, link pembayaran, dan halaman status pembayaran."],
        ["Fungsional admin", "Monitoring sistem, provider health, failed jobs, audit logs, seller management, concierge setup, dan retry/replay webhook."],
        ["AI", "Intent detection, sales stage, semantic product search, structured action, guardrails anti-halusinasi, trace, feedback, eval case, dan QA review."],
        ["Non-fungsional", "Aman, tenant-isolated, cepat, mobile-first, dapat diaudit, dapat dideploy murah, dan mudah dipelihara."],
    ], [3.2, 10.0]),
    ("figure", str(asset_paths[0]), "Gambar 1. Arsitektur sistem JUALIN.AI."),
    ("figure", str(asset_paths[1]), "Gambar 2. Alur penggunaan dan dampak yang diukur."),
    ("p", "Desain solusi menempatkan katalog sebagai sumber kebenaran utama. Setiap respons AI dibangun dari konteks produk seller, semantic search, histori percakapan terbatas, dan kebijakan untrusted data. Pendekatan ini mengurangi risiko AI menjawab di luar data toko dan membuat alur penjualan lebih dapat diaudit."),
    ("table", [
        ["Modul", "Desain solusi"],
        ["Katalog cerdas", "Produk memiliki nama, deskripsi, harga, stok, kategori, foto, summary, dan embedding 384 dimensi untuk semantic search."],
        ["AI chat", "Agent mendeteksi intent, sales stage, produk relevan, lalu membuat respons singkat berbahasa Indonesia."],
        ["Order", "Order dibuat hanya setelah detail customer dan produk dapat dicocokkan dengan data seller."],
        ["Payment", "Payment link dan webhook disiapkan untuk Midtrans/Cashi; status dapat dipantau customer dan seller."],
        ["Trust layer", "Kebijakan refund, shipping, support hours, dan verified payment ditampilkan di storefront/public trust profile."],
        ["Observability", "AI trace, eval run, feedback, usage event, audit log, dan provider health digunakan untuk pengawasan."],
    ], [3.0, 10.2]),
])

add_section("7. Implementasi Perangkat Lunak", [
    ("p", "Implementasi JUALIN.AI sudah berbentuk aplikasi web full-stack. Struktur repository menunjukkan backend, frontend, nginx, Docker Compose, migration Alembic, seed data, test backend, serta rencana hardening keamanan dan market acceptance. Berdasarkan inspeksi repository, prototipe memuat sekitar 171 endpoint API, 75 model basis data, 36 halaman frontend, dan 12 test backend."),
    ("table", [
        ["Layer", "Teknologi", "Alasan pemilihan"],
        ["Frontend", "Next.js 16, React 19, CSS Modules", "Cepat untuk dashboard dan public chat, mendukung routing modern dan UI mobile-first."],
        ["Backend", "FastAPI, Pydantic, SQLAlchemy", "Ringan, cocok untuk API modular, validasi request jelas, dan dokumentasi endpoint mudah."],
        ["Database", "PostgreSQL 16 + pgvector", "Data relasional tetap kuat, sementara pencarian semantik katalog dapat dilakukan di database yang sama."],
        ["Cache/queue", "Redis 7", "Digunakan untuk rate limit, cache katalog, dan job ringan agar VPS tetap hemat."],
        ["AI", "LLM via OpenAI-compatible endpoint, embedding all-MiniLM-L6-v2, guardrails", "Mendukung respons natural, semantic search, fallback aman, dan pengembangan murah."],
        ["Deployment", "Docker Compose, Nginx, GitHub Actions", "Mudah direplikasi pada VPS kecil dan siap dipindahkan ke server production."],
    ], [2.4, 4.2, 6.6]),
    ("p", "Fitur yang sudah tercermin di codebase meliputi autentikasi JWT, product CRUD, upload gambar aman, AI chat, streaming chat, order, payment, analytics, inbox, campaigns, workflows, billing, templates, onboarding, storefront, trust profile, growth links, WhatsApp templates, referrals, lead forms, AI playbooks, knowledge base, QA review, experiments, dan admin system dashboard."),
    ("bullets", [
        "Keamanan: production security validation, rate limiting, CORS control, request logging, JWT claims, upload image sanitization, webhook signature validation, open redirect protection, dan seller_id filtering pada route penting.",
        "Kualitas AI: tujuh guardrail utama, untrusted data policy, intent detection, sales stage detection, structured AI action, fallback response, dan trace untuk evaluasi.",
        "Keandalan: penggunaan idempotency key, background job, retry/replay admin, usage event ledger, dan health/readiness endpoint.",
        "Skalabilitas awal: deployment dirancang untuk VPS 4GB dengan Redis maxmemory dan worker concurrency terbatas.",
    ]),
    ("table", [
        ["Verifikasi", "Hasil"],
        ["python -m compileall backend", "Berhasil; semua file Python backend dapat dikompilasi sintaksis."],
        ["docker compose config --quiet", "Berhasil; konfigurasi compose valid secara struktur."],
        ["pytest backend/tests", "Belum dijalankan di runtime ini karena modul pytest tidak tersedia; test suite tetap tersedia di repository."],
    ], [5.0, 8.2]),
])

add_section("8. Screenshot Mockup Interface Perangkat Lunak", [
    ("p", "Mockup berikut disiapkan untuk menunjukkan pengalaman utama produk. Interface sengaja dibuat familiar untuk UMKM: chat seperti aplikasi percakapan, dashboard fokus pada uang/order, dan onboarding dibuat singkat agar seller tidak tersesat pada konfigurasi teknis."),
    ("figure", str(asset_paths[2]), "Gambar 3. Mockup halaman chat customer."),
    ("figure", str(asset_paths[3]), "Gambar 4. Mockup seller dashboard."),
    ("figure", str(asset_paths[4]), "Gambar 5. Mockup quick start onboarding."),
])

add_section("9. Dokumentasi Cara Penggunaan Perangkat Lunak", [
    ("p", "Cara penggunaan dibagi menjadi dua alur: alur seller sebagai pemilik toko dan alur customer sebagai pembeli. Dokumentasi ini juga dapat dipakai sebagai dasar video demo maksimal tiga menit pada tahap lanjutan."),
    ("table", [
        ["Langkah seller", "Deskripsi"],
        ["1. Registrasi", "Seller membuat akun, mengisi nama toko, nomor kontak, slug toko, dan memilih gaya AI."],
        ["2. Quick start", "Seller memilih kategori usaha, memasukkan 3-5 produk awal, dan menjalankan simulasi chat."],
        ["3. Kelola katalog", "Seller menambah produk, foto, harga, stok, kategori, dan mengecek catalog score."],
        ["4. Bagikan link", "Seller membagikan link chat/storefront ke WhatsApp, Instagram, atau bio sosial media."],
        ["5. Pantau chat dan order", "Seller melihat percakapan, mengambil alih manual jika perlu, memproses order, dan mengikuti status pembayaran."],
        ["6. Evaluasi", "Seller membaca dashboard money metrics, conversion funnel, produk laris, pending payment, dan rekomendasi campaign."],
    ], [3.2, 10.0]),
    ("table", [
        ["Langkah customer", "Deskripsi"],
        ["1. Buka link chat", "Customer membuka halaman chat publik toko tanpa login."],
        ["2. Tanya produk", "Customer menanyakan stok, harga, ukuran, rekomendasi, atau cara order."],
        ["3. Terima rekomendasi", "AI menjawab berdasarkan katalog dan menawarkan alternatif jika produk tidak tersedia."],
        ["4. Konfirmasi order", "Customer menyetujui detail item, jumlah, nama, alamat, dan nomor HP."],
        ["5. Bayar", "Customer membuka link pembayaran resmi dan memilih QRIS/VA jika gateway aktif."],
        ["6. Follow-up", "Jika belum bayar, seller/AI dapat melakukan follow-up sesuai aturan yang diaudit."],
    ], [3.2, 10.0]),
    ("p", "Skenario demo yang disarankan: seller login, menambah produk, membuka chat publik, customer menanyakan produk, AI memberi rekomendasi, customer mengonfirmasi order, sistem membuat order/payment link, lalu seller melihat order dan metrik pada dashboard."),
])

add_section("10. Ucapan Terima Kasih", [
    ("p", "Tim Digiboom mengucapkan terima kasih kepada Program Studi Sistem Informasi UNUSA, Himpunan Mahasiswa Sistem Informasi UNUSA, dosen pembimbing, panitia GEMASTIK DIGINEXS 2026, serta rekan-rekan mahasiswa dan pelaku UMKM yang bersedia memberi masukan terhadap pengembangan JUALIN.AI."),
    ("p", "Apresiasi juga diberikan kepada komunitas open-source yang menyediakan fondasi teknologi seperti FastAPI, Next.js, PostgreSQL, pgvector, Redis, dan Docker, sehingga mahasiswa dapat membangun prototipe software berkualitas tinggi dengan biaya pengembangan yang tetap masuk akal."),
])

add_section("11. Daftar Pustaka", [("refs", refs)])

add_section("12. Lampiran", [
    ("p", "Lampiran A. Instrumen validasi 30 responden asli. Instrumen ini disiapkan untuk GForm dan tidak boleh diisi sebagai data fiktif. Rekap akhir harus berasal dari jawaban responden yang benar-benar mengisi."),
    ("table", [
        ["No", "Pertanyaan", "Tipe jawaban"],
        ["1", "Profil responden: pemilik UMKM, reseller, admin online shop, calon pembeli aktif, atau lainnya", "Pilihan tunggal"],
        ["2", "Kanal yang paling sering digunakan untuk jual-beli online", "Pilihan ganda"],
        ["3", "Kendala terbesar saat jualan/berbelanja lewat chat", "Pilihan ganda"],
        ["4", "Seberapa sering chat customer terlambat dibalas atau tidak terjawab", "Skala 1-5"],
        ["5", "Seberapa penting asisten chat 24/7 yang paham katalog produk", "Skala 1-5"],
        ["6", "Fitur JUALIN.AI yang paling dibutuhkan", "Pilihan ganda"],
        ["7", "Seberapa besar minat mencoba JUALIN.AI setelah melihat deskripsi/demo", "Skala 1-5"],
        ["8", "Harga bulanan yang masih dianggap wajar untuk UMKM mikro", "Pilihan tunggal"],
        ["9", "Kekhawatiran terbesar terhadap penggunaan AI dalam chat penjualan", "Pilihan ganda"],
        ["10", "Saran atau kebutuhan tambahan", "Jawaban singkat"],
    ], [1.0, 8.2, 4.0]),
    ("p", "Lampiran B. Rencana rekap validasi. File Excel terpisah sudah disiapkan dengan 30 baris responden kosong, kolom jawaban, dan formula ringkasan. Tim hanya perlu menyalin hasil GForm asli ke sheet Respon_Asli."),
    ("table", [
        ["Indikator", "Target interpretasi"],
        ["Minat mencoba", "Rata-rata skor 4 atau lebih menunjukkan produk layak diprioritaskan untuk uji coba UMKM."],
        ["Kebutuhan asisten chat", "Mayoritas skor 4-5 menunjukkan masalah slow response relevan."],
        ["Fitur prioritas", "Fitur dengan pilihan tertinggi menjadi fokus demo: chat AI, katalog, order, payment, atau dashboard."],
        ["Kekhawatiran", "Kekhawatiran dominan diterjemahkan menjadi guardrails, manual takeover, dan edukasi penggunaan."],
    ], [4.0, 9.2]),
    ("p", "Lampiran C. Hasil uji similaritas. Sesuai guidebook, hasil uji similaritas maksimal 20% perlu dilampirkan oleh tim setelah pengecekan menggunakan Turnitin, iThenticate, atau alat sejenis. Dokumen ini belum menyertakan hasil tersebut karena akses alat similaritas berada pada tim/panitia/kampus."),
])


def build_workbook():
    wb = Workbook()
    ws = wb.active
    ws.title = "Pertanyaan GForm"
    ws.append(["No", "Pertanyaan", "Tipe", "Opsi yang disarankan"])
    questions = [
        (1, "Profil responden", "Pilihan tunggal", "Pemilik UMKM; Reseller/admin online shop; Calon pembeli aktif; Mahasiswa yang sering belanja online; Lainnya"),
        (2, "Kanal jual-beli online yang paling sering digunakan", "Pilihan ganda", "WhatsApp; Instagram; TikTok Shop; Marketplace; Facebook; Website toko"),
        (3, "Kendala terbesar dalam transaksi lewat chat", "Pilihan ganda", "Lambat dibalas; Stok/harga tidak jelas; Sulit checkout; Lupa follow-up bayar; Tidak percaya toko; Lainnya"),
        (4, "Frekuensi chat terlambat dibalas/tidak terjawab", "Skala 1-5", "1 Tidak pernah - 5 Sangat sering"),
        (5, "Pentingnya asisten chat 24/7 yang paham katalog", "Skala 1-5", "1 Tidak penting - 5 Sangat penting"),
        (6, "Fitur paling dibutuhkan", "Pilihan ganda", "Chat AI; Katalog produk; Auto order; Payment link; Follow-up; Dashboard analytics; Manual takeover"),
        (7, "Minat mencoba JUALIN.AI", "Skala 1-5", "1 Tidak berminat - 5 Sangat berminat"),
        (8, "Harga bulanan yang wajar", "Pilihan tunggal", "Gratis; < Rp50.000; Rp50.000-100.000; Rp100.000-300.000; > Rp300.000"),
        (9, "Kekhawatiran terbesar", "Pilihan ganda", "AI salah jawab; Data produk bocor; Biaya; Sulit dipakai; Tidak cocok dengan gaya bahasa toko; Lainnya"),
        (10, "Saran/kebutuhan tambahan", "Jawaban singkat", "Tuliskan bebas"),
    ]
    for row in questions:
        ws.append(row)
    ws2 = wb.create_sheet("Respon_Asli")
    cols = ["ID", "Profil", "Kanal", "Kendala", "Frekuensi slow response (1-5)", "Pentingnya AI chat (1-5)", "Fitur prioritas", "Minat mencoba (1-5)", "Harga wajar", "Kekhawatiran", "Saran"]
    ws2.append(cols)
    for i in range(1, 31):
        ws2.append([f"R{i:02d}"] + [""] * (len(cols) - 1))
    ws3 = wb.create_sheet("Ringkasan")
    for row in [
        ["Metrik", "Formula/hasil"],
        ["Jumlah responden terisi", "=COUNTA(Respon_Asli!B2:B31)"],
        ["Rata-rata frekuensi slow response", "=AVERAGEIF(Respon_Asli!E2:E31,\">0\")"],
        ["Rata-rata pentingnya AI chat", "=AVERAGEIF(Respon_Asli!F2:F31,\">0\")"],
        ["Rata-rata minat mencoba", "=AVERAGEIF(Respon_Asli!H2:H31,\">0\")"],
        ["Catatan", "Isi hanya dari respons GForm asli. Jangan memakai data simulasi sebagai bukti proposal."],
    ]:
        ws3.append(row)
    for sheet in [ws, ws2, ws3]:
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="16A34A")
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        for row in sheet.iter_rows():
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                cell.border = Border(
                    left=Side(style="thin", color="D9E2EC"),
                    right=Side(style="thin", color="D9E2EC"),
                    top=Side(style="thin", color="D9E2EC"),
                    bottom=Side(style="thin", color="D9E2EC"),
                )
        for idx, width in enumerate([10, 28, 28, 42, 20, 20, 30, 18, 24, 28, 36][:sheet.max_column], start=1):
            sheet.column_dimensions[get_column_letter(idx)].width = width
    ws2.freeze_panes = "A2"
    wb.save(XLSX_PATH)


def set_cell_shading(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def set_cell_text(cell, text, bold=False, color=None):
    cell.text = ""
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1.15
    run = p.add_run(str(text))
    run.font.name = "Times New Roman"
    run._element.rPr.rFonts.set(qn("w:ascii"), "Times New Roman")
    run._element.rPr.rFonts.set(qn("w:hAnsi"), "Times New Roman")
    run.font.size = Pt(10.5)
    run.bold = bold
    if color:
        run.font.color.rgb = RGBColor.from_string(color)


def docx_add_table(doc, rows, widths_cm):
    table = doc.add_table(rows=len(rows), cols=len(rows[0]))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = "Table Grid"
    for ri, row in enumerate(rows):
        for ci, value in enumerate(row):
            cell = table.cell(ri, ci)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            set_cell_text(cell, value, bold=(ri == 0), color=("FFFFFF" if ri == 0 else None))
            if ri == 0:
                set_cell_shading(cell, "16A34A")
            elif ri % 2 == 0:
                set_cell_shading(cell, "F8FAFC")
            if ci < len(widths_cm):
                cell.width = Cm(widths_cm[ci])
    doc.add_paragraph()


def docx_add_para(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.line_spacing = 1.5
    p.paragraph_format.space_after = Pt(6)
    run = p.add_run(text)
    run.font.name = "Times New Roman"
    run._element.rPr.rFonts.set(qn("w:ascii"), "Times New Roman")
    run._element.rPr.rFonts.set(qn("w:hAnsi"), "Times New Roman")
    run.font.size = Pt(12)


def docx_add_bullets(doc, items):
    for item in items:
        p = doc.add_paragraph(style="List Bullet")
        p.paragraph_format.line_spacing = 1.5
        p.paragraph_format.space_after = Pt(4)
        run = p.add_run(item)
        run.font.name = "Times New Roman"
        run.font.size = Pt(12)


def centered(doc, text, size=12, bold=False, after=6):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(after)
    p.paragraph_format.line_spacing = 1.5
    r = p.add_run(text)
    r.font.name = "Times New Roman"
    r._element.rPr.rFonts.set(qn("w:ascii"), "Times New Roman")
    r._element.rPr.rFonts.set(qn("w:hAnsi"), "Times New Roman")
    r.font.size = Pt(size)
    r.bold = bold


def build_docx():
    doc = Document()
    sec = doc.sections[0]
    sec.page_width = Cm(21.0)
    sec.page_height = Cm(29.7)
    sec.top_margin = Cm(3)
    sec.bottom_margin = Cm(3)
    sec.left_margin = Cm(4)
    sec.right_margin = Cm(3)
    styles = doc.styles
    styles["Normal"].font.name = "Times New Roman"
    styles["Normal"]._element.rPr.rFonts.set(qn("w:ascii"), "Times New Roman")
    styles["Normal"]._element.rPr.rFonts.set(qn("w:hAnsi"), "Times New Roman")
    styles["Normal"].font.size = Pt(12)
    for st_name, size in [("Heading 1", 14), ("Heading 2", 13), ("Heading 3", 12)]:
        st = styles[st_name]
        st.font.name = "Times New Roman"
        st._element.rPr.rFonts.set(qn("w:ascii"), "Times New Roman")
        st._element.rPr.rFonts.set(qn("w:hAnsi"), "Times New Roman")
        st.font.size = Pt(size)
        st.font.bold = True
        st.font.color.rgb = RGBColor(0, 0, 0)
        st.paragraph_format.line_spacing = 1.5
    for _ in range(5):
        doc.add_paragraph()
    centered(doc, "PROPOSAL PENGEMBANGAN PERANGKAT LUNAK", 14, True, 12)
    centered(doc, "JUALIN.AI", 18, True, 4)
    centered(doc, "AI Sales Assistant Berbasis Katalog untuk Otomasi Layanan Chat UMKM Mikro", 13, True, 24)
    centered(doc, "Divisi III: Pengembangan Perangkat Lunak (Software Development)", 12, False, 4)
    centered(doc, "GEMASTIK DIGINEXS 2026", 12, False, 24)
    centered(doc, "Tim Digiboom", 12, True, 8)
    centered(doc, "Ketua: [Nama Ketua] / [NIM]", 12, False, 2)
    centered(doc, "Anggota 1: [Nama Anggota 1] / [NIM]", 12, False, 2)
    centered(doc, "Anggota 2: [Nama Anggota 2] / [NIM]", 12, False, 24)
    centered(doc, "Program Studi Sistem Informasi", 12, False, 2)
    centered(doc, "Universitas Nahdlatul Ulama Surabaya", 12, False, 2)
    centered(doc, TODAY, 12, False, 2)
    doc.add_page_break()
    for title, blocks in sections:
        doc.add_heading(title, level=1)
        for block in blocks:
            kind = block[0]
            if kind == "p":
                docx_add_para(doc, block[1])
            elif kind == "bullets":
                docx_add_bullets(doc, block[1])
            elif kind == "table":
                docx_add_table(doc, block[1], block[2])
            elif kind == "figure":
                doc.add_picture(block[1], width=Inches(5.8))
                doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
                cap = doc.add_paragraph()
                cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                cap.paragraph_format.space_after = Pt(8)
                r = cap.add_run(block[2])
                r.font.name = "Times New Roman"
                r.font.size = Pt(10)
                r.italic = True
            elif kind == "refs":
                for i, ref in enumerate(block[1], start=1):
                    docx_add_para(doc, f"[{i}] {ref}")
        doc.add_paragraph()
    doc.save(DOCX_PATH)


def build_pdf():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="BodyJ", parent=styles["Normal"], fontName="TNR", fontSize=12, leading=18, alignment=TA_JUSTIFY, spaceAfter=7))
    styles.add(ParagraphStyle(name="BodyL", parent=styles["Normal"], fontName="TNR", fontSize=12, leading=18, alignment=TA_LEFT, spaceAfter=7))
    styles.add(ParagraphStyle(name="TitleCenter", parent=styles["Title"], fontName="TNR-Bold", fontSize=18, leading=24, alignment=TA_CENTER, spaceAfter=8))
    styles.add(ParagraphStyle(name="SubCenter", parent=styles["Normal"], fontName="TNR", fontSize=12, leading=18, alignment=TA_CENTER, spaceAfter=6))
    styles.add(ParagraphStyle(name="H1x", parent=styles["Heading1"], fontName="TNR-Bold", fontSize=14, leading=21, alignment=TA_LEFT, spaceBefore=12, spaceAfter=8))
    styles.add(ParagraphStyle(name="Caption", parent=styles["Normal"], fontName="TNR-Italic", fontSize=10, leading=13, alignment=TA_CENTER, spaceAfter=8))
    styles.add(ParagraphStyle(name="Cell", parent=styles["Normal"], fontName="TNR", fontSize=9.6, leading=12, alignment=TA_LEFT))
    styles.add(ParagraphStyle(name="CellHead", parent=styles["Normal"], fontName="TNR-Bold", fontSize=9.6, leading=12, alignment=TA_CENTER, textColor=colors.white))

    def para(text, style="BodyJ"):
        return Paragraph(html.escape(str(text)), styles[style])

    def make_table(rows, widths_cm):
        data = []
        for ri, row in enumerate(rows):
            data.append([Paragraph(html.escape(str(c)), styles["CellHead" if ri == 0 else "Cell"]) for c in row])
        t = Table(data, colWidths=[w * cm for w in widths_cm], hAlign="CENTER", repeatRows=1)
        ts = TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), HexColor("#16A34A")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.45, HexColor("#CBD5E1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ])
        for r in range(1, len(rows)):
            if r % 2 == 0:
                ts.add("BACKGROUND", (0, r), (-1, r), HexColor("#F8FAFC"))
        t.setStyle(ts)
        return t

    def make_bullets(items):
        return ListFlowable(
            [ListItem(para(i, "BodyL"), leftIndent=12) for i in items],
            bulletType="bullet",
            leftIndent=22,
            bulletFontName="TNR",
            bulletFontSize=10,
        )

    def add_figure(story, path, caption):
        img = RLImage(path)
        max_w = 13.0 * cm
        ratio = max_w / img.imageWidth
        img.drawWidth = max_w
        img.drawHeight = img.imageHeight * ratio
        story.append(KeepTogether([img, para(caption, "Caption")]))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("TNR", 9)
        canvas.setFillColor(colors.grey)
        canvas.drawString(4 * cm, 1.5 * cm, "JUALIN.AI - Proposal Software Development")
        canvas.drawRightString(A4[0] - 3 * cm, 1.5 * cm, f"Halaman {doc.page}")
        canvas.restoreState()

    story = []
    story.append(Spacer(1, 4.5 * cm))
    story.append(para("PROPOSAL PENGEMBANGAN PERANGKAT LUNAK", "SubCenter"))
    story.append(Paragraph("JUALIN.AI", styles["TitleCenter"]))
    story.append(para("AI Sales Assistant Berbasis Katalog untuk Otomasi Layanan Chat UMKM Mikro", "SubCenter"))
    story.append(Spacer(1, 0.8 * cm))
    story.append(para("Divisi III: Pengembangan Perangkat Lunak (Software Development)", "SubCenter"))
    story.append(para("GEMASTIK DIGINEXS 2026", "SubCenter"))
    story.append(Spacer(1, 1.2 * cm))
    story.append(para("Tim Digiboom", "SubCenter"))
    story.append(para("Ketua: [Nama Ketua] / [NIM]", "SubCenter"))
    story.append(para("Anggota 1: [Nama Anggota 1] / [NIM]", "SubCenter"))
    story.append(para("Anggota 2: [Nama Anggota 2] / [NIM]", "SubCenter"))
    story.append(Spacer(1, 1.2 * cm))
    story.append(para("Program Studi Sistem Informasi", "SubCenter"))
    story.append(para("Universitas Nahdlatul Ulama Surabaya", "SubCenter"))
    story.append(para(TODAY, "SubCenter"))
    story.append(PageBreak())
    for title, blocks in sections:
        story.append(Paragraph(html.escape(title), styles["H1x"]))
        for block in blocks:
            kind = block[0]
            if kind == "p":
                story.append(para(block[1]))
            elif kind == "bullets":
                story.append(make_bullets(block[1]))
            elif kind == "table":
                story.append(make_table(block[1], block[2]))
                story.append(Spacer(1, 0.25 * cm))
            elif kind == "figure":
                add_figure(story, block[1], block[2])
            elif kind == "refs":
                for i, ref in enumerate(block[1], start=1):
                    story.append(para(f"[{i}] {ref}", "BodyL"))
        story.append(Spacer(1, 0.2 * cm))
    doc = SimpleDocTemplate(str(PDF_PATH), pagesize=A4, leftMargin=4 * cm, rightMargin=3 * cm, topMargin=3 * cm, bottomMargin=3 * cm)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def build_notes():
    NOTES_PATH.write_text(
        "Catatan finalisasi submission JUALIN.AI\n"
        "1. Isi nama ketua, anggota, NIM, dan program studi pada cover DOCX/PDF.\n"
        "2. Jalankan GForm dengan pertanyaan pada Template_Kuesioner_Validasi_JUALIN_AI.xlsx. Gunakan jawaban asli, bukan data dummy.\n"
        "3. Setelah respons masuk, salin ke sheet Respon_Asli dan update bagian Lampiran/Ringkasan jika ingin mencantumkan hasil.\n"
        "4. Jalankan uji similaritas; lampirkan hasil maksimal 20% sesuai guidebook.\n"
        "5. File PDF utama untuk upload: SoftwareDevelopment_Digiboom.pdf.\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    build_workbook()
    build_docx()
    build_pdf()
    build_notes()
    from pypdf import PdfReader
    reader = PdfReader(str(PDF_PATH))
    print("CREATED", DOCX_PATH)
    print("CREATED", PDF_PATH, "pages=", len(reader.pages))
    print("CREATED", XLSX_PATH)
    print("CREATED", NOTES_PATH)
    print("ASSETS", [p.name for p in asset_paths])
