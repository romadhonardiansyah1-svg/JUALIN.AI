"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import styles from "./trust.module.css";

export default function TrustProfilePage() {
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  // Form state
  const [refundPolicy, setRefundPolicy] = useState("");
  const [shippingPolicy, setShippingPolicy] = useState("");
  const [supportHours, setSupportHours] = useState("");
  const [verifiedPhone, setVerifiedPhone] = useState(false);
  const [paymentEnabled, setPaymentEnabled] = useState(false);
  const [testimonials, setTestimonials] = useState([]);
  const [newTestimonial, setNewTestimonial] = useState({ name: "", text: "", rating: 5 });

  useEffect(() => {
    loadProfile();
  }, []);

  const loadProfile = async () => {
    try {
      const data = await api.getTrustProfile();
      setProfile(data);
      setRefundPolicy(data.refund_policy || "");
      setShippingPolicy(data.shipping_policy || "");
      setSupportHours(data.support_hours || "");
      setVerifiedPhone(data.verified_phone || false);
      setPaymentEnabled(data.payment_enabled || false);
      setTestimonials(data.testimonials || []);
    } catch { /* empty */ }
    setLoading(false);
  };

  const handleSave = async () => {
    setSaving(true);
    setMsg("");
    try {
      await api.updateTrustProfile({
        refund_policy: refundPolicy,
        shipping_policy: shippingPolicy,
        support_hours: supportHours,
        verified_phone: verifiedPhone,
        payment_enabled: paymentEnabled,
        testimonials_json: testimonials,
      });
      setMsg("✅ Trust profile berhasil disimpan");
    } catch (e) {
      setMsg("❌ " + (e.message || "Gagal menyimpan"));
    }
    setSaving(false);
  };

  const addTestimonial = () => {
    if (!newTestimonial.name.trim() || !newTestimonial.text.trim()) return;
    setTestimonials([...testimonials, { ...newTestimonial, date: new Date().toISOString().split("T")[0] }]);
    setNewTestimonial({ name: "", text: "", rating: 5 });
  };

  const removeTestimonial = (idx) => {
    setTestimonials(testimonials.filter((_, i) => i !== idx));
  };

  if (loading) return <div className="card" style={{ padding: "2rem", textAlign: "center" }}>Memuat trust profile...</div>;

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1 className={styles.title}>🛡️ Trust Profile</h1>
        <p className={styles.subtitle}>Tingkatkan kepercayaan customer dengan informasi yang transparan</p>
      </div>

      {msg && <div className={styles.alert}>{msg}</div>}

      <div className={styles.grid}>
        {/* Policies */}
        <div className="card">
          <h3 className={styles.sectionTitle}>📋 Kebijakan Toko</h3>

          <div className={styles.formGroup}>
            <label className={styles.label}>Kebijakan Refund / Retur</label>
            <textarea
              className={styles.textarea}
              placeholder="Contoh: Retur diterima dalam 3 hari setelah barang diterima. Syarat: tag masih menempel, belum dipakai."
              value={refundPolicy}
              onChange={(e) => setRefundPolicy(e.target.value)}
              rows={4}
            />
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Kebijakan Pengiriman</label>
            <textarea
              className={styles.textarea}
              placeholder="Contoh: Pengiriman via JNE/J&T. Jabodetabek 1-2 hari, luar Jawa 3-5 hari kerja."
              value={shippingPolicy}
              onChange={(e) => setShippingPolicy(e.target.value)}
              rows={4}
            />
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Jam Operasional</label>
            <input
              type="text"
              className={styles.input}
              placeholder="Contoh: Senin-Jumat 09:00-17:00 WIB"
              value={supportHours}
              onChange={(e) => setSupportHours(e.target.value)}
            />
          </div>
        </div>

        {/* Toggles */}
        <div className="card">
          <h3 className={styles.sectionTitle}>✅ Trust Signals</h3>

          <div className={styles.toggleRow}>
            <div>
              <div className={styles.toggleLabel}>Nomor Telepon Terverifikasi</div>
              <div className={styles.toggleDesc}>Tampilkan badge &quot;Verified&quot; di storefront</div>
            </div>
            <label className={styles.toggle}>
              <input type="checkbox" checked={verifiedPhone} onChange={(e) => setVerifiedPhone(e.target.checked)} />
              <span className={styles.slider}></span>
            </label>
          </div>

          <div className={styles.toggleRow}>
            <div>
              <div className={styles.toggleLabel}>Pembayaran Online Aktif</div>
              <div className={styles.toggleDesc}>Customer bisa bayar langsung via payment link</div>
            </div>
            <label className={styles.toggle}>
              <input type="checkbox" checked={paymentEnabled} onChange={(e) => setPaymentEnabled(e.target.checked)} />
              <span className={styles.slider}></span>
            </label>
          </div>
        </div>

        {/* Testimonials */}
        <div className="card" style={{ gridColumn: "1 / -1" }}>
          <h3 className={styles.sectionTitle}>⭐ Testimonial</h3>

          {testimonials.length === 0 && (
            <p className={styles.emptyState}>Belum ada testimonial. Tambahkan testimoni customer untuk meningkatkan trust.</p>
          )}

          <div className={styles.testimonialGrid}>
            {testimonials.map((t, i) => (
              <div key={i} className={styles.testimonialCard}>
                <div className={styles.testimonialHeader}>
                  <span className={styles.testimonialName}>{t.name}</span>
                  <span className={styles.testimonialRating}>{"⭐".repeat(t.rating)}</span>
                  <button className={styles.removeBtn} onClick={() => removeTestimonial(i)}>✕</button>
                </div>
                <p className={styles.testimonialText}>&quot;{t.text}&quot;</p>
              </div>
            ))}
          </div>

          <div className={styles.addTestimonial}>
            <input
              type="text" placeholder="Nama customer"
              className={styles.input}
              value={newTestimonial.name}
              onChange={(e) => setNewTestimonial({ ...newTestimonial, name: e.target.value })}
            />
            <input
              type="text" placeholder="Testimoni"
              className={styles.input}
              value={newTestimonial.text}
              onChange={(e) => setNewTestimonial({ ...newTestimonial, text: e.target.value })}
            />
            <select
              className={styles.input}
              value={newTestimonial.rating}
              onChange={(e) => setNewTestimonial({ ...newTestimonial, rating: parseInt(e.target.value) })}
            >
              {[5, 4, 3, 2, 1].map((r) => <option key={r} value={r}>{r} ⭐</option>)}
            </select>
            <button className="btn btn-outline btn-sm" onClick={addTestimonial}>+ Tambah</button>
          </div>
        </div>
      </div>

      <div className={styles.saveBar}>
        <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? "Menyimpan..." : "💾 Simpan Trust Profile"}
        </button>
      </div>
    </div>
  );
}
