"use client";
import { useEffect, useState } from "react";
import { listKnowledgeSources, createKnowledgeSource, reindexKnowledge, deleteKnowledge } from "@/lib/api";
import styles from "../scale.module.css";

const TYPE_ICONS = { manual: "📝", faq: "❓", policy: "📜", product_note: "📦", import_note: "📥" };

export default function KnowledgePage() {
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ type: "manual", title: "", content: "" });

  useEffect(() => { loadData(); }, []);
  async function loadData() {
    try { setSources(await listKnowledgeSources()); } catch (e) { console.error(e); }
    setLoading(false);
  }

  async function handleCreate(e) {
    e.preventDefault();
    try {
      await createKnowledgeSource(form);
      setShowForm(false); setForm({ type: "manual", title: "", content: "" });
      loadData();
    } catch (e) { alert(e.message); }
  }

  async function handleReindex(id) {
    try { await reindexKnowledge(id); alert("Reindexed!"); loadData(); } catch (e) { alert(e.message); }
  }

  async function handleDelete(id) {
    if (!confirm("Hapus knowledge source ini?")) return;
    try { await deleteKnowledge(id); loadData(); } catch (e) { alert(e.message); }
  }

  if (loading) return <div style={{ padding: 40, textAlign: "center" }}>⏳ Memuat...</div>;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h2>📚 Knowledge Base</h2>
        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
          {showForm ? "✕ Tutup" : "+ Tambah Source"}
        </button>
      </div>

      {showForm && (
        <form className="card" style={{ padding: 20, marginBottom: 20 }} onSubmit={handleCreate}>
          <div style={{ display: "flex", gap: 12, marginBottom: 12 }}>
            <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} className="input">
              <option value="manual">Manual Text</option>
              <option value="faq">FAQ</option>
              <option value="policy">Policy</option>
              <option value="product_note">Product Note</option>
            </select>
            <input className="input" placeholder="Judul" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required />
          </div>
          <textarea className="input" rows={6} placeholder="Konten knowledge..." value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} style={{ width: "100%", marginBottom: 12 }} />
          <button className="btn btn-primary" type="submit">💾 Simpan</button>
        </form>
      )}

      {sources.length === 0 ? (
        <div className={styles.stateBox}>Belum ada knowledge source. Tambahkan FAQ, policy, atau catatan produk agar AI bisa menjawab lebih akurat.</div>
      ) : sources.map((s) => (
        <div key={s.id} className="card" style={{ padding: 16, marginBottom: 8 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <span style={{ marginRight: 8 }}>{TYPE_ICONS[s.type] || "📄"}</span>
              <strong>{s.title}</strong>
              <div className="text-sm text-muted">{s.type} · {s.chunk_count} chunks · {s.status}</div>
            </div>
            <div style={{ display: "flex", gap: 4 }}>
              <button className="btn btn-sm btn-outline" onClick={() => handleReindex(s.id)}>🔄</button>
              <button className="btn btn-sm btn-danger" onClick={() => handleDelete(s.id)}>🗑️</button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
