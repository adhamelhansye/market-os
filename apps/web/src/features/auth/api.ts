import { apiGet, apiPost } from "@/lib/api-client";

import type { components } from "@marketing-os/shared-types";

export type AuthResponse = components["schemas"]["AuthResponse"];
export type MeResponse = components["schemas"]["MeResponse"];
export type LoginRequest = components["schemas"]["LoginRequest"];
export type SignupRequest = components["schemas"]["SignupRequest"];

export function signup(payload: SignupRequest): Promise<AuthResponse> {
  return apiPost<AuthResponse>("/api/v1/auth/signup", payload);
}

export function login(payload: LoginRequest): Promise<AuthResponse> {
  return apiPost<AuthResponse>("/api/v1/auth/login", payload);
}

export function logout(): Promise<void> {
  return apiPost<void>("/api/v1/auth/logout", {});
}

export function fetchMe(): Promise<MeResponse> {
  return apiGet<MeResponse>("/api/v1/auth/me");
}