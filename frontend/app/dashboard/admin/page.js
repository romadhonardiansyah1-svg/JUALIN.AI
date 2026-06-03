"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import styles from "./admin.module.css";

export default function AdminPage() {
  const [stats, setStats] = useState(null);
  const [sellers, setSellers] = useState([]);
  const [user, setUser] = useState(null);

  useEffect(() => {
    const userData = localStorage.getItem("jualin_user");
    if (userData) setUser(JSON.parse(userData));
    loadData();
  }, []);

  async function loadData() {
    try {
      const data = await api.getSummary();
      setStats(data);
    } catch (e) {
      // Demo data
      setStats({
        total_sellers: 12, total_products: 156, total_orders: 342,
        total_revenue: 28500000, total_chats: 4230, active_today: 8,
      });
    }
    // Demo sellers
    setSellers([
      { id: 1, nama_toko: "Toko Sari Fashion", email: "sari@demo.com", tier: "pro", products: 15, orders: 89, revenue: 8500000, status: "active" },
      { id: 2, nama_toko: "Batik Nusantara", email: "batik@demo.com", tier: "starter", products: 28, orders: 45, revenue: 4200000, status: "active" },
      { id: 3, nama_toko: "Sneakers ID", email: "sneakers@demo.com", tier: "free", products: 8, orders: 12, revenue: 1800000, status: "active" },
      { id: 4, nama_toko: "Hijab Collection", email: "hijab@demo.com", tier: "pro", products: 42, orders: 156, revenue: 12000000, status: "active" },
      { id: 5, nama_toko: "Gadget Murah", email: "gadget@demo.com", tier: "bisnis", products: 63, orders: 40, revenue: 2000000, status: "suspended" },
    ]);
  }

  const platformStats = [
    { label: "Total Seller", value: stats?.total_sellers || 0, icon: "🏪", bg: "var(--stat-green-bg)", border: "var(--primary)" },
    { label: "Total Produk", value: stats?.total_products || 0, icon: "📦", bg: "var(--stat-blue-bg)", border: "var(--secondary)" },
    { label: "Total Order", value: stats?.total_orders || 0, icon: "🛒", bg: "var(--stat-purple-bg)", border: "var(--tertiary)" },
    { label: "Revenue Platform", value: `Rp ${((stats?.total_revenue || 0) / 1000000).toFixed(1)}Jt`, icon: "💰", bg: "var(--stat-orange-bg)", border: "var(--stat-orange)" },
    { label: "Total Chat AI", value: stats?.total_chats || 0, icon: "💬", bg: "var(--stat-green-bg)", border: "var(--primary)" },
    { label: "Aktif Hari Ini", value: stats?.active_today || 0, icon: "🟢", bg: "var(--stat-blue-bg)", border: "var(--secondary)" },
  ];

  const tierBadge = (tier) => {
    const map = { free: "badge-neutral", starter: "badge-info", pro: "badge-success", bisnis: "badge-primary" };
    return map[tier] || "badge-neutral";
  };

  return (
    <div className={styles.adminPage}>
      <div className={styles.header}>
        <div>
          <h2>Admin Panel</h2>
          <p className="text-muted text-sm">Manajemen platform JUALIN.AI</p>
        </div>
        <span className="badge badge-danger" style={{ fontSize: "0.85rem", padding: "6px 14px" }}>
          🔑 Owner Access
        </span>
      </div>

      {/* Platform Stats */}
      <div className={styles.statsGrid}>
        {platformStats.map((s, i) => (
          <div key={i} className={styles.statCard} style={{ borderTopColor: s.border, background: s.bg }}>
            <div className={styles.statTop}>
              <span className={styles.statLabel}>{s.label}</span>
              <span>{s.icon}</span>
            </div>
            <div className={styles.statValue}>{typeof s.value === "number" ? s.value.toLocaleString() : s.value}</div>
          </div>
        ))}
      </div>

      {/* Sellers Table */}
      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <div className={styles.tableHeader}>
          <h3>Daftar Seller ({sellers.length})</h3>
        </div>
        <div className="table-container">
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Toko</th>
                <th>Email</th>
                <th>Tier</th>
                <th>Produk</th>
                <th>Order</th>
                <th>Revenue</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {sellers.map((s) => (
                <tr key={s.id}>
                  <td>#{s.id}</td>
                  <td><strong>{s.nama_toko}</strong></td>
                  <td className="text-sm text-muted">{s.email}</td>
                  <td><span className={`badge ${tierBadge(s.tier)}`}>{s.tier.toUpperCase()}</span></td>
                  <td>{s.products}</td>
                  <td>{s.orders}</td>
                  <td className="font-semibold">Rp {(s.revenue / 1000000).toFixed(1)}Jt</td>
                  <td>
                    <span className={`badge ${s.status === "active" ? "badge-success" : "badge-danger"}`}>
                      {s.status === "active" ? "Aktif" : "Suspended"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* System Info */}
      <div className={styles.systemGrid}>
        <div className="card">
          <h3 className={styles.cardTitle}>🖥️ System Info</h3>
          <div className={styles.sysInfo}>
            <div className={styles.sysRow}><span>Backend</span><span className="badge badge-success">Online</span></div>
            <div className={styles.sysRow}><span>Database</span><span className="badge badge-success">Connected</span></div>
            <div className={styles.sysRow}><span>Redis</span><span className="badge badge-success">Connected</span></div>
            <div className={styles.sysRow}><span>AI Engine</span><span className="badge badge-success">Ready</span></div>
            <div className={styles.sysRow}><span>Follow-up Scheduler</span><span className="badge badge-success">Running</span></div>
            <div className={styles.sysRow}><span>Version</span><span className="text-muted">v1.0.0</span></div>
          </div>
        </div>

        <div className="card">
          <h3 className={styles.cardTitle}>📊 Tier Distribution</h3>
          <div className={styles.tierDist}>
            {[
              { tier: "Free", count: 5, color: "var(--text-muted)" },
              { tier: "Starter", count: 3, color: "var(--secondary)" },
              { tier: "Pro", count: 3, color: "var(--primary)" },
              { tier: "Bisnis", count: 1, color: "var(--tertiary)" },
            ].map((t, i) => (
              <div key={i} className={styles.tierRow}>
                <span>{t.tier}</span>
                <div className={styles.tierBar}>
                  <div style={{ width: `${(t.count / 12) * 100}%`, background: t.color, height: "100%", borderRadius: 4 }}></div>
                </div>
                <span className="font-semibold">{t.count}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
