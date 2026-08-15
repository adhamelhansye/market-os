import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { renderWithI18n, screen } from "@/test/render";
import MetricsPage from "@/app/[locale]/(dashboard)/business/[business_id]/metrics/page";
import type {
  CampaignsRead,
  ComparisonRead,
  DataQualityRead,
  FunnelRead,
  SummaryRead,
  TimeseriesRead,
} from "@/features/metrics/api";

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    prefetch: vi.fn(),
    refresh: vi.fn(),
    forward: vi.fn(),
  }),
  usePathname: () => "/business/biz-1/metrics",
  useParams: () => ({ business_id: "biz-1" }),
  useSearchParams: () => new URLSearchParams(),
  redirect: vi.fn(),
}));

const state = vi.hoisted(() => ({
  summary: null as SummaryRead | null,
  timeseries: null as TimeseriesRead | null,
  funnel: null as FunnelRead | null,
  campaigns: null as CampaignsRead | null,
  quality: null as DataQualityRead | null,
  comparison: null as ComparisonRead | null,
}));

vi.mock("@/features/metrics/api", () => ({
  fetchMetricsSummary: vi.fn(() => Promise.resolve(state.summary)),
  fetchMetricsTimeseries: vi.fn(() => Promise.resolve(state.timeseries)),
  fetchMetricsFunnel: vi.fn(() => Promise.resolve(state.funnel)),
  fetchMetricsCampaigns: vi.fn(() => Promise.resolve(state.campaigns)),
  fetchMetricsDataQuality: vi.fn(() => Promise.resolve(state.quality)),
  fetchMetricsComparison: vi.fn(() => Promise.resolve(state.comparison)),
}));

function renderMetrics(locale: "en" | "ar") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return renderWithI18n(
    <QueryClientProvider client={queryClient}>
      <MetricsPage />
    </QueryClientProvider>,
    locale
  );
}

const summary: SummaryRead = {
  business_id: "biz-1",
  currency: "USD",
  timezone: "UTC",
  range: {
    kind: "last_30_days",
    start: "2026-07-14",
    end: "2026-08-12",
    previous_start: "2026-06-13",
    previous_end: "2026-07-13",
  },
  revenue: { value: "1250.00", status: "available", reason: null, currency: "USD", source: "commerce" },
  spend: { value: "1000.00", status: "available", reason: null, currency: "USD", source: "meta" },
  purchases: { value: 4, status: "available", reason: null },
  refunds: { value: "50.00", status: "available", reason: null, currency: "USD", source: "commerce" },
  impressions: { value: 2000, status: "available", reason: null },
  reach: { value: 1800, status: "available", reason: null },
  clicks: { value: 100, status: "available", reason: null },
  link_clicks: { value: 16, status: "available", reason: null },
  landing_page_views: { value: 12, status: "available", reason: null },
  conversions: { value: 8, status: "available", reason: null },
  ctr: { value: "0.05", status: "available", reason: null },
  cpc: { value: "10.00", status: "available", reason: null, currency: "USD", source: "meta" },
  cpm: { value: "500.00", status: "available", reason: null, currency: "USD", source: "meta" },
  cvr: { value: "0.04", status: "available", reason: null },
  cpa: { value: "250.00", status: "available", reason: null, currency: "USD", source: "meta" },
  aov: { value: "312.50", status: "available", reason: null, currency: "USD", source: "commerce" },
  roas: { value: "1.2000", status: "available", reason: null },
  mer: { value: "1.2500", status: "available", reason: null },
  contribution_profit: {
    value: "320.00",
    status: "available",
    reason: null,
    currency: "USD",
    source: "economics",
  },
  contribution_margin: { value: "0.2560", status: "available", reason: null },
  break_even_cpa: { value: "80.00", status: "available", reason: null, currency: "USD", source: "economics" },
  break_even_roas: { value: "1.5000", status: "available", reason: null },
};

const timeseries: TimeseriesRead = {
  business_id: "biz-1",
  currency: "USD",
  timezone: "UTC",
  range: summary.range,
  points: [
    {
      date: "2026-08-10",
      spend: "500.00",
      revenue: "700.00",
      purchases: 2,
      clicks: 50,
      impressions: 1000,
      conversions: 4,
      conversion_value: "400.00",
      ctr: null,
      cpa: null,
      roas: null,
      mer: null,
      contribution_profit: null,
    },
    {
      date: "2026-08-11",
      spend: "500.00",
      revenue: "550.00",
      purchases: 2,
      clicks: 50,
      impressions: 1000,
      conversions: 4,
      conversion_value: "400.00",
      ctr: null,
      cpa: null,
      roas: null,
      mer: null,
      contribution_profit: null,
    },
  ],
};

const funnel: FunnelRead = {
  business_id: "biz-1",
  range: summary.range,
  stages: [
    { metric: "impressions", value: 2000, status: "available", reason: null, conversion_rate: null, dropoff_rate: null },
    { metric: "clicks", value: 100, status: "available", reason: null, conversion_rate: { value: "0.05", status: "available", reason: null }, dropoff_rate: null },
    { metric: "purchases", value: 4, status: "available", reason: null, conversion_rate: null, dropoff_rate: null },
  ],
};

const campaigns: CampaignsRead = {
  business_id: "biz-1",
  currency: "USD",
  timezone: "UTC",
  range: summary.range,
  campaigns: [
    {
      id: "c-1",
      name: "Campaign 1",
      status: "ACTIVE",
      impressions: 1000,
      reach: 900,
      clicks: 10,
      link_clicks: 8,
      landing_page_views: 6,
      spend: "100.00",
      conversions: 3,
      conversion_value: "300.00",
      revenue_source: "meta_reported",
      ctr: { value: "0.01", status: "available", reason: null },
      cpc: { value: "10.00", status: "available", reason: null, currency: "USD", source: "meta" },
      cpm: { value: "100.00", status: "available", reason: null, currency: "USD", source: "meta" },
      cvr: { value: null, status: "unavailable", reason: "no purchase attribution at this grain" },
      cpa: { value: null, status: "unavailable", reason: "no purchase attribution at this grain", currency: "USD", source: null },
      aov: { value: null, status: "unavailable", reason: "no purchase attribution at this grain", currency: "USD", source: null },
      roas: { value: "3.0000", status: "available", reason: null },
    },
  ],
};

const quality: DataQualityRead = {
  business_id: "biz-1",
  timezone: "UTC",
  range: summary.range,
  providers: [
    {
      provider: "meta",
      connected: true,
      last_synced_at: "2026-08-12T10:00:00Z",
      last_successful_sync_at: "2026-08-12T10:00:00Z",
      coverage_start: "2026-07-14",
      coverage_end: "2026-08-11",
      covered_days: 29,
      missing_days: 1,
      freshness_status: "fresh",
      reason: null,
    },
    {
      provider: "shopify",
      connected: false,
      last_synced_at: null,
      last_successful_sync_at: null,
      coverage_start: null,
      coverage_end: null,
      covered_days: null,
      missing_days: null,
      freshness_status: "unavailable",
      reason: "not connected",
    },
  ],
};

const comparison: ComparisonRead = {
  business_id: "biz-1",
  currency: "USD",
  timezone: "UTC",
  range: summary.range,
  revenue: {
    current: "1250.00",
    previous: "1000.00",
    absolute_change: "250.00",
    percentage_change: { value: "25.00", status: "available", reason: null },
  },
  spend: {
    current: "1000.00",
    previous: "1200.00",
    absolute_change: "-200.00",
    percentage_change: { value: "-16.67", status: "available", reason: null },
  },
  purchases: { current: "4", previous: "3", absolute_change: "1", percentage_change: { value: "33.33", status: "available", reason: null } },
  roas: { current: "1.2000", previous: "1.0000", absolute_change: "0.2000", percentage_change: { value: "20.00", status: "available", reason: null } },
  mer: { current: "1.2500", previous: null, absolute_change: null, percentage_change: { value: null, status: "unavailable", reason: "no previous period data" } },
  cpa: { current: "250.00", previous: "400.00", absolute_change: "-150.00", percentage_change: { value: "-37.50", status: "available", reason: null } },
  aov: { current: "312.50", previous: "333.33", absolute_change: "-20.83", percentage_change: { value: "-6.25", status: "available", reason: null } },
  ctr: { current: "0.05", previous: "0.04", absolute_change: "0.01", percentage_change: { value: "25.00", status: "available", reason: null } },
  contribution_profit: { current: "320.00", previous: "240.00", absolute_change: "80.00", percentage_change: { value: "33.33", status: "available", reason: null } },
};

describe("metrics dashboard", () => {
  beforeEach(() => {
    state.summary = null;
    state.timeseries = null;
    state.funnel = null;
    state.campaigns = null;
    state.quality = null;
    state.comparison = null;
  });

  it("shows the empty state when there is no data", async () => {
    renderMetrics("en");
    expect(await screen.findByText("No analytics yet")).toBeInTheDocument();
    expect(
      screen.getByText("Connect your ad account and store to start measuring performance.")
    ).toBeInTheDocument();
  });

  it("shows the Arabic empty state with RTL text", async () => {
    renderMetrics("ar");
    expect(await screen.findByText("لا توجد تحليلات بعد")).toBeInTheDocument();
    expect(
      screen.getByText("اربط حساب الإعلانات ومتجرك لبدء قياس الأداء.")
    ).toBeInTheDocument();
  });

  it("renders KPI values and comparison changes", async () => {
    state.summary = summary;
    state.comparison = comparison;
    renderMetrics("en");
    expect(await screen.findByText("$1,250.00")).toBeInTheDocument();
    expect(screen.getByText("$1,000.00")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("$320.00")).toBeInTheDocument();
    expect(screen.getByText("$250.00")).toBeInTheDocument();
    expect(screen.getAllByText(/\+25%/).length).toBeGreaterThan(0);
    expect(screen.getByText(/-16\.67%/)).toBeInTheDocument();
    expect(screen.getByText("1.20×")).toBeInTheDocument();
    expect(screen.getByText("1.25×")).toBeInTheDocument();
  });

  it("marks unavailable measures without inventing zeros", async () => {
    state.summary = {
      ...summary,
      ctr: { value: null, status: "unavailable", reason: "no impressions" },
    };
    renderMetrics("en");
    expect(await screen.findByText("no impressions")).toBeInTheDocument();
  });

  it("renders the funnel and campaign tables", async () => {
    state.summary = summary;
    state.funnel = funnel;
    state.campaigns = campaigns;
    renderMetrics("en");
    expect(await screen.findByText("Campaign 1")).toBeInTheDocument();
    expect(screen.getByText("$100.00")).toBeInTheDocument();
    expect(screen.getByText("3.00×")).toBeInTheDocument();
    expect(screen.getAllByText("Impressions").length).toBeGreaterThan(0);
  });

  it("renders data quality freshness per provider", async () => {
    state.summary = summary;
    state.quality = quality;
    renderMetrics("en");
    expect(await screen.findByText("Fresh")).toBeInTheDocument();
    expect(screen.getByText(/Not connected/)).toBeInTheDocument();
  });
});