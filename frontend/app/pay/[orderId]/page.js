"use client";
import { useState, useEffect, useCallback } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import styles from "./payment.module.css";

/**
 * PAYMENT PAGE — /pay/[orderId]
 * Shows payment info (QR code, VA number, or Midtrans Snap redirect).
 * Polls for payment status every 5 seconds.
 */
export default function PaymentPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const orderId = params.orderId;
  const statusParam = searchParams.get("status"); // from Midtrans redirect

  const [loading, setLoading] = useState(true);
  const [order, setOrder] = useState(null);
  const [paymentInfo, setPaymentInfo] = useState(null);
  const [paymentStatus, setPaymentStatus] = useState("pending");
  const [error, setError] = useState(null);
  const [polling, setPolling] = useState(false);
  const [selectedMethod, setSelectedMethod] = useState(null);
  const [methods, setMethods] = useState([]);
  const [creating, setCreating] = useState(false);

  // Load order details
  useEffect(() => {
    async function loadOrder() {
      try {
        // Try to get order (might not be authed for public view)
        const data = await api.getPaymentStatus(orderId);
        setOrder(data);
        setPaymentStatus(data.status);
        if (data.payment_created) {
          setPaymentInfo(data);
        }
      } catch (e) {
        // Not authed — that's OK for public payment page
        setError(null);
      }
      setLoading(false);
    }

    loadOrder();
  }, [orderId]);

  // Load available payment methods
  useEffect(() => {
    async function loadMethods() {
      try {
        const data = await api.getPaymentMethods();
        setMethods(data.methods || []);
        if (data.methods?.length > 0) {
          setSelectedMethod(data.methods[0]);
        }
      } catch (e) {
        // Not authed — show basic info
      }
    }
    loadMethods();
  }, []);

  // Poll payment status
  useEffect(() => {
    if (!paymentInfo || paymentStatus === "paid" || paymentStatus === "expired") return;

    setPolling(true);
    const interval = setInterval(async () => {
      try {
        const data = await api.getPaymentStatus(orderId);
        setPaymentStatus(data.status);
        if (data.status === "paid") {
          clearInterval(interval);
          setPolling(false);
        }
      } catch (e) {
        // Ignore polling errors
      }
    }, 5000);

    return () => {
      clearInterval(interval);
      setPolling(false);
    };
  }, [paymentInfo, paymentStatus, orderId]);

  // Handle Midtrans redirect status
  useEffect(() => {
    if (statusParam === "finish") {
      setPaymentStatus("paid");
    }
  }, [statusParam]);

  // Create payment
  const handleCreatePayment = useCallback(async () => {
    if (!selectedMethod || creating) return;
    setCreating(true);
    setError(null);

    try {
      const data = await api.createPayment({
        order_id: parseInt(orderId),
        method: selectedMethod.method,
        provider: selectedMethod.provider,
      });
      setPaymentInfo(data);

      // If Midtrans Snap with redirect URL, redirect
      if (data.payment_url && selectedMethod.method === "snap") {
        window.location.href = data.payment_url;
        return;
      }
    } catch (e) {
      setError(e.message || "Gagal membuat pembayaran");
    }
    setCreating(false);
  }, [selectedMethod, orderId, creating]);

  // Format currency
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

  // Payment successful
  if (paymentStatus === "paid") {
    return (
      <div className={styles.page}>
        <div className={styles.card}>
          <div className={styles.successIcon}>✅</div>
          <h1 className={styles.title}>Pembayaran Berhasil!</h1>
          <p className={styles.subtitle}>
            Terima kasih! Order #{orderId} sudah dibayar.
          </p>
          <div className={styles.successDetail}>
            <p>Pesanan Anda sedang diproses oleh seller.</p>
            <p className={styles.muted}>Anda akan dihubungi untuk info pengiriman.</p>
          </div>
        </div>
      </div>
    );
  }

  // Payment expired
  if (paymentStatus === "expired" || paymentStatus === "cancelled") {
    return (
      <div className={styles.page}>
        <div className={styles.card}>
          <div className={styles.expiredIcon}>⏰</div>
          <h1 className={styles.title}>Pembayaran Expired</h1>
          <p className={styles.subtitle}>
            Waktu pembayaran untuk Order #{orderId} sudah habis.
          </p>
          <p className={styles.muted}>Silakan hubungi seller untuk membuat pesanan baru.</p>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        {/* Header */}
        <div className={styles.header}>
          <h1 className={styles.title}>💳 Pembayaran</h1>
          <p className={styles.subtitle}>Order #{orderId}</p>
        </div>

        {/* Amount */}
        {order && (
          <div className={styles.amountBox}>
            <span className={styles.amountLabel}>Total Pembayaran</span>
            <span className={styles.amount}>{formatRp(order.amount)}</span>
          </div>
        )}

        {/* Payment Info (if already created) */}
        {paymentInfo && paymentInfo.payment_url && (
          <div className={styles.paymentDetails}>
            {/* QR Code */}
            {paymentInfo.qr_data && (
              <div className={styles.qrSection}>
                <p className={styles.qrLabel}>Scan QR Code untuk bayar:</p>
                <img
                  src={paymentInfo.qr_data}
                  alt="QR Payment"
                  className={styles.qrImage}
                />
                <p className={styles.qrHint}>
                  Buka aplikasi e-wallet atau mobile banking, lalu scan QR di atas
                </p>
              </div>
            )}

            {/* VA Number */}
            {paymentInfo.va_number && (
              <div className={styles.vaSection}>
                <p className={styles.vaLabel}>Nomor Virtual Account:</p>
                <div className={styles.vaNumber}>
                  <span>{paymentInfo.va_number}</span>
                  <button
                    className={styles.copyBtn}
                    onClick={() => {
                      navigator.clipboard.writeText(paymentInfo.va_number);
                    }}
                  >
                    📋 Copy
                  </button>
                </div>
              </div>
            )}

            {/* Checkout URL */}
            {paymentInfo.payment_url && !paymentInfo.qr_data && !paymentInfo.va_number && (
              <a
                href={paymentInfo.payment_url}
                target="_blank"
                rel="noopener noreferrer"
                className={styles.payButton}
              >
                Lanjut ke Halaman Pembayaran →
              </a>
            )}

            {/* Expiry */}
            {paymentInfo.expires_at && (
              <p className={styles.expiry}>
                ⏰ Bayar sebelum: {paymentInfo.expires_at}
              </p>
            )}

            {/* Status */}
            <div className={styles.statusBar}>
              {polling && <span className={styles.pollingDot}></span>}
              <span>Status: <strong>{paymentStatus}</strong></span>
              {polling && <span className={styles.pollingText}>Menunggu pembayaran...</span>}
            </div>
          </div>
        )}

        {/* Payment method selection (if no payment created yet) */}
        {!paymentInfo && methods.length > 0 && (
          <div className={styles.methodSection}>
            <h3 className={styles.methodTitle}>Pilih Metode Pembayaran:</h3>
            <div className={styles.methodList}>
              {methods.map((m, i) => (
                <button
                  key={i}
                  className={`${styles.methodCard} ${selectedMethod?.method === m.method ? styles.methodSelected : ""}`}
                  onClick={() => setSelectedMethod(m)}
                >
                  <span className={styles.methodIcon}>{m.icon}</span>
                  <div>
                    <strong>{m.label}</strong>
                    <p className={styles.methodDesc}>{m.description}</p>
                  </div>
                </button>
              ))}
            </div>

            {error && <p className={styles.error}>{error}</p>}

            <button
              className={styles.createBtn}
              onClick={handleCreatePayment}
              disabled={creating || !selectedMethod}
            >
              {creating ? "Memproses..." : "Buat Pembayaran"}
            </button>
          </div>
        )}

        {/* Powered by */}
        <div className={styles.footer}>
          Powered by <strong>JUALIN.AI</strong>
        </div>
      </div>
    </div>
  );
}
