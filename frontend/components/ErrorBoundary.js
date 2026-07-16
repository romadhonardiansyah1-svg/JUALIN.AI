"use client";
import { Component } from "react";

/**
 * Error Boundary component — catches JS errors in child components
 * and displays a fallback UI instead of crashing the whole app.
 * (BUG 14 FIX)
 */
export class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    // P5.5 — never log full stacks with potential PII in production UI path.
    const safe = {
      name: error?.name || "Error",
      message: String(error?.message || "unknown").slice(0, 200),
      componentStack: String(errorInfo?.componentStack || "").slice(0, 300),
    };
    if (process.env.NODE_ENV !== "production") {
      console.error("ErrorBoundary caught:", safe);
    } else {
      console.error("ErrorBoundary caught:", safe.name, safe.message);
    }
  }

  render() {
    if (this.state.hasError) {
      const isProd = process.env.NODE_ENV === "production";
      return (
        <div style={{
          display: "flex", flexDirection: "column", alignItems: "center",
          justifyContent: "center", minHeight: "300px", padding: "40px",
          textAlign: "center", gap: "16px",
        }}>
          <span style={{ fontSize: "3rem" }} aria-hidden>⚠️</span>
          <h3 style={{ fontSize: "1.2rem", color: "#334155" }}>
            Terjadi Kesalahan
          </h3>
          <p style={{ color: "#64748B", maxWidth: "400px" }}>
            {isProd
              ? "Halaman ini mengalami error. Coba muat ulang. Jika berlanjut, hubungi dukungan dengan waktu kejadian."
              : (this.state.error?.message || "Halaman ini mengalami error. Coba muat ulang.")}
          </p>
          <button
            type="button"
            onClick={() => { this.setState({ hasError: false, error: null }); window.location.reload(); }}
            style={{
              padding: "10px 24px", background: "#6366F1", color: "white",
              border: "none", borderRadius: "8px", cursor: "pointer",
              fontSize: "0.95rem", fontWeight: 600,
            }}
          >
            🔄 Muat Ulang
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
