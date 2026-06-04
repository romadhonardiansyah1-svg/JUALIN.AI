"use client";
import { useEffect, useState } from "react";
import { getMyStorefront, generateStorefront, updateStorefront } from "@/lib/api";
import styles from "../scale.module.css";

const SECTION_ICONS = { hero: "🎯", featured_products: "⭐", categories: "🏷️", testimonials: "💬", cta: "📲" };

export default function StorefrontPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [generating, setGenerating] = useState(false);
  const [publishing, setPublishing] = useState(false);

  useEffect(() => { loadData(); }, []);

  async function loadData() {
    try {
      setData(await getMyStorefront());
    } catch (e) { setError(e.message); }
    setLoading(false);
  }

  async function handleGenerate() {
    setGenerating(true);
    try {
      const result = await generateStorefront();
      alert(result.message);
      await loadData();
    } catch (e) { setError(e.message); }
    setGenerating(false);
  }

  async function togglePublish() {
    if (!data?.storefront) return;
    setPublishing(true);
    try {
      await updateStorefront({ is_published: !data.storefront.is_published });
      await loadData();
    } catch (e) { setError(e.message); }
    setPublishing(false);
  }

  if (loading) return <div style={{ padding: 40, textAlign: "center" }}>⏳ Memuat storefront...</div>;

  const sf = data?.storefront;
  const sections = data?.sections || [];

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.titleBlock}>
          <h2>🏪 AI Storefront Builder</h2>
          <p className={styles.muted}>Buat halaman katalog publik yang SEO-friendly untuk toko kamu.</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {!sf && (
            <button className="btn btn-primary" onClick={handleGenerate} disabled={generating}>
              {generating ? "⏳ Generating..." : "✨ Generate Storefront"}
            </button>
          )}
          {sf && (
            <>
              <button className="btn btn-outline" onClick={handleGenerate} disabled={generating}>
                🔄 Regenerate
              </button>
              <button
                className={`btn ${sf.is_published ? "btn-danger" : "btn-primary"}`}
                onClick={togglePublish}
                disabled={publishing}
              >
                {publishing ? "⏳..." : sf.is_published ? "📴 Unpublish" : "🚀 Publish"}
              </button>
            </>
          )}
        </div>
      </div>

      {error && <div className={styles.error}>{error}</div>}

      {!sf && (
        <div className={styles.stateBox}>
          <p>Belum punya storefront. Klik &quot;Generate Storefront&quot; untuk membuat halaman katalog publik dari data toko kamu.</p>
        </div>
      )}

      {sf && (
        <>
          <div className="card" style={{ marginBottom: 20, padding: 20 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <h3 style={{ margin: 0 }}>{sf.title}</h3>
                <p className="text-muted text-sm" style={{ margin: "4px 0" }}>{sf.tagline}</p>
                <code className="text-xs">/{sf.slug}</code>
              </div>
              <span className={`badge ${sf.is_published ? "badge-success" : "badge-warning"}`}>
                {sf.is_published ? "● Published" : "○ Draft"}
              </span>
            </div>
            {sf.is_published && (
              <a href={`/store/${sf.slug}`} target="_blank" rel="noopener" className="btn btn-sm btn-outline" style={{ marginTop: 10 }}>
                🔗 Lihat Storefront
              </a>
            )}
          </div>

          <h3 style={{ marginBottom: 12 }}>📐 Sections</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {sections.map((s) => (
              <div key={s.id} className="card" style={{ padding: "16px 20px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{ fontSize: "1.3rem" }}>{SECTION_ICONS[s.type] || "📄"}</span>
                  <div style={{ flex: 1 }}>
                    <strong>{s.title}</strong>
                    <p className="text-xs text-muted" style={{ margin: 0 }}>Type: {s.type} | Order: {s.order}</p>
                  </div>
                  <span className={`badge ${s.is_visible ? "badge-success" : "badge-muted"}`}>
                    {s.is_visible ? "Visible" : "Hidden"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
