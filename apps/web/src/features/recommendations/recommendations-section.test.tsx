import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithI18n, screen } from "@/test/render";
import type { DecisionsRead } from "@/features/recommendations/api";
import { RecommendationsSection } from "@/features/recommendations/recommendations-section";

import type { RangeKind } from "@/features/metrics/api";

const state = vi.hoisted(() => ({
  decisions: null as DecisionsRead | null,
  error: false,
}));

vi.mock("@/features/recommendations/api", () => ({
  fetchRecommendations: vi.fn(() =>
    state.error ? Promise.reject(new Error("boom")) : Promise.resolve(state.decisions)
  ),
  generateRecommendations: vi.fn(() =>
    Promise.resolve(state.decisions ?? { decisions: [], summary: null })
  ),
}));

const range = {
  kind: "last_30_days" as const,
  start: "2026-07-17",
  end: "2026-08-15",
  previous_start: "2026-06-17",
  previous_end: "2026-07-16",
};

const decisions: DecisionsRead = {
  business_id: "biz-1",
  currency: "USD",
  range,
  decisions: [
    {
      id: "dec-1",
      business_id: "biz-1",
      entity_type: "business",
      entity_name: "Healthy Store",
      decision: "scale_review",
      evidence_strength: "strong",
      primary_reason: "profitable_performance",
      diagnostics: [],
      evidence: {
        primary_reason: "profitable_performance",
        evidence_strength: "strong",
        evidence_items: [],
        diagnostics_refs: [],
        forecast_refs: [],
        goal_refs: [],
      },
      review_suggestions: ["review_additional_budget_allocation"],
      metrics_snapshot: {},
      forecast_snapshot: null,
      range,
      created_at: "2026-08-16T02:39:29.243618Z",
      rules_version: "1.0",
    },
    {
      id: "dec-2",
      business_id: "biz-1",
      entity_type: "campaign",
      entity_name: "Campaign 1",
      decision: "maintain",
      evidence_strength: "moderate",
      primary_reason: "healthy_performance",
      diagnostics: [],
      evidence: {
        primary_reason: "healthy_performance",
        evidence_strength: "moderate",
        evidence_items: [],
        diagnostics_refs: [],
        forecast_refs: [],
        goal_refs: [],
      },
      review_suggestions: [],
      metrics_snapshot: {},
      forecast_snapshot: null,
      range,
      created_at: "2026-08-16T02:39:29.243618Z",
      rules_version: "1.0",
    },
  ],
  summary: {
    business_id: "biz-1",
    total: 2,
    scale_review: 1,
    optimize: 0,
    maintain: 1,
    kill_review: 0,
    learning: 0,
    insufficient_data: 0,
    tracking_issue: 0,
    data_quality_issue: 0,
    by_decision: { scale_review: 1, maintain: 1 },
    by_entity_type: { business: 1, campaign: 1 },
  },
};

function renderSection(
  businessId: string,
  locale: "en" | "ar" = "en",
  rangeKind: RangeKind = "last_30_days"
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return renderWithI18n(
    <QueryClientProvider client={queryClient}>
      <RecommendationsSection businessId={businessId} rangeKind={rangeKind} />
    </QueryClientProvider>,
    locale
  );
}

describe("RecommendationsSection", () => {
  beforeEach(() => {
    state.decisions = null;
    state.error = false;
  });

  it("renders loading state initially", () => {
    renderSection("biz-1");
    expect(screen.getByText(/Loading decisions/)).toBeInTheDocument();
  });

  it("renders decision cards and the review-only note", async () => {
    state.decisions = decisions;
    renderSection("biz-1");

    expect(await screen.findByTestId("review-only-note")).toBeInTheDocument();
    expect(screen.getByTestId("summary-total")).toHaveTextContent("2");
    expect(screen.getByTestId("summary-scale")).toHaveTextContent("1");
    expect(screen.getAllByTestId("decision-card")).toHaveLength(2);
    expect(screen.getByTestId("decision-scale_review")).toBeInTheDocument();
    expect(screen.getByTestId("decision-maintain")).toBeInTheDocument();
    expect(
      screen.getByTestId("suggestion-review_additional_budget_allocation")
    ).toBeInTheDocument();
  });

  it("renders error state on fetch failure", async () => {
    state.error = true;
    renderSection("biz-1");

    expect(await screen.findByText(/Failed to load decisions/)).toBeInTheDocument();
  });

  it("renders empty state when there are no decisions", async () => {
    state.decisions = {
      ...decisions,
      decisions: [],
      summary: { ...decisions.summary, total: 0 },
    };
    renderSection("biz-1");

    expect(await screen.findByText(/No decisions for this period/)).toBeInTheDocument();
  });

  it("renders with Arabic locale", async () => {
    state.decisions = decisions;
    renderSection("biz-1", "ar");

    expect(await screen.findByTestId("review-only-note")).toBeInTheDocument();
    expect(screen.getByTestId("decision-scale_review")).toBeInTheDocument();
  });
});