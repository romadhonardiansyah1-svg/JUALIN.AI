"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import styles from "../scale.module.css";

export default function ImportPage() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState("");

  async function runPreview(e) {
    e.preventDefault();
    if (!file) return;
    setError("");
    setPreview(null);
    try {
      setPreview(await api.previewProductImport(file));
    } catch (e) {
      setError(e.message);
    }
  }

  async function downloadCsv(endpoint, filename) {
    try {
      const token = localStorage.getItem("jualin_token");
      const apiBase = process.env.NEXT_PUBLIC_API_URL || "";
      const res = await fetch(`${apiBase}${endpoint}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Export gagal");
      const blob = await res.blob();
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = filename;
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.titleBlock}>
          <h2>Marketplace Import/Export</h2>
          <p className={styles.muted}>V1 memvalidasi CSV produk sebelum import final. Export order tetap memakai endpoint CSV order yang sudah ada.</p>
        </div>
      </div>
      {error && <div className={styles.error}>{error}</div>}
      <div className={styles.grid}>
        <div className={styles.panel}>
          <div className={styles.panelHeader}><strong>Preview Import Produk</strong></div>
          <form className={styles.panelBody} onSubmit={runPreview}>
            <input className="input" type="file" accept=".csv" onChange={(e) => setFile(e.target.files?.[0] || null)} />
            <button className="btn btn-primary" style={{ marginTop: 12 }} disabled={!file}>Preview CSV</button>
          </form>
        </div>
        <div className={styles.panel}>
          <div className={styles.panelHeader}><strong>Export Data</strong></div>
          <div className={styles.panelBody}>
            <div className={styles.toolbar}>
              <button className="btn btn-outline" onClick={() => downloadCsv("/api/orders/export/csv", "jualin_orders.csv")}>Export Orders</button>
              <button className="btn btn-outline" onClick={() => downloadCsv("/api/customers/export/csv", "jualin_customers.csv")}>Export Customers</button>
            </div>
            <p className={styles.muted} style={{ marginTop: 12 }}>Kolom import wajib: nama, harga. Kolom opsional: deskripsi, stok, kategori, foto_url.</p>
          </div>
        </div>
      </div>
      {preview && (
        <div className={styles.panel}>
          <div className={styles.panelHeader}>
            <strong>Preview Result</strong>
            <span className={`badge ${preview.valid ? "badge-success" : "badge-warning"}`}>{preview.count} row / {preview.errors?.length || 0} issue</span>
          </div>
          <div className={styles.tableWrap}>
            <table className="table">
              <thead><tr><th>Row</th><th>Status</th><th>Nama</th><th>Harga</th><th>Issue</th></tr></thead>
              <tbody>
                {(preview.rows || []).map((row) => {
                  const rowErrors = (preview.errors || []).filter((item) => item.row === row.row).map((item) => item.message);
                  return (
                  <tr key={row.row}>
                    <td>{row.row}</td>
                    <td><span className={`badge ${rowErrors.length === 0 ? "badge-success" : "badge-danger"}`}>{rowErrors.length === 0 ? "valid" : "invalid"}</span></td>
                    <td>{row.nama || "-"}</td>
                    <td>{row.harga || "-"}</td>
                    <td>{rowErrors.join(", ") || "-"}</td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
