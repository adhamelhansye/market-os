import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { renderWithI18n, screen } from "@/test/render";
import EconomicsPage from "@/app/[locale]/(dashboard)/business/[business_id]/economics/page";
import type { EconomicsSummary, ProductEconomics } from "@/features/economics/api";

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    prefetch: vi.fn(),
    refresh: vi.fn(),
    forward: vi.fn(),
  }),
  usePathname: () => "/business/biz-1/economics",
  useParams: () => ({ business_id: "biz-1" }),
  useSearchParams: () => new URLSearchParams(),
  redirect: vi.fn(),
}));

const state = vi.hoisted(() => ({
  summary: null as EconomicsSummary | null,
  products: [] as ProductEconomics[],
}));

vi.mock("@/features/economics/api", () => ({
  fetchEconomicsSummary: vi.fn(() => Promise.resolve(state.summary)),
  fetchEconomicsProducts: vi.fn(() => Promise.resolve(state.products)),
  fetchEconomicsGoals: vi.fn(() => Promise.resolve([])),
}));

const summary: EconomicsSummary = {
  business_id: "biz-1",
  business_name: "Coffee Shop",
  currency: "USD",
  active_products: 2,
  priced_products: 1,
  average_product_price: "150.00",
  average_contribution_profit: "80.00",
  average_contribution_margin: "0.5333",
  average_total_customer_revenue: null,
  break_even_cpa_range: ["100.00", "200.00"],
  break_even_roas: "1.5000",
  inventory_value: "1200.00",
  target_cpa: null,
  target_cpa_reason: null,
  current_goal: {
    id: "g-1",
    business_id: "biz-1",
    period_start: "2026-01-01T00:00:00Z",
    period_end: "2026-12-31T00:00:00Z",
    target_revenue: "50000.00",
    target_profit: null,
    ad_budget: null,
    maximum_cpa: null,
    target_roas: null,
    currency: "USD",
    created_at: "2026-08-13T00:00:00Z",
    updated_at: "2026-08-13T00:00:00Z",
  },
};

const product: ProductEconomics = {
  product_id: "p-1",
  name: "Mocha",
  sku: null,
  status: "active",
  currency: "USD",
  inventory_quantity: 12,
  product_revenue: "150.00",
  shipping_revenue: null,
  total_customer_revenue: null,
  product_cost: "70.00",
  shipping_cost: "0.00",
  payment_fees: "0.00",
  discount_amount: "0.00",
  contribution_profit: "80.00",
  contribution_margin: "0.5333",
  break_even_cpa: "93.02",
  break_even_roas: "1.0750",
  target_cpa: null,
  target_cpa_reason: null,
};

function renderEconomics(locale: "en" | "ar") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return renderWithI18n(
    <QueryClientProvider client={queryClient}>
      <EconomicsPage />
    </QueryClientProvider>,
    locale
  );
}

describe("economics dashboard", () => {
  beforeEach(() => {
    state.summary = null;
    state.products = [];
  });

  it("shows the empty state when there is no summary", async () => {
    renderEconomics("en");
    expect(await screen.findByText("No economics to show yet")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Add product cost and pricing information to calculate your break-even CPA."
      )
    ).toBeInTheDocument();
  });

  it("shows the Arabic empty state with RTL text", async () => {
    renderEconomics("ar");
    expect(await screen.findByText("لا توجد اقتصاديات للعرض بعد")).toBeInTheDocument();
    expect(
      screen.getByText("أضف تكلفة المنتج والتسعير لحساب الـ CPA عند نقطة التعادل.")
    ).toBeInTheDocument();
  });

  it("renders KPI values from the summary", async () => {
    state.summary = summary;
    renderEconomics("en");
    expect(await screen.findByText(/Coffee Shop/)).toBeInTheDocument();
    expect(screen.getByText("2 (Priced products: 1)")).toBeInTheDocument();
    expect(screen.getByText("$150.00")).toBeInTheDocument();
    expect(screen.getByText("$80.00")).toBeInTheDocument();
    expect(screen.getByText("53.33%")).toBeInTheDocument();
    expect(screen.getByText("$100.00 – $200.00")).toBeInTheDocument();
    expect(screen.getByText("150.00%")).toBeInTheDocument();
    expect(screen.getByText("$1,200.00")).toBeInTheDocument();
    expect(screen.getByText("$50,000.00")).toBeInTheDocument();
  });

  it("shows the products table with economics per product", async () => {
    state.summary = summary;
    state.products = [product];
    renderEconomics("en");
    expect(await screen.findByText("Mocha")).toBeInTheDocument();
    expect(screen.getByText("$93.02")).toBeInTheDocument();
    expect(screen.getByText("107.50%")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
  });

  it("shows a note when no products have pricing yet", async () => {
    state.summary = summary;
    renderEconomics("en");
    expect(
      await screen.findByText("None of your products have pricing yet.")
    ).toBeInTheDocument();
  });
});