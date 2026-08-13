"use client";

// Segment-level boundary for every /dashboard/* route. Deeper boundaries
// (e.g. dashboard/recovery/error.js) win, which is intended.
// Never render error.message — it can carry internal detail. digest only.
export default function DashboardError({ error, reset }) {
  return (
    <div className="card" role="alert" style={{ maxWidth: 520, margin: "40px auto", textAlign: "center" }}>
      <h2 style={{ fontSize: "1.15rem" }}>Halaman ini gagal dimuat</h2>
      <p className="text-sm text-muted mt-2">
        Terjadi kesalahan saat menyiapkan halaman. Data lain tetap aman. Coba lagi, dan
        hubungi dukungan jika masalah berlanjut.
      </p>
      {error?.digest && (
        <p className="text-xs text-muted mt-2">
          Kode rujukan: <code>{error.digest}</code>
        </p>
      )}
      <button type="button" className="btn btn-primary mt-2" onClick={() => reset()}>
        Coba lagi
      </button>
    </div>
  );
}
