import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithI18n, screen } from "@/test/render";
import { CreativeDecisionPlanSection } from "./creative-decision-plan-section";

const summaryAvailable = {
  status: "available",
  plan_status: "ready_for_review",
  total_items: 1,
  blocked_count: 0,
  fingerprint: "abcdef1234567890",
  rules_version: "cdecision-v1",
  source_optimization_fingerprint: "opt1234567890",
  review_progress: {
    proposed: 1,
    acknowledged: 0,
    dismissed: 0,
    deferred: 0,
    total_items: 1,
    reviewed_items: 0,
    remaining_items: 1,
  },
};

const itemsResponse = {
  status: "available",
  items: [
    {
      opportunity_id: "expand_supported_angle:angle:C",
      type: "expand_supported_angle",
      dimension: "angle",
      target_reference: "C",
      priority: "high",
      priority_score: "5.0",
      evidence_strength: "strong",
      learning_value: "low",
      rationale: "associated with stronger observed CTR; association observed, not causal.",
      data_sufficiency: "sufficient",
      review_only: true,
      execution_status: "not_executed",
      review_state: "proposed",
      suggested_review_focus: "draft creative test per 8B taxonomy",
    },
  ],
};

const reviewMock = vi.fn(() =>
  Promise.resolve({ id: "r-1", review_state: "acknowledged" })
);

vi.mock("./api", () => ({
  generateDecisionPlan: vi.fn(() =>
    Promise.resolve({ business_id: "b1", snapshot_id: "s-1", created: true })
  ),
  fetchDecisionPlanSummary: vi.fn(() => Promise.resolve(summaryAvailable)),
  fetchDecisionPlanItems: vi.fn(() => Promise.resolve(itemsResponse)),
  reviewDecisionItem: (...args: unknown[]) => reviewMock(...(args as [])),
}));

function renderSection(locale: "en" | "ar") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithI18n(
    <QueryClientProvider client={client}>
      <CreativeDecisionPlanSection businessId="business-1" />
    </QueryClientProvider>,
    locale
  );
}

describe("CreativeDecisionPlanSection", () => {
  beforeEach(() => {
    reviewMock.mockClear();
    reviewMock.mockImplementation(() =>
      Promise.resolve({ id: "r-1", review_state: "acknowledged" })
    );
  });

  it("renders plan status, item counts and fingerprints verbatim", async () => {
    renderSection("en");
    expect(await screen.findByTestId("decision-summary")).toBeInTheDocument();
    expect(screen.getByTestId("decision-summary")).toHaveTextContent("ready_for_review");
    expect(screen.getByTestId("decision-fingerprint")).toHaveTextContent("abcdef123456");
    expect(screen.getByTestId("decision-summary")).toHaveTextContent("opt123456789");
  });

  it("renders items with proposed state, focus and review_only badge", async () => {
    renderSection("en");
    const list = await screen.findByTestId("decision-items-list");
    expect(list).toHaveTextContent("expand_supported_angle");
    expect(list).toHaveTextContent("proposed");
    expect(list).toHaveTextContent("draft creative test per 8B taxonomy");
    expect(list).toHaveTextContent("review_only");
    expect(list).toHaveTextContent(/not causal/);
  });

  it("acknowledge writes review state and never implies execution", async () => {
    const user = userEvent.setup();
    renderSection("en");
    const button = await screen.findByRole("button", { name: "Acknowledge" });
    await user.click(button);
    expect(reviewMock).toHaveBeenCalledWith(
      "business-1",
      "expand_supported_angle:angle:C",
      { review_state: "acknowledged" }
    );
    // No execution-flavoured controls may exist.
    for (const forbidden of [/approve/i, /apply/i, /implement/i, /execute/i, /launch/i]) {
      expect(screen.queryByRole("button", { name: forbidden })).not.toBeInTheDocument();
    }
    expect(screen.getAllByText(/Review only - nothing executes/i).length).toBeGreaterThan(0);
  });

  it("renders Arabic labels", async () => {
    renderSection("ar");
    expect(await screen.findByText("خطة القرار")).toBeInTheDocument();
    await screen.findByTestId("decision-items-list");
    expect(screen.getByRole("button", { name: "إقرار" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "تجاهل" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "تأجيل" })).toBeInTheDocument();
  });

  it("renders explicit empty state when no optimization snapshot exists", async () => {
    const api = await import("./api");
    (api.fetchDecisionPlanSummary as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      status: "no_snapshot",
    });
    (
      api.fetchDecisionPlanItems as ReturnType<typeof vi.fn>
    ).mockResolvedValueOnce({ status: "no_snapshot" });
    renderSection("en");
    expect(await screen.findByTestId("decision-empty")).toHaveTextContent(
      /No decision plan yet/
    );
  });
});
