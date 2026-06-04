"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import styles from "../scale.module.css";

function money(value) {
  return `Rp ${Number(value || 0).toLocaleString("id-ID")}`;
}

export default function CustomersPage() {
  const [customers, setCustomers] = useState([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [tags, setTags] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");

  const loadCustomers = useCallback(async (q = "") => {
    setError("");
    try {
      setCustomers(await api.getCustomers(q));
    } catch (e) {
      setError(e.message);
    }
  }, []);

  async function selectCustomer(id) {
    setError("");
    try {
      const detail = await api.getCustomer(id);
      const events = await api.getCustomerTimeline(id);
      setSelected(detail);
      setTimeline(events);
      setTags((detail.tags || []).join(", "));
      setNotes(detail.profile?.notes || "");
    } catch (e) {
      setError(e.message);
    }
  }

  async function saveCustomer() {
    if (!selected) return;
    try {
      await api.updateCustomer(selected.id, {
        tags: tags.split(",").map((tag) => tag.trim()).filter(Boolean),
        notes,
      });
      await selectCustomer(selected.id);
      await loadCustomers(query);
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => {
    loadCustomers("");
  }, [loadCustomers]);

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.titleBlock}>
          <h2>Customer CRM</h2>
          <p className={styles.muted}>Profil pelanggan, tag, total belanja, dan timeline chat/order.</p>
        </div>
        <form className={styles.toolbar} onSubmit={(e) => { e.preventDefault(); loadCustomers(query); }}>
          <input className="input" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Cari nama, HP, email" />
          <button className="btn btn-outline">Cari</button>
        </form>
      </div>
      {error && <div className={styles.error}>{error}</div>}
      <div className={styles.twoColumn}>
        <div className={styles.panel}>
          <div className={styles.panelHeader}>
            <strong>Customers</strong>
            <span className="badge badge-primary">{customers.length}</span>
          </div>
          {customers.length === 0 && <div className={styles.stateBox}>Belum ada customer CRM.</div>}
          <div className={styles.list}>
            {customers.map((customer) => (
              <button key={customer.id} className={`${styles.listItem} ${selected?.id === customer.id ? styles.listItemActive : ""}`} onClick={() => selectCustomer(customer.id)}>
                <div className={styles.listTitle}>
                  <span>{customer.name || "Customer"}</span>
                  <span>{money(customer.total_spent)}</span>
                </div>
                <div className={styles.listMeta}>
                  <span>{customer.phone || "-"}</span>
                  <span>{customer.total_orders} order</span>
                </div>
                <div className={styles.tagList}>{(customer.tags || []).map((tag) => <span key={tag} className={styles.tag}>{tag}</span>)}</div>
              </button>
            ))}
          </div>
        </div>
        <div className={styles.panel}>
          {selected ? (
            <>
              <div className={styles.panelHeader}>
                <div>
                  <strong>{selected.name}</strong>
                  <div className={styles.muted}>{selected.phone || "-"} / {selected.email || "-"}</div>
                </div>
                <button className="btn btn-primary" onClick={saveCustomer}>Simpan</button>
              </div>
              <div className={styles.panelBody}>
                <div className={styles.grid}>
                  <div className={styles.statCard}><span className={styles.muted}>Total order</span><span className={styles.statValue}>{selected.total_orders}</span></div>
                  <div className={styles.statCard}><span className={styles.muted}>Total belanja</span><span className={styles.statValue}>{money(selected.total_spent)}</span></div>
                </div>
                <div className={styles.formGrid} style={{ marginTop: 16 }}>
                  <label className={styles.formRow}>Tags<input className="input" value={tags} onChange={(e) => setTags(e.target.value)} placeholder="vip, repeat-buyer" /></label>
                  <label className={styles.formRow}>Catatan seller<textarea className={`input ${styles.textarea}`} value={notes} onChange={(e) => setNotes(e.target.value)} /></label>
                </div>
                <h3 style={{ marginTop: 18 }}>Timeline</h3>
                {timeline.length === 0 && <div className={styles.stateBox}>Belum ada event customer.</div>}
                <div className={styles.list}>
                  {timeline.map((event) => (
                    <div key={event.id} className={styles.listItem}>
                      <div className={styles.listTitle}><span>{event.title}</span><span className="badge badge-neutral">{event.source}</span></div>
                      <div className={styles.listMeta}>{event.event_type} / {new Date(event.created_at).toLocaleString("id-ID")}</div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <div className={styles.stateBox}>Pilih customer untuk melihat profil.</div>
          )}
        </div>
      </div>
    </div>
  );
}
