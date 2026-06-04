"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import styles from "../scale.module.css";

export default function WorkflowsPage() {
  const [templates, setTemplates] = useState([]);
  const [rules, setRules] = useState([]);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const [templateData, ruleData] = await Promise.all([api.getWorkflowTemplates(), api.getWorkflowRules()]);
      setTemplates(templateData);
      setRules(ruleData);
      if (!selected && templateData.length) setSelected(templateData[0].key);
    } catch (e) {
      setError(e.message);
    }
  }, [selected]);

  async function createRule() {
    try {
      const template = templates.find((item) => item.key === selected);
      await api.createWorkflowRule({ template_key: selected, name: template?.name || selected });
      setMessage("Rule dibuat.");
      await load();
    } catch (e) {
      setError(e.message);
    }
  }

  async function toggleRule(rule) {
    try {
      await api.updateWorkflowRule(rule.id, { is_active: !rule.is_active });
      await load();
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
          <h2>Workflow Automation</h2>
          <p className={styles.muted}>Rule builder berbasis template untuk follow-up dan operasional UMKM.</p>
        </div>
      </div>
      {error && <div className={styles.error}>{error}</div>}
      {message && <div className={styles.success}>{message}</div>}
      <div className={styles.grid}>
        <div className={styles.panel}>
          <div className={styles.panelHeader}><strong>Template</strong></div>
          <div className={styles.panelBody}>
            <select className="input" value={selected} onChange={(e) => setSelected(e.target.value)}>
              {templates.map((template) => <option key={template.key} value={template.key}>{template.name}</option>)}
            </select>
            <button className="btn btn-primary" style={{ marginTop: 12 }} onClick={createRule}>Aktifkan Template</button>
          </div>
          <div className={styles.list}>
            {templates.map((template) => (
              <div key={template.key} className={styles.listItem}>
                <div className={styles.listTitle}>{template.name}</div>
                <div className={styles.listMeta}>{JSON.stringify(template.trigger)} &gt; {JSON.stringify(template.action)}</div>
              </div>
            ))}
          </div>
        </div>
        <div className={styles.panel}>
          <div className={styles.panelHeader}><strong>Rules Aktif</strong><span className="badge badge-primary">{rules.length}</span></div>
          {rules.length === 0 && <div className={styles.stateBox}>Belum ada automation rule.</div>}
          <div className={styles.list}>
            {rules.map((rule) => (
              <div key={rule.id} className={styles.listItem}>
                <div className={styles.listTitle}>
                  <span>{rule.name}</span>
                  <span className={`badge ${rule.is_active ? "badge-success" : "badge-neutral"}`}>{rule.is_active ? "active" : "paused"}</span>
                </div>
                <div className={styles.listMeta}>{rule.template_key}</div>
                <button className="btn btn-sm btn-outline" style={{ marginTop: 8 }} onClick={() => toggleRule(rule)}>{rule.is_active ? "Pause" : "Activate"}</button>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Run History ── */}
      <RunHistory />
    </div>
  );
}

function RunHistory() {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);

  async function loadRuns() {
    try {
      setRuns(await api.getWorkflowRuns());
    } catch (e) {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadRuns(); }, []);

  return (
    <div className={styles.panel} style={{ marginTop: 20 }}>
      <div className={styles.panelHeader}>
        <strong>Run History</strong>
        <button className="btn btn-sm btn-outline" onClick={loadRuns}>Refresh</button>
      </div>
      {loading && <div className={styles.stateBox}>Memuat...</div>}
      {!loading && runs.length === 0 && <div className={styles.stateBox}>Belum ada automation run.</div>}
      {runs.length > 0 && (
        <div style={{ overflowX: "auto" }}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>ID</th>
                <th>Template</th>
                <th>Entity</th>
                <th>Status</th>
                <th>Started</th>
                <th>Finished</th>
                <th>Error</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id}>
                  <td>{run.id}</td>
                  <td>{run.context?.template_key || "-"}</td>
                  <td>{run.context?.entity_type}:{run.context?.entity_id}</td>
                  <td>
                    <span className={`badge ${run.status === "done" ? "badge-success" : run.status === "failed" ? "badge-danger" : "badge-warning"}`}>
                      {run.status}
                    </span>
                  </td>
                  <td>{run.started_at ? new Date(run.started_at).toLocaleString("id-ID", { dateStyle: "short", timeStyle: "short" }) : "-"}</td>
                  <td>{run.finished_at ? new Date(run.finished_at).toLocaleString("id-ID", { dateStyle: "short", timeStyle: "short" }) : "-"}</td>
                  <td style={{ maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{run.error_message || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
