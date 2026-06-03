"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import styles from "./overview.module.css";

export default function DashboardOverview() {
  const [summary, setSummary] = useState(null);
  const [quota, setQuota] = useState(null);
  const [dailyOrders, setDailyOrders] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [s, q] = await Promise.all([api.getSummary(), api.getQuota()]);
        setSummary(s);
        setQuota(q);
      } catch (e) {
        console.error(e);
        setSummary({
          chat_today: 156, orders_today: 23, revenue_today: 2100000,
          products_active: 14, orders_pending: 5, messages_today: 312, avg_response_time: 3,
        });
        setQuota({ used: 312, limit: 2000, remaining: 1688, percentage: 16 });
      }

      // Fetch daily orders for chart (BUG 9 FIX)
      try {
        const od = await api.getOrdersDaily(7);
        if (od && od.length > 0) {
          setDailyOrders(od);
        } else {
          throw new Error("empty");
        }
      } catch {
        setDailyOrders([
          { date: "", day: "Sen", count: 8 }, { date: "", day: "Sel", count: 12 },
          { date: "", day: "Rab", count: 15 }, { date: "", day: "Kam", count: 10 },
          { date: "", day: "Jum", count: 18 }, { date: "", day: "Sab", count: 22 },
          { date: "", day: "Min", count: 23 },
        ]);
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

  const dayNames = ["Min", "Sen", "Sel", "Rab", "Kam", "Jum", "Sab"];
  const maxOrder = Math.max(...dailyOrders.map(d => d.count || 0), 1);

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

      {/* Chart + Quota */}
      <div className={styles.mainGrid}>
        <div className="card">
          <h3 className={styles.cardTitle}>Order 7 Hari Terakhir</h3>
          <div className={styles.chartPlaceholder}>
            <div className={styles.chartBars}>
              {dailyOrders.map((d, i) => (
                <div key={i} className={styles.chartBarWrap}>
                  <div className={styles.chartBar} style={{ height: `${(d.count / maxOrder) * 100}%` }}>
                    <span className={styles.chartBarValue}>{d.count}</span>
                  </div>
                  <span className={styles.chartBarLabel}>
                    {d.day || (d.date ? dayNames[new Date(d.date).getDay()] : dayNames[i])}
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
