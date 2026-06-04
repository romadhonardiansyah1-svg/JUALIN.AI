"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import styles from "../scale.module.css";

export default function ImportPage() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [importResult, setImportResult] = useState(null);
  const [importMode, setImportMode] = useState("skip_duplicates");
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function runPreview(e) {
    e.preventDefault();
    if (!file) return;
    setError("");
    setMessage("");
    setPreview(null);
    setImportResult(null);
    try {
      setPreview(await api.previewProductImport(file));
    } catch (e) {
      setError(e.message);
    }
  }

  async function runImport() {
    if (!preview?.preview_token) return;
    if (!confirm("Import produk dari preview ini?")) return;
    setImporting(true);
    setError("");
    setMessage("");
    try {
      const result = await api.executeProductImport({
        preview_token: preview.preview_token,
        mode: importMode,
      });
      setImportResult(result);
      setMessage(`Import selesai: ${result.inserted} ditambahkan, ${result.updated} diupdate, ${result.skipped} dilewati.`);
    } catch (e) {
      setError(e.message);
    } finally {
      setImporting(false);
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
          <p className={styles.muted}>Upload CSV, preview validasi, lalu import ke katalog produk.</p>
        </div>
      </div>
      {error && <div className={styles.error}>{error}</div>}
      {message && <div className={styles.success}>{message}</div>}
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
            <p className={styles.muted} style={{ marginTop: 12 }}>Kolom import wajib: nama, harga. Kolom opsional: deskripsi, stok, kategori.</p>
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
          {preview.preview_token && (
            <div className={styles.panelBody} style={{ borderTop: "1px solid var(--border-color)", paddingTop: 16 }}>
              <div className={styles.formRow}>
                <label>Mode duplikat:</label>
                <select className="input" value={importMode} onChange={(e) => setImportMode(e.target.value)} style={{ maxWidth: 220 }}>
                  <option value="skip_duplicates">Lewati duplikat</option>
                  <option value="update_duplicates">Update duplikat</option>
                </select>
              </div>
              <button className="btn btn-primary" style={{ marginTop: 12 }} onClick={runImport} disabled={importing}>
                {importing ? "Mengimport..." : `Import ${preview.count} Produk`}
              </button>
            </div>
          )}
        </div>
      )}
      {importResult && (
        <div className={styles.panel}>
          <div className={styles.panelHeader}><strong>Hasil Import</strong></div>
          <div className={styles.panelBody}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, textAlign: "center" }}>
              <div><strong style={{ fontSize: 24, color: "var(--success)" }}>{importResult.inserted}</strong><br /><span className={styles.muted}>Ditambahkan</span></div>
              <div><strong style={{ fontSize: 24, color: "var(--info)" }}>{importResult.updated}</strong><br /><span className={styles.muted}>Diupdate</span></div>
              <div><strong style={{ fontSize: 24, color: "var(--warning)" }}>{importResult.skipped}</strong><br /><span className={styles.muted}>Dilewati</span></div>
              <div><strong style={{ fontSize: 24 }}>{importResult.total_processed}</strong><br /><span className={styles.muted}>Total</span></div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
