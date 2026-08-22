import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import { renderWithI18n, screen } from "@/test/render";
import { CreativeOptimizationSection } from "./creative-optimization-section";

const summaryAvailable = {
  status: "available",
  optimization_status: "test_ready",
  entities_total: 4,
  entities_sufficient: 4,
  opportunities_total: 2,
  blocked_total: 1,
  by_priority: { high: 1, medium: 1, low: 0 },
  fingerprint: "abcdef1234567890",
  note: "prioritization score is deterministic review ordering; not a probability of success",
};

vi.mock("./api", () => ({
  generateCreativeOptimization: vi.fn(() =>
    Promise.resolve({ business_id: "b1", snapshot_id: "snap-1", created: true })
  ),
  fetchOptimizationSummary: vi.fn(() => Promise.resolve(summaryAvailable)),
  fetchOptimizationSection: vi.fn((_businessId: string, section: string) => {
    if (section === "opportunities") return Promise.resolve(opportunitiesResponse);
    if (section === "blocked") return Promise.resolve(blockedResponse);
    return Promise.resolve({ status: "available", items: [] });
  }),
}));

const opportunitiesResponse = {
  status: "available",
  items: [
    {
      opportunity_id: "expand_supported_angle:angle:winter_hook",
      type: "expand_supported_angle",
      dimension: "angle",
      target_reference: "winter_hook",
      status: "supported_pattern",
      evidence_strength: "strong",
      learning_value: "low",
      priority_score: "5.0",
      priority: "high",
      rationale:
        "Angle 'winter_hook' is associated with stronger observed CTR across 4 sufficiently observed creatives.",
      supporting_entity_ids: ["c-1", "c-2"],
      contradicting_entity_ids: [],
      evidence_count: 2,
      data_sufficiency: "sufficient",
      review_only: true,
    },
  ],
};

const blockedResponse = {
  status: "available",
  items: [
    {
      type: "expand_supported_angle",
      dimension: "angle",
      target_reference: "mixed_angle",
      blocked_by_gate: "conflicting_evidence",
      reason_code: "expansion_blocked",
      statement:
        "Positive association exists but a blocking gate (conflicting_evidence) prevents an expansion recommendation.",
    },
  ],
};

function renderSection(locale: "en" | "ar") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithI18n(
    <QueryClientProvider client={client}>
      <CreativeOptimizationSection businessId="business-1" />
    </QueryClientProvider>,
    locale
  );
}

describe("CreativeOptimizationSection", () => {
  it("renders plan status and priority counts verbatim", async () => {
    renderSection("en");
    expect(await screen.findByTestId("optimization-summary")).toBeInTheDocument();
    expect(screen.getByTestId("optimization-summary")).toHaveTextContent("test_ready");
    expect(screen.getByTestId("optimization-fingerprint")).toHaveTextContent("abcdef123456");
  });

  it("renders opportunities with review_only badges", async () => {
    renderSection("en");
    const list = await screen.findByTestId("optimization-opportunities-list");
    expect(list).toHaveTextContent("expand_supported_angle");
    expect(list).toHaveTextContent("strong · sufficient");
    expect(screen.getAllByTestId("optimization-review-only").length).toBeGreaterThan(0);
  });

  it("renders blocked recommendations with their blocking gate", async () => {
    renderSection("en");
    const list = await screen.findByTestId("optimization-blocked-list");
    expect(list).toHaveTextContent("conflicting_evidence");
    expect(list).toHaveTextContent("mixed_angle");
  });

  it("renders no execution controls for recommendations", async () => {
    renderSection("en");
    await screen.findByTestId("optimization-opportunities-list");
    for (const forbidden of [/execute/i, /apply/i, /pause/i, /kill/i, /scale/i]) {
      expect(screen.queryByRole("button", { name: forbidden })).not.toBeInTheDocument();
    }
  });

  it("renders Arabic labels", async () => {
    renderSection("ar");
    expect(await screen.findByText("ذكاء التحسين")).toBeInTheDocument();
    await screen.findByTestId("optimization-summary");
    expect(screen.getByTestId("optimization-summary")).toHaveTextContent("حالة الخطة");
    expect(await screen.findByText("الفرص ذات الأولوية")).toBeInTheDocument();
  });

  it("renders explicit no-snapshot state before generation", async () => {
    const api = await import("./api");
    (api.fetchOptimizationSummary as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      status: "no_snapshot",
    });
    (
      api.fetchOptimizationSection as unknown as ReturnType<typeof vi.fn>
    ).mockImplementation(() => Promise.resolve({ status: "no_snapshot" }));
    renderSection("en");
    expect(await screen.findByTestId("optimization-empty")).toHaveTextContent(
      /No optimization plan yet/
    );
  });
});
