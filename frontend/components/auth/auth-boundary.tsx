"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { usePathname, useRouter } from "next/navigation";

import {
  login as performLogin,
  logoutClient,
  restoreSession,
  type AuthRole,
  type AuthSession,
} from "@/lib/auth";

type AuthStatus = "loading" | "unauthenticated" | "authenticated";

type AuthContextValue = {
  status: AuthStatus;
  role: AuthRole | null;
  login: (apiKey: string) => Promise<AuthSession>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue>({
  status: "loading",
  role: null,
  login: async () => {
    throw new Error("AuthProvider not mounted");
  },
  logout: async () => {},
  refresh: async () => {},
});

/** Access the authentication context (status, role, login, logout). */
export function useAuth(): AuthContextValue {
  return useContext(AuthContext);
}

/**
 * Client-side authentication boundary mounted once at the app root.
 *
 * On mount it restores and validates any stored session against the backend
 * (`GET /auth/session`). While loading it renders a minimal splash so the UI
 * never flashes unauthenticated content. Unauthenticated visitors on any page
 * other than /login are redirected there; authenticated visitors on /login are
 * sent to the console. `login`/`logout` update this shared state so every page
 * and the header stay consistent.
 */
export function AuthBoundary({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [role, setRole] = useState<AuthRole | null>(null);

  const refresh = useCallback(async () => {
    const session = await restoreSession();
    if (session) {
      setRole(session.role);
      setStatus("authenticated");
    } else {
      setRole(null);
      setStatus("unauthenticated");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(
    async (apiKey: string): Promise<AuthSession> => {
      const session = await performLogin(apiKey);
      setRole(session.role);
      setStatus("authenticated");
      return session;
    },
    [],
  );

  const logout = useCallback(async () => {
    await logoutClient();
    setRole(null);
    setStatus("unauthenticated");
  }, []);

  const onLoginPage = pathname === "/login";

  useEffect(() => {
    if (onLoginPage) {
      return;
    }
    if (status === "unauthenticated") {
      router.replace("/login");
    }
  }, [status, onLoginPage, router]);

  useEffect(() => {
    if (onLoginPage && status === "authenticated") {
      router.replace("/");
    }
  }, [status, onLoginPage, router]);

  const value = useMemo(
    () => ({ status, role, login, logout, refresh }),
    [status, role, login, logout, refresh],
  );

  // The login page manages its own state; the splash only guards real pages.
  if (onLoginPage) {
    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
  }
  if (status !== "authenticated") {
    return (
      <AuthContext.Provider value={value}>
        <div className="flex min-h-screen items-center justify-center bg-background">
          <div className="flex flex-col items-center gap-3 text-muted-foreground">
            <div className="size-6 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-muted-foreground" />
            <p className="text-sm">Checking session…</p>
          </div>
        </div>
      </AuthContext.Provider>
    );
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}