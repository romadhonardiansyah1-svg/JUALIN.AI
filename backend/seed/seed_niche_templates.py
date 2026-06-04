"""
JUALIN.AI — Seed Niche Templates
Curated templates for 8 UMKM niches.
Each niche has: AI persona, campaign welcome, abandoned payment follow-up,
repeat buyer offer, FAQ, storefront section, canned replies.

Run: python -m seed.seed_niche_templates
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from models.database import engine, async_session, init_db
from models.template import Template


NICHES = {
    "kuliner": {
        "name": "Kuliner Rumahan",
        "templates": [
            {"type": "prompt", "name": "AI Persona Kuliner", "description": "Persona AI untuk toko kuliner rumahan", "category": "persona",
             "content_json": {"system_prompt": "Kamu adalah asisten jualan makanan rumahan. Bantu customer memilih menu, jelaskan bahan dan rasa. Sarankan paket hemat jika ada. Tanyakan jumlah porsi dan waktu pengiriman. Gaya bicara: ramah dan hangat seperti ibu rumah tangga."}},
            {"type": "campaign", "name": "Welcome Kuliner", "description": "Pesan selamat datang untuk customer baru", "category": "welcome",
             "content_json": {"content": "Halo kak! 👋 Selamat datang di {{store_name}}! Kami menyediakan masakan rumahan yang enak dan higienis. Yuk cek menu kami hari ini! 🍽️"}},
            {"type": "campaign", "name": "Follow-up Pembayaran Kuliner", "description": "Reminder pembayaran pesanan makanan", "category": "payment_followup",
             "content_json": {"content": "Halo kak {{customer_name}}! 😊 Pesanan kamu ({{order_items}}) sudah kami siapkan. Yuk segera selesaikan pembayaran biar bisa langsung kami proses ya! 🍳"}},
            {"type": "campaign", "name": "Repeat Buyer Kuliner", "description": "Promo untuk pelanggan setia", "category": "repeat_buyer",
             "content_json": {"content": "Hai kak {{customer_name}}! 🌟 Terima kasih sudah jadi pelanggan setia kami. Khusus untuk kamu, ada diskon 10% untuk pesanan berikutnya. Pakai kode: SETIA10 ❤️"}},
            {"type": "canned_reply", "name": "FAQ Pengiriman Kuliner", "description": "Jawaban standar soal pengiriman", "category": "faq",
             "content_json": {"content": "Kami kirim via GoSend/GrabExpress setiap hari jam 10-17. Ongkir tergantung jarak ya kak. Untuk area {{area}} biasanya Rp 10-15rb 🏍️"}},
            {"type": "canned_reply", "name": "FAQ Bahan Makanan", "description": "Jawaban soal bahan dan kebersihan", "category": "faq",
             "content_json": {"content": "Semua bahan kami fresh dan dibeli setiap hari di pasar. Kami jaga kebersihan dapur dan semua makanan dimasak dengan higienis. Halal dan tanpa MSG berlebihan ✅"}},
            {"type": "canned_reply", "name": "Pemesanan H-1", "description": "Info pre-order", "category": "general",
             "content_json": {"content": "Untuk pesanan catering/jumlah banyak, bisa pesan H-1 ya kak supaya kami bisa siapkan dengan maksimal 😊"}},
        ]
    },
    "fashion": {
        "name": "Fashion",
        "templates": [
            {"type": "prompt", "name": "AI Persona Fashion", "description": "Persona AI untuk toko fashion", "category": "persona",
             "content_json": {"system_prompt": "Kamu adalah fashion advisor AI. Bantu customer memilih outfit, sarankan size, dan jelaskan bahan. Tanyakan occasion (casual/formal/pesta). Tawarkan mix-and-match. Gaya bicara: stylish dan friendly."}},
            {"type": "campaign", "name": "Welcome Fashion", "description": "Pesan selamat datang fashion", "category": "welcome",
             "content_json": {"content": "Hi babe! 👗✨ Welcome to {{store_name}}! Koleksi terbaru kita udah ready lho. Mau cari outfit buat occasion apa nih? Let us help! 💕"}},
            {"type": "campaign", "name": "Follow-up Pembayaran Fashion", "description": "Reminder pembayaran baju", "category": "payment_followup",
             "content_json": {"content": "Hi kak {{customer_name}}! Outfit pilihan kamu ({{order_items}}) masih nunggu nih 👗 Yuk checkout sebelum kehabisan size-nya ya! ⏰"}},
            {"type": "campaign", "name": "New Arrival Fashion", "description": "Promo koleksi baru", "category": "repeat_buyer",
             "content_json": {"content": "Kak {{customer_name}}! 🆕 Koleksi terbaru udah landing nih. Sebagai valued customer, kamu bisa preview duluan sebelum yang lain. Check it out! 👀"}},
            {"type": "canned_reply", "name": "FAQ Size Chart", "description": "Info ukuran", "category": "faq",
             "content_json": {"content": "Size chart kami: S (LD 88), M (LD 92), L (LD 96), XL (LD 100). Kalau ragu, kasih tau TB dan BB kak, kami bantu pilihkan size yang pas 📏"}},
            {"type": "canned_reply", "name": "FAQ Retur Fashion", "description": "Kebijakan retur", "category": "faq",
             "content_json": {"content": "Kami terima retur/tukar size dalam 3 hari setelah diterima ya kak. Syarat: tag masih menempel, belum dicuci. Ongkir retur ditanggung pembeli 📦"}},
            {"type": "canned_reply", "name": "Estimasi Pengiriman", "description": "Info pengiriman fashion", "category": "general",
             "content_json": {"content": "Pengiriman via JNE/J&T. Jabodetabek 1-2 hari, luar Jawa 3-5 hari kerja. Kami packing rapi dan aman ya kak 📦✨"}},
        ]
    },
    "skincare": {
        "name": "Skincare & Kosmetik",
        "templates": [
            {"type": "prompt", "name": "AI Persona Skincare", "description": "Persona AI untuk toko skincare", "category": "persona",
             "content_json": {"system_prompt": "Kamu adalah beauty consultant AI. Bantu customer memilih skincare sesuai jenis kulit (oily/dry/combination/sensitive). Jelaskan ingredients dan manfaat. JANGAN membuat klaim medis. Sarankan routine step-by-step. Gaya: informatif dan caring."}},
            {"type": "campaign", "name": "Welcome Skincare", "description": "Pesan selamat datang skincare", "category": "welcome",
             "content_json": {"content": "Hi beautiful! ✨ Selamat datang di {{store_name}}. Yuk konsultasi gratis tentang skincare yang cocok untuk kulit kamu. Kulit kamu tipe apa nih? (Oily/Dry/Combination) 💆‍♀️"}},
            {"type": "campaign", "name": "Follow-up Pembayaran Skincare", "description": "Reminder pembayaran skincare", "category": "payment_followup",
             "content_json": {"content": "Hai kak {{customer_name}}! Skincare pilihan kamu udah siap kirim nih 🧴 Yuk selesaikan pembayaran biar bisa segera mulai glow up! ✨"}},
            {"type": "campaign", "name": "Restock Reminder", "description": "Reminder restock skincare", "category": "repeat_buyer",
             "content_json": {"content": "Kak {{customer_name}}! Udah sebulan sejak pembelian terakhir nih 📅 Skincare-nya udah mau habis belum? Yuk restock sebelum kehabisan! Ada bonus sample untuk repeat order 🎁"}},
            {"type": "canned_reply", "name": "FAQ BPOM", "description": "Info legalitas produk", "category": "faq",
             "content_json": {"content": "Semua produk kami sudah terdaftar BPOM dan halal MUI ya kak. Aman digunakan setiap hari ✅ Nomor BPOM bisa dilihat di kemasan produk."}},
            {"type": "canned_reply", "name": "FAQ Kulit Sensitif", "description": "Info untuk kulit sensitif", "category": "faq",
             "content_json": {"content": "Untuk kulit sensitif, kami sarankan patch test dulu di belakang telinga 24 jam sebelum pemakaian. Pilih produk yang fragrance-free dan hypoallergenic ya kak 🌿"}},
            {"type": "canned_reply", "name": "Cara Pakai", "description": "Urutan skincare routine", "category": "general",
             "content_json": {"content": "Urutan skincare: 1️⃣ Cleanser → 2️⃣ Toner → 3️⃣ Serum → 4️⃣ Moisturizer → 5️⃣ Sunscreen (pagi). Mau kami buatkan routine yang cocok untuk kulit kamu?"}},
        ]
    },
    "frozen_food": {
        "name": "Frozen Food",
        "templates": [
            {"type": "prompt", "name": "AI Persona Frozen Food", "description": "Persona AI untuk toko frozen food", "category": "persona",
             "content_json": {"system_prompt": "Kamu adalah asisten jualan frozen food. Bantu customer memilih menu, jelaskan cara penyimpanan dan pemanasan. Sarankan paket hemat untuk stok mingguan. Tekankan keamanan rantai dingin. Gaya: praktis dan informatif."}},
            {"type": "campaign", "name": "Welcome Frozen Food", "description": "Pesan selamat datang frozen food", "category": "welcome",
             "content_json": {"content": "Halo kak! 🧊 Selamat datang di {{store_name}}. Stok freezer kamu udah penuh belum? Kami punya aneka frozen food siap masak untuk seminggu ke depan! 🍗"}},
            {"type": "campaign", "name": "Follow-up Pembayaran Frozen", "description": "Reminder pembayaran frozen food", "category": "payment_followup",
             "content_json": {"content": "Kak {{customer_name}}, pesanan frozen food kamu sudah disiapkan! 🧊 Yuk bayar sekarang biar bisa langsung kami kirim dengan pengiriman dingin. ❄️"}},
            {"type": "campaign", "name": "Weekly Restock", "description": "Promo stok mingguan", "category": "repeat_buyer",
             "content_json": {"content": "Kak {{customer_name}}! Udah seminggu nih. Stok frozen food di freezer masih ada? 🧊 Order sekarang dapat gratis ongkir lho! Min. order 100rb. 📦"}},
            {"type": "canned_reply", "name": "FAQ Pengiriman Frozen", "description": "Info pengiriman frozen food", "category": "faq",
             "content_json": {"content": "Kami kirim pakai styrofoam + ice gel untuk menjaga suhu. Pengiriman same-day untuk area {{area}}. Luar kota via JNE YES + extra ice gel 🧊"}},
            {"type": "canned_reply", "name": "FAQ Penyimpanan", "description": "Cara simpan frozen food", "category": "faq",
             "content_json": {"content": "Simpan di freezer (-18°C) tahan 3 bulan. Setelah dicairkan, jangan dibekukan ulang ya kak. Untuk hasil terbaik, goreng/kukus langsung dari frozen ✅"}},
            {"type": "canned_reply", "name": "Paket Hemat", "description": "Info paket hemat", "category": "general",
             "content_json": {"content": "Paket hemat mingguan: 5 item pilihan cuma {{price}}. Bisa mix sesuai selera kak! Hemat sampai 20% dibanding beli satuan 💰"}},
        ]
    },
    "hampers": {
        "name": "Hampers & Kado",
        "templates": [
            {"type": "prompt", "name": "AI Persona Hampers", "description": "Persona AI untuk toko hampers", "category": "persona",
             "content_json": {"system_prompt": "Kamu adalah gift consultant AI. Bantu customer memilih hampers/kado sesuai occasion (birthday, wedding, Lebaran, Christmas, baby shower). Tanyakan budget dan preferensi penerima. Tawarkan personalisasi (kartu ucapan, wrapping). Gaya: warm dan creative."}},
            {"type": "campaign", "name": "Welcome Hampers", "description": "Pesan selamat datang hampers", "category": "welcome",
             "content_json": {"content": "Hai kak! 🎁 Selamat datang di {{store_name}}. Mau kasih surprise untuk orang tersayang? Cerita dulu dongoccasion-nya apa, kami bantu pilihkan hampers terbaik! 💝"}},
            {"type": "campaign", "name": "Follow-up Pembayaran Hampers", "description": "Reminder pembayaran hampers", "category": "payment_followup",
             "content_json": {"content": "Kak {{customer_name}}! Hampers pesanan kamu udah siap kami rangkai nih 🎀 Yuk bayar sekarang biar bisa sampai tepat waktu ya! ⏰"}},
            {"type": "campaign", "name": "Seasonal Hampers", "description": "Promo hampers musiman", "category": "repeat_buyer",
             "content_json": {"content": "Kak {{customer_name}}! 🎄 Musim liburan udah dekat nih. Yuk pesan hampers dari sekarang biar gak kehabisan. Early bird diskon 15%! 🎁"}},
            {"type": "canned_reply", "name": "FAQ Custom Hampers", "description": "Info custom hampers", "category": "faq",
             "content_json": {"content": "Bisa custom isi hampers sesuai budget kak! Mulai dari 100rb. Tinggal bilang budget dan tema-nya, kami buatkan kombinasi terbaik 🎨"}},
            {"type": "canned_reply", "name": "FAQ Kartu Ucapan", "description": "Info kartu ucapan", "category": "faq",
             "content_json": {"content": "Setiap hampers sudah termasuk kartu ucapan gratis ya kak. Kirim aja pesan yang mau ditulis, kami cetakkan dengan cantik 💌"}},
            {"type": "canned_reply", "name": "FAQ Pengiriman Hampers", "description": "Info pengiriman hampers", "category": "general",
             "content_json": {"content": "Pengiriman: Jabodetabek same-day (order sebelum jam 12). Luar kota 2-3 hari. Packing aman anti penyok. Bisa kirim langsung ke alamat penerima 📦🎀"}},
        ]
    },
    "digital": {
        "name": "Digital Product",
        "templates": [
            {"type": "prompt", "name": "AI Persona Digital", "description": "Persona AI untuk toko produk digital", "category": "persona",
             "content_json": {"system_prompt": "Kamu adalah asisten jualan produk digital. Bantu customer memilih paket/layanan (voucher, akun premium, template, course). Jelaskan cara penggunaan dan benefit. Tekankan pengiriman instan via chat. Gaya: tech-savvy dan helpful."}},
            {"type": "campaign", "name": "Welcome Digital", "description": "Pesan selamat datang digital product", "category": "welcome",
             "content_json": {"content": "Hey! 📱 Welcome to {{store_name}}. Semua produk digital kami dikirim instan via chat setelah pembayaran. Mau cari apa nih? 🚀"}},
            {"type": "campaign", "name": "Follow-up Digital", "description": "Reminder pembayaran produk digital", "category": "payment_followup",
             "content_json": {"content": "Hai {{customer_name}}! Produk digital kamu siap dikirim instan setelah pembayaran ya. Yuk bayar sekarang biar langsung bisa dipakai! ⚡"}},
            {"type": "campaign", "name": "Bundle Promo Digital", "description": "Promo bundle", "category": "repeat_buyer",
             "content_json": {"content": "{{customer_name}}! 🎮 Ada promo bundle khusus pelanggan setia nih. Beli 2 produk diskon 25%! Berlaku sampai akhir bulan. Cek sekarang! 💰"}},
            {"type": "canned_reply", "name": "FAQ Pengiriman Digital", "description": "Info pengiriman digital", "category": "faq",
             "content_json": {"content": "Produk digital dikirim via WhatsApp/Email dalam 1-5 menit setelah pembayaran dikonfirmasi. Kalau lebih dari 15 menit belum terima, langsung chat ya! ⚡"}},
            {"type": "canned_reply", "name": "FAQ Garansi Digital", "description": "Garansi produk digital", "category": "faq",
             "content_json": {"content": "Semua produk digital kami bergaransi penuh. Kalau ada masalah, langsung hubungi kami dan kami ganti tanpa ribet ✅"}},
            {"type": "canned_reply", "name": "Cara Pakai", "description": "Tutorial penggunaan", "category": "general",
             "content_json": {"content": "Setelah menerima produk, ikuti panduan yang kami kirim ya. Kalau bingung, bisa video call gratis untuk kami bantu step by step 📱"}},
        ]
    },
    "jasa": {
        "name": "Jasa Lokal",
        "templates": [
            {"type": "prompt", "name": "AI Persona Jasa", "description": "Persona AI untuk jasa lokal", "category": "persona",
             "content_json": {"system_prompt": "Kamu adalah asisten booking jasa lokal. Bantu customer menjelaskan layanan, estimasi harga, dan jadwal. Tanyakan lokasi, waktu yang diinginkan, dan detail kebutuhan spesifik. Selalu konfirmasi ulang sebelum booking. Gaya: profesional dan terpercaya."}},
            {"type": "campaign", "name": "Welcome Jasa", "description": "Pesan selamat datang jasa lokal", "category": "welcome",
             "content_json": {"content": "Halo kak! 🔧 Selamat datang di {{store_name}}. Butuh jasa apa nih? Cerita aja kebutuhannya, kami bantu carikan solusi terbaik! 👍"}},
            {"type": "campaign", "name": "Follow-up Booking Jasa", "description": "Reminder pembayaran jasa", "category": "payment_followup",
             "content_json": {"content": "Kak {{customer_name}}, booking jasa kamu sudah dikonfirmasi! 📋 Yuk selesaikan DP/pembayaran supaya jadwal kamu aman ya. ✅"}},
            {"type": "campaign", "name": "Repeat Service", "description": "Promo jasa berkala", "category": "repeat_buyer",
             "content_json": {"content": "Kak {{customer_name}}! Sudah waktunya service rutin nih 🔧 Booking sekarang dapat diskon langganan 10%! Hubungi kami untuk jadwal. 📅"}},
            {"type": "canned_reply", "name": "FAQ Area Layanan", "description": "Info area jangkauan", "category": "faq",
             "content_json": {"content": "Kami melayani area {{area}} dan sekitarnya (radius 15km). Untuk luar area, bisa ditambah biaya transport ya kak 🚗"}},
            {"type": "canned_reply", "name": "FAQ Garansi Jasa", "description": "Garansi pekerjaan", "category": "faq",
             "content_json": {"content": "Semua pekerjaan kami bergaransi 7 hari. Kalau ada masalah setelah pengerjaan, kami datang lagi tanpa biaya tambahan ya kak ✅"}},
            {"type": "canned_reply", "name": "Estimasi Harga", "description": "Info estimasi harga", "category": "general",
             "content_json": {"content": "Harga tergantung jenis pekerjaan dan tingkat kesulitan ya kak. Untuk estimasi yang lebih akurat, bisa kirim foto/video kondisinya? 📸"}},
        ]
    },
    "reseller": {
        "name": "Reseller & Dropship",
        "templates": [
            {"type": "prompt", "name": "AI Persona Reseller", "description": "Persona AI untuk reseller/dropshipper", "category": "persona",
             "content_json": {"system_prompt": "Kamu adalah asisten jualan untuk toko reseller/dropship. Bantu customer memilih produk, jelaskan keunggulan harga reseller. Tawarkan paket bundling. Tekankan proses pengiriman yang cepat. Gaya: to-the-point dan trustworthy."}},
            {"type": "campaign", "name": "Welcome Reseller", "description": "Pesan selamat datang reseller", "category": "welcome",
             "content_json": {"content": "Halo kak! 📦 Welcome to {{store_name}}! Harga kami bersaing karena ambil langsung dari supplier. Mau cari produk apa nih? 🔥"}},
            {"type": "campaign", "name": "Follow-up Pembayaran Reseller", "description": "Reminder pembayaran", "category": "payment_followup",
             "content_json": {"content": "Kak {{customer_name}}! Pesanan kamu ({{order_items}}) ready stock nih. Yuk bayar sekarang biar bisa langsung kami proses dan kirim hari ini! 📦🚀"}},
            {"type": "campaign", "name": "Restock Alert", "description": "Info restock produk", "category": "repeat_buyer",
             "content_json": {"content": "Kak {{customer_name}}! 🔔 Produk bestseller udah restock nih. Stock terbatas, siapa cepat dia dapat! Order sekarang free ongkir min 200rb 📦"}},
            {"type": "canned_reply", "name": "FAQ Dropship", "description": "Info dropship", "category": "faq",
             "content_json": {"content": "Bisa dropship kak! Kami kirim pakai nama toko kamu, tanpa invoice harga supplier. Syarat: min order 3 pcs. Daftar gratis! 📦"}},
            {"type": "canned_reply", "name": "FAQ Harga Grosir", "description": "Info harga grosir", "category": "faq",
             "content_json": {"content": "Harga grosir: 3-11 pcs diskon 10%, 12+ pcs diskon 20%. Makin banyak makin murah kak! Chat untuk pricelist lengkap 💰"}},
            {"type": "canned_reply", "name": "Pengiriman", "description": "Info pengiriman reseller", "category": "general",
             "content_json": {"content": "Pengiriman H+1 setelah pembayaran (kecuali Minggu). Support: JNE, J&T, SiCepat, GoSend (Jabodetabek). Resi dikirim via WA otomatis 📦✅"}},
        ]
    },
}


async def seed_niche_templates():
    """Seed curated templates for all niches."""
    await init_db()

    async with async_session() as db:
        total = 0
        for niche_id, niche_data in NICHES.items():
            pack_id = f"niche_{niche_id}"

            for t_data in niche_data["templates"]:
                # Check if template already exists
                existing = await db.execute(
                    select(Template).where(
                        Template.niche == niche_id,
                        Template.name == t_data["name"],
                    )
                )
                if existing.scalar_one_or_none():
                    continue

                template = Template(
                    type=t_data["type"],
                    name=t_data["name"],
                    description=t_data["description"],
                    category=t_data["category"],
                    niche=niche_id,
                    pack_id=pack_id,
                    content_json=t_data["content_json"],
                    tags=[niche_id, t_data["category"]],
                    is_public=True,
                    created_by=None,
                )
                db.add(template)
                total += 1

        await db.commit()
        print(f"🎯 Seeded {total} niche templates across {len(NICHES)} niches")
        for niche_id, niche_data in NICHES.items():
            print(f"  ✅ {niche_data['name']}: {len(niche_data['templates'])} templates")


if __name__ == "__main__":
    asyncio.run(seed_niche_templates())
