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
  setupAdmin as performSetup,
  setupStatus,
  type AuthRole,
  type AuthSession,
} from "@/lib/auth";

type AuthStatus = "loading" | "unauthenticated" | "authenticated";
type SetupStatus = "loading" | "required" | "complete";

type AuthContextValue = {
  status: AuthStatus;
  role: AuthRole | null;
  setupStatus: SetupStatus;
  login: (username: string, password: string) => Promise<AuthSession>;
  setupAdmin: (
    username: string,
    password: string,
    confirmPassword: string,
  ) => Promise<AuthSession>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue>({
  status: "loading",
  role: null,
  setupStatus: "loading",
  login: async () => {
    throw new Error("AuthProvider not mounted");
  },
  setupAdmin: async () => {
    throw new Error("AuthProvider not mounted");
  },
  logout: async () => {},
  refresh: async () => {},
});

/** Access the authentication context (status, role, setup, login, logout). */
export function useAuth(): AuthContextValue {
  return useContext(AuthContext);
}

/**
 * Client-side authentication boundary mounted once at the app root.
 *
 * On mount it restores/validates any stored session and probes whether
 * first-run administrator setup is still required. While loading it renders a
 * minimal splash so the UI never flashes unauthenticated content.
 *
 * Routing:
 * - setup required and no account yet → every route redirects to /setup.
 * - setup complete → unauthenticated visitors go to /login; the /setup page
 *   redirects there too (the one-time wizard is gone for good).
 * - authenticated visitors on /setup or /login are sent to the console.
 */
export function AuthBoundary({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [role, setRole] = useState<AuthRole | null>(null);
  const [setup, setSetup] = useState<SetupStatus>("loading");

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

  const loadSetupStatus = useCallback(async () => {
    try {
      const required = await setupStatus();
      setSetup(required ? "required" : "complete");
    } catch {
      // Backend unreachable — default to "complete" so a transient outage never
      // locks the user out of the login page once accounts exist.
      setSetup("complete");
    }
  }, []);

  useEffect(() => {
    void refresh();
    void loadSetupStatus();
  }, [refresh, loadSetupStatus]);

  const login = useCallback(
    async (username: string, password: string): Promise<AuthSession> => {
      const session = await performLogin(username, password);
      setRole(session.role);
      setStatus("authenticated");
      return session;
    },
    [],
  );

  const setupAdmin = useCallback(
    async (
      username: string,
      password: string,
      confirmPassword: string,
    ): Promise<AuthSession> => {
      const session = await performSetup(username, password, confirmPassword);
      setSetup("complete");
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

  const onAuthPage = pathname === "/login" || pathname === "/setup";

  useEffect(() => {
    if (status === "loading" || setup === "loading") {
      return;
    }
    if (status === "authenticated") {
      if (onAuthPage) {
        router.replace("/");
      }
      return;
    }
    if (setup === "required") {
      if (pathname !== "/setup") {
        router.replace("/setup");
      }
      return;
    }
    // Setup complete: /setup is permanently gone; everything else needs login.
    if (pathname === "/setup") {
      router.replace("/login");
    } else if (pathname !== "/login") {
      router.replace("/login");
    }
  }, [status, setup, onAuthPage, pathname, router]);

  const value = useMemo(
    () => ({ status, role, setupStatus: setup, login, setupAdmin, logout, refresh }),
    [status, role, setup, login, setupAdmin, logout, refresh],
  );

  // The auth pages (login/setup) manage their own state; the splash only
  // guards real pages while the session/setup state is still resolving.
  if (onAuthPage) {
    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
  }
  if (status !== "authenticated" || setup === "loading") {
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