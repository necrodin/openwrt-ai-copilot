/**
 * Application authentication for the OpenWrt AI Copilot frontend.
 *
 * The backend enforces bearer-token authentication on every /api/v1 route
 * (except /health, /ready, and /auth/login). Operator API keys
 * (AUTH_ADMIN_API_KEY / AUTH_READONLY_API_KEY) are operator credentials that
 * must NEVER be embedded in the client bundle. Instead the operator signs in
 * through the /login page, the backend exchanges the key for a short-lived,
 * server-side session token (POST /auth/login), and the browser sends only
 * that session token on every REST request and WebSocket upgrade. Logout
 * revokes the session server-side so the token is worthless immediately.
 *
 * The session token is stored in localStorage for reload resilience and sent
 * via `Authorization: Bearer <session>`. WebSockets cannot set request headers
 * in browsers, so the dashboard socket carries the same session token as a
 * query parameter. Neither the token here nor any NEXT_PUBLIC_* variable is a
 * backend master secret.
 */

import { API_BASE_URL } from "@/lib/api";

export type AuthRole = "admin" | "readonly";

export type AuthSession = {
  token: string;
  role: AuthRole;
  expires_at: string | null;
};

export type AuthHeaders = Record<string, string>;

const TOKEN_KEY = "openwrt-ai.session.token";
const ROLE_KEY = "openwrt-ai.session.role";
const EXPIRES_KEY = "openwrt-ai.session.expires_at";

function readStorage(): Record<string, string | null> {
  if (typeof window === "undefined" || typeof localStorage === "undefined") {
    return { token: null, role: null, expires_at: null };
  }
  try {
    return {
      token: localStorage.getItem(TOKEN_KEY),
      role: localStorage.getItem(ROLE_KEY),
      expires_at: localStorage.getItem(EXPIRES_KEY),
    };
  } catch {
    return { token: null, role: null, expires_at: null };
  }
}

function writeStorage(session: AuthSession): void {
  if (typeof window === "undefined" || typeof localStorage === "undefined") {
    return;
  }
  try {
    localStorage.setItem(TOKEN_KEY, session.token);
    localStorage.setItem(ROLE_KEY, session.role);
    if (session.expires_at) {
      localStorage.setItem(EXPIRES_KEY, session.expires_at);
    } else {
      localStorage.removeItem(EXPIRES_KEY);
    }
  } catch {
    // Storage unavailable (private mode) — the session simply does not survive
    // a page reload; requests in the current tab still carry the token.
  }
}

function clearStorage(): void {
  if (typeof window === "undefined" || typeof localStorage === "undefined") {
    return;
  }
  try {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(ROLE_KEY);
    localStorage.removeItem(EXPIRES_KEY);
  } catch {
    // ignore
  }
}

/** Currently stored session (no server-side validation). */
export function getStoredSession(): AuthSession | null {
  const { token, role, expires_at } = readStorage();
  if (!token || !role) {
    return null;
  }
  return { token, role: role as AuthRole, expires_at };
}

function storeSession(session: AuthSession): void {
  writeStorage(session);
}

function clearSession(): void {
  clearStorage();
}

/** Plain session token, or null when not signed in. */
export function sessionToken(): string | null {
  return getStoredSession()?.token ?? null;
}

function isExpired(session: AuthSession): boolean {
  if (!session.expires_at) {
    return false;
  }
  const at = Date.parse(session.expires_at);
  return Number.isNaN(at) || at <= Date.now();
}

/**
 * Returns a Headers object with the session bearer token attached when one is
 * present. Existing headers are preserved and overridden only by the
 * Authorization value.
 */
export function authHeaders(init?: HeadersInit): Headers {
  const headers = new Headers(init);
  const token = sessionToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return headers;
}

/**
 * Query-string fragment carrying the session token for the WebSocket upgrade.
 * Returns an empty string when no session exists so the URL shape is stable.
 */
export function wsAuthQuery(): string {
  const token = sessionToken();
  if (!token) {
    return "";
  }
  return `token=${encodeURIComponent(token)}`;
}

/**
 * Exchange an operator API key for a short-lived browser session token. The
 * master key is sent to the backend exactly once and is never stored.
 */
export async function login(apiKey: string): Promise<AuthSession> {
  const res = await fetch(`${API_BASE_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_key: apiKey }),
  });
  if (!res.ok) {
    let detail = "Sign-in failed";
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) {
        detail = body.detail;
      }
    } catch {
      // keep the generic message
    }
    throw new Error(detail);
  }
  const data = (await res.json()) as {
    token: string;
    role: AuthRole;
    expires_at: string;
  };
  const session: AuthSession = {
    token: data.token,
    role: data.role,
    expires_at: data.expires_at,
  };
  storeSession(session);
  return session;
}

/**
 * Revoke the current session server-side and clear local state. Called from
 * the logout button so a leaked or abandoned token is immediately worthless.
 */
export async function logoutClient(): Promise<void> {
  const token = sessionToken();
  if (token) {
    try {
      await fetch(`${API_BASE_URL}/auth/logout`, {
        method: "POST",
        headers: authHeaders(),
      });
    } catch {
      // Backend unreachable — the local token is cleared regardless.
    }
  }
  clearSession();
}

/**
 * Restore and validate a stored session. Returns the session when it is still
 * accepted by the backend, or null (after clearing) when rejected or expired.
 * On network failure a non-expired stored session is kept so transient backend
 * restarts do not bounce the user to the login page.
 */
export async function restoreSession(): Promise<AuthSession | null> {
  const stored = getStoredSession();
  if (!stored) {
    return null;
  }
  if (isExpired(stored)) {
    clearSession();
    return null;
  }
  try {
    const res = await fetch(`${API_BASE_URL}/auth/session`, {
      headers: authHeaders(),
    });
    if (!res.ok) {
      clearSession();
      return null;
    }
    const data = (await res.json()) as {
      role: AuthRole;
      expires_at: string | null;
    };
    const session: AuthSession = {
      token: stored.token,
      role: data.role ?? stored.role,
      expires_at: data.expires_at ?? stored.expires_at,
    };
    storeSession(session);
    return session;
  } catch {
    return stored;
  }
}