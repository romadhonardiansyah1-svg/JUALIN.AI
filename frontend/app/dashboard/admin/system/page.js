"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import styles from "../admin.module.css";

export default function AdminSystemPage() {
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    loadHealth();
  }, []);

  async function loadHealth() {
    try {
      const data = await api.getSystemHealth();
      setHealth(data);
    } catch (e) {
      console.error("Failed to load system health", e);
      setHealth({
        backend: "unknown",
        database: "unknown",
        redis: "unknown",
        ai_engine: "unknown",
        followup_scheduler: "unknown",
        version: "unknown",
        python_version: "-",
        platform: "-",
        llm_model: "-",
        embedding_model: "-",
      });
    }
    setLoading(false);
  }

  async function handleRefresh() {
    setRefreshing(true);
    await loadHealth();
    setRefreshing(false);
  }

  if (loading) {
    return (
      <div className={styles.loadingSkeleton}>
        <div className={styles.skelRow}>
          {[1,2].map(i => <div key={i} className={styles.skelCard} style={{ height: 200 }} />)}
        </div>
      </div>
    );
  }

  const statusColor = (val) => {
    const good = ["online", "connected", "ready", "running"];
    return good.includes(val) ? "badge-success" : "badge-danger";
  };

  const services = [
    { name: "Backend Server", key: "backend", icon: "🚀", desc: "FastAPI application server" },
    { name: "Database", key: "database", icon: "🗄️", desc: "PostgreSQL + pgvector" },
    { name: "Redis Cache", key: "redis", icon: "⚡", desc: "Cache & rate limiter" },
    { name: "AI Engine", key: "ai_engine", icon: "🤖", desc: "LLM + Embeddings" },
    { name: "Follow-up Scheduler", key: "followup_scheduler", icon: "⏰", desc: "Auto follow-up setiap 15 menit" },
  ];

  const configs = [
    { label: "App Version", value: `v${health?.version || "1.0.0"}` },
    { label: "Python", value: health?.python_version || "-" },
    { label: "Platform", value: health?.platform || "-" },
    { label: "LLM Model", value: health?.llm_model || "-" },
    { label: "Embedding Model", value: health?.embedding_model || "-" },
  ];

  return (
    <div className={styles.adminPage}>
      <div className={styles.header}>
        <div>
          <h2>🖥️ System Monitor</h2>
          <p className="text-muted text-sm">Status sistem dan konfigurasi JUALIN.AI</p>
        </div>
        <button 
          className="btn btn-outline" 
          onClick={handleRefresh} 
          disabled={refreshing}
        >
          {refreshing ? "⏳ Refreshing..." : "🔄 Refresh"}
        </button>
      </div>

      {/* Service Status Cards */}
      <div className={styles.statsGrid}>
        {services.map((svc) => (
          <div key={svc.key} className={styles.statCard} style={{ borderTopColor: health?.[svc.key] === "online" || health?.[svc.key] === "connected" || health?.[svc.key] === "ready" || health?.[svc.key] === "running" ? "#22C55E" : "#EF4444" }}>
            <div className={styles.statTop}>
              <span className={styles.statLabel}>{svc.name}</span>
              <span style={{ fontSize: "1.2rem" }}>{svc.icon}</span>
            </div>
            <div style={{ marginTop: 8 }}>
              <span className={`badge ${statusColor(health?.[svc.key])}`}>
                ● {health?.[svc.key] || "unknown"}
              </span>
            </div>
            <p className="text-xs text-muted" style={{ marginTop: 6 }}>{svc.desc}</p>
          </div>
        ))}
      </div>

      {/* Config + Info */}
      <div className={styles.mainGrid}>
        <div className="card">
          <h3 className={styles.cardTitle}>⚙️ Konfigurasi Sistem</h3>
          <div className={styles.sysInfo}>
            {configs.map((c, i) => (
              <div key={i} className={styles.sysRow}>
                <span className={styles.sysLabel}>{c.label}</span>
                <code style={{ 
                  background: "var(--bg)", padding: "4px 10px", borderRadius: 4, 
                  fontSize: "0.85rem", color: "var(--text)" 
                }}>{c.value}</code>
              </div>
            ))}
          </div>
        </div>

        <div className={styles.rightColumn}>
          <div className="card">
            <h3 className={styles.cardTitle}>📋 Quick Actions</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <button className="btn btn-outline" onClick={handleRefresh}>
                🔄 Refresh System Status
              </button>
              <button className="btn btn-outline" onClick={() => { api.clearCache(); alert("Cache frontend berhasil dibersihkan!"); }}>
                🧹 Clear Frontend Cache
              </button>
            </div>
          </div>

          <div className="card">
            <h3 className={styles.cardTitle}>📊 Rate Limits</h3>
            <div className={styles.sysInfo}>
              <div className={styles.sysRow}>
                <span className={styles.sysLabel}>Chat API</span>
                <span className="text-sm">10 req/menit</span>
              </div>
              <div className={styles.sysRow}>
                <span className={styles.sysLabel}>Auth API</span>
                <span className="text-sm">5 req/menit</span>
              </div>
              <div className={styles.sysRow}>
                <span className={styles.sysLabel}>General API</span>
                <span className="text-sm">60 req/menit</span>
              </div>
              <div className={styles.sysRow}>
                <span className={styles.sysLabel}>Static Assets</span>
                <span className="text-sm">120 req/menit</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
