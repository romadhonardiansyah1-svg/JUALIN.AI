"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import styles from "./whatsapp-templates.module.css";

const PURPOSES = [
  { id: "order_confirmation", icon: "✅", name: "Order Confirmation", desc: "Konfirmasi pesanan masuk" },
  { id: "payment_reminder", icon: "💰", name: "Payment Reminder", desc: "Reminder pembayaran" },
  { id: "promo", icon: "🎉", name: "Promo / Marketing", desc: "Kirim promo ke customer" },
  { id: "welcome", icon: "👋", name: "Welcome Message", desc: "Sapa customer baru" },
];

const STATUS_COLORS = {
  draft: { bg: "rgba(107,114,128,0.1)", color: "#6B7280", label: "Draft" },
  pending_review: { bg: "rgba(245,158,11,0.1)", color: "#F59E0B", label: "Pending Review" },
  approved: { bg: "rgba(16,185,129,0.1)", color: "#10B981", label: "Approved" },
  rejected: { bg: "rgba(239,68,68,0.1)", color: "#EF4444", label: "Rejected" },
};

export default function WATemplatesPage() {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [step, setStep] = useState(0); // 0=list, 1=purpose, 2=preview, 3=edit
  const [purpose, setPurpose] = useState("");
  const [generating, setGenerating] = useState(false);
  const [editTemplate, setEditTemplate] = useState(null);
  const [customPrompt, setCustomPrompt] = useState("");

  useEffect(() => { loadTemplates(); }, []);

  const loadTemplates = async () => {
    try {
      const data = await api.getWATemplates();
      setTemplates(data || []);
    } catch { /* empty */ }
    setLoading(false);
  };

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const result = await api.generateWATemplate({ purpose, custom_prompt: customPrompt });
      setEditTemplate(result);
      setStep(3);
    } catch { /* empty */ }
    setGenerating(false);
  };

  const handleSubmit = async (id) => {
    try {
      await api.submitWATemplate(id);
      await loadTemplates();
      setStep(0);
      setEditTemplate(null);
    } catch { /* empty */ }
  };

  const renderVariablePreview = (body, variables) => {
    let preview = body;
    (variables || []).forEach((v) => {
      preview = preview.replace(`{{${v.key}}}`, `[${v.sample_value}]`);
    });
    return preview;
  };

  if (loading) return <div className="card" style={{ padding: "2rem", textAlign: "center" }}>Memuat templates...</div>;

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>📱 WhatsApp Templates</h1>
          <p className={styles.subtitle}>Buat template pesan untuk campaign di luar 24 jam</p>
        </div>
        {step === 0 && (
          <button className="btn btn-primary" onClick={() => setStep(1)}>
            + Buat Template
          </button>
        )}
      </div>

      {/* Step 1: Choose Purpose */}
      {step === 1 && (
        <div className={`card ${styles.wizardCard}`}>
          <h3>Pilih Tujuan Template</h3>
          <div className={styles.purposeGrid}>
            {PURPOSES.map((p) => (
              <div
                key={p.id}
                className={`${styles.purposeCard} ${purpose === p.id ? styles.selected : ""}`}
                onClick={() => setPurpose(p.id)}
              >
                <span className={styles.purposeIcon}>{p.icon}</span>
                <span className={styles.purposeName}>{p.name}</span>
                <span className={styles.purposeDesc}>{p.desc}</span>
              </div>
            ))}
          </div>

          <div className={styles.formGroup} style={{ marginTop: "1.5rem" }}>
            <label className={styles.label}>Custom prompt (opsional)</label>
            <input
              className={styles.input}
              placeholder="Contoh: Buat template promo diskon 20% untuk produk frozen food"
              value={customPrompt}
              onChange={(e) => setCustomPrompt(e.target.value)}
            />
          </div>

          <div className={styles.wizardActions}>
            <button className="btn btn-outline" onClick={() => { setStep(0); setPurpose(""); }}>Batal</button>
            <button className="btn btn-primary" onClick={handleGenerate} disabled={!purpose || generating}>
              {generating ? "Generating..." : "🤖 Generate Template"}
            </button>
          </div>
        </div>
      )}

      {/* Step 3: Edit & Preview */}
      {step === 3 && editTemplate && (
        <div className={`card ${styles.wizardCard}`}>
          <h3>Preview & Edit Template</h3>

          <div className={styles.previewPhone}>
            <div className={styles.phoneBubble}>
              {renderVariablePreview(editTemplate.body, editTemplate.variables)}
            </div>
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Template Body</label>
            <textarea
              className={styles.textarea}
              value={editTemplate.body}
              onChange={(e) => setEditTemplate({ ...editTemplate, body: e.target.value })}
              rows={5}
            />
          </div>

          <div className={styles.variableList}>
            <h4>Variables:</h4>
            {(editTemplate.variables || []).map((v, i) => (
              <span key={i} className={styles.variableTag}>
                {"{{" + v.key + "}} = " + v.sample_value}
              </span>
            ))}
          </div>

          <div className={styles.wizardActions}>
            <button className="btn btn-outline" onClick={() => { setStep(0); setEditTemplate(null); }}>Simpan Draft</button>
            <button className="btn btn-primary" onClick={() => handleSubmit(editTemplate.id)}>
              📤 Submit for Review
            </button>
          </div>
        </div>
      )}

      {/* Templates List */}
      {step === 0 && (
        <div className={styles.templateList}>
          {templates.length === 0 ? (
            <div className="card" style={{ textAlign: "center", padding: "3rem" }}>
              <div style={{ fontSize: "3rem", marginBottom: "1rem" }}>📱</div>
              <h3>Belum ada template</h3>
              <p style={{ color: "var(--text-secondary)" }}>Buat template WhatsApp pertama kamu untuk campaign.</p>
            </div>
          ) : (
            templates.map((t) => {
              const sc = STATUS_COLORS[t.status] || STATUS_COLORS.draft;
              return (
                <div key={t.id} className={`card ${styles.templateCard}`}>
                  <div className={styles.templateHeader}>
                    <h4>{t.name}</h4>
                    <span className={styles.statusBadge} style={{ background: sc.bg, color: sc.color }}>
                      {sc.label}
                    </span>
                  </div>
                  <p className={styles.templateBody}>{t.body}</p>
                  {t.rejection_reason && (
                    <div className={styles.rejectionReason}>
                      ❌ Alasan ditolak: {t.rejection_reason}
                    </div>
                  )}
                  <div className={styles.templateMeta}>
                    <span>{t.category}</span>
                    <span>{t.language}</span>
                    <span>{t.created_at ? new Date(t.created_at).toLocaleDateString("id") : ""}</span>
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
