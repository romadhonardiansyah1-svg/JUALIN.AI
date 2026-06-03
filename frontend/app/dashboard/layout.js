"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import styles from "./dashboard.module.css";

const navItems = [
  { href: "/dashboard", icon: "📊", label: "Overview" },
  { href: "/dashboard/products", icon: "📦", label: "Produk" },
  { href: "/dashboard/orders", icon: "🛒", label: "Order" },
  { href: "/dashboard/chat", icon: "💬", label: "Chat" },
  { href: "/dashboard/analytics", icon: "📈", label: "Analitik" },
  { href: "/dashboard/settings", icon: "⚙️", label: "Settings" },
];

export default function DashboardLayout({ children }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState(null);

  useEffect(() => {
    const token = localStorage.getItem("jualin_token");
    const userData = localStorage.getItem("jualin_user");
    if (!token) {
      router.push("/login");
      return;
    }
    if (userData) {
      setUser(JSON.parse(userData));
    }
  }, [router]);

  const handleLogout = () => {
    localStorage.removeItem("jualin_token");
    localStorage.removeItem("jualin_user");
    router.push("/login");
  };

  if (!user) return null;

  return (
    <div className={styles.dashboardLayout}>
      {/* Sidebar */}
      <aside className={styles.sidebar}>
        <div className={styles.sidebarHeader}>
          <Link href="/" className={styles.logo}>
            <span className={styles.logoIcon}>🤖</span>
            <span className={styles.logoText}>JUALIN.AI</span>
          </Link>
        </div>

        <nav className={styles.sidebarNav}>
          {navItems.map((item) => {
            const isActive =
              item.href === "/dashboard"
                ? pathname === "/dashboard"
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`${styles.navItem} ${isActive ? styles.navItemActive : ""}`}
              >
                <span className={styles.navIcon}>{item.icon}</span>
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className={styles.sidebarFooter}>
          <div className={styles.userInfo}>
            <div className={styles.userAvatar}>
              {user.nama_toko?.charAt(0) || "T"}
            </div>
            <div className={styles.userDetails}>
              <span className={styles.userName}>{user.nama_toko}</span>
              <span className={`badge badge-primary ${styles.userTier}`}>
                {user.tier}
              </span>
            </div>
          </div>
          <button onClick={handleLogout} className={styles.logoutBtn} title="Logout">
            🚪
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className={styles.mainContent}>
        <header className={styles.topBar}>
          <div className={styles.topBarLeft}>
            <h2 className={styles.pageTitle}>
              {navItems.find((i) =>
                i.href === "/dashboard"
                  ? pathname === "/dashboard"
                  : pathname.startsWith(i.href)
              )?.label || "Dashboard"}
            </h2>
          </div>
          <div className={styles.topBarRight}>
            <button className={styles.notifBtn}>
              🔔 <span className={styles.notifBadge}>3</span>
            </button>
            <div className={styles.topAvatar}>
              {user.nama_toko?.charAt(0) || "T"}
            </div>
          </div>
        </header>
        <div className={styles.content}>{children}</div>
      </main>
    </div>
  );
}
