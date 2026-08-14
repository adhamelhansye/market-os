"use client";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const STORAGE_KEYS = {
  accessToken: "mos.accessToken",
  activeOrg: "mos.activeOrg",
  activeBusiness: "mos.activeBusiness",
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

export function getActiveBusinessId(): string | null {
  return typeof window === "undefined" ? null : window.localStorage.getItem(STORAGE_KEYS.activeBusiness);
}

async function refreshSession(): Promise<boolean> {
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
  const businessId = getActiveBusinessId();
  if (orgId) headers.set("X-Organization-Id", orgId);
  if (businessId) headers.set("X-Business-Id", businessId);

  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });

  if (res.status === 401 && retryOnUnauthorized) {
    const refreshed = await refreshSession();
    if (refreshed) return apiRequest<T>(path, init, false);
    setAccessToken(null);
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