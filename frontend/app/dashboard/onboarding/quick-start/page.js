"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import styles from "./quick-start.module.css";

const NICHES = [
  { id: "kuliner", icon: "🍳", name: "Kuliner" },
  { id: "fashion", icon: "👗", name: "Fashion" },
  { id: "skincare", icon: "✨", name: "Skincare" },
  { id: "frozen_food", icon: "🧊", name: "Frozen Food" },
  { id: "hampers", icon: "🎁", name: "Hampers" },
  { id: "digital", icon: "📱", name: "Digital" },
  { id: "jasa", icon: "🔧", name: "Jasa Lokal" },
  { id: "reseller", icon: "📦", name: "Reseller" },
];

const TONES = [
  { id: "santai", emoji: "😊", name: "Santai", desc: "Ramah & casual" },
  { id: "formal", emoji: "👔", name: "Formal", desc: "Profesional & sopan" },
  { id: "gaul", emoji: "🤙", name: "Gaul", desc: "Asyik & kekinian" },
];

const STEPS = [
  { key: "toko", label: "Toko" },
  { key: "produk", label: "Produk" },
  { key: "ai", label: "AI" },
  { key: "preview", label: "Preview" },
  { key: "golive", label: "Go Live" },
];

export default function QuickStartPage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Step 1: Toko
  const [niche, setNiche] = useState("");
  const [sellerGoal, setSellerGoal] = useState("");

  // Step 2: Produk
  const [products, setProducts] = useState([
    { nama: "", harga: "", deskripsi: "" },
  ]);

  // Step 3: AI
  const [tone, setTone] = useState("santai");

  // Step 4: Preview
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState("");
  const [simulating, setSimulating] = useState(false);

  // Step 5: Result
  const [result, setResult] = useState(null);

  const addProduct = () => {
    if (products.length < 5) {
      setProducts([...products, { nama: "", harga: "", deskripsi: "" }]);
    }
  };

  const removeProduct = (idx) => {
    setProducts(products.filter((_, i) => i !== idx));
  };

  const updateProduct = (idx, field, value) => {
    const updated = [...products];
    updated[idx] = { ...updated[idx], [field]: value };
    setProducts(updated);
  };

  const handleQuickStart = async () => {
    setLoading(true);
    setError("");
    try {
      const validProducts = products.filter((p) => p.nama.trim());
      const res = await api.quickStartOnboarding({
        store_category: niche,
        seller_goal: sellerGoal,
        tone: tone,
        top_products: validProducts.map((p) => ({
          nama: p.nama,
          harga: parseFloat(p.harga) || 0,
          deskripsi: p.deskripsi,
        })),
      });
      setResult(res);
      setStep(4); // Go to completion
    } catch (e) {
      setError(e.message || "Gagal menyelesaikan quick-start");
    } finally {
      setLoading(false);
    }
  };

  const handleSimulateChat = async () => {
    if (!chatInput.trim()) return;
    const userMsg = chatInput.trim();
    setChatMessages((prev) => [...prev, { role: "user", text: userMsg }]);
    setChatInput("");
    setSimulating(true);

    try {
      const res = await api.simulateChat({ message: userMsg });
      setChatMessages((prev) => [
        ...prev,
        { role: "ai", text: res.message, source: res.source },
      ]);
    } catch {
      setChatMessages((prev) => [
        ...prev,
        { role: "ai", text: "Maaf, terjadi error saat simulasi. Coba lagi ya!", source: "error" },
      ]);
    } finally {
      setSimulating(false);
    }
  };

  const canProceed = () => {
    switch (step) {
      case 0: return niche !== "";
      case 1: return products.some((p) => p.nama.trim());
      case 2: return tone !== "";
      case 3: return true;
      default: return false;
    }
  };

  const nextStep = () => {
    if (step === 3) {
      handleQuickStart();
    } else if (step < 4) {
      setStep(step + 1);
      if (step === 2) {
        // Auto-start simulation when entering preview
        setChatMessages([]);
      }
    }
  };

  return (
    <div className={styles.container}>
      {/* Progress Indicator */}
      <div className={styles.progress}>
        {STEPS.map((s, i) => (
          <div
            key={s.key}
            className={`${styles.progressStep} ${i === step ? "active" : ""} ${i < step ? "done" : ""}`}
            onClick={() => i < step && setStep(i)}
          >
            <div className={styles.progressDot}>
              {i < step ? "✓" : i + 1}
            </div>
            <span className={styles.progressLabel}>{s.label}</span>
            {i < STEPS.length - 1 && <div className={styles.progressLine} />}
          </div>
        ))}
      </div>

      {error && <div className={styles.errorBox}>⚠️ {error}</div>}

      {/* Step 1: Toko & Kategori */}
      {step === 0 && (
        <div className={styles.stepCard}>
          <h2 className={styles.stepTitle}>Kategori Toko Kamu</h2>
          <p className={styles.stepDesc}>Pilih yang paling sesuai dengan jualan kamu</p>

          <div className={styles.nicheGrid}>
            {NICHES.map((n) => (
              <div
                key={n.id}
                className={`${styles.nicheCard} ${niche === n.id ? styles.selected : ""}`}
                onClick={() => setNiche(n.id)}
              >
                <span className={styles.nicheIcon}>{n.icon}</span>
                <span className={styles.nicheName}>{n.name}</span>
              </div>
            ))}
          </div>

          <div className={styles.formGroup} style={{ marginTop: "1.5rem" }}>
            <label className={styles.formLabel}>Tujuan utama kamu (opsional)</label>
            <input
              type="text"
              className={styles.formInput}
              placeholder="Contoh: Meningkatkan penjualan online"
              value={sellerGoal}
              onChange={(e) => setSellerGoal(e.target.value)}
            />
          </div>
        </div>
      )}

      {/* Step 2: Produk */}
      {step === 1 && (
        <div className={styles.stepCard}>
          <h2 className={styles.stepTitle}>Tambah Produk</h2>
          <p className={styles.stepDesc}>Masukkan 3-5 produk utama kamu. Bisa diedit nanti.</p>

          {products.map((p, idx) => (
            <div key={idx} className={styles.productRow}>
              <div className={styles.formGroup}>
                <label className={styles.formLabel}>Nama Produk {idx + 1}</label>
                <input
                  type="text"
                  className={styles.formInput}
                  placeholder="Nama produk"
                  value={p.nama}
                  onChange={(e) => updateProduct(idx, "nama", e.target.value)}
                />
              </div>
              <div className={styles.formGroup}>
                <label className={styles.formLabel}>Harga (Rp)</label>
                <input
                  type="number"
                  className={styles.formInput}
                  placeholder="50000"
                  value={p.harga}
                  onChange={(e) => updateProduct(idx, "harga", e.target.value)}
                />
              </div>
              {products.length > 1 && (
                <button className={styles.removeBtn} onClick={() => removeProduct(idx)}>✕</button>
              )}
            </div>
          ))}

          {products.length < 5 && (
            <button className={styles.addProductBtn} onClick={addProduct}>
              ➕ Tambah Produk
            </button>
          )}
        </div>
      )}

      {/* Step 3: AI Persona */}
      {step === 2 && (
        <div className={styles.stepCard}>
          <h2 className={styles.stepTitle}>Pilih Gaya AI</h2>
          <p className={styles.stepDesc}>Bagaimana AI kamu bicara ke customer?</p>

          <div className={styles.toneGrid}>
            {TONES.map((t) => (
              <div
                key={t.id}
                className={`${styles.toneCard} ${tone === t.id ? styles.selected : ""}`}
                onClick={() => setTone(t.id)}
              >
                <span className={styles.toneEmoji}>{t.emoji}</span>
                <span className={styles.toneName}>{t.name}</span>
                <span className={styles.toneDesc}>{t.desc}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Step 4: Preview Chat */}
      {step === 3 && (
        <div className={styles.stepCard}>
          <h2 className={styles.stepTitle}>Test AI Kamu</h2>
          <p className={styles.stepDesc}>Coba tanya seperti customer. AI akan menjawab berdasarkan produk kamu.</p>

          <div className={styles.chatPreview}>
            {chatMessages.length === 0 && (
              <p style={{ color: "var(--text-secondary)", textAlign: "center", padding: "2rem 0" }}>
                💬 Mulai chat untuk test AI kamu
              </p>
            )}
            {chatMessages.map((msg, i) => (
              <div key={i} className={`${styles.chatBubble} ${msg.role === "user" ? styles.user : styles.ai}`}>
                {msg.text}
              </div>
            ))}
            {simulating && (
              <div className={`${styles.chatBubble} ${styles.ai}`}>
                <div className={styles.loadingDots}>
                  <span /><span /><span />
                </div>
              </div>
            )}
          </div>

          <div className={styles.chatInputRow}>
            <input
              type="text"
              className={`${styles.formInput} ${styles.chatInput}`}
              placeholder="Ketik pertanyaan customer..."
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSimulateChat()}
              disabled={simulating}
            />
            <button
              className="btn btn-primary"
              onClick={handleSimulateChat}
              disabled={simulating || !chatInput.trim()}
            >
              Kirim
            </button>
          </div>
        </div>
      )}

      {/* Step 5: Go Live */}
      {step === 4 && (
        <div className={styles.stepCard}>
          <div className={styles.completionCard}>
            <div className={styles.completionIcon}>🎉</div>
            <h2 className={styles.completionTitle}>Toko Kamu Siap!</h2>
            <p className={styles.completionDesc}>
              {result?.products_created || 0} produk draft berhasil dibuat.
              Kamu bisa mulai jualan sekarang!
            </p>

            <div className={styles.completionActions}>
              <Link
                href={result?.chat_url ? result.chat_url : "/chat"}
                className="btn btn-primary"
                target="_blank"
              >
                💬 Test Chat Page
              </Link>
              <Link href="/dashboard/products" className="btn btn-outline">
                📦 Edit Produk Draft
              </Link>
              <Link href="/dashboard/storefront" className="btn btn-outline">
                🏪 Atur Storefront
              </Link>
              <Link href="/dashboard/integrations" className="btn btn-outline">
                📱 Connect WhatsApp
              </Link>
              <Link href="/dashboard" className="btn btn-ghost">
                → Ke Dashboard
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* Navigation Buttons */}
      {step < 4 && (
        <div className={styles.navButtons}>
          {step > 0 ? (
            <button className="btn btn-outline" onClick={() => setStep(step - 1)}>
              ← Kembali
            </button>
          ) : (
            <div />
          )}
          <button
            className="btn btn-primary"
            onClick={nextStep}
            disabled={!canProceed() || loading}
          >
            {loading ? "Memproses..." : step === 3 ? "🚀 Go Live!" : "Lanjut →"}
          </button>
        </div>
      )}
    </div>
  );
}
