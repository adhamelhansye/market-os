"use client";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const STORAGE_KEYS = {
  accessToken: "mos.accessToken",
  activeOrg: "mos.activeOrg",
};

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function getAccessToken(): string | null {
  return typeof window === "undefined" ? null : window.localStorage.getItem(STORAGE_KEYS.accessToken);
}

export function setAccessToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token === null) window.localStorage.removeItem(STORAGE_KEYS.accessToken);
  else window.localStorage.setItem(STORAGE_KEYS.accessToken, token);
}

export function getActiveOrganizationId(): string | null {
  return typeof window === "undefined" ? null : window.localStorage.getItem(STORAGE_KEYS.activeOrg);
}

type AuthFailureHandler = () => void;

const authFailureHandlers = new Set<AuthFailureHandler>();

/** Registers a handler invoked when a refresh attempt fails (session over). */
export function onAuthFailure(handler: AuthFailureHandler): () => void {
  authFailureHandlers.add(handler);
  return () => authFailureHandlers.delete(handler);
}

function notifyAuthFailure(): void {
  for (const handler of authFailureHandlers) handler();
}

let refreshPromise: Promise<boolean> | null = null;

async function performRefresh(): Promise<boolean> {
  try {
    const res = await fetch(`${API_URL}/api/v1/auth/refresh`, {
      method: "POST",
      credentials: "include",
    });
    if (!res.ok) return false;
    const body = (await res.json()) as { access_token: string };
    setAccessToken(body.access_token);
    return true;
  } catch {
    return false;
  }
}

/**
 * Single-flight refresh: concurrent 401s share ONE refresh rotation.
 * On failure the access token is cleared and auth-failure handlers are
 * notified exactly once (all pending callers then fail fast).
 */
function refreshSession(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = performRefresh()
      .then((ok) => {
        if (!ok) {
          setAccessToken(null);
          notifyAuthFailure();
        }
        return ok;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
  retryOnUnauthorized = true
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const orgId = getActiveOrganizationId();
  if (orgId) headers.set("X-Organization-Id", orgId);

  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });

  if (res.status === 401 && retryOnUnauthorized) {
    await refreshSession();
    return apiRequest<T>(path, init, false);
  }

  if (!res.ok) {
    let code = "unknown_error";
    let message = res.statusText;
    try {
      const body = (await res.json()) as {
        error?: { code?: string; message?: string };
      };
      if (body.error) {
        code = body.error.code ?? code;
        message = body.error.message ?? message;
      }
    } catch {
      // Non-JSON error body; keep defaults.
    }
    throw new ApiError(res.status, code, message);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function apiGet<T>(path: string): Promise<T> {
  return apiRequest<T>(path, { method: "GET" });
}

export function apiPost<T>(path: string, body: unknown): Promise<T> {
  return apiRequest<T>(path, { method: "POST", body: JSON.stringify(body) });
}

export function apiPut<T>(path: string, body: unknown): Promise<T> {
  return apiRequest<T>(path, { method: "PUT", body: JSON.stringify(body) });
}

export function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return apiRequest<T>(path, { method: "PATCH", body: JSON.stringify(body) });
}

export function apiDelete<T>(path: string): Promise<T> {
  return apiRequest<T>(path, { method: "DELETE" });
}