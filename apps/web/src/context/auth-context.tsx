"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { apiGet, apiPost, setAccessToken } from "@/lib/api-client";
import { ApiError } from "@/lib/api-client";

import type { components } from "@marketing-os/shared-types";

type MeResponse = components["schemas"]["MeResponse"];
type AuthResponse = components["schemas"]["AuthResponse"];
type SignupRequest = components["schemas"]["SignupRequest"];
type LoginRequest = components["schemas"]["LoginRequest"];

type AuthStatus = "loading" | "authenticated" | "anonymous";

interface AuthContextValue {
  status: AuthStatus;
  user: MeResponse["user"] | null;
  memberships: MeResponse["memberships"];
  activeOrganizationId: string | null;
  login: (payload: LoginRequest) => Promise<void>;
  signup: (payload: SignupRequest) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<MeResponse["user"] | null>(null);
  const [memberships, setMemberships] = useState<MeResponse["memberships"]>([]);
  const [activeOrganizationId, setActiveOrganizationId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const me = await apiGet<MeResponse>("/api/v1/auth/me");
      setUser(me.user);
      setMemberships(me.memberships);
      setActiveOrganizationId(me.active_organization_id ?? null);
      setStatus("authenticated");
    } catch (error) {
      setUser(null);
      setMemberships([]);
      setStatus("anonymous");
      void error;
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(
    async (payload: LoginRequest) => {
      const response = await apiPost<AuthResponse>("/api/v1/auth/login", payload);
      setAccessToken(response.access_token);
      await refresh();
    },
    [refresh]
  );

  const signup = useCallback(
    async (payload: SignupRequest) => {
      const response = await apiPost<AuthResponse>("/api/v1/auth/signup", payload);
      setAccessToken(response.access_token);
      await refresh();
    },
    [refresh]
  );

  const logout = useCallback(async () => {
    try {
      await apiPost<undefined>("/api/v1/auth/logout", {});
    } catch {
      // Local logout proceeds even if the server session is already gone.
    }
    setAccessToken(null);
    setUser(null);
    setMemberships([]);
    setStatus("anonymous");
  }, []);

  const value = useMemo(
    () => ({
      status,
      user,
      memberships,
      activeOrganizationId,
      login,
      signup,
      logout,
      refresh,
    }),
    [status, user, memberships, activeOrganizationId, login, signup, logout, refresh]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}