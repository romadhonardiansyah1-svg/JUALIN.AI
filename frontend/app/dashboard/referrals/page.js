"use client";
import { useEffect, useState } from "react";
import { listReferralCodes, createReferralCode, getReferralSummary, listResellers } from "@/lib/api";
import styles from "../scale.module.css";

export default function ReferralsPage() {
  const [codes, setCodes] = useState([]);
  const [summary, setSummary] = useState(null);
  const [resellers, setResellers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("codes");

  useEffect(() => { loadData(); }, []);

  async function loadData() {
    try {
      const [c, s, r] = await Promise.all([listReferralCodes(), getReferralSummary(), listResellers()]);
      setCodes(c); setSummary(s); setResellers(r);
    } catch (e) { console.error(e); }
    setLoading(false);
  }

  async function handleCreate() {
    const desc = prompt("Deskripsi kode referral:");
    if (!desc) return;
    try {
      const result = await createReferralCode({ description: desc });
      alert(`Kode: ${result.code}`);
      loadData();
    } catch (e) { alert(e.message); }
  }

  if (loading) return <div style={{ padding: 40, textAlign: "center" }}>⏳ Memuat...</div>;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h2>🔗 Referral & Reseller</h2>
        <button className="btn btn-primary" onClick={handleCreate}>+ Buat Kode</button>
      </div>

      {summary && (
        <div className={styles.grid} style={{ marginBottom: 20 }}>
          {[
            { label: "Total Klik", value: summary.total_clicks, icon: "👆" },
            { label: "Konversi", value: summary.total_conversions, icon: "✅" },
            { label: "Revenue", value: `Rp ${(summary.total_revenue || 0).toLocaleString()}`, icon: "💰" },
            { label: "Komisi Pending", value: `Rp ${(summary.pending_commission || 0).toLocaleString()}`, icon: "⏳" },
          ].map((s) => (
            <div key={s.label} className="card" style={{ padding: 16, textAlign: "center" }}>
              <div style={{ fontSize: "1.5rem" }}>{s.icon}</div>
              <div style={{ fontWeight: 700, fontSize: "1.2rem" }}>{s.value}</div>
              <div className="text-sm text-muted">{s.label}</div>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <button className={`btn btn-sm ${tab === "codes" ? "btn-primary" : "btn-outline"}`} onClick={() => setTab("codes")}>Kode Referral</button>
        <button className={`btn btn-sm ${tab === "resellers" ? "btn-primary" : "btn-outline"}`} onClick={() => setTab("resellers")}>Reseller</button>
      </div>

      {tab === "codes" && codes.map((c) => (
        <div key={c.id} className="card" style={{ padding: 16, marginBottom: 8 }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <div><code style={{ fontSize: "1.1rem" }}>{c.code}</code><p className="text-sm text-muted" style={{ margin: "4px 0 0" }}>{c.description}</p></div>
            <div className="text-sm text-muted" style={{ textAlign: "right" }}>
              {c.total_clicks} klik · {c.total_conversions} konversi · {c.commission_percent}%
            </div>
          </div>
        </div>
      ))}

      {tab === "resellers" && (resellers.length === 0 ? (
        <div className={styles.stateBox}>Belum ada reseller.</div>
      ) : resellers.map((r) => (
        <div key={r.id} className="card" style={{ padding: 16, marginBottom: 8 }}>
          <strong>{r.name}</strong>
          <span className="text-sm text-muted"> · {r.email} · Rp {(r.total_earned || 0).toLocaleString()}</span>
        </div>
      )))}
    </div>
  );
}
