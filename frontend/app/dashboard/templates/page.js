"use client";
import { useCallback, useEffect, useState } from "react";
import { getTemplates, installTemplate, duplicateTemplate } from "@/lib/api";
import styles from "../scale.module.css";

const TYPES = [
  { value: "", label: "Semua" },
  { value: "campaign", label: "Campaign" },
  { value: "workflow", label: "Workflow" },
  { value: "prompt", label: "Prompt" },
  { value: "canned_reply", label: "Canned Reply" },
  { value: "storefront_section", label: "Storefront" },
];

const TYPE_ICONS = {
  campaign: "📢",
  workflow: "⚙️",
  prompt: "💬",
  canned_reply: "⚡",
  storefront_section: "🏪",
};

export default function TemplatesPage() {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filterType, setFilterType] = useState("");
  const [installing, setInstalling] = useState(null);

  const loadTemplates = useCallback(async () => {
    setLoading(true);
    try {
      const params = filterType ? { type: filterType } : {};
      setTemplates(await getTemplates(params));
    } catch (e) { setError(e.message); }
    setLoading(false);
  }, [filterType]);

  useEffect(() => { loadTemplates(); }, [loadTemplates]);

  async function handleInstall(id) {
    setInstalling(id);
    try {
      const result = await installTemplate(id);
      alert(`✅ ${result.message}`);
      await loadTemplates();
    } catch (e) { alert(`❌ ${e.message}`); }
    setInstalling(null);
  }

  async function handleDuplicate(id) {
    try {
      const result = await duplicateTemplate(id);
      alert(`✅ ${result.message}`);
      await loadTemplates();
    } catch (e) { alert(`❌ ${e.message}`); }
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.titleBlock}>
          <h2>📚 Template Marketplace</h2>
          <p className={styles.muted}>Browse dan install template untuk campaign, workflow, prompt, dan lainnya.</p>
        </div>
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 20, flexWrap: "wrap" }}>
        {TYPES.map((t) => (
          <button
            key={t.value}
            className={`btn btn-sm ${filterType === t.value ? "btn-primary" : "btn-outline"}`}
            onClick={() => setFilterType(t.value)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {error && <div className={styles.error}>{error}</div>}
      {loading && <div className={styles.stateBox}>Memuat template...</div>}

      {!loading && templates.length === 0 && (
        <div className={styles.stateBox}>Belum ada template tersedia untuk kategori ini.</div>
      )}

      <div className={styles.grid}>
        {templates.map((t) => (
          <div key={t.id} className="card" style={{ padding: 20 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
              <span style={{ fontSize: "1.5rem" }}>{TYPE_ICONS[t.type] || "📄"}</span>
              <span className="badge badge-primary" style={{ fontSize: "0.7em" }}>{t.type}</span>
            </div>
            <h4 style={{ margin: "8px 0 4px" }}>{t.name}</h4>
            <p className="text-sm text-muted" style={{ marginBottom: 12, minHeight: 40 }}>
              {t.description || "Tidak ada deskripsi."}
            </p>
            {t.tags && t.tags.length > 0 && (
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 8 }}>
                {t.tags.map((tag) => (
                  <span key={tag} className="badge badge-muted" style={{ fontSize: "0.7em" }}>#{tag}</span>
                ))}
              </div>
            )}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span className="text-xs text-muted">📥 {t.usage_count || 0}x installed</span>
              <div style={{ display: "flex", gap: 4 }}>
                <button
                  className="btn btn-sm btn-primary"
                  onClick={() => handleInstall(t.id)}
                  disabled={installing === t.id}
                >
                  {installing === t.id ? "⏳..." : "Install"}
                </button>
                <button className="btn btn-sm btn-outline" onClick={() => handleDuplicate(t.id)}>
                  📋
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
