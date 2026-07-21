"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const card = {
  background: "#0f172a", border: "1px solid #1e293b", borderRadius: 14,
  padding: 16, color: "#e2e8f0", marginBottom: 16,
};
const input = {
  width: "100%", padding: "8px 10px", borderRadius: 8, border: "1px solid #334155",
  background: "#111c33", color: "#e2e8f0", fontSize: 14, marginTop: 4,
};
const btn = (bg) => ({
  padding: "8px 14px", borderRadius: 8, border: "none", cursor: "pointer",
  fontWeight: 700, background: bg, color: "#0b1220",
});

export default function AdminLlmPage() {
  const [cfg, setCfg] = useState(null);
  const [newKey, setNewKey] = useState("");
  const [testResult, setTestResult] = useState(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [providers, setProviders] = useState([]);
  const emptyProv = { label: "", base_url: "", model: "", light_model: "", fallback_model: "", priority: 100, api_keys: "" };
  const [newProv, setNewProv] = useState(emptyProv);

  const load = async () => {
    try { setCfg(await api.adminLlmGet()); } catch (e) { setMsg(e.message); }
  };
  const loadProviders = async () => {
    try { const p = await api.adminLlmProviders(); setProviders(p.providers || []); } catch (e) { setMsg(e.message); }
  };
  useEffect(() => { load(); loadProviders(); }, []);

  const save = async () => {
    setBusy(true); setMsg("");
    try {
      await api.adminLlmUpdate({
        is_enabled: cfg.is_enabled,
        provider_label: cfg.provider_label,
        base_url: cfg.base_url,
        model: cfg.model,
        light_model: cfg.light_model,
        fallback_model: cfg.fallback_model,
      });
      setMsg("✅ Tersimpan. Konfigurasi aktif maksimal 60 detik lagi (atau langsung setelah Test).");
    } catch (e) { setMsg("❌ " + e.message); }
    setBusy(false);
  };

  const addKey = async () => {
    if (!newKey.trim()) return;
    setBusy(true); setMsg("");
    try {
      const r = await api.adminLlmAddKey(newKey.trim());
      setNewKey("");
      setCfg({ ...cfg, api_keys_masked: r.api_keys_masked });
      setMsg("✅ Key ditambahkan.");
    } catch (e) { setMsg("❌ " + e.message); }
    setBusy(false);
  };

  const removeKey = async (i) => {
    setBusy(true); setMsg("");
    try {
      const r = await api.adminLlmRemoveKey(i);
      setCfg({ ...cfg, api_keys_masked: r.api_keys_masked });
    } catch (e) { setMsg("❌ " + e.message); }
    setBusy(false);
  };

  const test = async () => {
    setBusy(true); setTestResult(null);
    try { setTestResult(await api.adminLlmTest()); } catch (e) { setTestResult({ ok: false, error: e.message }); }
    setBusy(false);
  };

  const setField = (id, field, value) => {
    setProviders((list) => list.map((p) => (p.id === id ? { ...p, [field]: value } : p)));
  };

  const saveProvider = async (p) => {
    setBusy(true); setMsg("");
    try {
      const body = {
        label: p.label, base_url: p.base_url, model: p.model,
        light_model: p.light_model, fallback_model: p.fallback_model,
        priority: Number(p.priority) || 100, is_enabled: !!p.is_enabled,
      };
      if (p.api_keys_input && p.api_keys_input.trim()) {
        body.api_keys = p.api_keys_input.split(",").map((s) => s.trim()).filter(Boolean);
      }
      await api.adminLlmProviderUpdate(p.id, body);
      setMsg("✅ Provider disimpan (aktif maksimal 60 detik lagi atau langsung setelah Test).");
      await loadProviders();
    } catch (e) { setMsg("❌ " + e.message); }
    setBusy(false);
  };

  const deleteProvider = async (id) => {
    setBusy(true); setMsg("");
    try { await api.adminLlmProviderDelete(id); setMsg("✅ Provider dihapus."); await loadProviders(); }
    catch (e) { setMsg("❌ " + e.message); }
    setBusy(false);
  };

  const addProvider = async () => {
    setBusy(true); setMsg("");
    try {
      await api.adminLlmProviderCreate({
        label: newProv.label, base_url: newProv.base_url, model: newProv.model,
        light_model: newProv.light_model, fallback_model: newProv.fallback_model,
        priority: Number(newProv.priority) || 100,
        api_keys: newProv.api_keys ? newProv.api_keys.split(",").map((s) => s.trim()).filter(Boolean) : [],
      });
      setNewProv(emptyProv);
      setMsg("✅ Provider ditambahkan.");
      await loadProviders();
    } catch (e) { setMsg("❌ " + e.message); }
    setBusy(false);
  };

  if (!cfg) return <div style={{ padding: 24, color: "#94a3b8" }}>Memuat…</div>;

  return (
    <div style={{ padding: 16, maxWidth: 720 }}>
      <h2 style={{ color: "#e2e8f0" }}>🧠 LLM Control Panel</h2>
      <p style={{ color: "#94a3b8", marginTop: 4 }}>
        Atur router AI (9Router/OpenRouter/OpenAI-compatible), tumpuk API key, dan pilih model — tanpa restart server.
      </p>

      <div style={card}>
        <label style={{ display: "flex", alignItems: "center", gap: 10, fontWeight: 700 }}>
          <input type="checkbox" checked={!!cfg.is_enabled}
            onChange={(e) => setCfg({ ...cfg, is_enabled: e.target.checked })} />
          Aktifkan konfigurasi ini (mati = pakai .env: {cfg.env_fallback?.model} @ {cfg.env_fallback?.base_url})
        </label>
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 12, color: "#94a3b8" }}>Label provider</div>
          <input style={input} value={cfg.provider_label || ""}
            onChange={(e) => setCfg({ ...cfg, provider_label: e.target.value })} placeholder="9router / openrouter" />
        </div>
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 12, color: "#94a3b8" }}>Base URL (OpenAI-compatible)</div>
          <input style={input} value={cfg.base_url || ""}
            onChange={(e) => setCfg({ ...cfg, base_url: e.target.value })}
            placeholder="https://openrouter.ai/api/v1" />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10, marginTop: 12 }}>
          <div>
            <div style={{ fontSize: 12, color: "#94a3b8" }}>Model utama</div>
            <input style={input} value={cfg.model || ""}
              onChange={(e) => setCfg({ ...cfg, model: e.target.value })} placeholder="llama-3.3-70b" />
          </div>
          <div>
            <div style={{ fontSize: 12, color: "#94a3b8" }}>Model ringan (nego)</div>
            <input style={input} value={cfg.light_model || ""}
              onChange={(e) => setCfg({ ...cfg, light_model: e.target.value })} placeholder="kosong = model utama" />
          </div>
          <div>
            <div style={{ fontSize: 12, color: "#94a3b8" }}>Model cadangan</div>
            <input style={input} value={cfg.fallback_model || ""}
              onChange={(e) => setCfg({ ...cfg, fallback_model: e.target.value })} placeholder="opsional" />
          </div>
        </div>
        <div style={{ marginTop: 14, display: "flex", gap: 10 }}>
          <button style={btn("#34d399")} disabled={busy} onClick={save}>💾 Simpan</button>
          <button style={btn("#93c5fd")} disabled={busy} onClick={test}>⚡ Test Koneksi</button>
        </div>
        {testResult && (
          <div style={{ marginTop: 10, fontSize: 13, color: testResult.ok ? "#34d399" : "#f87171" }}>
            {testResult.ok
              ? `✅ OK ${testResult.latency_ms}ms · model ${testResult.model} · key #${testResult.key_index} · sumber ${testResult.source} · "${testResult.reply}"`
              : `❌ Gagal: ${testResult.error}`}
          </div>
        )}
        {msg && <div style={{ marginTop: 8, fontSize: 13, color: "#fbbf24" }}>{msg}</div>}
      </div>

      <div style={card}>
        <h3 style={{ marginTop: 0 }}>🔑 API Keys (dirotasi + failover otomatis)</h3>
        {(cfg.api_keys_masked || []).length === 0 && (
          <div style={{ color: "#94a3b8" }}>Belum ada key — sistem memakai key dari .env.</div>
        )}
        {(cfg.api_keys_masked || []).map((k, i) => (
          <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
            padding: "8px 0", borderBottom: "1px solid #1e293b" }}>
            <code style={{ color: "#a5b4fc" }}>#{i} · {k}</code>
            <button style={btn("#f87171")} disabled={busy} onClick={() => removeKey(i)}>Hapus</button>
          </div>
        ))}
        <div style={{ display: "flex", gap: 10, marginTop: 12 }}>
          <input style={{ ...input, marginTop: 0 }} value={newKey} type="password"
            onChange={(e) => setNewKey(e.target.value)} placeholder="sk-… (key baru, ditumpuk ke daftar)" />
          <button style={btn("#34d399")} disabled={busy} onClick={addKey}>➕ Tambah</button>
        </div>
        <p style={{ fontSize: 12, color: "#64748b", marginTop: 10 }}>
          Kena limit/error di key #0 → otomatis pindah ke key berikutnya, lalu model cadangan, lalu .env.
        </p>
      </div>

      <div style={card}>
        <h3 style={{ marginTop: 0 }}>🧩 Multi-Provider (prioritas + failover otomatis)</h3>
        <p style={{ fontSize: 12, color: "#94a3b8", marginTop: 0 }}>
          Kalau ada provider aktif di sini, sistem memakainya lebih dulu (urut prioritas kecil → besar);
          gagal di satu provider otomatis pindah ke berikutnya. Kosong = pakai konfigurasi di atas / .env.
        </p>
        {providers.length === 0 && (
          <div style={{ color: "#94a3b8", marginBottom: 10 }}>Belum ada provider.</div>
        )}
        {providers.map((p) => (
          <div key={p.id} style={{ border: "1px solid #1e293b", borderRadius: 10, padding: 12, marginBottom: 10 }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              <div>
                <div style={{ fontSize: 12, color: "#94a3b8" }}>Label</div>
                <input style={input} value={p.label || ""} onChange={(e) => setField(p.id, "label", e.target.value)} />
              </div>
              <div>
                <div style={{ fontSize: 12, color: "#94a3b8" }}>Prioritas (kecil = didahulukan)</div>
                <input style={input} type="number" value={p.priority ?? 100} onChange={(e) => setField(p.id, "priority", e.target.value)} />
              </div>
            </div>
            <div style={{ marginTop: 8 }}>
              <div style={{ fontSize: 12, color: "#94a3b8" }}>Base URL (OpenAI-compatible)</div>
              <input style={input} value={p.base_url || ""} onChange={(e) => setField(p.id, "base_url", e.target.value)} placeholder="https://api.groq.com/openai/v1" />
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginTop: 8 }}>
              <div>
                <div style={{ fontSize: 12, color: "#94a3b8" }}>Model</div>
                <input style={input} value={p.model || ""} onChange={(e) => setField(p.id, "model", e.target.value)} />
              </div>
              <div>
                <div style={{ fontSize: 12, color: "#94a3b8" }}>Model ringan</div>
                <input style={input} value={p.light_model || ""} onChange={(e) => setField(p.id, "light_model", e.target.value)} />
              </div>
              <div>
                <div style={{ fontSize: 12, color: "#94a3b8" }}>Model cadangan</div>
                <input style={input} value={p.fallback_model || ""} onChange={(e) => setField(p.id, "fallback_model", e.target.value)} />
              </div>
            </div>
            <div style={{ marginTop: 8 }}>
              <div style={{ fontSize: 12, color: "#94a3b8" }}>
                API Keys (pisahkan koma; kosongkan = pertahankan yang ada). Sekarang: {(p.api_keys_masked || []).join(", ") || "—"}
              </div>
              <input style={input} type="password" value={p.api_keys_input || ""} onChange={(e) => setField(p.id, "api_keys_input", e.target.value)} placeholder="sk-…, sk-…" />
            </div>
            <div style={{ marginTop: 10, display: "flex", gap: 10, alignItems: "center" }}>
              <label style={{ display: "flex", gap: 6, alignItems: "center", color: "#e2e8f0" }}>
                <input type="checkbox" checked={!!p.is_enabled} onChange={(e) => setField(p.id, "is_enabled", e.target.checked)} /> Aktif
              </label>
              <button style={btn("#34d399")} disabled={busy} onClick={() => saveProvider(p)}>💾 Simpan</button>
              <button style={btn("#f87171")} disabled={busy} onClick={() => deleteProvider(p.id)}>🗑 Hapus</button>
            </div>
          </div>
        ))}

        <div style={{ borderTop: "1px dashed #334155", paddingTop: 12, marginTop: 4 }}>
          <h4 style={{ margin: "0 0 8px" }}>➕ Tambah provider</h4>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <input style={input} value={newProv.label} onChange={(e) => setNewProv({ ...newProv, label: e.target.value })} placeholder="Label (mis. Groq)" />
            <input style={input} type="number" value={newProv.priority} onChange={(e) => setNewProv({ ...newProv, priority: e.target.value })} placeholder="Prioritas (100)" />
          </div>
          <input style={{ ...input }} value={newProv.base_url} onChange={(e) => setNewProv({ ...newProv, base_url: e.target.value })} placeholder="Base URL: https://api.groq.com/openai/v1" />
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginTop: 8 }}>
            <input style={input} value={newProv.model} onChange={(e) => setNewProv({ ...newProv, model: e.target.value })} placeholder="Model" />
            <input style={input} value={newProv.light_model} onChange={(e) => setNewProv({ ...newProv, light_model: e.target.value })} placeholder="Model ringan (opsional)" />
            <input style={input} value={newProv.fallback_model} onChange={(e) => setNewProv({ ...newProv, fallback_model: e.target.value })} placeholder="Model cadangan (opsional)" />
          </div>
          <input style={{ ...input }} value={newProv.api_keys} onChange={(e) => setNewProv({ ...newProv, api_keys: e.target.value })} placeholder="API keys, pisahkan koma" />
          <button style={{ ...btn("#34d399"), marginTop: 10 }} disabled={busy} onClick={addProvider}>➕ Tambah Provider</button>
        </div>
      </div>
    </div>
  );
}
