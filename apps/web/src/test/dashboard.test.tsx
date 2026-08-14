import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { screen } from "@/test/render";
import { renderWithI18n } from "@/test/render";
import DashboardPage from "@/app/[locale]/(dashboard)/dashboard/page";
import type { Business } from "@/features/businesses/api";

const state = vi.hoisted(() => ({
  businesses: [] as unknown[],
  activeBusinessId: null as string | null,
}));

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
    user: {
      id: "user-1",
      email: "alice@example.com",
      name: "Alice",
      locale: "en",
      created_at: "2026-08-13T00:00:00Z",
    },
    memberships: [membership],
    activeOrganizationId: "org-1",
    login: vi.fn(),
    signup: vi.fn(),
    logout: vi.fn(),
    refresh: vi.fn(),
    isApiError: () => false,
  }),
}));

vi.mock("@/context/business-context", () => ({
  useBusiness: () => ({
    activeOrganizationId: "org-1",
    activeBusinessId: state.activeBusinessId,
    setActiveOrganization: vi.fn(),
    setActiveBusiness: vi.fn(),
    clear: vi.fn(),
  }),
}));

const baseBusiness: Business = {
  id: "biz-1",
  organization_id: "org-1",
  managed_by_organization_id: null,
  name: "Coffee Shop",
  currency: "USD",
  timezone: "UTC",
  industry: null,
  description: null,
  country: null,
  website_url: null,
  onboarding_status: "not_started",
  created_at: "2026-08-13T00:00:00Z",
};

vi.mock("@/features/businesses/api", () => ({
  fetchBusinesses: vi.fn().mockImplementation(() => Promise.resolve(state.businesses)),
  fetchBusiness: vi.fn(),
  createBusiness: vi.fn(),
  updateBusiness: vi.fn(),
  fetchBusinessProfile: vi.fn(),
  updateBusinessProfile: vi.fn(),
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

describe("dashboard business hub", () => {
  beforeEach(() => {
    state.businesses = [];
    state.activeBusinessId = null;
  });

  it("shows organization, role and the create-business form when no business exists", () => {
    renderDashboard("en");
    expect(screen.getByText("Acme Agency")).toBeInTheDocument();
    expect(screen.getByText("owner")).toBeInTheDocument();
    expect(screen.getByText("Create your business")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Your business starts with the onboarding flow: business info, products, economics, shipping and goals."
      )
    ).toBeInTheDocument();
  });

  it("shows the Arabic create-business form", () => {
    renderDashboard("ar");
    expect(screen.getByText("أنشئ نشاطك التجاري")).toBeInTheDocument();
  });

  it("shows business hub links and the onboarding CTA for an active business", async () => {
    state.businesses = [baseBusiness];
    state.activeBusinessId = "biz-1";
    renderDashboard("en");
    expect(await screen.findAllByText("Coffee Shop")).not.toHaveLength(0);
    expect(await screen.findByText("Start onboarding")).toBeInTheDocument();
    expect(screen.getByText("Economics dashboard")).toBeInTheDocument();
    expect(screen.getByText("Products")).toBeInTheDocument();
    expect(screen.getByText("Business settings")).toBeInTheDocument();
  });

  it("shows the Arabic CTA for an in-progress business", async () => {
    state.businesses = [{ ...baseBusiness, onboarding_status: "in_progress" }];
    state.activeBusinessId = "biz-1";
    renderDashboard("ar");
    expect(await screen.findByText("متابعة الإعداد")).toBeInTheDocument();
    expect(screen.getByText("لوحة الاقتصاديات")).toBeInTheDocument();
  });
});