"use client";
import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import styles from "./page.module.css";

export default function LandingPage() {
  const [email, setEmail] = useState("");
  const [activeAccordion, setActiveAccordion] = useState(null);
  const [isScrolled, setIsScrolled] = useState(false);
  const [visibleSections, setVisibleSections] = useState(new Set());

  // Navbar scroll effect
  useEffect(() => {
    const handleScroll = () => setIsScrolled(window.scrollY > 20);
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  // Intersection observer for scroll animations
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setVisibleSections((prev) => new Set([...prev, entry.target.id]));
          }
        });
      },
      { threshold: 0.15 }
    );

    document.querySelectorAll("[data-animate]").forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, []);

  const features = [
    { icon: "💬", title: "Chat AI Otomatis", desc: "Balas chat customer 24/7 dengan AI yang paham katalog produkmu. Respons instan, natural, dan sopan.", color: "--primary" },
    { icon: "📦", title: "Katalog Cerdas", desc: "AI memahami semua produk, harga, stok, dan variasi secara real-time dengan semantic search.", color: "--secondary" },
    { icon: "🛒", title: "Order dari Chat", desc: "Percakapan otomatis jadi pesanan tanpa input manual. Customer tinggal bilang mau pesan.", color: "--tertiary" },
    { icon: "💳", title: "Pembayaran Midtrans", desc: "Terima QRIS, transfer bank, e-wallet, dan kartu melalui Midtrans Snap.", color: "--stat-orange" },
    { icon: "📊", title: "Dashboard Analitik", desc: "Conversion funnel, sales stages, customer insights, dan tren penjualan real-time.", color: "--info" },
    { icon: "🧠", title: "Customer Memory", desc: "AI mengingat preferensi dan histori customer. Pelanggan berulang mendapat treatment VIP.", color: "--primary" },
  ];

  const pricing = [
    { name: "Free", price: "Rp 0", period: "selamanya", chat: "50 chat/bln", produk: "10 produk", features: ["Chat AI basic", "1 toko", "Dashboard"], popular: false },
    { name: "Starter", price: "Rp 49K", period: "/bulan", chat: "500 chat/bln", produk: "50 produk", features: ["Semua fitur Free", "Follow-up otomatis", "Analytics basic", "QRIS Payment"], popular: false },
    { name: "Pro", price: "Rp 299K", period: "/bulan", chat: "2.000 chat/bln", produk: "200 produk", features: ["Semua fitur Starter", "Semantic search", "Customer memory", "SSE Streaming", "Priority support"], popular: true },
    { name: "Bisnis", price: "Rp 799K", period: "/bulan", chat: "10.000 chat/bln", produk: "Unlimited", features: ["Semua fitur Pro", "API access", "Custom AI style", "Multi-payment", "Dedicated support"], popular: false },
  ];

  const faqs = [
    { q: "Apakah benar-benar gratis?", a: "Ya! Plan Free memberikan 50 chat AI per bulan tanpa biaya, selamanya. Tidak perlu kartu kredit untuk mendaftar." },
    { q: "Bagaimana AI bisa paham produk saya?", a: "Cukup tambahkan produk ke katalog, AI akan diarahkan menggunakan data katalog dan tetap dapat keliru. Selalu periksa respons sebelum dipublikasikan." },
    { q: "Apakah AI bisa salah jawab?", a: "AI diarahkan menggunakan data katalog dan tetap dapat keliru. Jika pertanyaan di luar konteks, AI diinstruksikan meminta customer menghubungi langsung, tetapi kesalahan tetap mungkin." },
    { q: "Bagaimana customer mengakses chat?", a: "Setiap toko mendapat link unik (contoh: jualin.ai/chat/nama-toko). Tinggal share ke customer atau pasang di bio Instagram/WhatsApp." },
    { q: "Bagaimana cara pembayaran?", a: "Pembayaran diproses melalui Midtrans Snap yang mendukung QRIS, transfer bank, e-wallet, dan metode lain yang tersedia di akun merchant." },
  ];

  const sectionClass = (id) =>
    `${visibleSections.has(id) ? styles.sectionVisible : styles.sectionHidden}`;

  return (
    <div className={styles.landing}>
      {/* ── Navbar ── */}
      <nav className={`${styles.navbar} ${isScrolled ? styles.navScrolled : ""}`}>
        <div className={`container ${styles.navContent}`}>
          <Link href="/" className={styles.logo}>
            <span className={styles.logoIcon}>🤖</span>
            <span className={styles.logoText}>JUALIN.AI</span>
          </Link>
          <div className={styles.navLinks}>
            <a href="#fitur">Fitur</a>
            <a href="#harga">Harga</a>
            <a href="#faq">FAQ</a>
          </div>
          <div className={styles.navActions}>
            <Link href="/login" className="btn btn-ghost">Login</Link>
            <Link href="/register" className="btn btn-primary">Coba Gratis</Link>
          </div>
        </div>
      </nav>

      {/* ── Hero ── */}
      <section className={styles.hero}>
        <div className={styles.heroBg}>
          <div className={styles.heroGlow1}></div>
          <div className={styles.heroGlow2}></div>
          <div className={styles.heroGrid}></div>
        </div>
        <div className="container">
          <div className={styles.heroContent}>
            <div className={styles.heroText}>
              <div className={styles.heroBadge}>
                <span className={styles.badgeDot}></span>
                🚀 AI-Powered Sales Assistant
              </div>
              <h1 className={styles.heroTitle}>
                Otomasi Chat Penjualan
                <br />
                <span className={styles.heroHighlight}>dengan AI Cerdas</span>
              </h1>
              <p className={styles.heroDesc}>
                JUALIN.AI membantu UMKM melayani customer 24/7, memproses pesanan dari chat,
                dan follow-up pembayaran secara otomatis — semua dengan AI yang paham produkmu.
              </p>
              <div className={styles.heroButtons}>
                <Link href="/register" className="btn btn-primary btn-lg">
                  Mulai Gratis →
                </Link>
                <Link href="/chat/toko-sari-fashion" className="btn btn-outline btn-lg">
                  ▶ Lihat Demo
                </Link>
              </div>
              <div className={styles.trustBadges}>
                <span>✓ Gratis selamanya</span>
                <span>✓ Tanpa kartu kredit</span>
                <span>✓ Setup terpandu</span>
              </div>
            </div>
            <div className={styles.heroVisual}>
              <div className={styles.chatPreview}>
                <div className={styles.chatHeader}>
                  <div className={styles.chatHeaderInfo}>
                    <span className={styles.chatDot}></span>
                    <span>Toko Sari Fashion · Online</span>
                  </div>
                  <span className={styles.chatBadge}>AI ⚡</span>
                </div>
                <div className={styles.chatMessages}>
                  <div className="chat-bubble customer">Kak, ada baju buat kondangan?</div>
                  <div className="chat-bubble ai">
                    Hai kak! Ada dong 😊 Kami punya:
                    <br />1. Baju Pink Satin — <strong>Rp 89.000</strong>
                    <br />2. Dress Emerald — <strong>Rp 189.000</strong>
                    <br />Mau lihat yang mana?
                  </div>
                  <div className="chat-bubble customer">Yang pink, ada ukuran M?</div>
                  <div className="chat-bubble ai">
                    Baju Pink Satin ukuran M <strong>ready stock</strong> kak! 🎉
                    <br />Mau langsung diorderkan? Saya buatkan pesanannya ya 🛒
                  </div>
                </div>
                <div className={styles.chatInputPreview}>
                  <span>Ketik pesan...</span>
                  <span className={styles.sendIcon}>➤</span>
                </div>
              </div>
              <div className={styles.floatingBadge1}>⚡ Respons Cepat</div>
              <div className={styles.floatingBadge2}>🛒 Auto Order</div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Social Proof Stats — truthful, no unverified claims ── */}
      <section className={styles.stats}>
        <div className="container">
          <div className={styles.statsGrid}>
            <div className={styles.statItem}>
              <span className={styles.statNumber}>Cepat</span>
              <span className={styles.statLabel}>Respons Chat Terarah</span>
            </div>
            <div className={styles.statDivider}></div>
            <div className={styles.statItem}>
              <span className={styles.statNumber}>Siaga</span>
              <span className={styles.statLabel}>Dapat Membantu di Luar Jam Operasional</span>
            </div>
            <div className={styles.statDivider}></div>
            <div className={styles.statItem}>
              <span className={styles.statNumber}>Rp 0</span>
              <span className={styles.statLabel}>Biaya Awal</span>
            </div>
            <div className={styles.statDivider}></div>
            <div className={styles.statItem}>
              <span className={styles.statNumber}>Panduan</span>
              <span className={styles.statLabel}>Setup Terpandu</span>
            </div>
          </div>
        </div>
      </section>

      {/* ── Features ── */}
      <section className={styles.features} id="fitur" data-animate>
        <div className={`container ${sectionClass("fitur")}`}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionBadge}>✨ Fitur</span>
            <h2 className={styles.sectionTitle}>Fitur yang Membuat Jualanmu Makin Cerdas</h2>
            <p className={styles.sectionDesc}>
              Semua tools yang dibutuhkan UMKM untuk otomasi penjualan via chat dalam satu platform
            </p>
          </div>
          <div className={styles.featuresGrid}>
            {features.map((f, i) => (
              <div key={i} className={styles.featureCard} style={{ animationDelay: `${i * 0.1}s` }}>
                <div className={styles.featureIconWrap}>
                  <span className={styles.featureIcon}>{f.icon}</span>
                </div>
                <h3>{f.title}</h3>
                <p>{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── How It Works ── */}
      <section className={styles.howItWorks} data-animate id="how">
        <div className={`container ${sectionClass("how")}`}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionBadge}>🎯 Cara Kerja</span>
            <h2 className={styles.sectionTitle}>3 Langkah Mudah</h2>
          </div>
          <div className={styles.stepsGrid}>
            <div className={styles.step}>
              <div className={styles.stepNum}>1</div>
              <h3>Daftar & Input Katalog</h3>
              <p>Buat akun gratis, lalu tambahkan produk, harga, dan stok ke katalog AI kamu.</p>
            </div>
            <div className={styles.stepArrow}>→</div>
            <div className={styles.step}>
              <div className={styles.stepNum}>2</div>
              <h3>Share Link Chat</h3>
              <p>Bagikan link chat AI toko kamu ke customer via Instagram, WhatsApp, atau bio.</p>
            </div>
            <div className={styles.stepArrow}>→</div>
            <div className={styles.step}>
              <div className={styles.stepNum}>3</div>
              <h3>AI Jualan 24/7</h3>
              <p>AI melayani customer, menjawab pertanyaan, dan memproses pesanan otomatis.</p>
            </div>
          </div>
        </div>
      </section>

      {/* ── Pricing ── */}
      <section className={styles.pricing} id="harga" data-animate>
        <div className={`container ${sectionClass("harga")}`}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionBadge}>💰 Harga</span>
            <h2 className={styles.sectionTitle}>Harga Terjangkau untuk Semua UMKM</h2>
            <p className={styles.sectionDesc}>
              Mulai gratis, upgrade kapan saja sesuai kebutuhan bisnismu
            </p>
          </div>
          <div className={styles.pricingGrid}>
            {pricing.map((p, i) => (
              <div key={i} className={`${styles.pricingCard} ${p.popular ? styles.pricingPopular : ""}`}>
                {p.popular && <div className={styles.popularBadge}>⭐ Most Popular</div>}
                <h3 className={styles.pricingName}>{p.name}</h3>
                <div className={styles.pricingPrice}>
                  <span className={styles.priceAmount}>{p.price}</span>
                  <span className={styles.pricePeriod}>{p.period}</span>
                </div>
                <p className={styles.pricingLimit}>{p.chat} · {p.produk}</p>
                <div className={styles.pricingDivider}></div>
                <ul className={styles.pricingFeatures}>
                  {p.features.map((f, j) => (
                    <li key={j}><span className={styles.checkIcon}>✓</span> {f}</li>
                  ))}
                </ul>
                <Link href="/register" className={`btn ${p.popular ? "btn-primary" : "btn-outline"}`} style={{ width: "100%", marginTop: "auto" }}>
                  {p.price === "Rp 0" ? "Mulai Gratis" : "Pilih Plan"}
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── FAQ ── */}
      <section className={styles.faq} id="faq" data-animate>
        <div className={`container ${sectionClass("faq")}`}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionBadge}>❓ FAQ</span>
            <h2 className={styles.sectionTitle}>Pertanyaan yang Sering Ditanyakan</h2>
          </div>
          <div className={styles.faqList}>
            {faqs.map((faq, i) => (
              <div key={i} className={`${styles.faqItem} ${activeAccordion === i ? styles.faqOpen : ""}`}>
                <button className={styles.faqQuestion} onClick={() => setActiveAccordion(activeAccordion === i ? null : i)}>
                  <span>{faq.q}</span>
                  <span className={styles.faqChevron}>{activeAccordion === i ? "−" : "+"}</span>
                </button>
                <div className={styles.faqAnswer}>
                  <p>{faq.a}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA ── */}
      <section className={styles.cta}>
        <div className={styles.ctaBg}></div>
        <div className="container text-center" style={{ position: "relative", zIndex: 1 }}>
          <h2 className={styles.ctaTitle}>Mulai Jual Lebih Cerdas Hari Ini</h2>
          <p className={styles.ctaDesc}>Daftar gratis dan aktifkan AI Sales Assistant dalam 5 menit</p>
          <div className={styles.ctaForm}>
            <input
              type="email"
              className="input"
              placeholder="Email kamu..."
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={{ maxWidth: 360 }}
            />
            <Link href={`/register${email ? `?email=${email}` : ""}`} className="btn btn-primary btn-lg">
              Daftar Gratis →
            </Link>
          </div>
          <p className={styles.ctaNote}>Dirancang untuk UMKM Indonesia 🇮🇩</p>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className={styles.footer}>
        <div className="container">
          <div className={styles.footerContent}>
            <div>
              <div className={styles.logo}>
                <span className={styles.logoIcon}>🤖</span>
                <span className={styles.logoText}>JUALIN.AI</span>
              </div>
              <p className="text-muted text-sm mt-2">AI Sales Assistant untuk UMKM Mikro Indonesia</p>
            </div>
            <div className={styles.footerLinks}>
              <a href="#fitur">Fitur</a>
              <a href="#harga">Harga</a>
              <a href="#faq">FAQ</a>
              <Link href="/login">Login</Link>
            </div>
            <p className="text-muted text-sm">© 2026 Tim Digiboom — GEMASTIK DIGINEXS</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
