import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import { renderWithI18n, screen } from "@/test/render";
import { CreativeTestReportSection } from "./creative-test-report-section";

const report = {
  rules_versions: { report: "creport-v1" },
  test: {
    test_id: "draft_abc123",
    name: "Draft test - expand_supported_angle - C",
    objective: "awareness",
    status: "active",
    hypothesis: "Observe whether supported value holds",
  },
  lifecycle: {
    current_status: "active",
    events: [
      { previous_status: "draft", new_status: "active", source_opportunity_id: "op-1" },
    ],
  },
  measurement: {
    observation_status: "sufficient",
    days_observed_max: 30,
    entities: [
      {
        entity_id: "concept-0001",
        attribution: { status: "linked" },
        observation_status: "sufficient",
        signals: [
          { code: "ctr", value: "0.0100", status: "available", source: "derived" },
          { code: "cpc", value: null, status: "unavailable", reason: "no clicks", source: "derived" },
        ],
        fatigue: { status: "healthy" },
        classification: { status: "strong" },
      },
    ],
  },
  learning: {
    status: "available",
    learnings: [
      { statement: "problem_agitation is associated with stronger observed CTR; not causal." },
    ],
  },
  completion_note: "Completion is a human decision.",
};

vi.mock("./api", () => ({
  fetchActionDrafts: vi.fn(() =>
    Promise.resolve([
      {
        id: "row-1",
        source_opportunity_id: "op-1",
        draft_test_id: "draft_abc123",
        draft_kind: "expansion" as const,
        review_state: "acknowledged" as const,
        note: null,
      },
    ])
  ),
  generateActionDrafts: vi.fn(),
  reviewActionDraft: vi.fn(),
  activateCreativeTest: vi.fn(),
  transitionCreativeTestLifecycle: vi.fn(),
  fetchLifecycleHistory: vi.fn(() => Promise.resolve([])),
  fetchTestReport: vi.fn(() => Promise.resolve(report)),
}));

function renderSection(locale: "en" | "ar") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithI18n(
    <QueryClientProvider client={client}>
      <CreativeTestReportSection businessId="business-1" />
    </QueryClientProvider>,
    locale
  );
}

describe("CreativeTestReportSection", () => {
  it("renders lifecycle status and observation sufficiency verbatim", async () => {
    renderSection("en");
    const panel = await screen.findByTestId("test-report-panel");
    expect(panel).toHaveTextContent("active");
    expect(panel).toHaveTextContent("sufficient");
    expect(panel).toHaveTextContent("human decision");
  });

  it("renders canonical 8C signals with unavailable states explicit", async () => {
    renderSection("en");
    const signals = await screen.findByTestId("report-signals");
    expect(signals).toHaveTextContent("0.0100"); // available
    expect(signals).toHaveTextContent("unavailable"); // cpc missing
  });

  it("renders fatigue, classification and learning blocks", async () => {
    renderSection("en");
    await screen.findByTestId("report-signals");
    expect(screen.getByTestId("report-learning")).toHaveTextContent(
      /associated with stronger observed CTR/
    );
  });

  it("renders Arabic labels", async () => {
    renderSection("ar");
    expect(await screen.findByText("تقرير الاختبار")).toBeInTheDocument();
    await screen.findByTestId("test-report-panel");
    expect(screen.getByTestId("report-learning")).toHaveTextContent("التعلّم");
  });

  it("renders empty state when no drafts exist", async () => {
    const api = await import("./api");
    (api.fetchActionDrafts as ReturnType<typeof vi.fn>).mockResolvedValueOnce([]);
    renderSection("en");
    expect(await screen.findByTestId("report-empty")).toBeInTheDocument();
  });
});
