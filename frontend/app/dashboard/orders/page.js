"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import styles from "./orders.module.css";

const STATUS_MAP = {
  pending: { label: "Menunggu Bayar", badge: "badge-warning" },
  paid: { label: "Sudah Bayar", badge: "badge-success" },
  shipped: { label: "Dikirim", badge: "badge-info" },
  done: { label: "Selesai", badge: "badge-primary" },
  cancelled: { label: "Dibatalkan", badge: "badge-danger" },
};

export default function OrdersPage() {
  const [orders, setOrders] = useState([]);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState("");
  const [updatingId, setUpdatingId] = useState(null);
  const [exporting, setExporting] = useState(false);

  // Format items array → readable text (BUG 8 FIX)
  function formatItems(items) {
    if (typeof items === "string") return items;
    if (!Array.isArray(items)) return "-";
    return items.map(i => `${i.nama || "Produk"} x${i.qty || 1}`).join(", ");
  }

  const loadOrders = useCallback(async () => {
    setError("");
    try {
      const data = await api.getOrders(filter);
      setOrders(data);
    } catch (e) {
      console.error("Failed to load orders:", e);
      setOrders([]);
      setError(e.message || "Gagal memuat order. Angka di bawah bukan data sebenarnya.");
    }
  }, [filter]);

  useEffect(() => {
    loadOrders();
  }, [loadOrders]);

  const handleStatusChange = async (id, newStatus) => {
    if (updatingId) return;
    setUpdatingId(id);
    try {
      await api.updateOrderStatus(id, { status: newStatus });
      await loadOrders();
    } catch (e) {
      alert(e.message);
    }
    setUpdatingId(null);
  };

  const handleExportCSV = async () => {
    if (exporting) return;
    setExporting(true);
    try {
      const apiBase = process.env.NEXT_PUBLIC_API_URL || "";
      const url = `${apiBase}/api/orders/export/csv${filter ? `?status=${filter}` : ""}`;
      const csrfCookie = (typeof document !== "undefined" ? document.cookie.split("; ").find(c => c.startsWith("jualin_csrf=") || c.startsWith("__Host-jualin_csrf=")) : null);
      const csrfValue = csrfCookie ? decodeURIComponent(csrfCookie.split("=")[1]) : "";
      const res = await fetch(url, {
        credentials: "include",
        headers: { ...(csrfValue ? { "X-CSRF-Token": csrfValue } : {}) },
      });
      if (!res.ok) throw new Error("Gagal export");
      const blob = await res.blob();
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `jualin_orders.csv`;
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (e) {
      alert("Export gagal: " + e.message);
    }
    setExporting(false);
  };

  return (
    <div className={styles.ordersPage}>
      <div className={styles.header}>
        <div>
          <h2>Order</h2>
          <p className="text-muted text-sm">{error ? "Jumlah order belum diketahui" : `${orders.length} total order`}</p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <div className={styles.filters}>
            {["", "pending", "paid", "shipped", "done"].map((s) => (
              <button
                key={s}
                className={`${styles.filterBtn} ${filter === s ? styles.filterActive : ""}`}
                onClick={() => setFilter(s)}
              >
                {s ? STATUS_MAP[s]?.label : "Semua"}
              </button>
            ))}
          </div>
          <button className="btn btn-outline" onClick={handleExportCSV} disabled={exporting} title="Export ke CSV">
            {exporting ? "⏳ Menyiapkan..." : "📥 Export CSV"}
          </button>
        </div>
      </div>

      {error && (
        <div className={styles.errorBox} role="alert">
          {error} <button className="btn btn-sm btn-outline" onClick={loadOrders}>Coba lagi</button>
        </div>
      )}

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <div className="table-container">
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Customer</th>
                <th>Produk</th>
                <th>Total</th>
                <th>Status</th>
                <th>Tanggal</th>
                <th>Aksi</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.id}>
                  <td>#{o.id}</td>
                  <td><strong>{o.customer_name}</strong></td>
                  <td className="text-sm">{formatItems(o.items)}</td>
                  <td className="font-semibold">Rp {o.total?.toLocaleString("id-ID")}</td>
                  <td><span className={`badge ${STATUS_MAP[o.status]?.badge || "badge-neutral"}`}>{STATUS_MAP[o.status]?.label || o.status}</span></td>
                  <td className="text-sm text-muted">{new Date(o.created_at).toLocaleDateString("id-ID")}</td>
                  <td>
                    {o.status === "pending" && (
                      <div style={{ display: "flex", gap: "6px" }}>
                        <button className="btn btn-sm btn-primary" onClick={() => handleStatusChange(o.id, "paid")} disabled={updatingId !== null}>✓ Bayar</button>
                        <button className="btn btn-sm btn-outline" style={{ color: "#EF4444" }} disabled={updatingId !== null} aria-label={`Batalkan order ${o.id}`} onClick={() => { if (confirm("Batalkan order ini?")) handleStatusChange(o.id, "cancelled"); }}>✕</button>
                      </div>
                    )}
                    {o.status === "paid" && (
                      <button className="btn btn-sm btn-outline" onClick={() => handleStatusChange(o.id, "shipped")} disabled={updatingId !== null}>📦 Kirim</button>
                    )}
                    {o.status === "shipped" && (
                      <button className="btn btn-sm btn-outline" onClick={() => handleStatusChange(o.id, "done")} disabled={updatingId !== null}>✅ Selesai</button>
                    )}
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
