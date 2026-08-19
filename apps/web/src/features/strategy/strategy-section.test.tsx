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

vi.mock("./api", () => ({
  fetchStrategySummary: vi.fn(() => Promise.resolve(summary)),
  createPositioningCandidate: vi.fn(() => Promise.resolve(summary.positioning.candidates[0])),
  recommendPositioning: vi.fn(() => Promise.resolve(summary.positioning)),
  createOfferCandidate: vi.fn(),
  recommendOffer: vi.fn(),
  validateOffer: vi.fn(),
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
  });

  it("renders Arabic labels", async () => {
    renderSection("ar");
    expect(await screen.findByText("أساس الاستراتيجية")).toBeInTheDocument();
    expect(screen.getByText("التموضع")).toBeInTheDocument();
  });
});
