"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import styles from "../scale.module.css";

function money(value) {
  return `Rp ${Number(value || 0).toLocaleString("id-ID")}`;
}

export default function BillingPage() {
  const [plans, setPlans] = useState([]);
  const [usage, setUsage] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const [planData, usageData] = await Promise.all([api.getBillingPlans(), api.getBillingUsage()]);
        setPlans(planData);
        setUsage(usageData);
      } catch (e) {
        setError(e.message);
      }
    })();
  }, []);

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.titleBlock}>
          <h2>Billing SaaS</h2>
          <p className={styles.muted}>Plan, limit, dan usage counter untuk monetisasi platform.</p>
        </div>
      </div>
      {error && <div className={styles.error}>{error}</div>}
      <div className={styles.grid}>
        {plans.map((plan) => (
          <div key={plan.code} className={styles.statCard}>
            <div className={styles.listTitle}><span>{plan.name}</span><span>{money(plan.price_monthly)}</span></div>
            <div className={styles.list} style={{ marginTop: 12 }}>
              {Object.entries(plan.limits || {}).map(([key, value]) => (
                <div key={key} className={styles.listMeta}><span>{key}</span><strong>{value}</strong></div>
              ))}
            </div>
          </div>
        ))}
      </div>
      <div className={styles.panel}>
        <div className={styles.panelHeader}><strong>Usage Bulan Ini</strong></div>
        {usage.length === 0 && <div className={styles.stateBox}>Belum ada usage counter tercatat.</div>}
        <div className={styles.tableWrap}>
          <table className="table">
            <thead><tr><th>Metric</th><th>Period</th><th>Used</th><th>Limit</th></tr></thead>
            <tbody>
              {usage.map((item) => {
                const pct = item.limit > 0 ? Math.round(item.used / item.limit * 100) : 0;
                const badgeCls = pct >= 90 ? "badge-danger" : pct >= 70 ? "badge-warning" : "badge-success";
                return (
                  <tr key={`${item.metric}-${item.period}`}>
                    <td>{item.metric}</td>
                    <td>{item.period}</td>
                    <td>
                      {item.used}
                      {item.limit > 0 && (
                        <span className={`badge ${badgeCls}`} style={{ marginLeft: 8, fontSize: "0.75em" }}>
                          {pct}%
                        </span>
                      )}
                    </td>
                    <td>{item.limit < 0 ? "∞" : item.limit}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
