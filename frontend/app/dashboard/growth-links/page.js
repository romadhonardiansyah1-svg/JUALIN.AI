"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import styles from "./growth-links.module.css";

const SOURCES = [
  { id: "wa_link", label: "WhatsApp Link", icon: "💬", desc: "Link menuju WhatsApp toko" },
  { id: "storefront_cta", label: "Link Katalog", icon: "🏪", desc: "Link menuju halaman katalog" },
  { id: "campaign", label: "Campaign", icon: "📢", desc: "Link untuk campaign tertentu" },
  { id: "manual", label: "Custom Link", icon: "🔗", desc: "Link custom ke URL mana saja" },
];

export default function GrowthLinksPage() {
  const [links, setLinks] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [copied, setCopied] = useState("");

  // Create form
  const [source, setSource] = useState("wa_link");
  const [campaignName, setCampaignName] = useState("");
  const [targetUrl, setTargetUrl] = useState("");

  useEffect(() => { load(); }, []);

  const load = async () => {
    try {
      const [l, s] = await Promise.all([api.getGrowthLinks(), api.getGrowthLinkStats()]);
      setLinks(l || []);
      setStats(s);
    } catch { /* empty */ }
    setLoading(false);
  };

  const handleCreate = async () => {
    setCreating(true);
    try {
      await api.createGrowthLink({ source, campaign_name: campaignName, target_url: targetUrl });
      setShowCreate(false);
      setCampaignName("");
      setTargetUrl("");
      await load();
    } catch { /* empty */ }
    setCreating(false);
  };

  const copyLink = (link) => {
    navigator.clipboard.writeText(link);
    setCopied(link);
    setTimeout(() => setCopied(""), 2000);
  };

  if (loading) return <div className="card" style={{ padding: "2rem", textAlign: "center" }}>Memuat growth links...</div>;

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>📈 Growth Links</h1>
          <p className={styles.subtitle}>Buat link trackable untuk mengukur performa setiap channel</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowCreate(!showCreate)}>
          + Buat Link
        </button>
      </div>

      {/* Stats */}
      {stats && (
        <div className={styles.statsRow}>
          <div className={styles.statCard}>
            <div className={styles.statValue}>{stats.total_links}</div>
            <div className={styles.statLabel}>Total Links</div>
          </div>
          <div className={styles.statCard}>
            <div className={styles.statValue}>{stats.total_clicks}</div>
            <div className={styles.statLabel}>Total Clicks</div>
          </div>
          <div className={styles.statCard}>
            <div className={styles.statValue}>{stats.total_orders}</div>
            <div className={styles.statLabel}>Orders</div>
          </div>
          <div className={styles.statCard}>
            <div className={styles.statValue}>Rp {(stats.total_revenue / 1000).toFixed(0)}K</div>
            <div className={styles.statLabel}>Revenue</div>
          </div>
        </div>
      )}

      {/* Create Form */}
      {showCreate && (
        <div className={`card ${styles.createForm}`}>
          <h3 style={{ marginBottom: "1rem" }}>Buat Growth Link Baru</h3>
          <div className={styles.sourceGrid}>
            {SOURCES.map((s) => (
              <div
                key={s.id}
                className={`${styles.sourceCard} ${source === s.id ? styles.selected : ""}`}
                onClick={() => setSource(s.id)}
              >
                <span className={styles.sourceIcon}>{s.icon}</span>
                <span className={styles.sourceName}>{s.label}</span>
                <span className={styles.sourceDesc}>{s.desc}</span>
              </div>
            ))}
          </div>

          <div className={styles.formRow}>
            <div className={styles.formGroup}>
              <label className={styles.label}>Nama Campaign (opsional)</label>
              <input className={styles.input} placeholder="Promo Ramadan" value={campaignName}
                onChange={(e) => setCampaignName(e.target.value)} />
            </div>
            {source === "manual" && (
              <div className={styles.formGroup}>
                <label className={styles.label}>URL Tujuan</label>
                <input className={styles.input} placeholder="https://..." value={targetUrl}
                  onChange={(e) => setTargetUrl(e.target.value)} />
              </div>
            )}
          </div>

          <button className="btn btn-primary" onClick={handleCreate} disabled={creating}>
            {creating ? "Membuat..." : "🚀 Buat Link"}
          </button>
        </div>
      )}

      {/* Links Table */}
      {links.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: "3rem" }}>
          <div style={{ fontSize: "3rem", marginBottom: "1rem" }}>🔗</div>
          <h3>Belum ada growth link</h3>
          <p style={{ color: "var(--text-secondary)" }}>Buat link pertama kamu untuk mulai tracking performa channel.</p>
        </div>
      ) : (
        <div className="card">
          <div className={styles.table}>
            <div className={styles.tableHeader}>
              <span>Source</span><span>Campaign</span><span>Clicks</span><span>Orders</span><span>Revenue</span><span>Action</span>
            </div>
            {links.map((l) => (
              <div key={l.id} className={styles.tableRow}>
                <span className={styles.badge}>{l.source}</span>
                <span>{l.campaign_name || "-"}</span>
                <span className={styles.num}>{l.click_count}</span>
                <span className={styles.num}>{l.order_count}</span>
                <span className={styles.num}>Rp {(l.revenue / 1000).toFixed(0)}K</span>
                <button className={`btn btn-outline btn-sm ${copied === l.link ? styles.copiedBtn : ""}`}
                  onClick={() => copyLink(l.link)}>
                  {copied === l.link ? "✅ Copied" : "📋 Copy"}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
