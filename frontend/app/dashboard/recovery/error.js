"use client";
export default function Error({ error, reset }) {
  return (
    <div style={{ padding: 20 }}>
      <h3>Bagian ini belum dapat dimuat. Data lain tetap aman.</h3>
      <p style={{ fontSize: "0.9rem", color: "#6b7280" }}>{error?.message || "Terjadi kesalahan"}</p>
      <button onClick={() => reset()} style={{ marginTop: 12, padding: "8px 16px", background: "#22c55e", color: "white", border: "none", borderRadius: 8, cursor: "pointer" }}>Coba lagi</button>
    </div>
  );
}
