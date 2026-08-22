import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import { renderWithI18n, screen } from "@/test/render";
import { CreativeLearningSection } from "./creative-learning-section";

vi.mock("./api", () => ({
  generateCreativeLearning: vi.fn(() =>
    Promise.resolve({ business_id: "b1", snapshot_id: "snap-1", created: true })
  ),
  fetchLearningSummary: vi.fn(() => Promise.resolve(summaryAvailable)),
  fetchLearningSection: vi.fn((_businessId: string, section: string) => {
    if (section === "patterns") return Promise.resolve(patternsResponse);
    if (section === "recommendations") return Promise.resolve(recommendationsResponse);
    return Promise.resolve({ status: "available", items: [] });
  }),
}));

const summaryAvailable = {
  status: "available",
  entities_total: 4,
  entities_sufficient: 4,
  patterns_total: 2,
  learnings_total: 1,
  recommendations_total: 2,
  learning_status: "stable",
  fingerprint: "abcdef1234567890",
};

const patternsResponse = {
  status: "available",
  items: [
    {
      dimension: "angle",
      value: "problem_agitation",
      status: "stable",
      dominant_direction: "positive",
      observed_entities: 4,
      evidence_strength: "strong",
    },
  ],
};

const recommendationsResponse = {
  status: "available",
  items: [
    {
      type: "expand_angle",
      reason_code: "positive_angle_association",
      statement:
        "problem_agitation is associated with stronger observed CTR; association observed, not causal.",
      affected: { dimension: "angle", value: "problem_agitation" },
      priority: "high",
      priority_score: "2.0",
      review_only: true,
      status: "informational",
    },
  ],
};

function renderSection(locale: "en" | "ar") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithI18n(
    <QueryClientProvider client={client}>
      <CreativeLearningSection businessId="business-1" />
    </QueryClientProvider>,
    locale
  );
}

describe("CreativeLearningSection", () => {
  it("renders summary counts and fingerprint from the snapshot", async () => {
    renderSection("en");
    expect(await screen.findByTestId("learning-summary")).toBeInTheDocument();
    expect(screen.getByTestId("learning-summary")).toHaveTextContent("Learning status");
    expect(screen.getByTestId("learning-fingerprint")).toHaveTextContent("abcdef123456");
  });

  it("renders observed patterns with status and volume verbatim", async () => {
    renderSection("en");
    expect(await screen.findByTestId("learning-patterns-list")).toBeInTheDocument();
    expect(screen.getAllByTestId("learning-pattern")[0]).toHaveTextContent(
      "angle: problem_agitation"
    );
    expect(screen.getAllByTestId("learning-pattern")[0]).toHaveTextContent("n=4");
    expect(screen.getAllByTestId("learning-pattern")[0]).toHaveTextContent("stable");
  });

  it("renders review-only recommendations and never action buttons", async () => {
    renderSection("en");
    expect(
      await screen.findByTestId("learning-recommendations-list")
    ).toBeInTheDocument();
    const rec = screen.getAllByTestId("learning-recommendation")[0];
    expect(rec).toHaveTextContent("expand_angle");
    expect(rec).toHaveTextContent("review_only");
    // No execution affordance may exist for a recommendation.
    expect(screen.queryByRole("button", { name: /apply/i })).not.toBeInTheDocument();
  });

  it("renders Arabic labels", async () => {
    renderSection("ar");
    expect(await screen.findByText("التعلّم الإبداعي")).toBeInTheDocument();
    await screen.findByTestId("learning-summary");
    expect(screen.getByTestId("learning-summary")).toHaveTextContent("حالة التعلّم");
    expect(await screen.findByText("الأنماط المرصودة")).toBeInTheDocument();
  });

  it("renders explicit no-snapshot state when nothing was generated", async () => {
    const api = await import("./api");
    (api.fetchLearningSummary as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      status: "no_snapshot",
    });
    (
      api.fetchLearningSection as unknown as ReturnType<typeof vi.fn>
    ).mockImplementation(() => Promise.resolve({ status: "no_snapshot" }));
    renderSection("en");
    expect(await screen.findByTestId("learning-empty")).toHaveTextContent(
      /No learning snapshot yet/
    );
    expect(screen.getAllByText(/No learning snapshot yet/).length).toBeGreaterThan(0);
  });
});
