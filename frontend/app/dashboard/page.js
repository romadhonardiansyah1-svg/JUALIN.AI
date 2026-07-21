"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import styles from "./overview.module.css";

export default function DashboardOverview() {
  const [summary, setSummary] = useState(null);
  const [quota, setQuota] = useState(null);
  const [dailyOrders, setDailyOrders] = useState([]);
  const [chatStats, setChatStats] = useState(null);
  const [moneyData, setMoneyData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [user, setUser] = useState(null);

  useEffect(() => {
    async function load() {
      // Identity from cookie session only — never rehydrate claims from localStorage.
      const meRes = await Promise.allSettled([api.getMe()]);
      setUser(meRes[0].status === "fulfilled" ? meRes[0].value : null);

      const [sRes, qRes, odRes, csRes, mdRes] = await Promise.allSettled([
        api.getSummary(),
        api.getQuota(),
        api.getOrdersDaily(7),
        api.getChatStats(7),
        api.getMoneyDashboard(),
      ]);
      // P5.5 — independent section results; failure is null/unavailable, not zero.
      setSummary(sRes.status === "fulfilled" ? sRes.value : null);
      setQuota(qRes.status === "fulfilled" ? qRes.value : null);
      setDailyOrders(
        odRes.status === "fulfilled" && Array.isArray(odRes.value) ? odRes.value : []
      );
      setChatStats(csRes.status === "fulfilled" ? csRes.value : null);
      setMoneyData(mdRes.status === "fulfilled" ? mdRes.value : null);
      setLoading(false);
    }
    load();
  }, []);

  if (loading) {
    return (
      <div className={styles.overview}>
        <div className={styles.statsGrid}>
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className={styles.skeletonCard}>
              <div className="skeleton skeleton-text" style={{ width: "60%" }}></div>
              <div className="skeleton skeleton-title" style={{ width: "40%" }}></div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  const stats = moneyData && !moneyData.is_empty
    ? [
        {
          label: "Omzet (teramati, bukan kausal AI)",
          value: `Rp ${((moneyData.ai_assisted_revenue || 0) / 1000000).toFixed(1)}Jt`,
          change: "",
          up: true,
          type: "green",
          icon: "📊",
        },
        {
          label: "Order terkait sesi chat",
          value: moneyData.ai_assisted_orders ?? "—",
          change: "",
          up: true,
          type: "blue",
          icon: "🛒",
        },
        {
          label: "Payment Pending",
          value: `Rp ${((moneyData.pending_payment_value || 0) / 1000000).toFixed(1)}Jt`,
          change: "",
          up: false,
          type: "orange",
          icon: "⏳",
        },
        {
          label: "Pembayaran teramati (bukan recovered by AI)",
          value: `Rp ${((moneyData.recovered_payment_value || 0) / 1000000).toFixed(1)}Jt`,
          change: "",
          up: true,
          type: "purple",
          icon: "💰",
        },
      ]
    : [
        { label: "Chat Hari Ini", value: summary?.chat_today ?? "—", change: "", up: true, type: "green", icon: "💬" },
        { label: "Order Hari Ini", value: summary?.orders_today ?? "—", change: "", up: true, type: "blue", icon: "🛒" },
        {
          label: "Revenue",
          value: summary != null ? `Rp ${((summary?.revenue_today || 0) / 1000000).toFixed(1)}Jt` : "—",
          change: "",
          up: true,
          type: "purple",
          icon: "💰",
        },
        {
          label: "Avg Respons",
          value: summary != null && summary?.avg_response_time != null
            ? `${summary.avg_response_time} dtk`
            : "—",
          change: "",
          up: true,
          type: "orange",
          icon: "⚡",
        },
      ];

  const dayNames = ["Min", "Sen", "Sel", "Rab", "Kam", "Jum", "Sab"];
  const maxOrder = Math.max(...dailyOrders.map(d => d.count || 0), 1);
  const quotaPercent = quota?.percentage || 0;

  return (
    <div className={styles.overview}>
      {/* Welcome Banner */}
      <div className={styles.welcomeBanner}>
        <div>
          <h1 className={styles.welcomeTitle}>
            Selamat datang, {user?.nama_toko || "Seller"} 👋
          </h1>
          <p className={styles.welcomeDesc}>Berikut ringkasan performa toko Anda hari ini</p>
        </div>
        <Link href={`/chat/${user?.slug || ""}`} className="btn btn-outline btn-sm" target="_blank">
          🔗 Lihat Chat Page
        </Link>
      </div>

      {/* Alert Banner — truthful, no claim of AI active without capability */}
      {summary?.orders_pending > 0 && (
        <div className={styles.alertBanner}>
          <span className={styles.alertIcon}>⚠️</span>
          <span>
            <strong>{summary.orders_pending} customer belum bayar</strong> — periksa pesanan menunggu pembayaran
          </span>
          <Link href="/dashboard/orders" className={styles.alertLink}>Lihat Order →</Link>
          <Link href="/dashboard/recovery" className={styles.alertLink}>Jualin Santai →</Link>
        </div>
      )}
      {summary === null && (
        <div className={styles.alertBanner}>
          <span className={styles.alertIcon}>ℹ️</span>
          <span>Bagian ringkasan belum dapat dimuat. Data lain tetap aman.</span>
        </div>
      )}

      {/* Stat Cards */}
      <div className={styles.statsGrid}>
        {stats.map((s, i) => (
          <div key={i} className={`stat-card ${s.type}`} style={{ animationDelay: `${i * 0.1}s` }}>
            <div className={styles.statTop}>
              <span className="stat-label">{s.label}</span>
              <span className={styles.statIcon}>{s.icon}</span>
            </div>
            <div className="stat-value">{s.value}</div>
            {s.change && (
              <div className={`stat-change ${s.up ? "up" : "down"}`}>
                {s.up ? "↑" : "↓"} {s.change} dari kemarin
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Main Grid: Chart + Quota + Quick Actions */}
      <div className={styles.mainGrid}>
        {/* Chart */}
        <div className="card">
          <div className={styles.cardHeader}>
            <h3 className={styles.cardTitle}>📊 Order 7 Hari Terakhir</h3>
            <span className={styles.cardBadge}>{dailyOrders.reduce((a, d) => a + (d.count || 0), 0)} total</span>
          </div>
          <div className={styles.chartArea}>
            <div className={styles.chartBars}>
              {dailyOrders.map((d, i) => (
                <div key={i} className={styles.chartBarWrap}>
                  <div className={styles.chartBarContainer}>
                    <div className={styles.chartBar} style={{ height: `${(d.count / maxOrder) * 100}%` }}>
                      <span className={styles.chartBarValue}>{d.count}</span>
                    </div>
                  </div>
                  <span className={styles.chartBarLabel}>
                    {d.day || (d.date ? dayNames[new Date(d.date).getDay()] : dayNames[i])}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right Column */}
        <div className={styles.rightCol}>
          {/* Quota */}
          <div className="card">
            <div className={styles.cardHeader}>
              <h3 className={styles.cardTitle}>💬 Quota Chat</h3>
              <span className={`badge ${quotaPercent > 80 ? "badge-warning" : "badge-primary"}`}>
                {quotaPercent}%
              </span>
            </div>
            <div className={styles.quotaInfo}>
              <div className={styles.quotaNumbers}>
                <span className={styles.quotaUsed}>{quota?.used || 0}</span>
                <span className={styles.quotaTotal}>/ {quota?.limit || 0}</span>
              </div>
              <div className="progress-bar">
                <div className="progress-fill" style={{ width: `${quotaPercent}%` }}></div>
              </div>
              <p className="text-sm text-muted mt-2">
                Sisa {quota?.remaining || 0} chat bulan ini
              </p>
            </div>
          </div>

          {/* Quick Stats */}
          <div className="card">
            <h3 className={styles.cardTitle}>📦 Ringkasan</h3>
            <div className={styles.quickStats}>
              <div className={styles.quickStatRow}>
                <span className={styles.quickLabel}>Produk Aktif</span>
                <span className={styles.quickValue}>
                  {summary != null ? (summary.products_active ?? "—") : "—"}
                </span>
              </div>
              <div className={styles.quickStatRow}>
                <span className={styles.quickLabel}>Avg Response Time</span>
                <span className={styles.quickValue}>
                  {chatStats?.avg_response_time_ms != null
                    ? `${(chatStats.avg_response_time_ms / 1000).toFixed(1)}s`
                    : summary?.avg_response_time != null
                      ? `${summary.avg_response_time}s`
                      : "—"}
                </span>
              </div>
              <div className={styles.quickStatRow}>
                <span className={styles.quickLabel}>Conversion Rate</span>
                <span className={styles.quickValue}>
                  {chatStats?.conversion_rate != null ? `${chatStats.conversion_rate}%` : "—"}
                </span>
              </div>
              <div className={styles.quickStatRow}>
                <span className={styles.quickLabel}>Total Interaksi</span>
                <span className={styles.quickValue}>
                  {chatStats?.total_interactions ?? summary?.messages_today ?? "—"}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
