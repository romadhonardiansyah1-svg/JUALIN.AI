"use client";
import { useEffect, useState } from "react";
import { listPlaybooks, updatePlaybook } from "@/lib/api";
import styles from "../scale.module.css";

const TONE_OPTIONS = ["friendly", "professional", "casual"];

export default function PlaybooksPage() {
  const [playbooks, setPlaybooks] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => { loadData(); }, []);
  async function loadData() {
    try { setPlaybooks(await listPlaybooks()); } catch (e) { console.error(e); }
    setLoading(false);
  }

  async function togglePlaybook(id, enabled) {
    try { await updatePlaybook(id, { is_enabled: !enabled }); loadData(); } catch (e) { alert(e.message); }
  }

  if (loading) return <div style={{ padding: 40, textAlign: "center" }}>⏳ Memuat playbooks...</div>;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h2>🎭 AI Sales Playbooks</h2>
        <p className={styles.muted}>Enable/disable strategi AI untuk berbagai tipe customer.</p>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {playbooks.map((p) => (
          <div key={p.id} className="card" style={{ padding: "16px 20px", opacity: p.is_enabled ? 1 : 0.6 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <strong>{p.name}</strong>
                  <span className={`badge ${p.is_enabled ? "badge-success" : "badge-muted"}`}>
                    {p.is_enabled ? "ON" : "OFF"}
                  </span>
                  <span className="badge badge-primary" style={{ fontSize: "0.65em" }}>P{p.priority}</span>
                </div>
                <p className="text-sm text-muted" style={{ margin: "4px 0 0" }}>{p.description}</p>
              </div>
              <button className={`btn btn-sm ${p.is_enabled ? "btn-danger" : "btn-primary"}`} onClick={() => togglePlaybook(p.id, p.is_enabled)}>
                {p.is_enabled ? "Disable" : "Enable"}
              </button>
            </div>
          </div>
        ))}
      </div>

      {playbooks.length === 0 && <div className={styles.stateBox}>Playbooks akan di-generate otomatis saat pertama kali dibuka.</div>}
    </div>
  );
}
