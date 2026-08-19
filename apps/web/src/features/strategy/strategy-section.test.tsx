import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import { renderWithI18n, screen } from "@/test/render";
import { StrategySection } from "./strategy-section";

const summary = {
  positioning: {
    strategy_id: "positioning-1",
    version: 1,
    strategy_version: "positioning_v1",
    status: "draft",
    selected_candidate_id: null,
    coverage: {},
    missing_research_areas: [],
    candidates: [{
      id: "candidate-1",
      name: "Problem led",
      candidate_type: "problem_led",
      target_customer: "Owners",
      problem: "Manual work",
      solution: "Operating system",
      differentiator: "Evidence",
      promise: "Clarity",
      supporting_benefits: [],
      proof_points: [],
      objections_addressed: [],
      positioning_statement: "For Owners facing Manual work, Operating system with Evidence, so they can Clarity.",
      classification: "observed",
      strength: "moderate",
      score: "0.8000",
      score_breakdown: {},
      status: "draft",
      assumptions: [],
      risks: [],
      provenance: [{ evidence_id: "e-1", finding_id: "f-1", source_id: "s-1", snapshot_id: "snap-1", source_title: "Review", statement: "Manual work", data_source: "pain_point" }],
      strategy_version: "positioning_v1",
    }],
  },
  offers: { strategy_id: null, version: null, strategy_version: "offer_v1", status: "insufficient_data", selected_candidate_id: null, candidates: [], coverage: {}, missing_research_areas: [] },
  missing_research_areas: [],
};

const decisions = {
  decisions: [{
    id: "decision-1",
    candidate_type: "positioning",
    candidate_id: "candidate-1",
    strategy_version: "positioning_v1",
    decision_rules_version: "strategy_decision_v1",
    status: "needs_evidence",
    overall_score: "0.5000",
    input_snapshot: {},
    evaluation: {
      goal_alignment: "unavailable",
      performance_compatibility: "available",
      forecast_alignment: "unavailable",
      simulation_alignment: "unavailable",
    },
    reasons: [{ type: "research", severity: "medium", statement: "More evidence is required.", source: "research" }],
    provenance: [],
    created_at: "2026-01-01T00:00:00Z",
  }],
};

const messaging = {
  id: "messaging-1",
  version: 2,
  messaging_version: "messaging_v1",
  status: "draft",
  positioning_candidate_id: "candidate-1",
  offer_candidate_id: null,
  strategy_decision_id: null,
  input_snapshot: {},
  core_message: {
    who: "Owners",
    problem: "Manual work",
    desired_outcome: "Clarity",
    solution: "Operating system",
    differentiator: "Evidence",
    promise: "Clarity",
    proof_available: true,
    cta: "view_product",
  },
  quality: {
    missing_components: [],
    performance_attribution: "no_performance_attribution",
    cta_validation: { cta_type: "view_product", available: true, basis: "offer_candidate" },
    unsupported_claims: [{ component_type: "promise", statement: "Best in the world", claims: ["best"], claim_status: "unsupported" }],
    prioritization: [],
    retention_directions: [],
    competitor_messaging: {
      patterns: [{ pattern: "shipping", frequency: 3, saturation: "common", competitor_ids: ["c-1"] }],
      whitespace_claim: "no_performance_claim",
    },
  },
  components: [
    {
      id: "comp-1",
      component_type: "objection",
      statement: "Too expensive",
      classification: "observed",
      strength: "strong",
      claim_status: "supported",
      status: "available",
      funnel_stage: "consideration",
      details: { response_available: true, response: "TCO study" },
      evidence_refs: [],
      provenance: [],
    },
    {
      id: "comp-2",
      component_type: "cta",
      statement: "View product",
      classification: "inferred",
      strength: "moderate",
      claim_status: "unknown",
      status: "available",
      funnel_stage: "purchase",
      details: {},
      evidence_refs: [],
      provenance: [],
    },
  ],
  angles: [
    {
      id: "angle-1",
      name: "Problem led",
      angle_type: "problem_led",
      core_message: "Manual work drains owners.",
      hook_direction: "Lead with the customer's documented problem.",
      supporting_points: ["Evidence"],
      cta_type: "view_product",
      funnel_stage: "awareness",
      strength: "moderate",
      status: "no_performance_attribution",
      evidence_refs: [],
    },
  ],
  created_at: "2026-01-01T00:00:00Z",
};

const messagingVersions = { versions: [{ ...messaging, id: "messaging-0", version: 1, status: "insufficient_data" }, messaging] };

const funnel = {
  id: "funnel-1",
  version: 1,
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
    evidence_ids: [],
    metrics_range: { kind: "last_30_days", start: "2026-07-20", end: "2026-08-18", previous_start: "2026-06-20", previous_end: "2026-07-19" },
    business_goal: { status: "unavailable", reason: "No active business goal exists." },
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
      evidence_refs: [],
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
    {
      id: "stage-purchase",
      stage: "purchase",
      position: 4,
      objective: "Convert consideration into a transaction.",
      audience_state: "Ready to buy",
      customer_problem: null,
      customer_desire: "Clarity",
      message_direction: "Direct product and offer message.",
      offer_direction: "Promote the standard offer.",
      content_direction: "Transactional",
      cta_type: "view_product",
      entry_condition: {},
      exit_condition: {},
      status: "healthy",
      risks: [],
      evidence_refs: [],
      provenance: [],
      channels: [
        {
          id: "ch-2",
          channel: "shopify",
          status: "recommended",
          role: "primary",
          priority: 1,
          weight: "1.0000",
          rationale: "Commerce conversion channel.",
          integration_connection_id: null,
          evidence_refs: [],
        },
      ],
      kpis: [
        { id: "k-2", kpi_code: "purchases", kpi_kind: "metric", role: "primary", status: "available", metric_code: "purchases", value_ref: { value: "2" }, threshold_code: null, details: { unit: "count" } },
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

const funnelVersions = { versions: [funnel] };

vi.mock("./api", () => ({
  fetchStrategySummary: vi.fn(() => Promise.resolve(summary)),
  createPositioningCandidate: vi.fn(() => Promise.resolve(summary.positioning.candidates[0])),
  recommendPositioning: vi.fn(() => Promise.resolve(summary.positioning)),
  createOfferCandidate: vi.fn(),
  recommendOffer: vi.fn(),
  validateOffer: vi.fn(),
  fetchStrategyDecisions: vi.fn(() => Promise.resolve(decisions)),
  evaluateStrategyDecision: vi.fn(),
  fetchMessaging: vi.fn(() => Promise.resolve(messaging)),
  generateMessaging: vi.fn(() => Promise.resolve(messaging)),
  fetchMessagingVersions: vi.fn(() => Promise.resolve(messagingVersions)),
  fetchFunnel: vi.fn(() => Promise.resolve(funnel)),
  generateFunnel: vi.fn(() => Promise.resolve(funnel)),
  fetchFunnelVersions: vi.fn(() => Promise.resolve(funnelVersions)),
}));

function renderSection(locale: "en" | "ar") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithI18n(<QueryClientProvider client={client}><StrategySection businessId="business-1" /></QueryClientProvider>, locale);
}

describe("StrategySection", () => {
  it("renders positioning, economics area and provenance in English", async () => {
    renderSection("en");
    expect(await screen.findByText("Strategy foundation")).toBeInTheDocument();
    expect(await screen.findByText("Problem led")).toBeInTheDocument();
    expect(screen.getByText(/Review/)).toBeInTheDocument();
    expect(screen.getByText("No strategy candidates yet.")).toBeInTheDocument();
    expect(await screen.findByText("Strategy decisions")).toBeInTheDocument();
    expect(screen.getByText(/More evidence is required/)).toBeInTheDocument();
  });

  it("renders Arabic labels", async () => {
    renderSection("ar");
    expect(await screen.findByText("أساس الاستراتيجية")).toBeInTheDocument();
    expect(screen.getByText("التموضع")).toBeInTheDocument();
    expect(await screen.findByText("قرارات الاستراتيجية")).toBeInTheDocument();
  });

  it("renders messaging strategy, core message, angles and claim validation in English", async () => {
    renderSection("en");
    expect(await screen.findByText("Messaging strategy")).toBeInTheDocument();
    expect(await screen.findByText(/Version 2 · messaging_v1 · draft/)).toBeInTheDocument();
    expect(await screen.findByTestId("core-message")).toHaveTextContent("Operating system");
    expect(screen.getByText(/Manual work drains owners/)).toBeInTheDocument();
    expect(screen.getByText(/TCO study/)).toBeInTheDocument();
    expect(screen.getByText(/Claim validation/)).toBeInTheDocument();
    expect(screen.getByText(/shipping \(common\)/)).toBeInTheDocument();
    expect(screen.getByText(/1 insufficient_data · 2 draft/)).toBeInTheDocument();
  });

  it("renders messaging strategy labels in Arabic", async () => {
    renderSection("ar");
    expect(await screen.findByText("استراتيجية الرسائل")).toBeInTheDocument();
    expect(await screen.findByText("اتجاهات الرسائل")).toBeInTheDocument();
    expect(screen.getByText("التحقق من الادعاءات")).toBeInTheDocument();
    expect(screen.getByText(/الاعتراض/)).toBeInTheDocument();
  });
});
