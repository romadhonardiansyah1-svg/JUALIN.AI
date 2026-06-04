"use client";
import { useEffect, useState } from "react";
import { listLeadForms, listLeadSubmissions, createLeadForm } from "@/lib/api";
import styles from "../scale.module.css";

export default function LeadsPage() {
  const [forms, setForms] = useState([]);
  const [submissions, setSubs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("forms");

  useEffect(() => { loadData(); }, []);
  async function loadData() {
    try {
      const [f, s] = await Promise.all([listLeadForms(), listLeadSubmissions()]);
      setForms(f); setSubs(s);
    } catch (e) { console.error(e); }
    setLoading(false);
  }

  async function handleCreate() {
    const title = prompt("Judul form:");
    const slug = prompt("Slug (URL-friendly):");
    if (!title || !slug) return;
    try {
      await createLeadForm({ title, slug });
      loadData();
    } catch (e) { alert(e.message); }
  }

  if (loading) return <div style={{ padding: 40, textAlign: "center" }}>⏳ Memuat...</div>;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h2>📋 Lead Capture</h2>
        <button className="btn btn-primary" onClick={handleCreate}>+ Buat Form</button>
      </div>
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <button className={`btn btn-sm ${tab === "forms" ? "btn-primary" : "btn-outline"}`} onClick={() => setTab("forms")}>Forms</button>
        <button className={`btn btn-sm ${tab === "subs" ? "btn-primary" : "btn-outline"}`} onClick={() => setTab("subs")}>Submissions ({submissions.length})</button>
      </div>

      {tab === "forms" && (forms.length === 0 ? (
        <div className={styles.stateBox}>Belum ada form. Buat form pertama untuk mulai menangkap lead.</div>
      ) : forms.map((f) => (
        <div key={f.id} className="card" style={{ padding: 16, marginBottom: 8 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <strong>{f.title}</strong>
              <div className="text-sm text-muted">/{f.slug} · {f.fields?.length || 0} fields · {f.submission_count || 0} submissions</div>
            </div>
            <span className={`badge ${f.is_active ? "badge-success" : "badge-muted"}`}>{f.is_active ? "Active" : "Inactive"}</span>
          </div>
        </div>
      )))}

      {tab === "subs" && (submissions.length === 0 ? (
        <div className={styles.stateBox}>Belum ada submission.</div>
      ) : submissions.map((s) => (
        <div key={s.id} className="card" style={{ padding: 16, marginBottom: 8 }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <pre className="text-sm" style={{ margin: 0, overflow: "auto" }}>{JSON.stringify(s.data, null, 2)}</pre>
            <span className={`badge badge-${s.status === "new" ? "primary" : "muted"}`}>{s.status}</span>
          </div>
          <div className="text-xs text-muted">{s.created_at}</div>
        </div>
      )))}
    </div>
  );
}
