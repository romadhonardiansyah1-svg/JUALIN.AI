"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import styles from "./proof.module.css";

/**
 * P6.3 — Safety Receipt UI for deterministic Proof Mode.
 * Permanent DATA SIMULASI watermark. PASS only from assertion values.
 */
export default function ProofModePage() {
  const [capability, setCapability] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const cap = await api.getProofCapability();
      setCapability(cap);
      try {
        const latest = await api.getProofLatest();
        setResult(latest);
      } catch (e) {
        if (!(e instanceof ApiError && e.status === 404)) {
          // leave empty on 404
        }
      }
    } catch (e) {
      setError(e.message || "Proof Mode tidak tersedia");
      setCapability(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function runSuite() {
    setRunning(true);
    setError("");
    try {
      const data = await api.runProofMode({ suite: "backend", seed: 42 });
      setResult(data);
    } catch (e) {
      setError(e.message || "Gagal menjalankan Proof Mode");
    } finally {
      setRunning(false);
    }
  }

  if (loading) {
    return <div className={styles.page}>Memeriksa kapabilitas Proof Mode…</div>;
  }

  const enabled = capability?.enabled;
  const dims = result?.dimensions || {};

  return (
    <div className={styles.page}>
      <div className={styles.watermark} aria-hidden>
        DATA SIMULASI
      </div>
      <header className={styles.header}>
        <h1>Proof Mode — Safety Receipt</h1>
        <p className={styles.sub}>
          Harness deterministik untuk invariant keselamatan. Bukan bukti staging
          WhatsApp/payment live. Browser E2E terpisah.
        </p>
      </header>

      {!enabled && (
        <div className={styles.bannerWarn} role="status">
          Proof Mode tidak diaktifkan untuk sesi ini (admin/demo only
          {capability?.blocked ? `; blocked: ${capability.block_reason}` : ""}).
        </div>
      )}

      <div className={styles.actions}>
        <button
          type="button"
          className={styles.runBtn}
          disabled={!enabled || running}
          onClick={runSuite}
        >
          {running ? "Menjalankan…" : "Jalankan suite backend (seed 42)"}
        </button>
        <button type="button" className={styles.secondary} onClick={load} disabled={running}>
          Muat artifact terakhir
        </button>
      </div>

      {error && <div className={styles.error}>{error}</div>}

      <section className={styles.dims}>
        <h2>Dimensi status</h2>
        <ul>
          <li>
            Backend invariants:{" "}
            <strong>{dims.backend_invariants || result?.status || "—"}</strong>
          </li>
          <li>
            Browser E2E: <strong>{dims.browser_e2e || "not_run"}</strong>
          </li>
          <li>
            Staging provider: <strong>{dims.staging_provider || "blocked"}</strong>
          </li>
        </ul>
      </section>

      {result && (
        <section className={styles.card}>
          <h2>Evidence</h2>
          <dl className={styles.meta}>
            <div>
              <dt>Status</dt>
              <dd className={result.status === "passed" ? styles.pass : styles.fail}>
                {result.status}
              </dd>
            </div>
            <div>
              <dt>Commit</dt>
              <dd>
                <code>{result.commit_sha || "—"}</code>
              </dd>
            </div>
            <div>
              <dt>Run ID</dt>
              <dd>
                <code>{result.run_id || "—"}</code>
              </dd>
            </div>
            <div>
              <dt>Seed</dt>
              <dd>{result.seed ?? "—"}</dd>
            </div>
            <div>
              <dt>Summary</dt>
              <dd>
                passed {result.summary?.backend_passed ?? result.summary?.passed ?? "—"} /{" "}
                {result.summary?.backend_required ?? result.summary?.total ?? "—"} backend
              </dd>
            </div>
          </dl>
          <p className={styles.disclaimer}>{result.disclaimer}</p>
          <p className={styles.sim}>WATERMARK: {result.watermark || "DATA SIMULASI"}</p>

          <h3>Scenarios</h3>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Status</th>
                  <th>Assertions</th>
                  <th>Invariants</th>
                  <th>Provider calls</th>
                </tr>
              </thead>
              <tbody>
                {(result.scenarios || []).map((s) => (
                  <tr key={s.scenario_id}>
                    <td>
                      <code>{s.scenario_id}</code>
                    </td>
                    <td>{s.status}</td>
                    <td>
                      {(s.assertions || []).filter((a) => a.ok).length}/
                      {(s.assertions || []).length}
                    </td>
                    <td>{(s.invariants || []).join(", ") || "—"}</td>
                    <td>{s.provider_calls ?? 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <details className={styles.raw}>
            <summary>JSON artifact (sanitized)</summary>
            <pre>{JSON.stringify(result, null, 2)}</pre>
          </details>
        </section>
      )}
    </div>
  );
}
