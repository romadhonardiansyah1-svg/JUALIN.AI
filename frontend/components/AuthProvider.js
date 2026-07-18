"use client";
import { createContext, useContext, useEffect, useState, useCallback, useRef } from "react";
import { api, clearAuthStateAndCache, ApiError } from "@/lib/api";

const AuthContext = createContext(null);

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

export default function AuthProvider({ children }) {
  const [state, setState] = useState("checking"); // checking | authenticated | unauthenticated | recoverable_error | refreshing
  const [user, setUser] = useState(null);
  const [error, setError] = useState(null);
  const refreshingRef = useRef(false);

  const clearAndLogout = useCallback((broadcast = true) => {
    try {
      clearAuthStateAndCache();
    } catch {}
    setUser(null);
    setState("unauthenticated");
    if (!broadcast) return;

    try {
      const bc = new BroadcastChannel("jualin-auth");
      bc.postMessage({ type: "logout", epoch: Date.now() });
      bc.close();
    } catch {}
    if (typeof window !== "undefined") {
      try {
        localStorage.setItem("jualin_logout", Date.now().toString());
      } catch {}
    }
  }, []);

  const fetchMe = useCallback(async (isRefresh = false) => {
    if (!isRefresh) setState((prev) => (prev === "authenticated" ? "refreshing" : "checking"));
    try {
      const freshUser = await api.getMe();
      if (freshUser && freshUser.email) {
        // Clean legacy localStorage keys after cookie established
        try {
          localStorage.removeItem("jualin_token");
          localStorage.removeItem("jualin_user");
        } catch {}
        setUser(freshUser);
        setState("authenticated");
        setError(null);
        return freshUser;
      } else {
        throw new Error("Invalid user");
      }
    } catch (e) {
      if (e instanceof ApiError) {
        if (e.status === 401) {
          // Terminal 401 -> unauthenticated
          if (!isRefresh) {
            clearAndLogout();
          }
          return null;
        }
        if (e.status === 0 || e.status >= 500) {
          // Network or 503 -> recoverable
          setState("recoverable_error");
          setError(e.message);
          return null;
        }
      }
      // For other errors, treat as recoverable if checking, else unauthenticated?
      if (e.message && e.message.includes("Session changed")) {
        clearAndLogout();
        return null;
      }
      setState("recoverable_error");
      setError(e.message);
      return null;
    }
  }, [clearAndLogout]);

  // Single-flight refresh
  const refreshOnce = useCallback(async () => {
    if (refreshingRef.current) return;
    refreshingRef.current = true;
    try {
      await api.refreshAuth();
      await fetchMe(true);
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 409)) {
        clearAndLogout();
      }
    } finally {
      refreshingRef.current = false;
    }
  }, [fetchMe, clearAndLogout]);

  // Initial check
  useEffect(() => {
    fetchMe(false);

    // Listen for storage events (logout from other tabs)
    const onStorage = (e) => {
      if (e.key === "jualin_logout") {
        clearAndLogout(false);
      }
    };
    window.addEventListener("storage", onStorage);

    // BroadcastChannel for logout
    let bc;
    try {
      bc = new BroadcastChannel("jualin-auth");
      bc.onmessage = (ev) => {
        if (ev.data?.type === "logout") {
          clearAndLogout(false);
        }
      };
    } catch {}

    return () => {
      window.removeEventListener("storage", onStorage);
      try {
        bc?.close();
      } catch {}
    };
  }, [fetchMe, clearAndLogout]);

  const login = useCallback(async (credentials) => {
    try {
      clearAuthStateAndCache();
      const data = await api.login(credentials);
      // Server sets HttpOnly cookies, we don't store token in localStorage
      // Clean legacy keys
      try {
        localStorage.removeItem("jualin_token");
        localStorage.removeItem("jualin_user");
      } catch {}
      await fetchMe(true);
      return data;
    } catch (e) {
      throw e;
    }
  }, [fetchMe]);

  const logout = useCallback(async () => {
    await api.logout();
    clearAndLogout();
    if (typeof window !== "undefined") window.location.href = "/login";
  }, [clearAndLogout]);

  const updateUser = useCallback((nextUser) => {
    if (!nextUser) return;
    setUser(nextUser);
    setState("authenticated");
    setError(null);
  }, []);

  const value = {
    state,
    user,
    error,
    updateUser,
    isAuthenticated: state === "authenticated" && !!user,
    isChecking: state === "checking" || state === "refreshing",
    login,
    logout,
    refresh: refreshOnce,
    fetchMe,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
