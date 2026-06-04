"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import styles from "../scale.module.css";

export default function AIQualityPage() {
  const [traces, setTraces] = useState([]);
  const [cases, setCases] = useState([]);
  const [status, setStatus] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const [traceData, caseData] = await Promise.all([api.getAITraces(status), api.getAIEvalCases()]);
      setTraces(traceData);
      setCases(caseData);
    } catch (e) {
      setError(e.message);
    }
  }, [status]);

  async function runEval() {
    setError("");
    setMessage("");
    try {
      const data = await api.runAIEval();
      setMessage(`${data.message}. Total case: ${data.total_cases}`);
    } catch (e) {
      setError(e.message);
    }
  }

  async function markDown(traceId) {
    try {
      await api.createAIFeedback({ trace_id: traceId, rating: "down", reason: "seller_report", note: "Ditandai dari AI Quality Center" });
      setMessage("Feedback disimpan.");
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.titleBlock}>
          <h2>AI Quality Center</h2>
          <p className={styles.muted}>Trace LLM, action gagal, confidence rendah, dan dataset eval.</p>
        </div>
        <div className={styles.toolbar}>
          <select className="input" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">Semua status</option>
            <option value="ok">OK</option>
            <option value="failed">Failed</option>
          </select>
          <button className="btn btn-outline" onClick={load}>Refresh</button>
          <button className="btn btn-primary" onClick={runEval}>Run Eval</button>
        </div>
      </div>
      {error && <div className={styles.error}>{error}</div>}
      {message && <div className={styles.success}>{message}</div>}
      <div className={styles.grid}>
        <div className={styles.statCard}><span className={styles.muted}>Trace terbaru</span><span className={styles.statValue}>{traces.length}</span></div>
        <div className={styles.statCard}><span className={styles.muted}>Eval cases</span><span className={styles.statValue}>{cases.length}</span></div>
      </div>
      <div className={styles.panel}>
        <div className={styles.panelHeader}><strong>Traces</strong></div>
        {traces.length === 0 && <div className={styles.stateBox}>Belum ada AI trace.</div>}
        <div className={styles.tableWrap}>
          <table className="table">
            <thead><tr><th>Trace</th><th>Model</th><th>Stage</th><th>Status</th><th>Latency</th><th>Preview</th><th>Aksi</th></tr></thead>
            <tbody>
              {traces.map((trace) => (
                <tr key={trace.id}>
                  <td>{trace.trace_id}</td>
                  <td>{trace.provider || "-"} / {trace.model || "-"}</td>
                  <td>{trace.stage || "-"}</td>
                  <td><span className={`badge ${trace.status === "ok" ? "badge-success" : "badge-danger"}`}>{trace.status}</span></td>
                  <td>{trace.latency_ms} ms</td>
                  <td>{trace.response_preview || trace.error_message || "-"}</td>
                  <td><button className="btn btn-sm btn-outline" onClick={() => markDown(trace.trace_id)}>Flag</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className={styles.panel}>
        <div className={styles.panelHeader}><strong>Eval Dataset</strong><span className="badge badge-primary">{cases.length}</span></div>
        <div className={styles.list}>
          {cases.slice(0, 30).map((item, index) => (
            <div className={styles.listItem} key={`${item.name}-${index}`}>
              <div className={styles.listTitle}><span>{item.name}</span><span className="badge badge-neutral">{item.category}</span></div>
              <div className={styles.listMeta}>{item.prompt}</div>
              <p className={styles.muted}>{item.expected_behavior}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
