"use client";
import { useState, useEffect } from "react";
import styles from "./settings.module.css";

export default function SettingsPage() {
  const [user, setUser] = useState(null);
  const [aiStyle, setAiStyle] = useState("santai");
  const [aiActive, setAiActive] = useState(true);

  useEffect(() => {
    const userData = localStorage.getItem("jualin_user");
    if (userData) {
      const u = JSON.parse(userData);
      setUser(u);
      setAiStyle(u.ai_style || "santai");
      setAiActive(u.ai_active !== false);
    }
  }, []);

  if (!user) return null;

  return (
    <div className={styles.settingsPage}>
      <h2 className={styles.title}>Settings</h2>

      {/* Store Info */}
      <div className="card mb-6">
        <h3 className={styles.sectionTitle}>Informasi Toko</h3>
        <div className={styles.fieldGroup}>
          <div className={styles.field}>
            <label className="label">Nama Toko</label>
            <input className="input" value={user.nama_toko} readOnly />
          </div>
          <div className={styles.field}>
            <label className="label">Email</label>
            <input className="input" value={user.email} readOnly />
          </div>
          <div className={styles.field}>
            <label className="label">Slug (URL toko)</label>
            <input className="input" value={user.slug} readOnly />
            <p className="text-xs text-muted mt-1">Chat URL: /chat/{user.slug}</p>
          </div>
          <div className={styles.field}>
            <label className="label">No. HP</label>
            <input className="input" value={user.no_hp || "-"} readOnly />
          </div>
        </div>
      </div>

      {/* AI Settings */}
      <div className="card mb-6">
        <h3 className={styles.sectionTitle}>🤖 Pengaturan AI</h3>
        <div className={styles.fieldGroup}>
          <div className={styles.toggleRow}>
            <div>
              <strong>AI Auto-Reply</strong>
              <p className="text-sm text-muted">Aktifkan AI untuk membalas chat customer otomatis</p>
            </div>
            <label className={styles.toggle}>
              <input type="checkbox" checked={aiActive} onChange={(e) => setAiActive(e.target.checked)} />
              <span className={styles.toggleSlider}></span>
            </label>
          </div>

          <div className={styles.field}>
            <label className="label">Gaya Bahasa AI</label>
            <div className={styles.styleOptions}>
              {[
                { value: "formal", label: "Formal", desc: "Bahasa sopan, panggil Bapak/Ibu" },
                { value: "santai", label: "Santai", desc: "Ramah, panggil Kak, emoji secukupnya" },
                { value: "gaul", label: "Gaul", desc: "Friendly, panggil Kak/Bestie, lebih banyak emoji" },
              ].map((s) => (
                <div
                  key={s.value}
                  className={`${styles.styleCard} ${aiStyle === s.value ? styles.styleActive : ""}`}
                  onClick={() => setAiStyle(s.value)}
                >
                  <strong>{s.label}</strong>
                  <p className="text-xs text-muted">{s.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Plan Info */}
      <div className="card">
        <h3 className={styles.sectionTitle}>📋 Plan & Billing</h3>
        <div className={styles.planInfo}>
          <div className={styles.planCurrent}>
            <span className="badge badge-primary" style={{ fontSize: "1rem", padding: "6px 16px" }}>{user.tier?.toUpperCase()}</span>
            <p className="text-muted text-sm mt-2">Plan kamu saat ini</p>
          </div>
          <button className="btn btn-outline">Upgrade Plan</button>
        </div>
      </div>
    </div>
  );
}
