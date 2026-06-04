"use client";
import { useCallback, useEffect, useState } from "react";
import { listQAReviews, approveQA, rejectQA, editAndSendQA } from "@/lib/api";
import styles from "../scale.module.css";

const PRIORITY_COLORS = { urgent: "badge-danger", high: "badge-warning", medium: "badge-primary", low: "badge-muted" };
const TYPE_LABELS = {
  low_confidence: "⚠️ Low Confidence",
  action_failed: "❌ Action Failed",
  complaint: "😡 Complaint",
  feedback_down: "👎 Feedback Down",
  payment_conflict: "💳 Payment Conflict",
  sensitive_discount: "🔒 Sensitive Discount",
};

export default function QAReviewPage() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("pending");
  const [editItem, setEditItem] = useState(null);
  const [editText, setEditText] = useState("");

  const loadData = useCallback(async () => {
    setLoading(true);
    try { setItems(await listQAReviews(filter)); } catch (e) { console.error(e); }
    setLoading(false);
  }, [filter]);

  useEffect(() => { loadData(); }, [loadData]);

  async function handleApprove(id) {
    try { await approveQA(id, { notes: "" }); loadData(); } catch (e) { alert(e.message); }
  }

  async function handleReject(id) {
    const reason = prompt("Alasan reject:");
    try { await rejectQA(id, { notes: reason || "" }); loadData(); } catch (e) { alert(e.message); }
  }

  async function handleEditSend() {
    if (!editItem || !editText) return;
    try { await editAndSendQA(editItem.id, { edited_content: editText }); setEditItem(null); loadData(); }
    catch (e) { alert(e.message); }
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h2>🔍 QA Review Queue</h2>
        <div style={{ display: "flex", gap: 8 }}>
          {["pending", "approved", "rejected", "edited"].map((s) => (
            <button key={s} className={`btn btn-sm ${filter === s ? "btn-primary" : "btn-outline"}`} onClick={() => setFilter(s)}>
              {s.charAt(0).toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {loading && <div className={styles.stateBox}>Memuat...</div>}
      {!loading && items.length === 0 && <div className={styles.stateBox}>Tidak ada item {filter}.</div>}

      {items.map((item) => (
        <div key={item.id} className="card" style={{ padding: 16, marginBottom: 10 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <div>
              <span>{TYPE_LABELS[item.type] || item.type}</span>
              <span className={`badge ${PRIORITY_COLORS[item.priority] || "badge-muted"}`} style={{ marginLeft: 8, fontSize: "0.65em" }}>{item.priority}</span>
            </div>
            <span className="text-xs text-muted">{item.created_at}</span>
          </div>
          {item.reason && <p className="text-sm text-muted" style={{ margin: "4px 0" }}>Reason: {item.reason}</p>}
          <div className="text-sm" style={{ background: "var(--bg-code, #0f172a)", padding: 8, borderRadius: 6, marginBottom: 8, maxHeight: 120, overflow: "auto" }}>
            {item.original_content || "(no content)"}
          </div>
          {filter === "pending" && (
            <div style={{ display: "flex", gap: 6 }}>
              <button className="btn btn-sm btn-primary" onClick={() => handleApprove(item.id)}>✅ Approve</button>
              <button className="btn btn-sm btn-danger" onClick={() => handleReject(item.id)}>❌ Reject</button>
              <button className="btn btn-sm btn-outline" onClick={() => { setEditItem(item); setEditText(item.original_content || ""); }}>✏️ Edit & Send</button>
            </div>
          )}
        </div>
      ))}

      {editItem && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}>
          <div className="card" style={{ padding: 24, maxWidth: 600, width: "90%" }}>
            <h3>✏️ Edit & Kirim</h3>
            <textarea className="input" rows={6} value={editText} onChange={(e) => setEditText(e.target.value)} style={{ width: "100%", marginBottom: 12 }} />
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button className="btn btn-outline" onClick={() => setEditItem(null)}>Batal</button>
              <button className="btn btn-primary" onClick={handleEditSend}>📤 Kirim</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
