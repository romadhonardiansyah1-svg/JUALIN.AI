"use client";
import { useEffect, useState } from "react";
import { getOnboarding, updateOnboarding, completeOnboarding, onboardingTestChat } from "@/lib/api";

const STEPS = [
  { key: "profile", label: "Profil Toko", icon: "🏪", desc: "Lengkapi nama dan deskripsi toko", required: true },
  { key: "product", label: "Tambah Produk", icon: "📦", desc: "Tambahkan minimal satu produk", required: true },
  { key: "payment", label: "Setup Pembayaran", icon: "💳", desc: "Konfigurasi gateway pembayaran" },
  { key: "whatsapp", label: "Connect WhatsApp", icon: "💬", desc: "Hubungkan nomor WhatsApp bisnis" },
  { key: "ai_persona", label: "AI Persona", icon: "🤖", desc: "Pilih gaya bahasa AI", required: true },
  { key: "test_chat", label: "Test Chat", icon: "🧪", desc: "Coba chat dengan AI toko kamu" },
  { key: "go_live", label: "Go Live!", icon: "🚀", desc: "Toko siap menerima customer!" },
];

export default function OnboardingPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [completing, setCompleting] = useState(false);

  useEffect(() => { loadData(); }, []);

  async function loadData() {
    try {
      setData(await getOnboarding());
    } catch (e) { setError(e.message); }
    setLoading(false);
  }

  async function markStep(step) {
    try {
      await updateOnboarding({ step, completed: true });
      await loadData();
    } catch (e) { setError(e.message); }
  }

  async function handleTestChat() {
    try {
      const result = await onboardingTestChat();
      alert(result.message);
      await loadData();
    } catch (e) { setError(e.message); }
  }

  async function handleComplete() {
    setCompleting(true);
    try {
      const result = await completeOnboarding();
      alert(result.message);
      await loadData();
    } catch (e) {
      alert(e.message || "Gagal menyelesaikan onboarding");
    }
    setCompleting(false);
  }

  if (loading) return <div style={{ padding: 40, textAlign: "center" }}>⏳ Memuat onboarding...</div>;

  const steps = data?.steps || {};
  const completedCount = Object.values(steps).filter(Boolean).length;
  const progress = Math.round((completedCount / STEPS.length) * 100);

  return (
    <div style={{ maxWidth: 700, margin: "0 auto", padding: 20 }}>
      <div style={{ textAlign: "center", marginBottom: 30 }}>
        <h2>🎯 Setup Toko Kamu</h2>
        <p className="text-muted">Selesaikan langkah-langkah berikut untuk mulai berjualan</p>
        <div style={{
          background: "var(--card-bg, #1e293b)", borderRadius: 12, height: 12, marginTop: 16, overflow: "hidden"
        }}>
          <div style={{
            width: `${progress}%`, height: "100%",
            background: "linear-gradient(90deg, #6366f1, #22c55e)",
            borderRadius: 12, transition: "width 0.5s ease",
          }} />
        </div>
        <p className="text-sm text-muted" style={{ marginTop: 8 }}>{completedCount}/{STEPS.length} selesai ({progress}%)</p>
      </div>

      {error && <div className="badge badge-danger" style={{ marginBottom: 16 }}>{error}</div>}

      {data?.completed && (
        <div className="card" style={{ textAlign: "center", padding: 30, marginBottom: 20 }}>
          <h3>🎉 Selamat! Toko kamu sudah Go Live!</h3>
          <p className="text-muted">Customer sudah bisa mulai chat dan belanja di toko kamu.</p>
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {STEPS.map((step, i) => {
          const done = steps[step.key];
          const isCurrent = data?.current_step === step.key;

          return (
            <div key={step.key} className="card" style={{
              padding: "16px 20px",
              border: isCurrent ? "2px solid #6366f1" : "1px solid var(--border, #334155)",
              opacity: done ? 0.7 : 1,
              transition: "all 0.3s ease",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <span style={{ fontSize: "1.5rem" }}>{done ? "✅" : step.icon}</span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, display: "flex", alignItems: "center", gap: 8 }}>
                    {step.label}
                    {step.required && <span className="badge badge-warning" style={{ fontSize: "0.65em" }}>Wajib</span>}
                  </div>
                  <p className="text-muted text-sm" style={{ margin: 0 }}>{step.desc}</p>
                </div>
                {!done && step.key === "test_chat" && (
                  <button className="btn btn-sm btn-primary" onClick={handleTestChat}>🧪 Test</button>
                )}
                {!done && step.key !== "go_live" && step.key !== "test_chat" && (
                  <button className="btn btn-sm btn-outline" onClick={() => markStep(step.key)}>Tandai Selesai</button>
                )}
                {step.key === "go_live" && !data?.completed && (
                  <button
                    className="btn btn-sm btn-primary"
                    onClick={handleComplete}
                    disabled={completing}
                  >
                    {completing ? "⏳..." : "🚀 Go Live!"}
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
