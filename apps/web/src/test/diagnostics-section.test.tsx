import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithI18n, screen } from "@/test/render";
import type { DiagnosticsRead } from "@/features/diagnostics/api";
import { DiagnosticsSection } from "@/features/diagnostics/diagnostics-section";

const state = vi.hoisted(() => ({
  diagnostics: null as DiagnosticsRead | null,
  error: false,
}));

vi.mock("@/features/diagnostics/api", () => ({
  fetchDiagnostics: vi.fn(() =>
    state.error ? Promise.reject(new Error("boom")) : Promise.resolve(state.diagnostics)
  ),
}));

function renderSection(locale: "en" | "ar") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return renderWithI18n(
    <QueryClientProvider client={queryClient}>
      <DiagnosticsSection businessId="biz-1" rangeKind="last_30_days" />
    </QueryClientProvider>,
    locale
  );
}

const range = {
  kind: "last_30_days",
  start: "2026-07-16",
  end: "2026-08-14",
  previous_start: "2026-06-15",
  previous_end: "2026-07-15",
};

const diagnostics: DiagnosticsRead = {
  business_id: "biz-1",
  currency: "USD",
  timezone: "UTC",
  range,
  summary: {
    total_findings: 3,
    critical: 0,
    high: 1,
    medium: 0,
    low: 1,
    info: 1,
    insufficient_data: 1,
    affected_entities: 2,
  },
  findings: [
    {
      id: "f1",
      business_id: "biz-1",
      business_name: "Test Business",
      entity_type: "business",
      entity_id: null,
      entity_name: null,
      category: "tracking",
      code: "provider_conversion_mismatch",
      severity: "low",
      status: "detected",
      title_key: "diagnostics.provider_conversion_mismatch.title",
      description_key: "diagnostics.provider_conversion_mismatch.description",
      reason: null,
      evidence: {
        metric: { code: "conversions", current: "8", previous: "4" },
        threshold: { code: "conversion_mismatch_percent", operator: "gte", value: "50", unit: "percent" },
        comparison: null,
        funnel: null,
        facts: [
          { code: "conversions", value: "8", unit: "count" },
          { code: "purchases", value: "4", unit: "count" },
        ],
      },
      affected_stage: "purchase",
      range,
      currency: "USD",
      review_status: null,
    },
    {
      id: "f2",
      business_id: "biz-1",
      business_name: "Test Business",
      entity_type: "campaign",
      entity_id: "camp-1",
      entity_name: "Campaign 1",
      category: "performance",
      code: "high_cpc",
      severity: "high",
      status: "detected",
      title_key: "diagnostics.high_cpc.title",
      description_key: "diagnostics.high_cpc.description",
      reason: null,
      evidence: {
        metric: { code: "cpc", current: "12.50", previous: null },
        threshold: { code: "cpc_high", operator: "gt", value: "10.00", unit: "money" },
        comparison: null,
        funnel: null,
        facts: [{ code: "impressions", value: "1000", unit: "count" }],
      },
      affected_stage: null,
      range,
      currency: "USD",
      review_status: null,
    },
    {
      id: "f3",
      business_id: "biz-1",
      business_name: "Test Business",
      entity_type: "campaign",
      entity_id: "camp-1",
      entity_name: "Campaign 1",
      category: "performance",
      code: "high_cpa",
      severity: "info",
      status: "insufficient_data",
      title_key: "diagnostics.high_cpa.title",
      description_key: "diagnostics.high_cpa.description",
      reason: "insufficient purchases sample: 2 < 3",
      evidence: {
        metric: { code: "purchases", current: "2", previous: null },
        threshold: { code: "sample_min_purchases", operator: "lt", value: "3", unit: "count" },
        comparison: null,
        funnel: null,
        facts: [],
      },
      affected_stage: null,
      range,
      currency: "USD",
      review_status: null,
    },
    {
      id: "f4",
      business_id: "biz-1",
      business_name: "Test Business",
      entity_type: "business",
      entity_id: null,
      entity_name: null,
      category: "data_quality",
      code: "recent_sync_failures",
      severity: "medium",
      status: "detected",
      title_key: "diagnostics.recent_sync_failures.title",
      description_key: "diagnostics.recent_sync_failures.description",
      reason: null,
      evidence: { metric: null, threshold: null, comparison: null, funnel: null, facts: [] },
      affected_stage: null,
      range,
      currency: "USD",
      review_status: "review_required",
    },
    {
      id: "f5",
      business_id: "biz-1",
      business_name: "Test Business",
      entity_type: "business",
      entity_id: null,
      entity_name: null,
      category: "funnel",
      code: "funnel_bottleneck",
      severity: "medium",
      status: "detected",
      title_key: "diagnostics.funnel_bottleneck.title",
      description_key: "diagnostics.funnel_bottleneck.description",
      reason: null,
      evidence: {
        metric: null,
        threshold: { code: "funnel_low_transition", operator: "lt", value: "0.05", unit: "ratio" },
        comparison: null,
        funnel: { from_stage: "landing_page_views", to_stage: "purchases", conversion_rate: "0.0167", previous_rate: "0.05" },
        facts: [],
      },
      affected_stage: "purchase",
      range,
      currency: "USD",
      review_status: null,
    },
  ],
  campaign_states: [
    {
      campaign_id: "camp-1",
      name: "Campaign 1",
      performance_state: "attention",
      scaling_readiness: {
        status: "insufficient_data",
        ready_for_review: false,
        gates: [
          { code: "spend", value: "120.00", unit: "money" },
          { code: "impressions", value: "1200", unit: "count" },
          { code: "days", value: "1", unit: "count" },
          { code: "conversions", value: "3", unit: "count" },
        ],
      },
      finding_count: 2,
      highest_severity: "high",
    },
  ],
};

describe("DiagnosticsSection", () => {
  beforeEach(() => {
    state.diagnostics = diagnostics;
    state.error = false;
  });

  it("renders overview counts from the summary", async () => {
    renderSection("en");
    expect(await screen.findByTestId("summary-total")).toHaveTextContent("3");
    expect(screen.getByTestId("summary-critical")).toHaveTextContent("0");
    expect(screen.getByTestId("summary-entities")).toHaveTextContent("2");
    expect(screen.getByTestId("summary-insufficient")).toHaveTextContent("1");
  });

  it("renders finding cards with severity, title, threshold and facts", async () => {
    renderSection("en");
    await screen.findByTestId("findings-list");
    expect(await screen.findByText("Provider conversions vs purchases")).toBeInTheDocument();
    expect(screen.getAllByTestId("finding-card").length).toBe(5);
    expect(screen.getByTestId("severity-low")).toBeInTheDocument();
    expect(screen.getAllByTestId("severity-high").length).toBeGreaterThan(0);
    expect(
      screen.getAllByTestId("threshold-value").some((el) => (el.textContent ?? "").includes("10.00"))
    ).toBe(true);
    expect(screen.getAllByTestId("fact-impressions").length).toBeGreaterThan(0);
  });

  it("shows insufficient-data findings distinctly", async () => {
    renderSection("en");
    expect(await screen.findByText("Cost per acquisition above target")).toBeInTheDocument();
    expect(screen.getByTestId("severity-info")).toBeInTheDocument();
  });

  it("shows the funnel bottleneck highlight with stage transition", async () => {
    renderSection("en");
    const bottleneck = await screen.findByTestId("funnel-bottleneck");
    expect(bottleneck).toHaveTextContent("landing_page_views");
    expect(bottleneck).toHaveTextContent("purchases");
  });

  it("shows the empty state when there are no findings", async () => {
    state.diagnostics = { ...diagnostics, findings: [], campaign_states: [], summary: { ...diagnostics.summary, total_findings: 0, affected_entities: 0 } };
    renderSection("en");
    expect(await screen.findByText("No findings for the selected filters.")).toBeInTheDocument();
    expect(screen.getByText("No campaign data for this period.")).toBeInTheDocument();
    expect(screen.getByText("No data quality warnings.")).toBeInTheDocument();
  });

  it("shows the loading state while pending", async () => {
    state.diagnostics = null;
    renderSection("en");
    expect(screen.getByText("Loading diagnostics…")).toBeInTheDocument();
  });

  it("shows an error state with retry", async () => {
    state.error = true;
    renderSection("en");
    expect(await screen.findByText("Could not load diagnostics.")).toBeInTheDocument();
    expect(screen.getByText("Retry")).toBeInTheDocument();
  });

  it("renders Arabic translations with the same structure", async () => {
    renderSection("ar");
    expect(await screen.findByTestId("summary-total")).toHaveTextContent("3");
    expect(await screen.findByText("تحويلات المزوّد مقابل المشتريات")).toBeInTheDocument();
  });
});