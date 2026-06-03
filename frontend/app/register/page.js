"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import styles from "../login/auth.module.css";

export default function RegisterPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [form, setForm] = useState({
    email: searchParams.get("email") || "",
    password: "",
    nama_toko: "",
    no_hp: "",
  });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const data = await api.register(form);
      localStorage.setItem("jualin_token", data.access_token);
      localStorage.setItem("jualin_user", JSON.stringify(data.user));
      router.push("/dashboard");
    } catch (err) {
      setError(err.message || "Registrasi gagal");
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
          <h1>Daftar Gratis</h1>
          <p className="text-muted">Buat toko dan aktifkan AI Sales Assistant dalam 2 menit</p>
        </div>

        <form onSubmit={handleSubmit} className={styles.authForm}>
          {error && <div className={styles.errorMsg}>{error}</div>}

          <div className={styles.field}>
            <label className="label">Nama Toko</label>
            <input
              type="text"
              className="input"
              placeholder="Contoh: Toko Sari Fashion"
              value={form.nama_toko}
              onChange={(e) => setForm({ ...form, nama_toko: e.target.value })}
              required
            />
          </div>

          <div className={styles.field}>
            <label className="label">Email</label>
            <input
              type="email"
              className="input"
              placeholder="email@tokoku.com"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              required
            />
          </div>

          <div className={styles.field}>
            <label className="label">No. HP (opsional)</label>
            <input
              type="tel"
              className="input"
              placeholder="0812-xxxx-xxxx"
              value={form.no_hp}
              onChange={(e) => setForm({ ...form, no_hp: e.target.value })}
            />
          </div>

          <div className={styles.field}>
            <label className="label">Password</label>
            <input
              type="password"
              className="input"
              placeholder="Minimal 6 karakter"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              required
              minLength={6}
            />
          </div>

          <button type="submit" className="btn btn-primary btn-lg" style={{ width: "100%" }} disabled={loading}>
            {loading ? "Mendaftar..." : "Daftar & Mulai Gratis →"}
          </button>
        </form>

        <p className={styles.authFooter}>
          Sudah punya akun? <Link href="/login">Masuk</Link>
        </p>
      </div>
    </div>
  );
}
