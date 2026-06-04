"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import styles from "../scale.module.css";

export default function IntegrationsPage() {
  const [integrations, setIntegrations] = useState([]);
  const [health, setHealth] = useState([]);
  const [form, setForm] = useState({ display_name: "WhatsApp", phone_number_id: "", access_token: "", app_secret: "" });
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function load() {
    setError("");
    try {
      setIntegrations(await api.getIntegrations());
    } catch (e) {
      setError(e.message);
    }
  }

  async function checkHealth() {
    try {
      setHealth(await api.getIntegrationHealth());
    } catch (e) {
      setError(e.message);
    }
  }

  async function connect(e) {
    e.preventDefault();
    setError("");
    setMessage("");
    try {
      const data = await api.connectWhatsApp(form);
      setMessage(`${data.display_name} connected.`);
      setForm({ ...form, access_token: "", app_secret: "" });
      await load();
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.titleBlock}>
          <h2>Integrations</h2>
          <p className={styles.muted}>Koneksi provider eksternal tersimpan terenkripsi di backend.</p>
        </div>
        <button className="btn btn-outline" onClick={checkHealth}>Health Check</button>
      </div>
      {error && <div className={styles.error}>{error}</div>}
      {message && <div className={styles.success}>{message}</div>}
      <div className={styles.grid}>
        <div className={styles.panel}>
          <div className={styles.panelHeader}><strong>Connect WhatsApp Cloud</strong></div>
          <form className={styles.panelBody} onSubmit={connect}>
            <label className={styles.formRow}>Display name<input className="input" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} /></label>
            <label className={styles.formRow} style={{ marginTop: 12 }}>Phone number ID<input className="input" value={form.phone_number_id} onChange={(e) => setForm({ ...form, phone_number_id: e.target.value })} required /></label>
            <label className={styles.formRow} style={{ marginTop: 12 }}>Access token<input className="input" type="password" value={form.access_token} onChange={(e) => setForm({ ...form, access_token: e.target.value })} required /></label>
            <label className={styles.formRow} style={{ marginTop: 12 }}>App secret<input className="input" type="password" value={form.app_secret} onChange={(e) => setForm({ ...form, app_secret: e.target.value })} /></label>
            <button className="btn btn-primary" style={{ marginTop: 14 }}>Connect</button>
          </form>
        </div>
        <div className={styles.panel}>
          <div className={styles.panelHeader}><strong>Connected Providers</strong><span className="badge badge-primary">{integrations.length}</span></div>
          {integrations.length === 0 && <div className={styles.stateBox}>Belum ada integrasi aktif.</div>}
          <div className={styles.list}>
            {integrations.map((item) => (
              <div key={item.id} className={styles.listItem}>
                <div className={styles.listTitle}><span>{item.display_name}</span><span className="badge badge-neutral">{item.status}</span></div>
                <div className={styles.listMeta}>{item.provider_type} / {item.provider} / health: {item.last_health_status}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
      {health.length > 0 && (
        <div className={styles.panel}>
          <div className={styles.panelHeader}><strong>Provider Health</strong></div>
          <div className={styles.list}>
            {health.map((item) => (
              <div key={`${item.provider_type}-${item.provider}`} className={styles.listItem}>
                <div className={styles.listTitle}><span>{item.provider}</span><span className={`badge ${item.healthy ? "badge-success" : "badge-danger"}`}>{item.healthy ? "healthy" : "unhealthy"}</span></div>
                <div className={styles.listMeta}>{item.detail}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
