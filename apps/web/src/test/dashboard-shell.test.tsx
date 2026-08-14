import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DashboardShell } from "@/components/layout/dashboard-shell";
import { renderWithI18n } from "@/test/render";

const { replaceMock } = vi.hoisted(() => ({ replaceMock: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock, push: vi.fn() }),
  usePathname: () => "/en/dashboard",
}));

vi.mock("@/context/auth-context", () => ({
  useAuth: () => ({
    status: "anonymous",
    user: null,
    memberships: [],
    activeOrganizationId: null,
    login: vi.fn(),
    signup: vi.fn(),
    logout: vi.fn(),
    refresh: vi.fn(),
  }),
}));

vi.mock("@/context/business-context", () => ({
  useBusiness: () => ({
    activeOrganizationId: null,
    activeBusinessId: null,
    setActiveOrganization: vi.fn(),
    setActiveBusiness: vi.fn(),
    clear: vi.fn(),
  }),
}));

describe("DashboardShell (protected route behavior)", () => {
  it("redirects anonymous users to the locale login page", async () => {
    renderWithI18n(
      <DashboardShell>
        <div>page content</div>
      </DashboardShell>,
      "en"
    );

    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/en/login"));
  });
});