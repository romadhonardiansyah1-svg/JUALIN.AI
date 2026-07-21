"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const card = {
  background: "#0f172a", border: "1px solid #1e293b", borderRadius: 14,
  padding: 16, color: "#e2e8f0", marginBottom: 16,
};
const cellInput = {
  width: "100%", padding: "6px 8px", borderRadius: 6, border: "1px solid #334155",
  background: "#111c33", color: "#e2e8f0", fontSize: 13, boxSizing: "border-box",
};
const th = { padding: "6px 8px", fontSize: 12, fontWeight: 600, borderBottom: "1px solid #1e293b", whiteSpace: "nowrap" };
const td = { padding: "6px 6px", borderBottom: "1px solid #1e293b", verticalAlign: "middle" };
const btn = (bg) => ({
  padding: "8px 14px", borderRadius: 8, border: "none", cursor: "pointer",
  fontWeight: 700, background: bg, color: "#0b1220",
});
const miniBtn = (bg) => ({
  padding: "5px 8px", borderRadius: 6, border: "none", cursor: "pointer",
  fontWeight: 700, background: bg, color: "#0b1220", marginRight: 4,
});

const EMPTY = { label: "", base_url: "", model: "", priority: 100, api_keys: "" };

export default function AdminLlmPage() {
  const [providers, setProviders] = useState([]);
  const [envInfo, setEnvInfo] = useState(null);
  const [newProv, setNewProv] = useState(EMPTY);
  const [testResult, setTestResult] = useState(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const p = await api.adminLlmProviders();
      setProviders(p.providers || []);
    } catch (e) { setMsg(e.message); }
    try {
      const s = await api.adminLlmGet();
      setEnvInfo(s.env_fallback || null);
    } catch { /* fallback info optional */ }
  };
  useEffect(() => { load(); }, []);

  const setField = (id, field, value) => {
    setProviders((list) => list.map((p) => (p.id === id ? { ...p, [field]: value } : p)));
  };

  const saveProvider = async (p) => {
    setBusy(true); setMsg("");
    try {
      const body = {
        label: p.label, base_url: p.base_url, model: p.model,
        priority: Number(p.priority) || 100, is_enabled: !!p.is_enabled,
      };
      if (p.api_keys_input && p.api_keys_input.trim()) {
        body.api_keys = p.api_keys_input.split(",").map((s) => s.trim()).filter(Boolean);
      }
      await api.adminLlmProviderUpdate(p.id, body);
      setMsg("✅ Tersimpan (aktif maksimal 60 detik lagi, atau langsung setelah Tes Koneksi).");
      await load();
    } catch (e) { setMsg("❌ " + e.message); }
    setBusy(false);
  };

  const deleteProvider = async (id) => {
    setBusy(true); setMsg("");
    try { await api.adminLlmProviderDelete(id); setMsg("✅ Penyedia dihapus."); await load(); }
    catch (e) { setMsg("❌ " + e.message); }
    setBusy(false);
  };

  const addProvider = async () => {
    if (!newProv.base_url.trim() || !newProv.model.trim()) {
      setMsg("❌ Base URL dan Model wajib diisi.");
      return;
    }
    setBusy(true); setMsg("");
    try {
      await api.adminLlmProviderCreate({
        label: newProv.label, base_url: newProv.base_url, model: newProv.model,
        priority: Number(newProv.priority) || 100,
        api_keys: newProv.api_keys ? newProv.api_keys.split(",").map((s) => s.trim()).filter(Boolean) : [],
      });
      setNewProv(EMPTY);
      setMsg("✅ Penyedia ditambahkan.");
      await load();
    } catch (e) { setMsg("❌ " + e.message); }
    setBusy(false);
  };

  const test = async () => {
    setBusy(true); setTestResult(null);
    try { setTestResult(await api.adminLlmTest()); } catch (e) { setTestResult({ ok: false, error: e.message }); }
    setBusy(false);
  };

  return (
    <div style={{ padding: 16, maxWidth: 860 }}>
      <h2 style={{ color: "#e2e8f0" }}>🧠 LLM Control Panel</h2>
      <p style={{ color: "#94a3b8", marginTop: 4 }}>
        Kelola semua penyedia AI dalam satu tabel (OpenAI-compatible: Groq/OpenRouter/OpenAI/dll).
        Sistem memakai penyedia <b>aktif</b> berurutan prioritas (kecil → besar) dengan failover otomatis. Tanpa restart.
      </p>

      <div style={card}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <h3 style={{ margin: 0 }}>Penyedia AI</h3>
          <button style={btn("#93c5fd")} disabled={busy} onClick={test}>⚡ Tes Koneksi</button>
        </div>

        {testResult && (
          <div style={{ marginBottom: 10, fontSize: 13, color: testResult.ok ? "#34d399" : "#f87171" }}>
            {testResult.ok
              ? `✅ OK ${testResult.latency_ms}ms · model ${testResult.model} · "${testResult.reply}"`
              : `❌ Gagal: ${testResult.error}`}
          </div>
        )}

        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ color: "#94a3b8", textAlign: "left" }}>
                <th style={th}>Aktif</th>
                <th style={th}>Label</th>
                <th style={th}>Base URL</th>
                <th style={th}>Model</th>
                <th style={th}>API Key</th>
                <th style={{ ...th, width: 64 }}>Prio</th>
                <th style={{ ...th, width: 90 }}>Aksi</th>
              </tr>
            </thead>
            <tbody>
              {providers.map((p) => (
                <tr key={p.id}>
                  <td style={{ ...td, textAlign: "center" }}>
                    <input type="checkbox" checked={!!p.is_enabled} onChange={(e) => setField(p.id, "is_enabled", e.target.checked)} />
                  </td>
                  <td style={td}><input style={cellInput} value={p.label || ""} onChange={(e) => setField(p.id, "label", e.target.value)} placeholder="Groq" /></td>
                  <td style={td}><input style={cellInput} value={p.base_url || ""} onChange={(e) => setField(p.id, "base_url", e.target.value)} placeholder="https://…/v1" /></td>
                  <td style={td}><input style={cellInput} value={p.model || ""} onChange={(e) => setField(p.id, "model", e.target.value)} placeholder="model" /></td>
                  <td style={td}>
                    <input style={cellInput} type="password" value={p.api_keys_input || ""}
                      onChange={(e) => setField(p.id, "api_keys_input", e.target.value)}
                      placeholder={(p.api_keys_masked || []).join(", ") || "sk-…"} />
                  </td>
                  <td style={td}><input style={{ ...cellInput, width: 60 }} type="number" value={p.priority ?? 100} onChange={(e) => setField(p.id, "priority", e.target.value)} /></td>
                  <td style={td}>
                    <button style={miniBtn("#34d399")} disabled={busy} onClick={() => saveProvider(p)} title="Simpan">💾</button>
                    <button style={miniBtn("#f87171")} disabled={busy} onClick={() => deleteProvider(p.id)} title="Hapus">🗑</button>
                  </td>
                </tr>
              ))}

              <tr style={{ background: "#0b1526" }}>
                <td style={{ ...td, textAlign: "center", color: "#64748b" }}>➕</td>
                <td style={td}><input style={cellInput} value={newProv.label} onChange={(e) => setNewProv({ ...newProv, label: e.target.value })} placeholder="Groq" /></td>
                <td style={td}><input style={cellInput} value={newProv.base_url} onChange={(e) => setNewProv({ ...newProv, base_url: e.target.value })} placeholder="https://api.groq.com/openai/v1" /></td>
                <td style={td}><input style={cellInput} value={newProv.model} onChange={(e) => setNewProv({ ...newProv, model: e.target.value })} placeholder="llama-3.3-70b-versatile" /></td>
                <td style={td}><input style={cellInput} type="password" value={newProv.api_keys} onChange={(e) => setNewProv({ ...newProv, api_keys: e.target.value })} placeholder="gsk_… (pisah koma)" /></td>
                <td style={td}><input style={{ ...cellInput, width: 60 }} type="number" value={newProv.priority} onChange={(e) => setNewProv({ ...newProv, priority: e.target.value })} /></td>
                <td style={td}><button style={miniBtn("#34d399")} disabled={busy} onClick={addProvider} title="Tambah penyedia">➕</button></td>
              </tr>
            </tbody>
          </table>
        </div>

        {providers.length === 0 && (
          <div style={{ color: "#94a3b8", fontSize: 13, marginTop: 10 }}>
            Belum ada penyedia — sementara sistem memakai .env
            {envInfo ? ` (${envInfo.model} @ ${envInfo.base_url})` : ""}. Isi baris ➕ lalu klik tombol ➕ untuk menambah.
          </div>
        )}

        {msg && <div style={{ marginTop: 10, fontSize: 13, color: "#fbbf24" }}>{msg}</div>}

        <p style={{ fontSize: 12, color: "#64748b", marginTop: 12 }}>
          Kolom API Key: kosongkan saat menyimpan = pertahankan key yang ada; isi (pisah koma) untuk mengganti.
          Failover otomatis: penyedia prioritas terkecil dipakai dulu, gagal → pindah ke penyedia berikutnya.
        </p>
      </div>
    </div>
  );
}
