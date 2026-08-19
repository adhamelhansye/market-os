import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api-client";
import { renderWithI18n, screen } from "@/test/render";
import { FunnelSection } from "./funnel-section";

const funnel = {
  id: "funnel-1",
  version: 2,
  funnel_version: "funnel_v1",
  variant: "ecommerce",
  status: "viable",
  positioning_candidate_id: "candidate-1",
  offer_candidate_id: "offer-1",
  strategy_decision_id: null,
  messaging_strategy_id: null,
  input_snapshot: {
    variant: "ecommerce",
    variant_signal: "offer",
    funnel_rules_version: "funnel_rules_v1",
    positioning_candidate_id: "candidate-1",
    offer_candidate_id: "offer-1",
    evidence_ids: ["e-1"],
    metrics_range: { kind: "last_30_days", start: "2026-07-20", end: "2026-08-18", previous_start: "2026-06-20", previous_end: "2026-07-19" },
    business_goal: { status: "available", maximum_cpa: "20.00", target_roas: "2.00", currency: "USD" },
    integrations: { meta: { status: "connected" }, shopify: { status: "recommended" } },
  },
  health: {
    score: "1.0000",
    bucket: "healthy",
    rules_version: "funnel_rules_v1",
    cta_validation: { cta_type: "view_product", basis: "offer product reference", available: true },
    stage_breakdown: {
      awareness: { status: "healthy", weight: "1.0", excluded: false },
      interest: { status: "healthy", weight: "1.0", excluded: false },
      consideration: { status: "healthy", weight: "1.0", excluded: false },
      purchase: { status: "healthy", weight: "1.0", excluded: false },
      retention: { status: "not_configured", weight: null, excluded: true },
    },
    performance_claims: "no_performance_claim",
  },
  stages: [
    {
      id: "stage-awareness",
      stage: "awareness",
      position: 1,
      objective: "Make the business problem visible.",
      audience_state: "Cold, unaware",
      customer_problem: "Manual work",
      customer_desire: null,
      message_direction: "Lead with the customer's documented problem.",
      offer_direction: null,
      content_direction: "Educational",
      cta_type: null,
      entry_condition: {},
      exit_condition: {
        transition: "clicks/impressions",
        target_stage: "interest",
        value: "0.0300",
        status: "available",
        bottleneck: "likely",
        threshold_code: "funnel_low_transition",
        threshold_value: "0.05",
      },
      status: "healthy",
      risks: [],
      evidence_refs: [{ evidence_id: "e-1" }],
      provenance: [],
      channels: [
        {
          id: "ch-1",
          channel: "meta",
          status: "connected",
          role: "primary",
          priority: 1,
          weight: "1.0000",
          rationale: "Broad reach at the top of the funnel.",
          integration_connection_id: "conn-1",
          evidence_refs: [],
        },
      ],
      kpis: [
        { id: "k-1", kpi_code: "impressions", kpi_kind: "metric", role: "primary", status: "available", metric_code: "impressions", value_ref: { value: "2000" }, threshold_code: null, details: { unit: "count" } },
      ],
    },
  ],
  gaps: [
    {
      id: "gap-1",
      gap_type: "transition",
      stage_from: "awareness",
      stage_to: "interest",
      severity: "high",
      title: "Top-of-funnel transition is below threshold",
      description: "The awareness → interest transition sits below the deterministic threshold.",
      evidence: [],
      recommended_direction: "Improve the top-of-funnel message and targeting.",
      status: "open",
    },
  ],
  created_at: "2026-08-18T00:00:00Z",
};

vi.mock("./api", () => ({
  fetchFunnel: vi.fn(() => Promise.resolve(funnel)),
  generateFunnel: vi.fn(() => Promise.resolve({ ...funnel, version: 3 })),
  fetchFunnelVersions: vi.fn(() => Promise.resolve({ versions: [funnel] })),
}));

function renderFunnel(locale: "en" | "ar") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithI18n(<QueryClientProvider client={client}><FunnelSection businessId="business-1" /></QueryClientProvider>, locale);
}

describe("FunnelSection", () => {
  it("renders funnel health, stages, channels, kpis and gaps in English", async () => {
    renderFunnel("en");
    expect(await screen.findByText(/Version 2 · funnel_v1 · viable/)).toBeInTheDocument();
    expect(screen.getByText("Funnel health")).toBeInTheDocument();
    expect(screen.getAllByText(/1\.0000/).length).toBeGreaterThan(0);
    expect(await screen.findByText("Awareness")).toBeInTheDocument();
    expect(screen.getByTestId("funnel-stage-awareness")).toHaveTextContent("Cold, unaware");
    expect(screen.getByTestId("stage-channels-awareness")).toHaveTextContent("meta · primary · connected");
    expect(screen.getByTestId("stage-kpis-awareness")).toHaveTextContent("impressions");
    expect(screen.getByText(/clicks\/impressions/)).toBeInTheDocument();
    expect(screen.getByText(/Bottleneck: likely/)).toBeInTheDocument();
    expect(screen.getByText("Gaps")).toBeInTheDocument();
    expect(screen.getByText(/Top-of-funnel transition is below threshold/)).toBeInTheDocument();
    expect(screen.getByText(/Improve the top-of-funnel message/)).toBeInTheDocument();
    expect(screen.getByText("Input snapshot")).toBeInTheDocument();
    expect(screen.getByTestId("funnel-versions")).toHaveTextContent("2 viable");
  });

  it("renders funnel labels in Arabic", async () => {
    renderFunnel("ar");
    expect(await screen.findByText("استراتيجية القمع")).toBeInTheDocument();
    await screen.findByText(/الإصدار 2 · funnel_v1 · viable/);
    expect(screen.getByText("صحة القمع")).toBeInTheDocument();
    expect(screen.getByText("الوعي")).toBeInTheDocument();
    expect(screen.getByText("الفجوات")).toBeInTheDocument();
    expect(screen.getByText("لقطة المدخلات")).toBeInTheDocument();
  });

  it("renders an empty state when no funnel exists", async () => {
    const { fetchFunnel } = await import("./api");
    (fetchFunnel as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new ApiError(404, "not_found", "not found"));
    renderFunnel("en");
    expect(await screen.findByText(/No funnel strategy yet/)).toBeInTheDocument();
  });

  it("generates a funnel and refreshes the latest version", async () => {
    const user = (await import("@testing-library/user-event")).default;
    const { fetchFunnel, generateFunnel } = await import("./api");
    const generate = generateFunnel as ReturnType<typeof vi.fn>;
    const fetch = fetchFunnel as ReturnType<typeof vi.fn>;
    renderFunnel("en");
    await screen.findByText(/Version 2 · funnel_v1 · viable/);
    fetch.mockResolvedValueOnce({ ...funnel, version: 3 });
    const button = await screen.findByRole("button", { name: "Generate funnel" });
    await user.click(button);
    expect(generate).toHaveBeenCalledWith("business-1");
    expect(await screen.findByText(/Version 3 · funnel_v1 · viable/)).toBeInTheDocument();
  });
});
