import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import { screen } from "@/test/render";
import { renderWithI18n } from "@/test/render";
import DashboardPage from "@/app/[locale]/(dashboard)/dashboard/page";

const membership = {
  organization: {
    id: "org-1",
    name: "Acme Agency",
    slug: "acme-agency",
    type: "agency",
    locale_default: "en",
    created_at: "2026-08-13T00:00:00Z",
  },
  role_name: "owner",
  permissions: ["org:read", "business:read", "dashboard:read"],
};

vi.mock("@/context/auth-context", () => ({
  useAuth: () => ({
    status: "authenticated",
    user: { id: "user-1", email: "alice@example.com", name: "Alice", locale: "en", created_at: "2026-08-13T00:00:00Z" },
    memberships: [membership],
    activeOrganizationId: "org-1",
    login: vi.fn(),
    signup: vi.fn(),
    logout: vi.fn(),
    refresh: vi.fn(),
  }),
}));

vi.mock("@/context/business-context", () => ({
  useBusiness: () => ({
    activeOrganizationId: "org-1",
    activeBusinessId: null,
    setActiveOrganization: vi.fn(),
    setActiveBusiness: vi.fn(),
    clear: vi.fn(),
  }),
}));

function renderDashboard(locale: "en" | "ar") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return renderWithI18n(
    <QueryClientProvider client={queryClient}>
      <DashboardPage />
    </QueryClientProvider>,
    locale
  );
}

describe("dashboard (Phase 0 mock empty state)", () => {
  it("shows organization, role and empty state in English", () => {
    renderDashboard("en");
    expect(screen.getByText("Acme Agency")).toBeInTheDocument();
    expect(screen.getByText("owner")).toBeInTheDocument();
    expect(
      screen.getByText("Connect your data to start analyzing your marketing performance.")
    ).toBeInTheDocument();
  });

  it("shows the Arabic empty state message", () => {
    renderDashboard("ar");
    expect(screen.getByText("اربط بياناتك لبدء تحليل أداء التسويق.")).toBeInTheDocument();
  });
});