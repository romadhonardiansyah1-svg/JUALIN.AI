"use client";
import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";

const ROLE_EMOJI = {
  orchestrator: "🧭", sales: "🛍️", negotiator: "🤝",
  inventory: "📦", growth: "📣", finance: "💰", cs: "🎧",
};

function rupiah(n) {
  return "Rp " + Number(n || 0).toLocaleString("id-ID");
}

export default function AgentOsPage() {
  const [overview, setOverview] = useState(null);
  const [activity, setActivity] = useState([]);
  const [brief, setBrief] = useState(null);
  const [approvals, setApprovals] = useState([]);
  const [negotiations, setNegotiations] = useState([]);
  const [policy, setPolicy] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setError("");
      const [ov, act, appr, neg, pol] = await Promise.all([
        api.agentOsOverview(),
        api.agentOsActivity(40),
        api.agentOsApprovals("pending"),
        api.agentOsNegotiations(),
        api.agentOsGetPolicy(),
      ]);
      setOverview(ov);
      setActivity(act);
      setApprovals(appr);
      setNegotiations(neg);
      setPolicy(pol);
    } catch (e) {
      setError(e.message || "Gagal memuat");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 8000); // live refresh feed
    return () => clearInterval(t);
  }, [load]);

  const loadBrief = async () => {
    try {
      const b = await api.agentOsBrief();
      setBrief(b);
    } catch (e) {
      setError(e.message);
    }
  };

  const decide = async (id, action) => {
    try {
      if (action === "approve") await api.agentOsApprove(id);
      else await api.agentOsReject(id);
      await load();
    } catch (e) {
      setError(e.message);
    }
  };

  const savePolicy = async (patch) => {
    try {
      const next = { ...policy, ...patch };
      setPolicy(next);
      await api.agentOsUpdatePolicy(patch);
    } catch (e) {
      setError(e.message);
    }
  };

  if (loading) return <div style={{ padding: 24, color: "#94a3b8" }}>Memuat AI Crew…</div>;

  const card = {
    background: "#0f172a", border: "1px solid #1e293b", borderRadius: 14,
    padding: 16, color: "#e2e8f0",
  };
  const chip = (bg) => ({
    display: "inline-block", padding: "2px 8px", borderRadius: 999,
    fontSize: 11, fontWeight: 700, background: bg, color: "#0b1220",
  });

  return (
    <div className="aurora-bg" style={{ display: "flex", flexDirection: "column", gap: 16, padding: 16, borderRadius: 20 }}>
      {/* Header */}
      <div style={{ ...card, background: "linear-gradient(135deg,#0b3b2e,#0f172a)" }}>
        <h2 className="gradient-text" style={{ margin: 0, fontSize: 22 }}>🤖 AI Crew — Pusat Komando Toko Otonom</h2>
        <p style={{ margin: "6px 0 0", color: "#94a3b8" }}>
          Tim karyawan AI yang menjalankan tokomu. Semua tindakan tercatat &amp; bisa kamu kendalikan.
        </p>
      </div>

      {error && <div style={{ ...card, borderColor: "#7f1d1d", color: "#fecaca" }}>{error}</div>}

      {/* KPI ringkas */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(160px,1fr))", gap: 12 }}>
        <div style={card}>
          <div style={{ color: "#94a3b8", fontSize: 12 }}>Omzet hari ini</div>
          <div style={{ fontSize: 22, fontWeight: 800 }}>{rupiah(overview?.finance?.revenue_today)}</div>
          <div style={{ fontSize: 12, color: (overview?.finance?.revenue_delta_pct ?? 0) >= 0 ? "#34d399" : "#f87171" }}>
            {overview?.finance?.revenue_delta_pct ?? 0}% vs kemarin
          </div>
        </div>
        <div style={card}>
          <div style={{ color: "#94a3b8", fontSize: 12 }}>Pembayaran tertunda</div>
          <div style={{ fontSize: 22, fontWeight: 800 }}>{overview?.finance?.pending_today ?? 0}</div>
          <div style={{ fontSize: 12, color: "#fbbf24" }}>{rupiah(overview?.finance?.pending_value)}</div>
        </div>
        <div style={card}>
          <div style={{ color: "#94a3b8", fontSize: 12 }}>Menunggu persetujuan</div>
          <div style={{ fontSize: 22, fontWeight: 800 }}>{overview?.pending_approvals ?? 0}</div>
        </div>
        <div style={card}>
          <div style={{ color: "#94a3b8", fontSize: 12 }}>Produk terlaris</div>
          <div style={{ fontSize: 16, fontWeight: 700 }}>{overview?.finance?.top_product || "-"}</div>
        </div>
      </div>

      {/* Crew cards */}
      <div style={card}>
        <h3 style={{ marginTop: 0 }}>Tim Agen</h3>
        <div className="deck-3d" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 10 }}>
          {(overview?.crew || []).map((c) => (
            <div key={c.role} className="card-3d" style={{ background: "#111c33", borderRadius: 12, padding: 12, textAlign: "center" }}>
              <div style={{ fontSize: 26 }}>{ROLE_EMOJI[c.role] || "🤖"}</div>
              <div style={{ fontWeight: 700, marginTop: 4 }}>{c.label}</div>
              <div style={{ fontSize: 12, color: "#94a3b8" }}>{c.actions_24h} aksi / 24 jam</div>
              <span style={chip("#34d399")}>aktif</span>
            </div>
          ))}
        </div>
      </div>

      {/* Approvals */}
      <div style={card}>
        <h3 style={{ marginTop: 0 }}>🔔 Menunggu Persetujuan Kamu ({approvals.length})</h3>
        {approvals.length === 0 && <div style={{ color: "#94a3b8" }}>Tidak ada yang perlu disetujui. 👍</div>}
        {approvals.map((a) => (
          <div key={a.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
            padding: "10px 0", borderBottom: "1px solid #1e293b" }}>
            <div>
              <div style={{ fontWeight: 700 }}>{a.title}</div>
              <div style={{ fontSize: 12, color: "#94a3b8" }}>{a.action_type} · {a.agent_role}</div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button onClick={() => decide(a.id, "approve")}
                style={{ background: "#22c55e", border: 0, color: "#06210f", fontWeight: 700, padding: "8px 14px", borderRadius: 8, cursor: "pointer" }}>
                Setujui
              </button>
              <button onClick={() => decide(a.id, "reject")}
                style={{ background: "#334155", border: 0, color: "#e2e8f0", padding: "8px 14px", borderRadius: 8, cursor: "pointer" }}>
                Tolak
              </button>
            </div>
          </div>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        {/* Activity feed */}
        <div style={card}>
          <h3 style={{ marginTop: 0 }}>📡 Aktivitas Agen (live)</h3>
          <div style={{ maxHeight: 360, overflowY: "auto" }}>
            {activity.length === 0 && <div style={{ color: "#94a3b8" }}>Belum ada aktivitas.</div>}
            {activity.map((r) => (
              <div key={r.id} style={{ display: "flex", gap: 10, padding: "8px 0", borderBottom: "1px solid #1e293b" }}>
                <div style={{ fontSize: 20 }}>{ROLE_EMOJI[r.agent_role] || "🤖"}</div>
                <div>
                  <div style={{ fontSize: 13 }}>{r.summary}</div>
                  <div style={{ fontSize: 11, color: "#64748b" }}>
                    {r.agent_role} · {r.trigger} · {r.created_at?.slice(11, 19)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Negotiations */}
        <div style={card}>
          <h3 style={{ marginTop: 0 }}>🤝 Negosiasi Berjalan</h3>
          <div style={{ maxHeight: 360, overflowY: "auto" }}>
            {negotiations.length === 0 && <div style={{ color: "#94a3b8" }}>Belum ada negosiasi.</div>}
            {negotiations.map((n) => (
              <div key={n.id} style={{ padding: "8px 0", borderBottom: "1px solid #1e293b", fontSize: 13 }}>
                <div>Normal {rupiah(n.list_price)} · Lantai {rupiah(n.floor_price)}</div>
                <div>Penawaran terakhir: <b>{rupiah(n.current_offer)}</b> · {n.rounds} ronde · <span style={chip(
                  n.status === "accepted" ? "#34d399" : n.status === "escalated" ? "#fbbf24" : "#60a5fa"
                )}>{n.status}</span></div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Daily brief */}
      <div style={card}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h3 style={{ margin: 0 }}>🗞️ Laporan Harian Manajer AI</h3>
          <button onClick={loadBrief}
            style={{ background: "#22c55e", border: 0, color: "#06210f", fontWeight: 700, padding: "8px 14px", borderRadius: 8, cursor: "pointer" }}>
            Buat / Refresh Laporan
          </button>
        </div>
        {brief ? (
          <p style={{ marginTop: 12, lineHeight: 1.6 }}>{brief.narrative}</p>
        ) : (
          <p style={{ color: "#94a3b8" }}>Klik tombol untuk menghasilkan laporan hari ini.</p>
        )}
      </div>

      {/* Policy */}
      {policy && (
        <div style={card}>
          <h3 style={{ marginTop: 0 }}>⚙️ Kebijakan &amp; Kendali</h3>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 12 }}>
            <label style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span>Negosiasi otomatis</span>
              <input type="checkbox" checked={!!policy.allow_auto_negotiation}
                onChange={(e) => savePolicy({ allow_auto_negotiation: e.target.checked })} />
            </label>
            <label style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span>Diskon maksimum (%)</span>
              <input type="number" value={policy.max_discount_percent}
                onChange={(e) => setPolicy({ ...policy, max_discount_percent: e.target.value })}
                onBlur={(e) => savePolicy({ max_discount_percent: Number(e.target.value) })}
                style={{ width: 70 }} />
            </label>
            <label style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span>Margin minimum (%)</span>
              <input type="number" value={policy.margin_floor_percent}
                onChange={(e) => setPolicy({ ...policy, margin_floor_percent: e.target.value })}
                onBlur={(e) => savePolicy({ margin_floor_percent: Number(e.target.value) })}
                style={{ width: 70 }} />
            </label>
            <label style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span>Butuh approval di atas (%)</span>
              <input type="number" value={policy.require_approval_above_percent}
                onChange={(e) => setPolicy({ ...policy, require_approval_above_percent: e.target.value })}
                onBlur={(e) => savePolicy({ require_approval_above_percent: Number(e.target.value) })}
                style={{ width: 70 }} />
            </label>
          </div>
        </div>
      )}
    </div>
  );
}
