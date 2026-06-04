"use client";
import { useEffect, useState } from "react";
import { listExperiments, createExperiment, startExperiment, stopExperiment, getExperimentResults } from "@/lib/api";
import styles from "../scale.module.css";

const STATUS_BADGES = { draft: "badge-muted", running: "badge-success", stopped: "badge-warning", completed: "badge-primary" };

export default function ExperimentsPage() {
  const [experiments, setExperiments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [results, setResults] = useState(null);

  useEffect(() => { loadData(); }, []);
  async function loadData() {
    try { setExperiments(await listExperiments()); } catch (e) { console.error(e); }
    setLoading(false);
  }

  async function handleCreate() {
    const name = prompt("Nama experiment:");
    const type = prompt("Type (prompt / campaign_cta / storefront_cta / offer_wording):") || "prompt";
    if (!name) return;
    try { await createExperiment({ name, type }); loadData(); } catch (e) { alert(e.message); }
  }

  async function handleStart(id) {
    try { await startExperiment(id); loadData(); } catch (e) { alert(e.message); }
  }

  async function handleStop(id) {
    try { await stopExperiment(id); loadData(); } catch (e) { alert(e.message); }
  }

  async function handleResults(id) {
    try { setResults(await getExperimentResults(id)); } catch (e) { alert(e.message); }
  }

  if (loading) return <div style={{ padding: 40, textAlign: "center" }}>⏳ Memuat...</div>;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h2>🧪 A/B Experiments</h2>
        <button className="btn btn-primary" onClick={handleCreate}>+ Buat Experiment</button>
      </div>

      {experiments.length === 0 ? (
        <div className={styles.stateBox}>Belum ada experiment. Buat experiment untuk test prompt, CTA, atau offer wording.</div>
      ) : experiments.map((e) => (
        <div key={e.id} className="card" style={{ padding: 16, marginBottom: 10 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <strong>{e.name}</strong>
              <span className={`badge ${STATUS_BADGES[e.status] || "badge-muted"}`} style={{ marginLeft: 8, fontSize: "0.65em" }}>{e.status}</span>
              <div className="text-sm text-muted">{e.type} · {e.description || "No description"}</div>
            </div>
            <div style={{ display: "flex", gap: 4 }}>
              {e.status === "draft" && <button className="btn btn-sm btn-primary" onClick={() => handleStart(e.id)}>▶ Start</button>}
              {e.status === "running" && <button className="btn btn-sm btn-danger" onClick={() => handleStop(e.id)}>⏹ Stop</button>}
              <button className="btn btn-sm btn-outline" onClick={() => handleResults(e.id)}>📊</button>
            </div>
          </div>
        </div>
      ))}

      {results && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}>
          <div className="card" style={{ padding: 24, maxWidth: 500, width: "90%" }}>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <h3>📊 {results.experiment?.name}</h3>
              <button className="btn btn-sm btn-outline" onClick={() => setResults(null)}>✕</button>
            </div>
            <table style={{ width: "100%", marginTop: 12, fontSize: "0.9rem" }}>
              <thead><tr><th>Variant</th><th>Impr.</th><th>Conv.</th><th>Rate</th><th>Revenue</th></tr></thead>
              <tbody>
                {results.variants?.map((v) => (
                  <tr key={v.id}>
                    <td><strong>{v.name}</strong> ({v.weight}%)</td>
                    <td>{v.impressions}</td>
                    <td>{v.conversions}</td>
                    <td>{v.conversion_rate}%</td>
                    <td>Rp {(v.revenue || 0).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
