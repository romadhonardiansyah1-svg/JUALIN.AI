"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import styles from "./overview.module.css";

export default function DashboardOverview() {
  const [summary, setSummary] = useState(null);
  const [quota, setQuota] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [s, q] = await Promise.all([api.getSummary(), api.getQuota()]);
        setSummary(s);
        setQuota(q);
      } catch (e) {
        console.error(e);
        // Use demo data for offline
        setSummary({
          chat_today: 156, orders_today: 23, revenue_today: 2100000,
          products_active: 14, orders_pending: 5, messages_today: 312, avg_response_time: 3,
        });
        setQuota({ used: 312, limit: 2000, remaining: 1688, percentage: 16 });
      }
      setLoading(false);
    }
    load();
  }, []);

  if (loading) return <div className={styles.loading}>Loading...</div>;

  const stats = [
    { label: "Chat Hari Ini", value: summary?.chat_today || 0, change: "+12%", type: "green", icon: "💬" },
    { label: "Order Hari Ini", value: summary?.orders_today || 0, change: "+8%", type: "blue", icon: "🛒" },
    { label: "Revenue", value: `Rp ${((summary?.revenue_today || 0) / 1000000).toFixed(1)}Jt`, change: "+15%", type: "purple", icon: "💰" },
    { label: "Avg Respons", value: `${summary?.avg_response_time || 3} dtk`, change: "", type: "orange", icon: "⏱️" },
  ];

  return (
    <div className={styles.overview}>
      {/* Alert Banner */}
      {summary?.orders_pending > 0 && (
        <div className={styles.alertBanner}>
          ⚠️ <strong>{summary.orders_pending} customer belum bayar</strong> — follow-up AI aktif
        </div>
      )}

      {/* Stat Cards */}
      <div className={styles.statsGrid}>
        {stats.map((s, i) => (
          <div key={i} className={`stat-card ${s.type}`}>
            <div className={styles.statTop}>
              <span className="stat-label">{s.label}</span>
              <span className={styles.statIcon}>{s.icon}</span>
            </div>
            <div className="stat-value">{s.value}</div>
            {s.change && <div className="stat-change up">↑ {s.change} dari kemarin</div>}
          </div>
        ))}
      </div>

      {/* Chart placeholder + Orders table */}
      <div className={styles.mainGrid}>
        <div className="card">
          <h3 className={styles.cardTitle}>Order 7 Hari Terakhir</h3>
          <div className={styles.chartPlaceholder}>
            <div className={styles.chartBars}>
              {[8, 12, 15, 10, 18, 22, 23].map((v, i) => (
                <div key={i} className={styles.chartBarWrap}>
                  <div className={styles.chartBar} style={{ height: `${(v / 25) * 100}%` }}>
                    <span className={styles.chartBarValue}>{v}</span>
                  </div>
                  <span className={styles.chartBarLabel}>
                    {["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"][i]}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="card">
          <h3 className={styles.cardTitle}>Quota Chat</h3>
          <div className={styles.quotaInfo}>
            <div className={styles.quotaNumbers}>
              <span className={styles.quotaUsed}>{quota?.used || 0}</span>
              <span className={styles.quotaTotal}>/ {quota?.limit || 0}</span>
            </div>
            <div className="progress-bar">
              <div className="progress-fill" style={{ width: `${quota?.percentage || 0}%` }}></div>
            </div>
            <p className="text-sm text-muted mt-2">
              Sisa {quota?.remaining || 0} chat bulan ini
            </p>
          </div>

          <h3 className={styles.cardTitle} style={{ marginTop: 28 }}>Produk Aktif</h3>
          <div className={styles.quickStat}>
            <span className={styles.quickStatValue}>{summary?.products_active || 0}</span>
            <span className="text-muted">produk</span>
          </div>
        </div>
      </div>
    </div>
  );
}
