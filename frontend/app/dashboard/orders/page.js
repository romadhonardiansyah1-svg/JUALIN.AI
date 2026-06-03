"use client";
import { useEffect, useState } from "react";
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

  useEffect(() => {
    loadOrders();
  }, [filter]);

  async function loadOrders() {
    try {
      const data = await api.getOrders(filter);
      setOrders(data);
    } catch (e) {
      setOrders([
        { id: 1, customer_name: "Rina Sari", items: "Baju Pink Satin x2", total: 178000, status: "pending", created_at: new Date().toISOString() },
        { id: 2, customer_name: "Budi Santoso", items: "Kaos Oversize Hitam x1, Hoodie Abu-abu x1", total: 184000, status: "paid", created_at: new Date().toISOString() },
        { id: 3, customer_name: "Dewi Lestari", items: "Dress Emerald Elegan x1", total: 189000, status: "shipped", created_at: new Date().toISOString() },
        { id: 4, customer_name: "Ahmad Fadli", items: "Celana Cargo Hijau x1", total: 135000, status: "done", created_at: new Date().toISOString() },
        { id: 5, customer_name: "Siti Nurhaliza", items: "Gamis Pesta Navy x1", total: 225000, status: "pending", created_at: new Date().toISOString() },
      ]);
    }
  }

  const handleStatusChange = async (id, newStatus) => {
    try {
      await api.updateOrderStatus(id, { status: newStatus });
      loadOrders();
    } catch (e) {
      alert(e.message);
    }
  };

  return (
    <div className={styles.ordersPage}>
      <div className={styles.header}>
        <div>
          <h2>Order</h2>
          <p className="text-muted text-sm">{orders.length} total order</p>
        </div>
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
      </div>

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
                  <td className="text-sm">{typeof o.items === "string" ? o.items : JSON.stringify(o.items)}</td>
                  <td className="font-semibold">Rp {o.total?.toLocaleString("id-ID")}</td>
                  <td><span className={`badge ${STATUS_MAP[o.status]?.badge || "badge-neutral"}`}>{STATUS_MAP[o.status]?.label || o.status}</span></td>
                  <td className="text-sm text-muted">{new Date(o.created_at).toLocaleDateString("id-ID")}</td>
                  <td>
                    {o.status === "pending" && (
                      <button className="btn btn-sm btn-primary" onClick={() => handleStatusChange(o.id, "paid")}>✓ Bayar</button>
                    )}
                    {o.status === "paid" && (
                      <button className="btn btn-sm btn-outline" onClick={() => handleStatusChange(o.id, "shipped")}>📦 Kirim</button>
                    )}
                    {o.status === "shipped" && (
                      <button className="btn btn-sm btn-outline" onClick={() => handleStatusChange(o.id, "done")}>✅ Selesai</button>
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
