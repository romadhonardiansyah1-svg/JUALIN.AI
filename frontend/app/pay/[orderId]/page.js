"use client";
/* eslint-disable @next/next/no-img-element */
import { useState, useEffect, useCallback } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import styles from "./payment.module.css";

/**
 * PAYMENT PAGE — /pay/[orderId] — P2.4 secure capability flow
 * - Fragment token #token=... cleaned via replaceState, POST exchange -> HttpOnly session
 * - Legacy ?token= compat (one-use, metric, sunset)
 * - Consent checkbox for transactional reminder (unchecked default, separate)
 * - No token in referrer/analytics, private no-store responses
 */
export default function PaymentPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const orderId = params.orderId;
  const statusParam = searchParams.get("status");
  const legacyToken = searchParams.get("token") || "";

  const [loading, setLoading] = useState(true);
  const [order, setOrder] = useState(null);
  const [paymentInfo, setPaymentInfo] = useState(null);
  const [paymentStatus, setPaymentStatus] = useState("pending");
  const [error, setError] = useState(null);
  const [polling, setPolling] = useState(false);
  const [selectedMethod, setSelectedMethod] = useState(null);
  const [methods, setMethods] = useState([]);
  const [methodsLoaded, setMethodsLoaded] = useState(false);
  const [creating, setCreating] = useState(false);
  const [capabilityExchanged, setCapabilityExchanged] = useState(false);
  const [capabilityReady, setCapabilityReady] = useState(false);

  const [consentGranted, setConsentGranted] = useState(false);
  const [consentCopyVersion] = useState("v1");
  const [consentSaving, setConsentSaving] = useState(false);
  const [consentMessage, setConsentMessage] = useState("");

  const extractFragmentToken = () => {
    if (typeof window === "undefined") return null;
    const hash = window.location.hash || "";
    if (!hash) return null;
    const frag = hash.startsWith("#") ? hash.slice(1) : hash;
    const p = new URLSearchParams(frag);
    return p.get("token") || p.get("t") || p.get("payment_token") || null;
  };

  useEffect(() => {
    async function initializeCapability() {
      const fragmentToken = extractFragmentToken();
      if (!fragmentToken) {
        setCapabilityReady(true);
        return;
      }
      try {
        const cleanUrl = window.location.pathname + window.location.search;
        window.history.replaceState(null, "", cleanUrl);
      } catch {}
      try {
        await api.exchangePublicCapability(orderId, fragmentToken);
        setCapabilityExchanged(true);
        setCapabilityReady(true);
      } catch (e) {
        console.error("Capability exchange failed", e);
        setError(e.message || "Token pembayaran tidak valid");
        setLoading(false);
      }
    }
    initializeCapability();
  }, [orderId]);

  useEffect(() => {
    if (!capabilityReady) return;

    async function loadOrder() {
      try {
        let data;
        if (capabilityExchanged || !legacyToken) {
          try {
            data = await api.getPublicPaymentStatusViaSession(orderId);
          } catch (sessionErr) {
            if (legacyToken) data = await api.getPublicPaymentStatus(orderId, legacyToken);
            else throw sessionErr;
          }
        } else {
          data = await api.getPublicPaymentStatus(orderId, legacyToken);
        }
        setOrder(data);
        setPaymentStatus(data.status);
        if (data.payment_created) setPaymentInfo(data);
      } catch (e) {
        setError(e.message || "Link pembayaran tidak valid");
      }
      setLoading(false);
    }
    loadOrder();
  }, [orderId, legacyToken, capabilityExchanged, capabilityReady]);

  useEffect(() => {
    if (!capabilityReady) return;

    async function loadMethods() {
      try {
        let data;
        if (capabilityExchanged || !legacyToken) {
          try {
            data = await api.getPublicPaymentMethodsViaSession(orderId);
          } catch (sessionErr) {
            if (legacyToken) data = await api.getPublicPaymentMethods(orderId, legacyToken);
            else throw sessionErr;
          }
        } else {
          data = await api.getPublicPaymentMethods(orderId, legacyToken);
        }
        setMethods(data.methods || []);
        if (data.methods?.length > 0) setSelectedMethod(data.methods[0]);
      } catch (e) {
        console.error("Failed to load payment methods", e);
      } finally {
        setMethodsLoaded(true);
      }
    }
    loadMethods();
  }, [orderId, legacyToken, capabilityExchanged, capabilityReady]);

  useEffect(() => {
    if (!capabilityReady || !paymentInfo || paymentStatus === "paid" || paymentStatus === "expired") return;
    setPolling(true);
    const interval = setInterval(async () => {
      try {
        let data;
        if (capabilityExchanged || !legacyToken) {
          try {
            data = await api.getPublicPaymentStatusViaSession(orderId);
          } catch (sessionErr) {
            if (legacyToken) data = await api.getPublicPaymentStatus(orderId, legacyToken);
            else throw sessionErr;
          }
        } else {
          data = await api.getPublicPaymentStatus(orderId, legacyToken);
        }
        setPaymentStatus(data.status);
        if (data.status === "paid") {
          clearInterval(interval);
          setPolling(false);
        }
      } catch {}
    }, 5000);
    return () => {
      clearInterval(interval);
      setPolling(false);
    };
  }, [paymentInfo, paymentStatus, orderId, legacyToken, capabilityExchanged, capabilityReady]);

  useEffect(() => {
    if (statusParam === "finish") setPolling(true);
  }, [statusParam]);

  const handleCreatePayment = useCallback(async () => {
    if (!capabilityReady || !selectedMethod || creating) return;
    setCreating(true);
    setError(null);
    try {
      let data;
      if (capabilityExchanged || !legacyToken) {
        data = await api.createPublicPaymentViaSession({
          order_id: parseInt(orderId),
          method: selectedMethod.method,
          provider: selectedMethod.provider,
        });
      } else {
        data = await api.createPublicPayment({
          order_id: parseInt(orderId),
          token: legacyToken,
          method: selectedMethod.method,
          provider: selectedMethod.provider,
        });
      }
      setPaymentInfo(data);
      setOrder(data);
      if (data.payment_url && selectedMethod.method === "snap") {
        window.location.href = data.payment_url;
        return;
      }
    } catch (e) {
      setError(e.message || "Gagal membuat pembayaran");
    }
    setCreating(false);
  }, [selectedMethod, orderId, legacyToken, creating, capabilityExchanged, capabilityReady]);

  const handleConsentSave = useCallback(async () => {
    if (!capabilityReady) return;
    setConsentSaving(true);
    setConsentMessage("");
    try {
      const result = await api.grantReminderConsent(orderId, consentGranted, consentCopyVersion);
      setConsentMessage(result.message || (consentGranted ? "Izin disimpan." : "Izin ditarik."));
    } catch (e) {
      setConsentMessage(e.message || "Gagal menyimpan izin");
    }
    setConsentSaving(false);
  }, [orderId, consentGranted, consentCopyVersion, capabilityReady]);

  const formatRp = (amount) => `Rp ${Number(amount || 0).toLocaleString("id-ID")}`;

  if (loading) {
    return (
      <div className={styles.page}>
        <div className={styles.card}>
          <div className={styles.loading}>
            <div className={styles.spinner}></div>
            <p>Memuat informasi pembayaran...</p>
          </div>
        </div>
      </div>
    );
  }

  if (error && !paymentInfo) {
    return (
      <div className={styles.page}>
        <div className={styles.card}>
          <div className={styles.expiredIcon}>⚠️</div>
          <h1 className={styles.title}>Link Pembayaran Tidak Valid</h1>
          <p className={styles.subtitle}>{error}</p>
          <p className={styles.muted}>Silakan minta link pembayaran baru dari seller.</p>
        </div>
      </div>
    );
  }

  if (paymentStatus === "paid") {
    return (
      <div className={styles.page}>
        <div className={styles.card}>
          <div className={styles.successIcon}>✅</div>
          <h1 className={styles.title}>Pembayaran Berhasil!</h1>
          <p className={styles.subtitle}>Terima kasih! Order #{orderId} sudah dibayar.</p>
          <div className={styles.successDetail}>
            <p>Pesanan Anda sedang diproses oleh seller.</p>
            <p className={styles.muted}>Anda akan dihubungi untuk info pengiriman.</p>
          </div>
        </div>
      </div>
    );
  }

  if (paymentStatus === "expired" || paymentStatus === "cancelled") {
    return (
      <div className={styles.page}>
        <div className={styles.card}>
          <div className={styles.expiredIcon}>⏰</div>
          <h1 className={styles.title}>Pembayaran Expired</h1>
          <p className={styles.subtitle}>Waktu pembayaran untuk Order #{orderId} sudah habis.</p>
          <p className={styles.muted}>Silakan hubungi seller untuk membuat pesanan baru.</p>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.header}>
          <h1 className={styles.title}>💳 Pembayaran</h1>
          <p className={styles.subtitle}>Order #{orderId}</p>
        </div>

        {order && (
          <div className={styles.amountBox}>
            <span className={styles.amountLabel}>Total Pembayaran</span>
            <span className={styles.amount}>{formatRp(order.amount)}</span>
          </div>
        )}

        {paymentInfo && (paymentInfo.payment_url || paymentInfo.qr_data || paymentInfo.va_number) && (
          <div className={styles.paymentDetails}>
            {paymentInfo.qr_data && (
              <div className={styles.qrSection}>
                <p className={styles.qrLabel}>Scan QR Code untuk bayar:</p>
                <img src={paymentInfo.qr_data} alt="QR Payment" className={styles.qrImage} />
                <p className={styles.qrHint}>Buka e-wallet atau mobile banking, lalu scan QR di atas</p>
              </div>
            )}
            {paymentInfo.va_number && (
              <div className={styles.vaSection}>
                <p className={styles.vaLabel}>Nomor Virtual Account:</p>
                <div className={styles.vaNumber}>
                  <span>{paymentInfo.va_number}</span>
                  <button className={styles.copyBtn} onClick={() => navigator.clipboard.writeText(paymentInfo.va_number)}>📋 Copy</button>
                </div>
              </div>
            )}
            {paymentInfo.payment_url && !paymentInfo.qr_data && !paymentInfo.va_number && (
              <a href={paymentInfo.payment_url} target="_blank" rel="noopener noreferrer" className={styles.payButton}>Lanjut ke Halaman Pembayaran →</a>
            )}
            {paymentInfo.expires_at && <p className={styles.expiry}>⏰ Bayar sebelum: {paymentInfo.expires_at}</p>}
            <div className={styles.statusBar}>
              {polling && <span className={styles.pollingDot}></span>}
              <span>Status: <strong>{paymentStatus}</strong></span>
              {polling && <span className={styles.pollingText}>Menunggu pembayaran...</span>}
            </div>
          </div>
        )}

        {!paymentInfo && methods.length > 0 && (
          <div className={styles.methodSection}>
            <h3 className={styles.methodTitle}>Pilih Metode Pembayaran:</h3>
            <div className={styles.methodList}>
              {methods.map((m, i) => (
                <button key={i} className={`${styles.methodCard} ${selectedMethod?.method === m.method ? styles.methodSelected : ""}`} onClick={() => setSelectedMethod(m)}>
                  <span className={styles.methodIcon}>{m.icon}</span>
                  <div><strong>{m.label}</strong><p className={styles.methodDesc}>{m.description}</p></div>
                </button>
              ))}
            </div>
            {error && <p className={styles.error}>{error}</p>}
            <button className={styles.createBtn} onClick={handleCreatePayment} disabled={creating || !selectedMethod}>{creating ? "Memproses..." : "Buat Pembayaran"}</button>
          </div>
        )}

        {!paymentInfo && methodsLoaded && methods.length === 0 && (
          <div className={styles.notice}><strong>Metode pembayaran belum tersedia.</strong><p>Silakan hubungi seller untuk menyelesaikan pembayaran order ini.</p></div>
        )}

        {/* Consent — P2.4 */}
        <div className={styles.methodSection} style={{ marginTop: 20, borderTop: "1px solid #f3f4f6", paddingTop: 16 }}>
          <h3 className={styles.methodTitle}>Pengingat Pembayaran</h3>
          <label style={{ display: "flex", gap: 10, alignItems: "flex-start", fontSize: "0.9rem", cursor: "pointer" }}>
            <input type="checkbox" checked={consentGranted} onChange={(e) => setConsentGranted(e.target.checked)} style={{ marginTop: 4 }} />
            <span>Saya setuju menerima status dan maksimal satu pengingat pembayaran untuk pesanan ini melalui WhatsApp.</span>
          </label>
          <p className={styles.muted} style={{ fontSize: "0.78rem", marginTop: 8 }}>
            Izin ini hanya untuk pesanan ini, dapat ditarik kapan saja dengan membalas STOP/BERHENTI, dan terpisah dari izin marketing.
            <br />
            <a href="/privacy" target="_blank" rel="noopener noreferrer" style={{ color: "#22c55e" }}>Kebijakan privasi</a>
          </p>
          <button className={styles.createBtn} onClick={handleConsentSave} disabled={consentSaving} style={{ marginTop: 10, background: consentGranted ? "#22c55e" : "#6b7280" }}>
            {consentSaving ? "Menyimpan..." : consentGranted ? "Simpan Izin" : "Tarik Izin"}
          </button>
          {consentMessage && <p className={styles.muted} style={{ marginTop: 8, color: "#16a34a" }}>{consentMessage}</p>}
        </div>

        <div className={styles.footer}>Powered by <strong>JUALIN.AI</strong></div>
      </div>
    </div>
  );
}
