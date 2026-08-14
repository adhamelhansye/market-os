import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  apiGet,
  getAccessToken,
  onAuthFailure,
  setAccessToken,
} from "@/lib/api-client";

const API = "http://localhost:8000";
const THINGS_URL = `${API}/api/v1/things`;
const REFRESH_URL = `${API}/api/v1/auth/refresh`;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

type FetchMock = ReturnType<typeof vi.fn>;

function installFetch(mock: (url: string) => Promise<Response>): FetchMock {
  const fn = vi.fn(async (input: RequestInfo | URL) => mock(String(input)));
  vi.stubGlobal("fetch", fn);
  return fn;
}

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("api-client single-flight refresh", () => {
  it("issues ONE refresh for concurrent 401s and retries with the new token", async () => {
    let refreshCalls = 0;
    let thingCalls = 0;
    installFetch(async (url) => {
      if (url === REFRESH_URL) {
        refreshCalls += 1;
        setAccessToken("new-token");
        return jsonResponse(200, { access_token: "new-token" });
      }
      thingCalls += 1;
      return thingCalls <= 2
        ? jsonResponse(401, { error: { code: "authentication_required" } })
        : jsonResponse(200, { ok: true });
    });
    setAccessToken("old-token");

    const [a, b] = await Promise.all([apiGet("/api/v1/things"), apiGet("/api/v1/things")]);

    expect(a).toEqual({ ok: true });
    expect(b).toEqual({ ok: true });
    expect(refreshCalls).toBe(1);
    expect(getAccessToken()).toBe("new-token");
  });

  it("notifies auth failure once, clears the token and rejects all callers when refresh fails", async () => {
    installFetch(async () => jsonResponse(401, { error: { code: "authentication_required" } }));
    setAccessToken("stale-token");

    const handler = vi.fn();
    const unsubscribe = onAuthFailure(handler);

    const results = await Promise.allSettled([apiGet("/api/v1/things"), apiGet("/api/v1/things")]);

    expect(results.every((r) => r.status === "rejected")).toBe(true);
    expect(handler).toHaveBeenCalledTimes(1);
    expect(getAccessToken()).toBeNull();
    unsubscribe();
  });

  it("retries exactly once after a successful refresh, then surfaces the error", async () => {
    let refreshCalls = 0;
    installFetch(async (url) => {
      if (url === REFRESH_URL) {
        refreshCalls += 1;
        return jsonResponse(200, { access_token: "fresh-token" });
      }
      return jsonResponse(401, { error: { code: "authentication_required" } });
    });
    setAccessToken("old-token");

    await expect(apiGet("/api/v1/things")).rejects.toMatchObject({ status: 401 });
    expect(refreshCalls).toBe(1);
  });

  it("does not retry a second 401 after a failed refresh (no infinite loop)", async () => {
    let refreshCalls = 0;
    let thingCalls = 0;
    installFetch(async (url) => {
      if (url === REFRESH_URL) {
        refreshCalls += 1;
        return jsonResponse(401, {});
      }
      thingCalls += 1;
      return jsonResponse(401, {});
    });
    setAccessToken("old-token");

    await expect(apiGet("/api/v1/things")).rejects.toBeInstanceOf(ApiError);
    expect(refreshCalls).toBe(1);
    expect(thingCalls).toBe(2); // original 401 + single retry
  });
});