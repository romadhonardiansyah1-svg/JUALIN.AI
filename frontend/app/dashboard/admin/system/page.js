"use client";
import { useEffect, useState } from "react";
import { api, adminListJobs, adminRetryJob } from "@/lib/api";
import styles from "../admin.module.css";

export default function AdminSystemPage() {
  const [health, setHealth] = useState(null);
  const [providers, setProviders] = useState(null);
  const [jobs, setJobs] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [retrying, setRetrying] = useState(null);
  const [jobFilter, setJobFilter] = useState("");

  useEffect(() => {
    loadAll();
  }, []);

  async function loadAll() {
    try {
      const [healthData, providerData, jobData] = await Promise.all([
        api.getSystemHealth().catch(() => null),
        api.getProviderHealth().catch(() => null),
        adminListJobs({ limit: 20 }).catch(() => null),
      ]);
      setHealth(healthData);
      setProviders(providerData);
      setJobs(jobData);
    } catch (e) {
      console.error("Failed to load system data", e);
    }
    setLoading(false);
  }

  async function handleRefresh() {
    setRefreshing(true);
    await loadAll();
    setRefreshing(false);
  }

  async function handleRetryJob(jobId) {
    if (!confirm("Retry job ini?")) return;
    setRetrying(jobId);
    try {
      await adminRetryJob(jobId);
      await loadAll();
    } catch (e) {
      alert("Retry gagal: " + (e.message || "Error"));
    }
    setRetrying(null);
  }

  async function filterJobs(status) {
    setJobFilter(status);
    try {
      const data = await adminListJobs({ status, limit: 20 });
      setJobs(data);
    } catch (e) { console.error(e); }
  }

  if (loading) {
    return (
      <div className={styles.loadingSkeleton}>
        <div className={styles.skelRow}>
          {[1,2,3].map(i => <div key={i} className={styles.skelCard} style={{ height: 120 }} />)}
        </div>
      </div>
    );
  }

  const providerStatusBadge = (status) => {
    const map = {
      alive: { cls: "badge-success", label: "● Alive" },
      configured: { cls: "badge-success", label: "● OK" },
      degraded: { cls: "badge-warning", label: "◐ Degraded" },
      offline: { cls: "badge-danger", label: "○ Offline" },
      disabled: { cls: "badge-muted", label: "○ Disabled" },
      not_configured: { cls: "badge-warning", label: "○ Not Set" },
      missing_config: { cls: "badge-warning", label: "○ Missing" },
      unknown: { cls: "badge-muted", label: "? Unknown" },
    };
    const m = map[status] || map.unknown;
    return <span className={`badge ${m.cls}`}>{m.label}</span>;
  };

  const providerCards = providers ? [
    { name: "Database", icon: "🗄️", status: providers.database?.status },
    { name: "Redis", icon: "⚡", status: providers.redis?.status },
    { name: "Worker", icon: "⚙️", status: providers.worker?.status, extra: providers.worker?.last_seen },
    { name: "WhatsApp", icon: "💬", status: providers.whatsapp?.status },
    { name: "LLM", icon: "🤖", status: providers.llm?.status, extra: providers.llm?.provider },
    { name: "Midtrans", icon: "💳", status: providers.payment?.midtrans },
    { name: "Cashi", icon: "📱", status: providers.payment?.cashi },
  ] : [];

  const jobStatusColor = (s) => {
    if (s === "done") return "#22C55E";
    if (s === "failed" || s === "dead_letter") return "#EF4444";
    if (s === "running") return "#3B82F6";
    if (s === "queued") return "#F59E0B";
    return "#6B7280";
  };

  return (
    <div className={styles.adminPage}>
      <div className={styles.header}>
        <div>
          <h2>🖥️ System & Ops Dashboard</h2>
          <p className="text-muted text-sm">Provider health, worker status, dan job management</p>
        </div>
        <button className="btn btn-outline" onClick={handleRefresh} disabled={refreshing}>
          {refreshing ? "⏳ Refreshing..." : "🔄 Refresh"}
        </button>
      </div>

      {/* Provider Health Cards */}
      <div className={styles.statsGrid}>
        {providerCards.map((p) => (
          <div key={p.name} className={styles.statCard} style={{
            borderTopColor: ["alive", "configured"].includes(p.status) ? "#22C55E" :
              p.status === "degraded" ? "#F59E0B" : "#EF4444"
          }}>
            <div className={styles.statTop}>
              <span className={styles.statLabel}>{p.name}</span>
              <span style={{ fontSize: "1.2rem" }}>{p.icon}</span>
            </div>
            <div style={{ marginTop: 8 }}>
              {providerStatusBadge(p.status)}
            </div>
            {p.extra && (
              <p className="text-xs text-muted" style={{ marginTop: 4 }}>{p.extra}</p>
            )}
          </div>
        ))}
      </div>

      {/* Job Status Summary */}
      {jobs?.status_counts && (
        <div className="card" style={{ marginTop: 20 }}>
          <h3 className={styles.cardTitle}>📊 Job Status Summary</h3>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 10 }}>
            {Object.entries(jobs.status_counts).map(([status, count]) => (
              <button
                key={status}
                className={`badge ${jobFilter === status ? "badge-primary" : "badge-muted"}`}
                onClick={() => filterJobs(jobFilter === status ? "" : status)}
                style={{ cursor: "pointer", padding: "6px 12px" }}
              >
                {status}: {count}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Jobs Table */}
      <div className="card" style={{ marginTop: 20 }}>
        <h3 className={styles.cardTitle}>🔧 Background Jobs</h3>
        {(!jobs?.jobs || jobs.jobs.length === 0) ? (
          <p className="text-muted text-sm">Belum ada job tercatat.</p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className={styles.table || "table"} style={{ width: "100%", fontSize: "0.85rem" }}>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Attempts</th>
                  <th>Error</th>
                  <th>Created</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {jobs.jobs.map((j) => (
                  <tr key={j.id}>
                    <td>{j.id}</td>
                    <td><code>{j.job_type}</code></td>
                    <td>
                      <span style={{
                        color: jobStatusColor(j.status),
                        fontWeight: 600,
                      }}>
                        {j.status}
                      </span>
                    </td>
                    <td>{j.attempts}/{j.max_attempts}</td>
                    <td style={{ maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {j.error_message || "-"}
                    </td>
                    <td>{j.created_at ? new Date(j.created_at).toLocaleString("id-ID") : "-"}</td>
                    <td>
                      {(j.status === "failed" || j.status === "dead_letter") && (
                        <button
                          className="btn btn-sm btn-outline"
                          onClick={() => handleRetryJob(j.id)}
                          disabled={retrying === j.id}
                          style={{ fontSize: "0.8rem", padding: "3px 8px" }}
                        >
                          {retrying === j.id ? "⏳" : "🔄 Retry"}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Config & Quick Actions */}
      <div className={styles.mainGrid} style={{ marginTop: 20 }}>
        <div className="card">
          <h3 className={styles.cardTitle}>⚙️ System Info</h3>
          <div className={styles.sysInfo}>
            {[
              { label: "App Version", value: `v${health?.version || "1.0.0"}` },
              { label: "Python", value: health?.python_version || "-" },
              { label: "LLM Model", value: health?.llm_model || "-" },
              { label: "Embedding", value: health?.embedding_model || "-" },
            ].map((c, i) => (
              <div key={i} className={styles.sysRow}>
                <span className={styles.sysLabel}>{c.label}</span>
                <code style={{ background: "var(--bg)", padding: "4px 10px", borderRadius: 4, fontSize: "0.85rem", color: "var(--text)" }}>{c.value}</code>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <h3 className={styles.cardTitle}>📋 Quick Actions</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <button className="btn btn-outline" onClick={handleRefresh}>
              🔄 Refresh All
            </button>
            <button className="btn btn-outline" onClick={() => { api.clearCache(); alert("Cache cleared!"); }}>
              🧹 Clear Frontend Cache
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
