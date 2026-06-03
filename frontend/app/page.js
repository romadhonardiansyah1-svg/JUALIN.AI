"use client";
import { useState } from "react";
import Link from "next/link";
import styles from "./page.module.css";

export default function LandingPage() {
  const [email, setEmail] = useState("");

  const features = [
    { icon: "💬", title: "Chat AI Otomatis", desc: "Balas chat customer 24/7 dengan AI yang paham katalog produkmu" },
    { icon: "📦", title: "Katalog Cerdas", desc: "AI memahami semua produk, harga, dan stok secara real-time" },
    { icon: "🛒", title: "Buat Order dari Chat", desc: "Percakapan otomatis jadi pesanan tanpa input manual" },
    { icon: "🔔", title: "Follow-up Otomatis", desc: "AI ingatkan customer yang belum bayar secara sopan" },
    { icon: "📊", title: "Dashboard Analitik", desc: "Lihat data penjualan, produk terlaris, dan tren" },
    { icon: "🏪", title: "Multi-Toko", desc: "Satu platform untuk banyak toko dengan data terisolasi" },
  ];

  const pricing = [
    { name: "Free", price: "Rp 0", period: "selamanya", chat: "50 chat/bulan", produk: "10 produk", features: ["Chat AI basic", "1 toko", "Dashboard"], popular: false },
    { name: "Starter", price: "Rp 49K", period: "/bulan", chat: "500 chat/bulan", produk: "50 produk", features: ["Semua fitur Free", "Follow-up otomatis", "Analytics basic"], popular: false },
    { name: "Pro", price: "Rp 299K", period: "/bulan", chat: "2.000 chat/bulan", produk: "200 produk", features: ["Semua fitur Starter", "Semantic search", "Customer memory", "Priority support"], popular: true },
    { name: "Bisnis", price: "Rp 799K", period: "/bulan", chat: "10.000 chat/bulan", produk: "Unlimited", features: ["Semua fitur Pro", "API access", "Custom AI style", "Dedicated support"], popular: false },
  ];

  return (
    <div className={styles.landing}>
      {/* Navbar */}
      <nav className={styles.navbar}>
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

      {/* Hero */}
      <section className={styles.hero}>
        <div className="container">
          <div className={styles.heroContent}>
            <div className={styles.heroText}>
              <div className={styles.heroBadge}>🚀 AI-Powered Sales Assistant</div>
              <h1 className={styles.heroTitle}>
                AI Sales Assistant
                <br />
                <span className={styles.heroHighlight}>untuk UMKM Mikro</span>
              </h1>
              <p className={styles.heroDesc}>
                Otomasi chat penjualan, proses pesanan, dan follow-up pembayaran
                dengan AI yang memahami katalog produkmu. Respons 300× lebih cepat.
              </p>
              <div className={styles.heroButtons}>
                <Link href="/register" className="btn btn-primary btn-lg">
                  Mulai Gratis →
                </Link>
                <Link href="/chat/toko-sari-fashion" className="btn btn-outline btn-lg">
                  Lihat Demo
                </Link>
              </div>
              <p className={styles.heroNote}>✓ Gratis selamanya untuk 50 chat/bulan · Tanpa kartu kredit</p>
            </div>
            <div className={styles.heroVisual}>
              <div className={styles.chatPreview}>
                <div className={styles.chatHeader}>
                  <span className={styles.chatDot} style={{ background: "#22C55E" }}></span>
                  <span>Toko Sari Fashion · Online</span>
                </div>
                <div className={styles.chatMessages}>
                  <div className="chat-bubble customer">Kak, ada baju buat kondangan?</div>
                  <div className="chat-bubble ai">
                    Hai kak! Ada dong 😊 Kami punya:
                    <br />1. Baju Pink Satin — Rp 89.000
                    <br />2. Dress Emerald — Rp 189.000
                    <br />Mau lihat yang mana?
                  </div>
                  <div className="chat-bubble customer">Yang pink, ada ukuran M?</div>
                  <div className="typing-indicator">
                    <span></span><span></span><span></span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Stats */}
      <section className={styles.stats}>
        <div className="container">
          <div className={styles.statsGrid}>
            <div className={styles.statItem}>
              <span className={styles.statNumber}>300×</span>
              <span className={styles.statLabel}>Lebih Cepat Respons</span>
            </div>
            <div className={styles.statItem}>
              <span className={styles.statNumber}>100%</span>
              <span className={styles.statLabel}>Chat Terbalas</span>
            </div>
            <div className={styles.statItem}>
              <span className={styles.statNumber}>Rp 0</span>
              <span className={styles.statLabel}>Biaya Awal</span>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className={styles.features} id="fitur">
        <div className="container">
          <h2 className={styles.sectionTitle}>Fitur yang Membuat Jualanmu Makin Cerdas</h2>
          <p className={`${styles.sectionDesc} text-muted`}>
            Semua yang dibutuhkan UMKM untuk otomasi penjualan via chat
          </p>
          <div className={styles.featuresGrid}>
            {features.map((f, i) => (
              <div key={i} className={styles.featureCard}>
                <span className={styles.featureIcon}>{f.icon}</span>
                <h3>{f.title}</h3>
                <p>{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section className={styles.pricing} id="harga">
        <div className="container">
          <h2 className={styles.sectionTitle}>Harga Terjangkau untuk Semua UMKM</h2>
          <p className={`${styles.sectionDesc} text-muted`}>
            Mulai gratis, upgrade kapan saja sesuai kebutuhan
          </p>
          <div className={styles.pricingGrid}>
            {pricing.map((p, i) => (
              <div key={i} className={`${styles.pricingCard} ${p.popular ? styles.pricingPopular : ""}`}>
                {p.popular && <div className={styles.popularBadge}>Popular</div>}
                <h3>{p.name}</h3>
                <div className={styles.pricingPrice}>
                  <span className={styles.priceAmount}>{p.price}</span>
                  <span className={styles.pricePeriod}>{p.period}</span>
                </div>
                <p className={styles.pricingLimit}>{p.chat} · {p.produk}</p>
                <ul className={styles.pricingFeatures}>
                  {p.features.map((f, j) => (
                    <li key={j}>✓ {f}</li>
                  ))}
                </ul>
                <Link href="/register" className={`btn ${p.popular ? "btn-primary" : "btn-outline"}`} style={{ width: "100%" }}>
                  {p.price === "Rp 0" ? "Mulai Gratis" : "Pilih Plan"}
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className={styles.cta}>
        <div className="container text-center">
          <h2>Mulai Jual Lebih Cerdas Hari Ini</h2>
          <p className="text-muted mt-2">Daftar gratis dan aktifkan AI Sales Assistant dalam 5 menit</p>
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
        </div>
      </section>

      {/* Footer */}
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
            <p className="text-muted text-sm">© 2026 Tim Digiboom — GEMASTIK DIGINEXS</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
