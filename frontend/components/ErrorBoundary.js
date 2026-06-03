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
    console.error("ErrorBoundary caught:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          display: "flex", flexDirection: "column", alignItems: "center",
          justifyContent: "center", minHeight: "300px", padding: "40px",
          textAlign: "center", gap: "16px",
        }}>
          <span style={{ fontSize: "3rem" }}>⚠️</span>
          <h3 style={{ fontSize: "1.2rem", color: "#334155" }}>
            Terjadi Kesalahan
          </h3>
          <p style={{ color: "#64748B", maxWidth: "400px" }}>
            {this.state.error?.message || "Halaman ini mengalami error. Coba muat ulang."}
          </p>
          <button
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
