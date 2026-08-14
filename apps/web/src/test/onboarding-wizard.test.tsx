import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { renderWithI18n, screen } from "@/test/render";
import { OnboardingWizard } from "@/features/onboarding/onboarding-wizard";
import type { Business } from "@/features/businesses/api";
import type { Goal } from "@/features/goals/api";
import type { ProductDetail } from "@/features/products/api";
import type { ShippingRule } from "@/features/shipping/api";

const state = vi.hoisted(() => ({
  updateBusiness: vi.fn(),
  fetchProducts: vi.fn(),
  fetchEconomicsProducts: vi.fn(),
  fetchShippingRules: vi.fn(),
  fetchGoals: vi.fn(),
  createGoal: vi.fn(),
  createProduct: vi.fn(),
  createPrice: vi.fn(),
  createCost: vi.fn(),
  createShippingRule: vi.fn(),
  updateShippingRule: vi.fn(),
  completeCalls: [] as unknown[],
}));

vi.mock("@/features/businesses/api", () => ({
  updateBusiness: (...args: unknown[]) => state.updateBusiness(...args),
  fetchBusinesses: vi.fn(),
  fetchBusiness: vi.fn(),
  createBusiness: vi.fn(),
  fetchBusinessProfile: vi.fn(),
  updateBusinessProfile: vi.fn(),
}));

vi.mock("@/features/products/api", () => ({
  fetchProducts: (...args: unknown[]) => state.fetchProducts(...args),
  createProduct: (...args: unknown[]) => state.createProduct(...args),
  createPrice: (...args: unknown[]) => state.createPrice(...args),
  createCost: (...args: unknown[]) => state.createCost(...args),
  fetchProduct: vi.fn(),
  updateProduct: vi.fn(),
  archiveProduct: vi.fn(),
  fetchPrices: vi.fn(),
  fetchCosts: vi.fn(),
  fetchInventory: vi.fn(),
  setInventory: vi.fn(),
  adjustInventory: vi.fn(),
}));

vi.mock("@/features/economics/api", () => ({
  fetchEconomicsSummary: vi.fn(),
  fetchEconomicsProducts: (...args: unknown[]) => state.fetchEconomicsProducts(...args),
  fetchEconomicsGoals: vi.fn(),
}));

vi.mock("@/features/goals/api", () => ({
  fetchGoals: (...args: unknown[]) => state.fetchGoals(...args),
  createGoal: (...args: unknown[]) => state.createGoal(...args),
  updateGoal: vi.fn(),
  deleteGoal: vi.fn(),
}));

vi.mock("@/features/shipping/api", () => ({
  fetchShippingRules: (...args: unknown[]) => state.fetchShippingRules(...args),
  createShippingRule: (...args: unknown[]) => state.createShippingRule(...args),
  updateShippingRule: (...args: unknown[]) => state.updateShippingRule(...args),
}));

const business: Business = {
  id: "biz-1",
  organization_id: "org-1",
  managed_by_organization_id: null,
  name: "Coffee Shop",
  currency: "EGP",
  timezone: "Africa/Cairo",
  industry: null,
  description: null,
  country: null,
  website_url: null,
  onboarding_status: "not_started",
  created_at: "2026-08-13T00:00:00Z",
};

const existingProduct: ProductDetail = {
  id: "p-1",
  business_id: "biz-1",
  sku: null,
  name: "Mocha",
  description: null,
  status: "active",
  currency: "EGP",
  created_at: "2026-08-13T00:00:00Z",
  updated_at: "2026-08-13T00:00:00Z",
  inventory_quantity: 0,
  active_price: "120.00",
  contribution_profit: "60.00",
  contribution_margin: "0.5000",
};

const defaultShippingRule: ShippingRule = {
  id: "s-1",
  business_id: "biz-1",
  name: "Standard",
  country: "EG",
  region: null,
  method: "flat",
  cost: "30.00",
  customer_price: "50.00",
  free_shipping_threshold: null,
  is_default: true,
  active: true,
  created_at: "2026-08-13T00:00:00Z",
  updated_at: "2026-08-13T00:00:00Z",
};

const goal: Goal = {
  id: "g-1",
  business_id: "biz-1",
  period_start: "2026-01-01T00:00:00Z",
  period_end: "2026-12-31T00:00:00Z",
  target_revenue: "1000000.00",
  target_profit: null,
  ad_budget: null,
  maximum_cpa: null,
  target_roas: null,
  currency: "EGP",
  created_at: "2026-08-13T00:00:00Z",
  updated_at: "2026-08-13T00:00:00Z",
};

function renderWizard() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return renderWithI18n(
    <QueryClientProvider client={queryClient}>
      <OnboardingWizard businessId="biz-1" business={business} />
    </QueryClientProvider>,
    "en"
  );
}

describe("onboarding wizard", () => {
  beforeEach(() => {
    state.updateBusiness.mockReset();
    state.fetchProducts.mockReset();
    state.fetchEconomicsProducts.mockReset();
    state.fetchShippingRules.mockReset();
    state.fetchGoals.mockReset();
    state.createGoal.mockReset();
    state.createProduct.mockReset();
    state.createPrice.mockReset();
    state.createCost.mockReset();
    state.createShippingRule.mockReset();
    state.updateShippingRule.mockReset();
    state.updateBusiness.mockImplementation((_id, payload) =>
      Promise.resolve({ ...business, ...payload })
    );
    state.fetchProducts.mockResolvedValue([]);
    state.fetchEconomicsProducts.mockResolvedValue([]);
    state.fetchShippingRules.mockResolvedValue([]);
    state.fetchGoals.mockResolvedValue([]);
    state.createGoal.mockResolvedValue(goal);
    state.createProduct.mockImplementation((_id, payload) =>
      Promise.resolve({ ...existingProduct, name: payload.name, id: "new-p" })
    );
    state.createPrice.mockResolvedValue({ id: "price-1", price: "100.00" });
    state.createCost.mockResolvedValue({ id: "cost-1", cogs: "50.00" });
    state.createShippingRule.mockResolvedValue(defaultShippingRule);
    state.updateShippingRule.mockResolvedValue(defaultShippingRule);
  });

  it("shows all six stages and pre-fills business info", () => {
    renderWizard();
    for (const label of [
      "Business",
      "Products",
      "Economics",
      "Shipping",
      "Goals",
      "Review",
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByDisplayValue("Coffee Shop")).toBeInTheDocument();
    expect(screen.getByText("Step 1 of 6")).toBeInTheDocument();
  });

  it("saves business info and advances to the products step", async () => {
    const user = userEvent.setup();
    renderWizard();
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(state.updateBusiness).toHaveBeenCalledWith("biz-1", {
      name: "Coffee Shop",
      currency: "EGP",
      timezone: "Africa/Cairo",
      country: null,
      industry: null,
      website_url: null,
      description: null,
      onboarding_status: "in_progress",
    });
    expect(await screen.findByText("Add your first products")).toBeInTheDocument();
  });

  it("resumes with existing products and a default shipping rule", async () => {
    state.fetchProducts.mockResolvedValue([existingProduct]);
    state.fetchShippingRules.mockResolvedValue([defaultShippingRule]);
    const user = userEvent.setup();
    renderWizard();
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("Mocha")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Next" }));
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText(/^Standard/)).toBeInTheDocument();
  });

  it("completes onboarding from the review step and navigates to economics", async () => {
    const user = userEvent.setup();
    renderWizard();
    // Step through Business, Products, Economics, Shipping, Goals.
    for (let i = 0; i < 4; i += 1) {
      await user.click(screen.getByRole("button", { name: "Next" }));
    }
    await user.click(screen.getByRole("button", { name: "Skip goals for now" }));
    expect(await screen.findByText("Review and finish")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Complete onboarding" }));
    expect(state.updateBusiness).toHaveBeenCalledWith("biz-1", {
      onboarding_status: "completed",
    });
  });
});