"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import styles from "./proof.module.css";

/**
 * P6.3 — Safety Receipt UI. PASS only from assertion values.
 * Permanent DATA SIMULASI watermark. Stale/missing → UNVERIFIED.
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
        if (e instanceof ApiError && e.status === 404) {
          setResult({
            status: "UNVERIFIED",
            verification_status: "UNVERIFIED",
            unverified_reason: "missing_artifact",
            watermark: "DATA SIMULASI",
            scenarios: [],
          });
        }
      }
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        setError("Proof Mode tidak tersedia di environment ini.");
      } else {
        setError(e.message || "Proof Mode tidak tersedia");
      }
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

  async function downloadJson() {
    try {
      const data = await api.downloadProofArtifact("proof-backend-latest.json");
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "proof-backend-latest.json";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e.message || "Download gagal");
    }
  }

  if (loading) {
    return (
      <div className={styles.page} role="status">
        Memeriksa kapabilitas Proof Mode…
      </div>
    );
  }

  const enabled = capability?.enabled;
  const dims = result?.dimensions || {};
  const displayStatus =
    result?.verification_status || result?.status || "UNVERIFIED";
  const backendDim = dims.backend_invariants || displayStatus;
  const browserDim = dims.browser_e2e || "not_run";
  const stagingDim = dims.staging_provider || "blocked";

  return (
    <div className={styles.page}>
      <div className={styles.watermark} aria-hidden>
        DATA SIMULASI
      </div>
      <header className={styles.header}>
        <h1>Proof Mode — Safety Receipt</h1>
        <p className={styles.sub}>
          Harness deterministik. Bukan staging provider. Browser E2E terpisah.
          Status dihitung dari assertion artifact, bukan hardcode UI.
        </p>
      </header>

      {!enabled && (
        <div className={styles.bannerWarn} role="status">
          Proof Mode tidak diaktifkan (admin/demo only
          {capability?.blocked ? `; ${capability.block_reason}` : ""}).
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
        <button
          type="button"
          className={styles.secondary}
          onClick={downloadJson}
          disabled={!enabled || !result || result.unverified_reason === "missing_artifact"}
        >
          Unduh JSON (authorized)
        </button>
      </div>

      {error && (
        <div className={styles.error} role="alert">
          {error}
        </div>
      )}

      <section className={styles.dims} aria-label="Dimensi status">
        <h2>Dimensi (jangan digabung jadi full PASS jika browser not_run)</h2>
        <ul>
          <li>
            Backend invariants: <strong>{backendDim}</strong>
          </li>
          <li>
            Browser E2E: <strong>{browserDim}</strong>
          </li>
          <li>
            Staging provider: <strong>{stagingDim}</strong>
          </li>
        </ul>
      </section>

      {result && (
        <section className={styles.card}>
          <h2>Evidence</h2>
          <dl className={styles.meta}>
            <div>
              <dt>Status (from assertions)</dt>
              <dd
                className={
                  displayStatus === "passed" ? styles.pass : styles.fail
                }
              >
                {displayStatus}
              </dd>
            </div>
            <div>
              <dt>Commit SHA</dt>
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
              <dt>Environment</dt>
              <dd>{result.environment || "—"}</dd>
            </div>
            <div>
              <dt>Generated</dt>
              <dd>
                {result.generated_at || result.finished_at || result.started_at || "—"}
              </dd>
            </div>
            <div>
              <dt>Schema</dt>
              <dd>{result.schema_version || "—"}</dd>
            </div>
            <div>
              <dt>Redaction</dt>
              <dd>{result.redaction_status || "—"}</dd>
            </div>
            <div>
              <dt>Unverified reason</dt>
              <dd>{result.unverified_reason || "—"}</dd>
            </div>
          </dl>
          <p className={styles.disclaimer}>{result.disclaimer}</p>
          <p className={styles.sim}>WATERMARK: {result.watermark || "DATA SIMULASI"}</p>

          <h3>Scenarios</h3>
          {!result.scenarios?.length && (
            <p className={styles.sub}>Empty — artifact missing or UNVERIFIED.</p>
          )}
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">ID</th>
                  <th scope="col">Status</th>
                  <th scope="col">Assertions</th>
                  <th scope="col">Invariants</th>
                  <th scope="col">Expected / Actual</th>
                  <th scope="col">Provider calls</th>
                  <th scope="col">Audit</th>
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
                    <td>
                      {(s.assertions || [])
                        .slice(0, 2)
                        .map((a, i) => (
                          <div key={i}>
                            {a.expected != null ? `exp:${String(a.expected)} ` : ""}
                            {a.actual != null ? `act:${JSON.stringify(a.actual)}` : a.message}
                          </div>
                        ))}
                    </td>
                    <td>{s.provider_calls ?? 0}</td>
                    <td>
                      {(s.assertions || [])
                        .map((a) => a.audit_code)
                        .filter(Boolean)
                        .join(", ") || "—"}
                    </td>
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
