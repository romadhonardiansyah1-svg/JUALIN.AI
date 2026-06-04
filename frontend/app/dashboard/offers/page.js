"use client";
import { useEffect, useState } from "react";
import { listOffers, createOffer, listOfferRecommendations, approveOfferRec } from "@/lib/api";
import styles from "../scale.module.css";

const OFFER_TYPES = [
  { value: "fixed_discount", label: "Diskon Tetap", icon: "💸" },
  { value: "free_shipping", label: "Gratis Ongkir", icon: "🚚" },
  { value: "bundle", label: "Bundle", icon: "📦" },
  { value: "urgency", label: "Limited Stock", icon: "⚡" },
];

export default function OffersPage() {
  const [offers, setOffers] = useState([]);
  const [recs, setRecs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("offers");

  useEffect(() => { loadData(); }, []);
  async function loadData() {
    try {
      const [o, r] = await Promise.all([listOffers(), listOfferRecommendations()]);
      setOffers(o); setRecs(r);
    } catch (e) { console.error(e); }
    setLoading(false);
  }

  async function handleCreate() {
    const name = prompt("Nama offer:");
    if (!name) return;
    try { await createOffer({ name }); loadData(); } catch (e) { alert(e.message); }
  }

  async function handleApprove(id) {
    try { await approveOfferRec(id); loadData(); } catch (e) { alert(e.message); }
  }

  if (loading) return <div style={{ padding: 40, textAlign: "center" }}>⏳ Memuat...</div>;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h2>🎁 Dynamic Offers</h2>
        <button className="btn btn-primary" onClick={handleCreate}>+ Buat Offer</button>
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <button className={`btn btn-sm ${tab === "offers" ? "btn-primary" : "btn-outline"}`} onClick={() => setTab("offers")}>Offers ({offers.length})</button>
        <button className={`btn btn-sm ${tab === "recs" ? "btn-primary" : "btn-outline"}`} onClick={() => setTab("recs")}>Rekomendasi ({recs.length})</button>
      </div>

      {tab === "offers" && offers.map((o) => (
        <div key={o.id} className="card" style={{ padding: 16, marginBottom: 8 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <strong>{o.name}</strong>
              <div className="text-sm text-muted">{o.type} · {o.value_type === "percent" ? `${o.value}%` : `Rp ${o.value.toLocaleString()}`} · {o.current_redemptions}x used</div>
            </div>
            <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
              {o.allow_chat_auto && <span className="badge badge-primary" style={{ fontSize: "0.65em" }}>Auto-Chat</span>}
              <span className={`badge ${o.is_active ? "badge-success" : "badge-muted"}`}>{o.is_active ? "Active" : "Inactive"}</span>
            </div>
          </div>
        </div>
      ))}

      {tab === "recs" && (recs.length === 0 ? (
        <div className={styles.stateBox}>Belum ada rekomendasi offer dari AI.</div>
      ) : recs.map((r) => (
        <div key={r.id} className="card" style={{ padding: 16, marginBottom: 8 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <strong>{r.trigger_type}</strong>
              <div className="text-sm text-muted">Segment: {r.customer_segment} · Est. impact: +{r.estimated_impact}%</div>
            </div>
            {r.status === "pending" && (
              <button className="btn btn-sm btn-primary" onClick={() => handleApprove(r.id)}>✅ Approve</button>
            )}
          </div>
        </div>
      )))}
    </div>
  );
}
