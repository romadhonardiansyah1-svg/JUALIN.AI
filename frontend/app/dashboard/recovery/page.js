"use client";
import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import styles from "./recovery.module.css";

/**
 * Jualin Santai — Observe-only dashboard (P2.7)
 * Shows mode/capability banner, honest summary, opportunity evidence, suppression reasons
 * No approve/send control in observe mode
 */

function StateBox({ state, children }) {
  if (state === "loading") return <div className={styles.stateBox}>Memeriksa peluang pembayaran…</div>;
  if (state === "empty") return <div className={styles.stateBox}>{children || "Belum ada pembayaran yang perlu ditinjau."}</div>;
  if (state === "error") return <div className={styles.stateBoxError}>Bagian ini belum dapat dimuat. Data lain tetap aman.</div>;
  if (state === "disabled") return <div className={styles.stateBox}>Jualin Santai belum diaktifkan untuk toko ini.</div>;
  if (state === "stale") return <div className={styles.stateBox}>Menampilkan data terakhir. Muat ulang sebelum mengambil keputusan.</div>;
  return <div className={styles.stateBox}>{children}</div>;
}

export default function RecoveryPage() {
  const [capabilities, setCapabilities] = useState(null);
  const [capLoading, setCapLoading] = useState(true);
  const [overview, setOverview] = useState(null);
  const [overviewState, setOverviewState] = useState("loading");
  const [opportunities, setOpportunities] = useState([]);
  const [oppState, setOppState] = useState("loading");
  const [selected, setSelected] = useState(null);
  const [detailState, setDetailState] = useState("empty");

  const loadCapabilities = useCallback(async () => {
    try {
      const data = await api.getCapabilities();
      setCapabilities(data.capabilities?.payment_recovery || null);
    } catch {
      setCapabilities(null);
    }
    setCapLoading(false);
  }, []);

  const loadOverview = useCallback(async () => {
    setOverviewState("loading");
    try {
      const data = await api.getRecoveryOverview();
      setOverview(data);
      setOverviewState("ready");
    } catch {
      setOverviewState("error");
    }
  }, []);

  const loadOpportunities = useCallback(async () => {
    setOppState("loading");
    try {
      const data = await api.getRecoveryOpportunities({ status: "detected", limit: 20 });
      setOpportunities(data.items || []);
      setOppState(data.items?.length ? "ready" : "empty");
    } catch {
      setOppState("error");
    }
  }, []);

  const loadDetail = useCallback(async (id) => {
    setDetailState("loading");
    try {
      const data = await api.getRecoveryOpportunity(id);
      setSelected(data);
      setDetailState("ready");
    } catch {
      setDetailState("error");
    }
  }, []);

  useEffect(() => {
    loadCapabilities();
    loadOverview();
    loadOpportunities();
  }, [loadCapabilities, loadOverview, loadOpportunities]);

  const mode = capabilities?.mode || overview?.mode || "observe";
  const paused = capabilities?.paused || false;
  const enabled = capabilities?.enabled ?? false;

  const getModeBanner = () => {
    if (capLoading) return { text: "Memeriksa sesi Anda…", type: "loading" };
    if (!enabled || paused) {
      if (capabilities?.reason === "feature_disabled") return { text: "Jualin Santai belum diaktifkan untuk toko ini.", type: "disabled" };
      if (capabilities?.reason === "tenant_paused" || paused) return { text: "Pemulihan dijeda untuk toko ini. Tidak ada pesan baru yang dikirim.", type: "paused" };
      return { text: "Jualin Santai belum diaktifkan untuk toko ini.", type: "disabled" };
    }
    if (mode === "observe") return { text: "Mode observasi — tidak ada pesan yang dikirim.", type: "observe" };
    if (mode === "approval") return { text: "Mode persetujuan — pesan dikirim hanya setelah Anda setujui.", type: "approval" };
    return { text: "Mode observasi — tidak ada pesan yang dikirim.", type: "observe" };
  };

  const banner = getModeBanner();

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>Jualin Santai</h1>
        <p className={styles.subtitle}>AI yang menemukan pembayaran tertinggal, meminta persetujuan dengan bukti yang jelas, mengirim satu pengingat yang aman, lalu menunjukkan hasil secara jujur.</p>
      </div>

      <div className={`${styles.banner} ${styles[banner.type]}`}>{banner.text}</div>

      {overviewState === "loading" ? (
        <StateBox state="loading" />
      ) : overviewState === "error" ? (
        <StateBox state="error" />
      ) : overview ? (
        <div className={styles.summaryGrid}>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>Menunggu Persetujuan</span>
            <span className={styles.summaryValue}>{overview.counts?.awaiting_approval ?? 0}</span>
          </div>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>Terjadwal</span>
            <span className={styles.summaryValue}>{overview.counts?.scheduled ?? 0}</span>
          </div>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>Ditekan (Suppressed)</span>
            <span className={styles.summaryValue}>{overview.counts?.suppressed ?? 0}</span>
          </div>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>Pembayaran Teramati</span>
            <span className={styles.summaryValue}>{overview.outcomes?.observed_payment?.orders ?? 0}</span>
            <span className={styles.summaryAmount}>Rp{overview.outcomes?.observed_payment?.amount || "0.00"}</span>
          </div>
        </div>
      ) : (
        <StateBox state="empty">Belum ada simulasi peluang pada periode ini.</StateBox>
      )}

      <div className={styles.mainGrid}>
        <div className={styles.listPanel}>
          <h3 className={styles.panelTitle}>Peluang Pembayaran</h3>
          {oppState === "loading" && <StateBox state="loading" />}
          {oppState === "error" && <StateBox state="error" />}
          {oppState === "empty" && <StateBox state="empty">Belum ada pembayaran yang perlu ditinjau.</StateBox>}
          {oppState === "ready" && (
            <div className={styles.list}>
              {opportunities.map((opp) => (
                <button key={opp.id} className={`${styles.listItem} ${selected?.id === opp.id ? styles.selected : ""}`} onClick={() => loadDetail(opp.id)}>
                  <div className={styles.listRow}>
                    <span className={styles.orderRef}>ORD-{opp.order_id}</span>
                    <span className={styles.amount}>Rp{opp.amount}</span>
                  </div>
                  <div className={styles.listMeta}>
                    <span className={`badge ${opp.status}`}>{opp.status}</span>
                    <span>{opp.expires_at ? new Date(opp.expires_at).toLocaleString("id-ID") : ""}</span>
                  </div>
                  {opp.suppression_code && <div className={styles.suppression}>Alasan: {opp.suppression_code}</div>}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className={styles.detailPanel}>
          <h3 className={styles.panelTitle}>Detail & Bukti Aman</h3>
          {detailState === "empty" && <StateBox state="empty">Pilih peluang untuk melihat bukti.</StateBox>}
          {detailState === "loading" && <StateBox state="loading" />}
          {detailState === "error" && <StateBox state="error" />}
          {detailState === "ready" && selected && (
            <div className={styles.detail}>
              <div className={styles.evidenceSection}>
                <h4>Mengapa aman?</h4>
                <ul className={styles.evidenceList}>
                  {selected.evidence?.map((ev, i) => (
                    <li key={i} className={styles.evidenceItem}>
                      <span className={styles.evidenceCode}>{ev.code}</span>
                      <span className={styles.evidenceTime}>{ev.observed_at ? new Date(ev.observed_at).toLocaleString("id-ID") : ""}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className={styles.previewSection}>
                <h4>Preview Pesan</h4>
                <div className={styles.previewBox}>
                  <p><strong>Template:</strong> {selected.preview?.template_code}</p>
                  <p>{selected.preview?.text}</p>
                  <p className={styles.muted}>Domain terpercaya: {selected.preview?.payment_reference?.trusted_domain} — {selected.preview?.payment_reference?.masked_path}</p>
                  <p className={styles.muted}>Jadwal: {selected.preview?.scheduled_at ? new Date(selected.preview.scheduled_at).toLocaleString("id-ID") : "-"}</p>
                  <p className={styles.muted}>Kedaluwarsa persetujuan: {selected.preview?.expires_at ? new Date(selected.preview.expires_at).toLocaleString("id-ID") : "-"}</p>
                </div>
                <p className={styles.revalidationNote}>Pesanan akan diperiksa ulang tepat sebelum pengiriman.</p>
              </div>

              <div className={styles.recipientSection}>
                <p><strong>Penerima (masked):</strong> {selected.recipient?.masked}</p>
                <p><strong>Jumlah:</strong> Rp{selected.order?.amount} {selected.order?.currency}</p>
              </div>

              <div className={styles.observeNote}>
                <strong>Mode observasi:</strong> Ini hanya simulasi; tidak ada pesan yang dikirim. Persetujuan & pengiriman akan aktif di fase berikutnya setelah gate keamanan lulus.
              </div>
            </div>
          )}
        </div>
      </div>

      <div className={styles.outcomesPanel}>
        <h3>Outcomes Terbaru</h3>
        <p className={styles.muted}>Pembayaran teramati setelah pengingat (bukan bukti kausal). Data ini menunjukkan urutan waktu, bukan bukti bahwa pengingat menyebabkan pembayaran.</p>
        {overview?.outcomes && (
          <div className={styles.outcomesGrid}>
            <div>Teramati: Rp{overview.outcomes.observed_payment?.amount} ({overview.outcomes.observed_payment?.orders} order)</div>
            <div>Terkait aturan: Rp{overview.outcomes.rule_attributed?.amount}</div>
            <div>Estimasi kausal: {overview.outcomes.causal_estimate ?? "Belum tersedia karena belum ada kelompok pembanding yang memadai."}</div>
          </div>
        )}
      </div>
    </div>
  );
}
