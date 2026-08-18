import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import { renderWithI18n, screen } from "@/test/render";
import { IntelligencePanel } from "./intelligence-panel";

const response = {
  snapshot_id: "snap-1",
  intelligence_type: "market",
  generated_at: "2026-08-15T10:00:00Z",
  intelligence_version: "research_intelligence_v1",
  items: [
    {
      id: "item-1",
      intelligence_type: "market",
      category: "pricing",
      title: "Pricing signal",
      statement: "Product price is SAR 199.",
      classification: "observed",
      strength: "weak",
      evidence_count: 1,
      source_count: 1,
      freshness: "fresh",
      provenance: [
        {
          finding_id: "finding-1",
          finding_title: "Pricing signal",
          evidence_id: "evidence-1",
          evidence_statement: "Product price is SAR 199.",
          source_id: "source-1",
          source_title: "Product page",
          source_url: "https://example.test/product",
          snapshot_id: "snapshot-1",
          captured_at: "2026-08-15T10:00:00Z",
        },
      ],
    },
  ],
  total: 1,
  freshness: "fresh",
  coverage: {},
  missing_research_areas: [],
};

vi.mock("./api", () => ({
  fetchResearchIntelligenceSummary: vi.fn(() =>
    Promise.resolve({
      snapshot_id: "snap-1",
      generated_at: "2026-08-15T10:00:00Z",
      intelligence_version: "research_intelligence_v1",
      source_count: 1,
      snapshot_count: 1,
      evidence_count: 1,
      finding_count: 1,
      market_signal_count: 1,
      customer_signal_count: 0,
      competitor_count: 0,
      competitor_signal_count: 0,
      freshness: "fresh",
      coverage: {},
      missing_research_areas: [],
    })
  ),
  fetchResearchIntelligence: vi.fn(() => Promise.resolve(response)),
  fetchResearchPricing: vi.fn(() => Promise.resolve({ ...response, pricing: {} })),
  fetchResearchMessaging: vi.fn(() => Promise.resolve({ ...response, items: [], total: 0 })),
}));

function renderPanel(locale: "en" | "ar") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithI18n(
    <QueryClientProvider client={queryClient}>
      <IntelligencePanel businessId="business-1" projectId="project-1" />
    </QueryClientProvider>,
    locale
  );
}

describe("IntelligencePanel", () => {
  it("renders evidence-backed intelligence and provenance in English", async () => {
    renderPanel("en");
    expect(await screen.findByText("Research intelligence")).toBeInTheDocument();
    expect((await screen.findAllByText("Product price is SAR 199.")).length).toBeGreaterThan(0);
    expect((await screen.findAllByText(/Product page/)).length).toBeGreaterThan(0);
  });

  it("renders the intelligence section in Arabic", async () => {
    renderPanel("ar");
    expect(await screen.findByText("ذكاء البحث")).toBeInTheDocument();
    expect(screen.getByText("الحداثة")).toBeInTheDocument();
  });
});
