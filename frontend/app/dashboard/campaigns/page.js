"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import styles from "../scale.module.css";

const segments = [
  "repeat_buyer",
  "abandoned_payment",
  "asked_not_ordered",
  "bought_category",
  "inactive_customer",
];

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState([]);
  const [form, setForm] = useState({ title: "", segment: "repeat_buyer", offer: "" });
  const [selected, setSelected] = useState(null);
  const [content, setContent] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(""); // "generate" | "save" | "preview" | "send"

  async function loadCampaigns() {
    try {
      setCampaigns(await api.getCampaigns());
    } catch (e) {
      setError(e.message);
    }
  }

  async function generate(e) {
    e.preventDefault();
    if (busy) return;
    setBusy("generate");
    setError("");
    setMessage("");
    try {
      const campaign = await api.generateCampaign(form);
      setSelected(campaign);
      setContent(campaign.content);
      await loadCampaigns();
    } catch (e) {
      setError(e.message);
    }
    setBusy("");
  }

  async function saveDraft() {
    if (!selected || busy) return;
    setBusy("save");
    try {
      const updated = await api.updateCampaign(selected.id, { content });
      setSelected(updated);
      setMessage("Draft disimpan.");
      await loadCampaigns();
    } catch (e) {
      setError(e.message);
    }
    setBusy("");
  }

  async function preview() {
    if (!selected || busy) return;
    setBusy("preview");
    try {
      const data = await api.previewCampaign(selected.id);
      setMessage(`Preview siap untuk ${data.recipient_count} recipient.`);
      await loadCampaigns();
    } catch (e) {
      setError(e.message);
    }
    setBusy("");
  }

  async function send() {
    if (!selected || busy) return;
    if (!confirm("Approve dan queue campaign ini?")) return;
    setBusy("send");
    try {
      const data = await api.sendCampaign(selected.id);
      setMessage(`Campaign queued untuk ${data.recipient_count} recipient.`);
      await loadCampaigns();
    } catch (e) {
      setError(e.message);
    }
    setBusy("");
  }

  useEffect(() => {
    loadCampaigns();
  }, []);

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.titleBlock}>
          <h2>Campaign Generator</h2>
          <p className={styles.muted}>Generate, edit, preview recipient, lalu approve send secara manual.</p>
        </div>
      </div>
      {error && <div className={styles.error}>{error}</div>}
      {message && <div className={styles.success}>{message}</div>}
      <div className={styles.twoColumn}>
        <div className={styles.panel}>
          <div className={styles.panelHeader}><strong>Buat Campaign</strong></div>
          <form className={styles.panelBody} onSubmit={generate}>
            <div className={styles.formRow}>
              <label>Judul</label>
              <input className="input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required />
            </div>
            <div className={styles.formRow} style={{ marginTop: 12 }}>
              <label>Segment</label>
              <select className="input" value={form.segment} onChange={(e) => setForm({ ...form, segment: e.target.value })}>
                {segments.map((segment) => <option key={segment} value={segment}>{segment}</option>)}
              </select>
            </div>
            <div className={styles.formRow} style={{ marginTop: 12 }}>
              <label>Offer</label>
              <input className="input" value={form.offer} onChange={(e) => setForm({ ...form, offer: e.target.value })} placeholder="contoh: bundle Ramadan 10%" />
            </div>
            <button className="btn btn-primary" style={{ marginTop: 14 }} disabled={!!busy}>
              {busy === "generate" ? "Generating..." : "Generate"}
            </button>
          </form>
          <div className={styles.panelHeader}><strong>Campaigns</strong><span className="badge badge-primary">{campaigns.length}</span></div>
          <div className={styles.list}>
            {campaigns.map((campaign) => (
              <button key={campaign.id} className={`${styles.listItem} ${selected?.id === campaign.id ? styles.listItemActive : ""}`} onClick={() => { setSelected(campaign); setContent(campaign.content); }}>
                <div className={styles.listTitle}><span>{campaign.title}</span><span className="badge badge-neutral">{campaign.status}</span></div>
                <div className={styles.listMeta}>
                  {campaign.segment} / {campaign.channel}
                  {campaign.recipient_count > 0 && <span> · {campaign.recipient_count} recipients</span>}
                  {campaign.sent_count > 0 && <span style={{color: "var(--success)"}}>  ✓{campaign.sent_count}</span>}
                  {campaign.failed_count > 0 && <span style={{color: "var(--danger)"}}>  ✗{campaign.failed_count}</span>}
                </div>
              </button>
            ))}
          </div>
        </div>
        <div className={styles.panel}>
          {selected ? (
            <>
              <div className={styles.panelHeader}>
                <strong>{selected.title}</strong>
                <span className="badge badge-primary">{selected.status}</span>
              </div>
              <div className={styles.panelBody}>
                <textarea className={`input ${styles.textarea}`} value={content} onChange={(e) => setContent(e.target.value)} disabled={["queued", "sending", "sent", "partial_failed"].includes(selected.status)} />
                <div className={styles.toolbar} style={{ marginTop: 12 }}>
                  <button className="btn btn-outline" onClick={saveDraft} disabled={!!busy || ["queued", "sending", "sent"].includes(selected.status)}>{busy === "save" ? "Menyimpan..." : "Simpan Draft"}</button>
                  <button className="btn btn-outline" onClick={preview} disabled={!!busy || ["queued", "sending", "sent"].includes(selected.status)}>{busy === "preview" ? "Memproses..." : "Preview"}</button>
                  <button className="btn btn-primary" onClick={send} disabled={!!busy || ["queued", "sending", "sent"].includes(selected.status)}>{busy === "send" ? "Mengirim..." : "Approve Send"}</button>
                  <button className="btn btn-outline" onClick={loadCampaigns} disabled={!!busy}>Refresh</button>
                </div>
              </div>
            </>
          ) : (
            <div className={styles.stateBox}>Pilih atau generate campaign.</div>
          )}
        </div>
      </div>
    </div>
  );
}
