import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import { renderWithI18n, screen } from "@/test/render";
import { CreativePerformanceSection } from "./creative-performance-section";
import type { PerformanceReportResponse } from "./api";

const report: PerformanceReportResponse = {
  business_id: "business-1",
  currency: "USD",
  range: { kind: "last_30_days", start: "2026-07-23", end: "2026-08-21" },
  rules_versions: {
    engine: "cperf-1",
    fatigue: "cfat-1",
    classification: "cclass-1",
    readiness: "cready-1",
    comparison: "ccmp-1",
  },
  break_even_roas_available: false,
  attribution: { status: "linked", linked_entities: 1 },
  fingerprint: "abc123",
  entities: [
    {
      link_id: "link-1",
      entity: { type: "creative_concept", id: "concept-0001" },
      attribution: { status: "linked", reason: null },
      context: {},
      observation: {
        entity: { type: "creative_concept", id: "concept-0001" },
        range: { kind: "last_30_days" },
        days_covered: 30,
        totals: {},
      },
      signals: [
        {
          code: "impressions",
          value: "30000",
          status: "available",
          reason: null,
          unit: "count",
          source: "meta_reported",
        },
        {
          code: "ctr",
          value: "0.0100",
          status: "available",
          reason: null,
          unit: "ratio",
          source: "derived",
        },
        {
          code: "cvr_meta",
          value: null,
          status: "unavailable",
          reason: "no clicks",
          unit: "ratio",
          source: "meta_reported",
        },
      ],
      trend: { metrics: { ctr: { direction: "rising" } } },
      fatigue: {
        status: "watch",
        signals: [{ code: "ctr_decline", triggered: true }],
      },
      classification: {
        status: "strong",
        rule: "R4_strong",
        reasons: ["CTR at/above low baseline"],
      },
      scaling_readiness: {
        status: "ready_for_review",
        ready_for_review: true,
        gates: [
          { code: "sample_min_spend", met: true, value: "300.00", threshold_value: "100.00" },
        ],
      },
      provenance: {
        chain: [
          { step: "entity", id: "concept-0001" },
          { step: "provider_object", id: "ad-9" },
        ],
      },
    },
  ],
  comparisons: {},
};

vi.mock("./api", () => ({
  fetchCreativePerformanceReport: vi.fn(() => Promise.resolve(report)),
  createCreativePerformanceSnapshot: vi.fn(() =>
    Promise.resolve({ snapshot_id: "snap-1", fingerprint: "abc123def456", created: true })
  ),
}));

function renderSection(locale: "en" | "ar") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithI18n(
    <QueryClientProvider client={client}>
      <CreativePerformanceSection businessId="business-1" />
    </QueryClientProvider>,
    locale
  );
}

describe("CreativePerformanceSection", () => {
  it("renders observed signals with sources and never invents values", async () => {
    renderSection("en");
    expect(await screen.findByTestId("performance-entity")).toBeInTheDocument();
    expect(screen.getByTestId("performance-signals")).toHaveTextContent("impressions");
    expect(screen.getByTestId("performance-signals")).toHaveTextContent("meta_reported");
    expect(screen.getByTestId("performance-signals")).toHaveTextContent("0.0100");
    // Unavailable signal shows explicit state + reason, never a fabricated number.
    expect(screen.getByTestId("performance-signals")).toHaveTextContent(/no clicks/);
  });

  it("renders classification, fatigue and readiness from the payload", async () => {
    renderSection("en");
    expect(await screen.findByTestId("performance-classification")).toHaveTextContent("strong");
    expect(screen.getByTestId("performance-fatigue")).toHaveTextContent("watch");
    expect(screen.getByTestId("performance-fatigue")).toHaveTextContent("ctr_decline");
    expect(screen.getByTestId("performance-readiness")).toHaveTextContent("ready_for_review");
    expect(screen.getByText(/Rule: R4_strong/)).toBeInTheDocument();
  });

  it("renders provenance chain", async () => {
    renderSection("en");
    await screen.findByTestId("performance-entity");
    expect(screen.getByText(/concept-0001 → ad-9/)).toBeInTheDocument();
  });

  it("renders Arabic labels", async () => {
    renderSection("ar");
    expect(await screen.findByText("أداء المحتوى الإبداعي")).toBeInTheDocument();
    await screen.findByTestId("performance-readiness");
    expect(screen.getByTestId("performance-readiness")).toHaveTextContent(
      "جاهزية التوسع (مراجعة فقط)"
    );
    expect(screen.getByTestId("performance-fatigue")).toHaveTextContent("الإرهاق الإعلاني");
  });

  it("renders the unavailable attribution state when nothing is linked", async () => {
    const api = await import("./api");
    (api.fetchCreativePerformanceReport as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ...report,
      attribution: { status: "unavailable", reason: "no_performance_links_recorded", linked_entities: 0 },
      entities: [],
      comparisons: {},
    });
    renderSection("en");
    expect(
      await screen.findByText(/Unavailable — no_performance_links_recorded/)
    ).toBeInTheDocument();
    expect(screen.getByTestId("performance-empty")).toHaveTextContent(/No performance links/);
  });
});
