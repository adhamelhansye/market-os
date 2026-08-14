import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth } from "@/context/auth-context";
import { setAccessToken } from "@/lib/api-client";

const API = "http://localhost:8000";
const ME_URL = `${API}/api/v1/auth/me`;
const LOGOUT_URL = `${API}/api/v1/auth/logout`;
const REFRESH_URL = `${API}/api/v1/auth/refresh`;

const ME_BODY = {
  user: {
    id: "user-1",
    email: "alice@example.com",
    name: "Alice",
    locale: "en",
    created_at: "2026-08-13T00:00:00Z",
  },
  active_organization_id: "org-1",
  memberships: [
    {
      organization: {
        id: "org-1",
        name: "Acme Agency",
        slug: "acme-agency",
        type: "agency",
        locale_default: "en",
        created_at: "2026-08-13T00:00:00Z",
      },
      role_name: "owner",
      permissions: ["org:read"],
    },
  ],
};

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function installFetch(router: (url: string) => Promise<Response>): ReturnType<typeof vi.fn> {
  const fn = vi.fn(async (input: RequestInfo | URL) => router(String(input)));
  vi.stubGlobal("fetch", fn);
  return fn;
}

function Probe() {
  const { status, user, logout } = useAuth();
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="user">{user ? user.email : "none"}</span>
      <button onClick={() => void logout()}>logout</button>
    </div>
  );
}

beforeEach(() => {
  window.localStorage.clear();
  setAccessToken(null);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("AuthProvider", () => {
  it("authenticates on mount and transitions to anonymous after logout", async () => {
    installFetch(async (url) => {
      if (url === ME_URL) return jsonResponse(200, ME_BODY);
      if (url === LOGOUT_URL) return new Response(null, { status: 204 });
      if (url === REFRESH_URL) return jsonResponse(401, {});
      return jsonResponse(404, {});
    });
    setAccessToken("some-token");

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));
    expect(screen.getByTestId("user")).toHaveTextContent("alice@example.com");

    await act(async () => {
      screen.getByRole("button", { name: "logout" }).click();
    });

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("anonymous"));
    expect(screen.getByTestId("user")).toHaveTextContent("none");
  });

  it("starts anonymous when the session is invalid", async () => {
    installFetch(async () => jsonResponse(401, { error: { code: "authentication_required" } }));
    setAccessToken("expired-token");

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("anonymous"));
    expect(screen.getByTestId("user")).toHaveTextContent("none");
  });
});