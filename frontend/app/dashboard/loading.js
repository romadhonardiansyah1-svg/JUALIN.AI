// Segment-level fallback for all /dashboard/* routes.
// Reuses the global .skeleton utilities from app/globals.css.
export default function Loading() {
  return (
    <div role="status" aria-busy="true" aria-label="Memuat halaman dasbor">
      <div className="skeleton skeleton-title" aria-hidden="true"></div>
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 16 }} aria-hidden="true">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="card">
            <div className="skeleton skeleton-text" style={{ width: "60%" }}></div>
            <div className="skeleton skeleton-title" style={{ width: "40%" }}></div>
          </div>
        ))}
      </div>
      <div className="card mt-2" aria-hidden="true">
        <div className="skeleton skeleton-text" style={{ width: "90%" }}></div>
        <div className="skeleton skeleton-text" style={{ width: "75%" }}></div>
        <div className="skeleton skeleton-text" style={{ width: "80%" }}></div>
      </div>
    </div>
  );
}
