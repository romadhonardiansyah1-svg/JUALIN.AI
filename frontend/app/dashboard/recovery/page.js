"use client";
import { useEffect, useState, useCallback, useRef } from "react";
import { api, ApiError } from "@/lib/api";
import styles from "./recovery.module.css";

/**
 * Jualin Santai — Observe (P2.7) + seller approval (P4.5)
 * Action digest is never user-editable. Approve/reject only in approval mode.
 */

function StateBox({ state, children }) {
  if (state === "loading") return <div className={styles.stateBox}>Memeriksa peluang pembayaran…</div>;
  if (state === "empty") return <div className={styles.stateBox}>{children || "Belum ada pembayaran yang perlu ditinjau."}</div>;
  if (state === "error") return <div className={styles.stateBoxError}>Bagian ini belum dapat dimuat. Data lain tetap aman.</div>;
  if (state === "disabled") return <div className={styles.stateBox}>Jualin Santai belum diaktifkan untuk toko ini.</div>;
  if (state === "stale") return <div className={styles.stateBox}>Menampilkan data terakhir. Muat ulang sebelum mengambil keputusan.</div>;
  return <div className={styles.stateBox}>{children}</div>;
}

function newIdempotencyKey(prefix) {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return `${prefix}:${crypto.randomUUID()}`;
  }
  return `${prefix}:${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function decisionCopy(err) {
  if (!(err instanceof ApiError)) {
    return "Keputusan belum dapat diproses. Coba lagi sebentar.";
  }
  const code = err.code || "";
  if (err.status === 202 || code === "accepted") return null;
  if (err.status === 409 && code === "idempotency_conflict") {
    return "Permintaan bentrok dengan keputusan sebelumnya. Muat ulang kartu.";
  }
  if (err.status === 409 || code === "approval_stale" || code === "approval_already_used") {
    return "Persetujuan sudah tidak berlaku. Muat ulang sebelum memutuskan ulang.";
  }
  if (err.status === 410) {
    return "Peluang ini sudah kedaluwarsa.";
  }
  if (err.status === 403) {
    return "Mode persetujuan belum diaktifkan atau Anda tidak berhak memutuskan.";
  }
  if (err.status === 404) {
    return "Peluang tidak ditemukan.";
  }
  return err.message || "Keputusan belum dapat diproses.";
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
  const [decisionState, setDecisionState] = useState("idle");
  const [decisionMessage, setDecisionMessage] = useState("");
  const [liveMessage, setLiveMessage] = useState("");
  const approveKeyRef = useRef(null);
  const rejectKeyRef = useRef(null);
  const detailRequestId = useRef(0);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const loadCapabilities = useCallback(async () => {
    try {
      const data = await api.getCapabilities();
      if (!mountedRef.current) return;
      setCapabilities(data.capabilities?.payment_recovery || null);
    } catch {
      if (!mountedRef.current) return;
      setCapabilities(null);
    }
    if (mountedRef.current) setCapLoading(false);
  }, []);

  const loadOverview = useCallback(async () => {
    setOverviewState("loading");
    try {
      const data = await api.getRecoveryOverview();
      if (!mountedRef.current) return;
      setOverview(data);
      setOverviewState("ready");
    } catch {
      if (!mountedRef.current) return;
      setOverviewState("error");
    }
  }, []);

  const loadOpportunities = useCallback(async () => {
    setOppState("loading");
    try {
      // Prefer awaiting_approval for decision queue; fall back to detected for observe.
      let data = await api.getRecoveryOpportunities({ status: "awaiting_approval", limit: 20 });
      if (!data.items?.length) {
        data = await api.getRecoveryOpportunities({ status: "detected", limit: 20 });
      }
      if (!mountedRef.current) return;
      setOpportunities(data.items || []);
      setOppState(data.items?.length ? "ready" : "empty");
    } catch {
      if (!mountedRef.current) return;
      setOppState("error");
    }
  }, []);

  const loadDetail = useCallback(async (id) => {
    const reqId = ++detailRequestId.current;
    setDetailState("loading");
    setDecisionState("idle");
    setDecisionMessage("");
    approveKeyRef.current = newIdempotencyKey("recovery-approve");
    rejectKeyRef.current = newIdempotencyKey("recovery-reject");
    try {
      const data = await api.getRecoveryOpportunity(id);
      if (!mountedRef.current || reqId !== detailRequestId.current) return;
      setSelected(data);
      setDetailState("ready");
    } catch {
      if (!mountedRef.current || reqId !== detailRequestId.current) return;
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
  const canApproveMode = enabled && !paused && mode === "approval";

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
  const deciding = decisionState === "submitting";
  const canDecide =
    canApproveMode &&
    selected?.can_decide &&
    selected?.preview?.action_digest &&
    !deciding &&
    detailState === "ready";

  async function handleApprove() {
    if (!canDecide || !selected) return;
    setDecisionState("submitting");
    setDecisionMessage("");
    setLiveMessage("Mengirim persetujuan…");
    try {
      const result = await api.approveRecoveryOpportunity(selected.id, {
        expected_version: selected.state_version,
        action_digest: selected.preview.action_digest,
        idempotency_key: approveKeyRef.current,
      });
      if (!mountedRef.current) return;
      setDecisionState("success");
      setDecisionMessage(
        result?.message ||
          "Disetujui dan dijadwalkan. Status belum berarti terkirim ke pelanggan."
      );
      setLiveMessage("Persetujuan diterima. Pengingat dijadwalkan, belum terkirim.");
      await Promise.all([loadOverview(), loadOpportunities()]);
      await loadDetail(selected.id);
    } catch (err) {
      if (!mountedRef.current) return;
      const msg = decisionCopy(err);
      setDecisionState("error");
      setDecisionMessage(msg);
      setLiveMessage(msg);
      if (err instanceof ApiError && (err.status === 409 || err.status === 410)) {
        await loadDetail(selected.id);
      }
    }
  }

  async function handleReject() {
    if (!selected || deciding || !canApproveMode) return;
    if (selected.status !== "awaiting_approval" && !selected.can_decide) return;
    setDecisionState("submitting");
    setDecisionMessage("");
    setLiveMessage("Mengirim penolakan…");
    try {
      const result = await api.rejectRecoveryOpportunity(selected.id, {
        expected_version: selected.state_version,
        idempotency_key: rejectKeyRef.current,
        reason: "seller_skipped",
      });
      if (!mountedRef.current) return;
      setDecisionState("success");
      setDecisionMessage(result?.message || "Peluang ditolak. Tidak ada pesan yang dikirim.");
      setLiveMessage("Peluang ditolak.");
      await Promise.all([loadOverview(), loadOpportunities()]);
      await loadDetail(selected.id);
    } catch (err) {
      if (!mountedRef.current) return;
      const msg = decisionCopy(err);
      setDecisionState("error");
      setDecisionMessage(msg);
      setLiveMessage(msg);
      if (err instanceof ApiError && (err.status === 409 || err.status === 410)) {
        await loadDetail(selected.id);
      }
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>Jualin Santai</h1>
        <p className={styles.subtitle}>
          AI yang menemukan pembayaran tertinggal, meminta persetujuan dengan bukti yang jelas,
          mengirim satu pengingat yang aman, lalu menunjukkan hasil secara jujur.
        </p>
      </div>

      <div className={`${styles.banner} ${styles[banner.type]}`} role="status">
        {banner.text}
      </div>
      <div className={styles.srOnly} aria-live="polite">
        {liveMessage}
      </div>

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
            <div className={styles.list} role="list">
              {opportunities.map((opp) => (
                <button
                  key={opp.id}
                  type="button"
                  className={`${styles.listItem} ${selected?.id === opp.id ? styles.selected : ""}`}
                  onClick={() => loadDetail(opp.id)}
                >
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
                  {(selected.evidence || []).map((ev, i) => (
                    <li key={i} className={styles.evidenceItem}>
                      <span className={styles.evidenceCode}>{ev.code}</span>
                      <span className={styles.evidenceTime}>
                        {ev.observed_at ? new Date(ev.observed_at).toLocaleString("id-ID") : ""}
                      </span>
                    </li>
                  ))}
                  {!selected.evidence?.length && (
                    <li className={styles.evidenceItem}>
                      <span className={styles.evidenceCode}>evidence_pending</span>
                      <span className={styles.evidenceTime}>Belum ada kode bukti terstruktur</span>
                    </li>
                  )}
                </ul>
              </div>

              <div className={styles.previewSection}>
                <h4>Preview Pesan</h4>
                <div className={styles.previewBox}>
                  <p>
                    <strong>Template:</strong> {selected.preview?.template_code}
                  </p>
                  <p>
                    <strong>Status template provider:</strong>{" "}
                    {selected.preview?.template_provider_status || "belum diverifikasi"}
                  </p>
                  <p>{selected.preview?.text}</p>
                  <p className={styles.muted}>
                    Domain terpercaya: {selected.preview?.payment_reference?.trusted_domain} —{" "}
                    {selected.preview?.payment_reference?.masked_path}
                  </p>
                  <p className={styles.muted}>
                    Jadwal:{" "}
                    {selected.preview?.scheduled_at
                      ? new Date(selected.preview.scheduled_at).toLocaleString("id-ID")
                      : "-"}
                  </p>
                  <p className={styles.muted}>
                    Kedaluwarsa persetujuan:{" "}
                    {selected.preview?.expires_at
                      ? new Date(selected.preview.expires_at).toLocaleString("id-ID")
                      : "-"}
                  </p>
                  {selected.preview?.action_digest && (
                    <p className={styles.digest}>
                      Digest aksi (hanya baca): <code>{selected.preview.action_digest.slice(0, 16)}…</code>
                    </p>
                  )}
                </div>
                <p className={styles.revalidationNote}>
                  Pesanan, consent, dan status pembayaran diperiksa ulang tepat sebelum pengiriman.
                </p>
              </div>

              <div className={styles.recipientSection}>
                <p>
                  <strong>Penerima (masked):</strong> {selected.recipient?.masked}
                </p>
                <p>
                  <strong>Jumlah:</strong> Rp{selected.order?.amount} {selected.order?.currency}
                </p>
                <p>
                  <strong>Status:</strong> {selected.status}
                </p>
              </div>

              {canApproveMode ? (
                <div className={styles.decisionBar}>
                  <button
                    type="button"
                    className={styles.approveBtn}
                    disabled={!canDecide}
                    onClick={handleApprove}
                  >
                    {deciding ? "Memproses…" : "Setujui & jadwalkan"}
                  </button>
                  <button
                    type="button"
                    className={styles.rejectBtn}
                    disabled={deciding || selected.status !== "awaiting_approval"}
                    onClick={handleReject}
                  >
                    Lewati
                  </button>
                  {!selected.can_decide && selected.status === "awaiting_approval" && (
                    <p className={styles.muted}>
                      Digest aksi belum tersedia. Materialisasi approval mungkin belum selesai.
                    </p>
                  )}
                  {!canDecide && selected.status !== "awaiting_approval" && (
                    <p className={styles.muted}>Keputusan hanya untuk peluang menunggu persetujuan.</p>
                  )}
                </div>
              ) : (
                <div className={styles.observeNote}>
                  <strong>Mode observasi:</strong> Ini hanya simulasi; tidak ada pesan yang dikirim.
                  Aktifkan mode persetujuan setelah gate keamanan lulus untuk menyetujui pengingat.
                </div>
              )}

              {decisionMessage && (
                <div
                  className={
                    decisionState === "error" ? styles.decisionError : styles.decisionSuccess
                  }
                  role="status"
                >
                  {decisionMessage}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <div className={styles.outcomesPanel}>
        <h3>Outcomes Terbaru</h3>
        <p className={styles.muted}>
          Pembayaran teramati setelah pengingat (bukan bukti kausal). Data ini menunjukkan urutan
          waktu, bukan bukti bahwa pengingat menyebabkan pembayaran.
        </p>
        {overview?.outcomes && (
          <div className={styles.outcomesGrid}>
            <div>
              Teramati: Rp{overview.outcomes.observed_payment?.amount} (
              {overview.outcomes.observed_payment?.orders} order)
            </div>
            <div>Terkait aturan: Rp{overview.outcomes.rule_attributed?.amount}</div>
            <div>
              Estimasi kausal:{" "}
              {overview.outcomes.causal_estimate ??
                "Belum tersedia karena belum ada kelompok pembanding yang memadai."}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
