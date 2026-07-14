"use client";
import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import styles from "./dashboard.module.css";

// Seller navigation
const sellerNavItems = [
  { href: "/dashboard", icon: "📊", label: "Overview" },
  { href: "/dashboard/agent-os", icon: "🤖", label: "AI Crew" },
  { href: "/dashboard/products", icon: "📦", label: "Produk" },
  { href: "/dashboard/orders", icon: "🛒", label: "Order" },
  { href: "/dashboard/recovery", icon: "💰", label: "Jualin Santai" },
  { href: "/dashboard/inbox", icon: "IN", label: "Inbox" },
  { href: "/dashboard/customers", icon: "C", label: "Customers" },
  { href: "/dashboard/chat", icon: "💬", label: "Chat" },
  { href: "/dashboard/campaigns", icon: "M", label: "Campaigns" },
  { href: "/dashboard/workflows", icon: "W", label: "Workflows" },
  { href: "/dashboard/ai-quality", icon: "Q", label: "AI Quality" },
  { href: "/dashboard/integrations", icon: "P", label: "Integrations" },
  { href: "/dashboard/import", icon: "X", label: "Import" },
  { href: "/dashboard/billing", icon: "$", label: "Billing" },
  { href: "/dashboard/analytics", icon: "📈", label: "Analitik" },
  { href: "/dashboard/templates", icon: "📚", label: "Templates" },
  { href: "/dashboard/storefront", icon: "🏪", label: "Storefront" },
  { href: "/dashboard/onboarding", icon: "🎯", label: "Setup" },
  { href: "/dashboard/referrals", icon: "🔗", label: "Referral" },
  { href: "/dashboard/trust", icon: "🛡️", label: "Trust" },
  { href: "/dashboard/growth-links", icon: "📈", label: "Growth Links" },
  { href: "/dashboard/whatsapp-templates", icon: "📱", label: "WA Templates" },
  { href: "/dashboard/leads", icon: "📋", label: "Leads" },
  { href: "/dashboard/ai-playbooks", icon: "🎭", label: "Playbooks" },
  { href: "/dashboard/offers", icon: "🎁", label: "Offers" },
  { href: "/dashboard/knowledge", icon: "🧠", label: "Knowledge" },
  { href: "/dashboard/qa-review", icon: "🔍", label: "QA Review" },
  { href: "/dashboard/experiments", icon: "🧪", label: "Experiments" },
  { href: "/dashboard/settings", icon: "⚙️", label: "Settings" },
];

// Admin navigation
const adminNavItems = [
  { href: "/dashboard/admin", icon: "🏠", label: "Dashboard" },
  { href: "/dashboard/admin/sellers", icon: "👥", label: "Kelola Seller" },
  { href: "/dashboard/admin/system", icon: "🖥️", label: "System" },
  { href: "/dashboard", icon: "🏪", label: "Toko Saya", divider: true },
  { href: "/dashboard/agent-os", icon: "🤖", label: "AI Crew" },
  { href: "/dashboard/products", icon: "📦", label: "Produk" },
  { href: "/dashboard/orders", icon: "🛒", label: "Order" },
  { href: "/dashboard/inbox", icon: "IN", label: "Inbox" },
  { href: "/dashboard/customers", icon: "C", label: "Customers" },
  { href: "/dashboard/chat", icon: "💬", label: "Chat AI" },
  { href: "/dashboard/campaigns", icon: "M", label: "Campaigns" },
  { href: "/dashboard/workflows", icon: "W", label: "Workflows" },
  { href: "/dashboard/ai-quality", icon: "Q", label: "AI Quality" },
  { href: "/dashboard/integrations", icon: "P", label: "Integrations" },
  { href: "/dashboard/import", icon: "X", label: "Import" },
  { href: "/dashboard/billing", icon: "$", label: "Billing" },
  { href: "/dashboard/analytics", icon: "📈", label: "Analitik" },
  { href: "/dashboard/templates", icon: "📚", label: "Templates" },
  { href: "/dashboard/storefront", icon: "🏪", label: "Storefront" },
  { href: "/dashboard/onboarding", icon: "🎯", label: "Setup" },
  { href: "/dashboard/referrals", icon: "🔗", label: "Referral" },
  { href: "/dashboard/trust", icon: "🛡️", label: "Trust" },
  { href: "/dashboard/growth-links", icon: "📈", label: "Growth Links" },
  { href: "/dashboard/whatsapp-templates", icon: "📱", label: "WA Templates" },
  { href: "/dashboard/leads", icon: "📋", label: "Leads" },
  { href: "/dashboard/ai-playbooks", icon: "🎭", label: "Playbooks" },
  { href: "/dashboard/offers", icon: "🎁", label: "Offers" },
  { href: "/dashboard/knowledge", icon: "🧠", label: "Knowledge" },
  { href: "/dashboard/qa-review", icon: "🔍", label: "QA Review" },
  { href: "/dashboard/experiments", icon: "🧪", label: "Experiments" },
  { href: "/dashboard/settings", icon: "⚙️", label: "Settings" },
];

export default function DashboardLayout({ children }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("jualin_token");
    const userData = localStorage.getItem("jualin_user");
    if (!token) {
      router.push("/login");
      return;
    }
    if (userData) {
      try {
        setUser(JSON.parse(userData));
      } catch (e) {
        localStorage.removeItem("jualin_user");
        router.push("/login");
        return;
      }
    }
    
    // Refresh user data from API in background
    import("@/lib/api").then(({ api }) => {
      api.getMe().then(freshUser => {
        if (freshUser && freshUser.email) {
          localStorage.setItem("jualin_user", JSON.stringify(freshUser));
          setUser(freshUser);
        }
      }).catch(() => { /* ignore */ });
    });
  }, [router]);

  // Close sidebar on navigation (mobile)
  useEffect(() => {
    setSidebarOpen(false);
  }, [pathname]);

  const isAdmin = user?.role === "admin";
  const navItems = useMemo(
    () => (isAdmin ? adminNavItems : sellerNavItems),
    [isAdmin]
  );

  const pageTitle = useMemo(() => {
    const flat = isAdmin ? adminNavItems : sellerNavItems;
    const match = flat.find((i) =>
      i.href === "/dashboard"
        ? pathname === "/dashboard"
        : pathname.startsWith(i.href)
    );
    return match?.label || "Dashboard";
  }, [pathname, isAdmin]);

  const handleLogout = () => {
    // P0.3b: clear tenant-isolated cache and epoch on logout
    import("@/lib/api").then(({ clearAuthStateAndCache }) => {
      try {
        clearAuthStateAndCache();
      } catch {}
      router.push("/login");
    }).catch(() => {
      try {
        localStorage.removeItem("jualin_token");
        localStorage.removeItem("jualin_user");
      } catch {}
      router.push("/login");
    });
  };

  if (!user) return null;

  return (
    <div className={styles.dashboardLayout}>
      {/* Mobile Overlay */}
      {sidebarOpen && (
        <div className={styles.overlay} onClick={() => setSidebarOpen(false)} />
      )}

      {/* Sidebar */}
      <aside className={`${styles.sidebar} ${isAdmin ? styles.sidebarAdmin : ""} ${sidebarOpen ? styles.sidebarOpen : ""}`}>
        <div className={styles.sidebarHeader}>
          <Link href="/" className={styles.logo}>
            <span className={styles.logoIcon}>🤖</span>
            <span className={styles.logoText}>JUALIN.AI</span>
          </Link>
          {isAdmin && (
            <span className={styles.adminBadge}>ADMIN</span>
          )}
        </div>

        <nav className={styles.sidebarNav}>
          {navItems.map((item, idx) => {
            const isActive =
              item.href === "/dashboard"
                ? pathname === "/dashboard"
                : pathname.startsWith(item.href);
            return (
              <div key={`${item.href}-${idx}`}>
                {item.divider && (
                  <div className={styles.navDivider}>
                    <span>Toko Saya</span>
                  </div>
                )}
                <Link
                  href={item.href}
                  className={`${styles.navItem} ${isActive ? styles.navItemActive : ""}`}
                >
                  <span className={styles.navIcon}>{item.icon}</span>
                  <span>{item.label}</span>
                  {isActive && <span className={styles.activeIndicator}></span>}
                </Link>
              </div>
            );
          })}
        </nav>

        <div className={styles.sidebarFooter}>
          <div className={styles.userInfo}>
            <div className={`${styles.userAvatar} ${isAdmin ? styles.userAvatarAdmin : ""}`}>
              {user.nama_toko?.charAt(0) || "T"}
            </div>
            <div className={styles.userDetails}>
              <span className={styles.userName}>{user.nama_toko}</span>
              <span className={`badge ${isAdmin ? "badge-danger" : "badge-primary"} ${styles.userTier}`}>
                {isAdmin ? "ADMIN" : user.tier?.toUpperCase()}
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
            <button className={styles.hamburger} onClick={() => setSidebarOpen(!sidebarOpen)}>
              <span></span><span></span><span></span>
            </button>
            <h2 className={styles.pageTitle}>{pageTitle}</h2>
          </div>
          <div className={styles.topBarRight}>
            <button className={styles.notifBtn}>
              🔔 <span className={styles.notifBadge}>3</span>
            </button>
            <div className={`${styles.topAvatar} ${isAdmin ? styles.topAvatarAdmin : ""}`}>
              {user.nama_toko?.charAt(0) || "T"}
            </div>
          </div>
        </header>
        {user.impersonation && (
          <div className={styles.impersonationBanner}>
            Mode impersonasi aktif. Semua perubahan dicatat atas admin #{user.impersonated_by || "-"}.
          </div>
        )}
        <div className={styles.content}><ErrorBoundary>{children}</ErrorBoundary></div>
      </main>
    </div>
  );
}
