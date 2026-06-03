"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import styles from "../admin.module.css";

export default function AdminSellersPage() {
  const [sellers, setSellers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filterTier, setFilterTier] = useState("");
  const [updating, setUpdating] = useState(null);

  useEffect(() => {
    loadSellers();
  }, []);

  async function loadSellers() {
    try {
      const data = await api.getAdminSellers();
      setSellers(data);
    } catch (e) {
      // Demo data
      setSellers([
        { id: 1, nama_toko: "Toko Sari Fashion", email: "sari@demo.com", tier: "pro", products: 15, orders: 89, revenue: 8500000, chats: 456, ai_active: true, slug: "toko-sari-fashion", no_hp: "081234567890", created_at: "2026-01-15T10:00:00" },
        { id: 2, nama_toko: "Batik Nusantara", email: "batik@demo.com", tier: "starter", products: 28, orders: 45, revenue: 4200000, chats: 234, ai_active: true, slug: "batik-nusantara", no_hp: "082345678901", created_at: "2026-02-20T10:00:00" },
        { id: 3, nama_toko: "Sneakers ID", email: "sneakers@demo.com", tier: "free", products: 8, orders: 12, revenue: 1800000, chats: 89, ai_active: true, slug: "sneakers-id", no_hp: "", created_at: "2026-03-10T10:00:00" },
        { id: 4, nama_toko: "Hijab Collection", email: "hijab@demo.com", tier: "pro", products: 42, orders: 156, revenue: 12000000, chats: 890, ai_active: true, slug: "hijab-collection", no_hp: "084567890123", created_at: "2026-01-05T10:00:00" },
        { id: 5, nama_toko: "Gadget Murah", email: "gadget@demo.com", tier: "bisnis", products: 63, orders: 40, revenue: 2000000, chats: 120, ai_active: false, slug: "gadget-murah", no_hp: "085678901234", created_at: "2026-04-01T10:00:00" },
      ]);
    }
    setLoading(false);
  }

  const handleTierChange = async (sellerId, newTier) => {
    setUpdating(sellerId);
    try {
      await api.updateAdminSeller(sellerId, { tier: newTier });
      setSellers(prev => prev.map(s => s.id === sellerId ? { ...s, tier: newTier } : s));
    } catch (e) {
      alert("Gagal update tier: " + e.message);
    }
    setUpdating(null);
  };

  const handleToggleAI = async (sellerId, currentActive) => {
    setUpdating(sellerId);
    try {
      await api.updateAdminSeller(sellerId, { ai_active: !currentActive });
      setSellers(prev => prev.map(s => s.id === sellerId ? { ...s, ai_active: !currentActive, status: !currentActive ? "active" : "inactive" } : s));
    } catch (e) {
      alert("Gagal update status: " + e.message);
    }
    setUpdating(null);
  };

  const filtered = sellers.filter(s => {
    const matchSearch = s.nama_toko.toLowerCase().includes(search.toLowerCase()) ||
                       s.email.toLowerCase().includes(search.toLowerCase());
    const matchTier = !filterTier || s.tier === filterTier;
    return matchSearch && matchTier;
  });

  const tierBadge = (tier) => {
    const map = { free: "badge-neutral", starter: "badge-info", pro: "badge-success", bisnis: "badge-primary" };
    return map[tier] || "badge-neutral";
  };

  if (loading) {
    return (
      <div className={styles.loadingSkeleton}>
        <div className={styles.skelRow}>
          {[1,2,3,4].map(i => <div key={i} className={styles.skelCard} />)}
        </div>
        <div className={styles.skelBlock} />
      </div>
    );
  }

  return (
    <div className={styles.adminPage}>
      <div className={styles.header}>
        <div>
          <h2>👥 Kelola Seller</h2>
          <p className="text-muted text-sm">{sellers.length} seller terdaftar</p>
        </div>
        <div className={styles.headerActions}>
          <input
            type="text"
            className="input"
            placeholder="🔍 Cari seller..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: 220 }}
          />
          <select className="select" value={filterTier} onChange={(e) => setFilterTier(e.target.value)}>
            <option value="">Semua Tier</option>
            <option value="free">Free</option>
            <option value="starter">Starter</option>
            <option value="pro">Pro</option>
            <option value="bisnis">Bisnis</option>
          </select>
        </div>
      </div>

      {/* Summary Cards */}
      <div className={styles.statsGrid}>
        <div className={styles.statCard} style={{ borderTopColor: "#22C55E" }}>
          <div className={styles.statTop}>
            <span className={styles.statLabel}>Total Seller</span>
            <span className={styles.statIconBg} style={{ background: "#22C55E15", color: "#22C55E" }}>🏪</span>
          </div>
          <div className={styles.statValue}>{sellers.length}</div>
        </div>
        <div className={styles.statCard} style={{ borderTopColor: "#0EA5E9" }}>
          <div className={styles.statTop}>
            <span className={styles.statLabel}>AI Aktif</span>
            <span className={styles.statIconBg} style={{ background: "#0EA5E915", color: "#0EA5E9" }}>🤖</span>
          </div>
          <div className={styles.statValue}>{sellers.filter(s => s.ai_active).length}</div>
        </div>
        <div className={styles.statCard} style={{ borderTopColor: "#8B5CF6" }}>
          <div className={styles.statTop}>
            <span className={styles.statLabel}>Total Produk</span>
            <span className={styles.statIconBg} style={{ background: "#8B5CF615", color: "#8B5CF6" }}>📦</span>
          </div>
          <div className={styles.statValue}>{sellers.reduce((a, s) => a + (s.products || 0), 0)}</div>
        </div>
        <div className={styles.statCard} style={{ borderTopColor: "#F97316" }}>
          <div className={styles.statTop}>
            <span className={styles.statLabel}>Total Revenue</span>
            <span className={styles.statIconBg} style={{ background: "#F9731615", color: "#F97316" }}>💰</span>
          </div>
          <div className={styles.statValue}>Rp {(sellers.reduce((a, s) => a + (s.revenue || 0), 0) / 1000000).toFixed(1)}Jt</div>
        </div>
      </div>

      {/* Sellers Table */}
      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <div className={styles.tableHeader}>
          <h3>Daftar Seller ({filtered.length})</h3>
        </div>
        <div className="table-container">
          <table className="table">
            <thead>
              <tr>
                <th>Toko</th>
                <th>Tier</th>
                <th>Produk</th>
                <th>Order</th>
                <th>Chat</th>
                <th>Revenue</th>
                <th>AI Status</th>
                <th>Aksi</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((s) => (
                <tr key={s.id}>
                  <td>
                    <div className={styles.sellerCell}>
                      <div className={styles.sellerAvatar}>{s.nama_toko?.charAt(0)}</div>
                      <div>
                        <strong>{s.nama_toko}</strong>
                        <span className="text-xs text-muted" style={{ display: "block" }}>{s.email}</span>
                      </div>
                    </div>
                  </td>
                  <td>
                    <select 
                      className="select" 
                      value={s.tier} 
                      onChange={(e) => handleTierChange(s.id, e.target.value)}
                      disabled={updating === s.id}
                      style={{ padding: "4px 8px", fontSize: "0.8rem" }}
                    >
                      <option value="free">Free</option>
                      <option value="starter">Starter</option>
                      <option value="pro">Pro</option>
                      <option value="bisnis">Bisnis</option>
                    </select>
                  </td>
                  <td>{s.products}</td>
                  <td>{s.orders}</td>
                  <td>{s.chats}</td>
                  <td className="font-semibold">Rp {((s.revenue || 0) / 1000000).toFixed(1)}Jt</td>
                  <td>
                    <span className={`badge ${s.ai_active ? "badge-success" : "badge-danger"}`}>
                      {s.ai_active ? "Aktif" : "Nonaktif"}
                    </span>
                  </td>
                  <td>
                    <button 
                      className={`btn btn-sm ${s.ai_active ? "btn-danger" : "btn-primary"}`}
                      onClick={() => handleToggleAI(s.id, s.ai_active)}
                      disabled={updating === s.id}
                    >
                      {updating === s.id ? "..." : (s.ai_active ? "Nonaktifkan" : "Aktifkan")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
