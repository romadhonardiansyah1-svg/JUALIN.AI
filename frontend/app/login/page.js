"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import styles from "./auth.module.css";

export default function LoginPage() {
  const router = useRouter();
  const [form, setForm] = useState({ email: "", password: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const data = await api.login(form);
      localStorage.setItem("jualin_token", data.access_token);
      localStorage.setItem("jualin_user", JSON.stringify(data.user));
      router.push("/dashboard");
    } catch (err) {
      setError(err.message || "Login gagal. Periksa email dan password Anda.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.authPage}>
      <div className={styles.authCard}>
        <div className={styles.authHeader}>
          <Link href="/" className={styles.logo}>
            <span>🤖</span>
            <span className={styles.logoText}>JUALIN.AI</span>
          </Link>
          <h1>Masuk ke Dashboard</h1>
          <p className="text-muted">Kelola toko dan pantau performa AI kamu</p>
        </div>

        <form onSubmit={handleSubmit} className={styles.authForm}>
          {error && <div className={styles.errorMsg}>⚠️ {error}</div>}

          <div className={styles.field}>
            <label className="label">Email</label>
            <input
              type="email"
              className="input"
              placeholder="email@tokoku.com"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              required
              autoFocus
            />
          </div>

          <div className={styles.field}>
            <label className="label">Password</label>
            <div className={styles.fieldWithToggle}>
              <input
                type={showPassword ? "text" : "password"}
                className="input"
                placeholder="Masukkan password"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                required
                style={{ paddingRight: 44 }}
              />
              <button
                type="button"
                className={styles.passwordToggle}
                onClick={() => setShowPassword(!showPassword)}
                tabIndex={-1}
              >
                {showPassword ? "🙈" : "👁️"}
              </button>
            </div>
          </div>

          <button type="submit" className="btn btn-primary btn-lg" style={{ width: "100%" }} disabled={loading}>
            {loading ? "Memproses..." : "Masuk →"}
          </button>
        </form>

        <p className={styles.authFooter}>
          Belum punya akun? <Link href="/register">Daftar Gratis</Link>
        </p>
      </div>
    </div>
  );
}
