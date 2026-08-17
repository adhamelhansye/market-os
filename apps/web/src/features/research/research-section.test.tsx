import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { within } from "@testing-library/react";

import { renderWithI18n, screen } from "@/test/render";
import { ResearchSection } from "./research-section";

const state = vi.hoisted(() => ({
  searchResults: new Map<string, any>(),
  projects: {
    projects: [
      {
        id: "p1",
        name: "Q3 competitor scan",
        type: "competitor",
        status: "draft",
        scope: "market scan",
        created_at: "2026-08-15T10:00:00Z",
        updated_at: "2026-08-15T10:00:00Z",
      },
    ],
    total: 1,
  },
  projectDetail: {
    id: "p1",
    name: "Q3 competitor scan",
    type: "competitor",
    status: "draft",
    scope: "market scan",
    created_at: "2026-08-15T10:00:00Z",
    updated_at: "2026-08-15T10:00:00Z",
    source_count: 1,
    evidence_count: 2,
    finding_count: 1,
    competitor_count: 1,
    data_quality: {
      source_count: 1,
      evidence_count: 2,
      finding_count: 1,
      competitor_count: 1,
      coverage: {
        status: "available",
        covered_categories: 2,
        total_categories: 11,
        missing_areas: ["retention"],
      },
      freshness: "2026-08-15T10:00:00Z",
      missing_areas: ["retention"],
    },
  },
  competitors: {
    competitors: [
      {
        id: "c1",
        name: "Acme Inc",
        domain: "acme.example",
        description: "Direct competitor",
        market: "GCC",
        status: "active",
        metadata: {},
        created_at: "2026-08-15T10:00:00Z",
        updated_at: "2026-08-15T10:00:00Z",
      },
    ],
    total: 1,
  },
  sources: {
    sources: [
      {
        id: "s1",
        source_type: "website",
        title: "Acme homepage",
        url: "https://acme.example",
        domain: "acme.example",
        author: null,
        published_at: null,
        captured_at: "2026-08-15T10:00:00Z",
        content_hash: "hash-1",
        metadata: {},
        status: "active",
        competitor_id: "c1",
        created_at: "2026-08-15T10:00:00Z",
        updated_at: "2026-08-15T10:00:00Z",
      },
    ],
    total: 1,
  },
  evidence: {
    evidence: [
      {
        id: "e1",
        source_id: "s1",
        evidence_type: "trust_signal",
        statement: "Free shipping above SAR 200",
        raw_excerpt: "Free shipping above SAR 200",
        structured_value: null,
        unit: null,
        captured_at: "2026-08-15T10:00:00Z",
        classification: "observed",
        provenance: "collected",
        created_at: "2026-08-15T10:00:00Z",
        updated_at: "2026-08-15T10:00:00Z",
      },
      {
        id: "e2",
        source_id: "s1",
        evidence_type: "pricing",
        statement: "SAR 200 threshold",
        raw_excerpt: "SAR 200 threshold",
        structured_value: null,
        unit: null,
        captured_at: "2026-08-15T10:00:00Z",
        classification: "inferred",
        provenance: "analyzed",
        created_at: "2026-08-15T10:00:00Z",
        updated_at: "2026-08-15T10:00:00Z",
      },
    ],
    total: 2,
  },
  findings: {
    findings: [
      {
        id: "f1",
        research_project_id: "p1",
        category: "messaging",
        title: "Free shipping",
        statement: "Free shipping appears in offer copy",
        classification: "inferred",
        importance: "medium",
        evidence_strength: "moderate",
        created_at: "2026-08-15T10:00:00Z",
        updated_at: "2026-08-15T10:00:00Z",
      },
    ],
    total: 1,
  },
  findingDetail: {
    id: "f1",
    research_project_id: "p1",
    category: "messaging",
    title: "Free shipping",
    statement: "Free shipping appears in offer copy",
    classification: "inferred",
    importance: "medium",
    evidence_strength: "moderate",
    created_at: "2026-08-15T10:00:00Z",
    updated_at: "2026-08-15T10:00:00Z",
    evidence: [
      {
        id: "e1",
        source_id: "s1",
        evidence_type: "trust_signal",
        statement: "Free shipping above SAR 200",
        classification: "observed",
        provenance: "collected",
        raw_excerpt: "Free shipping above SAR 200",
      },
      {
        id: "e2",
        source_id: "s1",
        evidence_type: "pricing",
        statement: "SAR 200 threshold",
        classification: "inferred",
        provenance: "analyzed",
        raw_excerpt: "SAR 200 threshold",
      },
    ],
  },
}));

vi.mock("./api", () => ({
  fetchResearchProjects: vi.fn(() => Promise.resolve(state.projects)),
  fetchResearchProject: vi.fn(() => Promise.resolve(state.projectDetail)),
  fetchResearchCompetitors: vi.fn(() => Promise.resolve(state.competitors)),
  fetchResearchSources: vi.fn(() => Promise.resolve(state.sources)),
  fetchResearchEvidence: vi.fn(() => Promise.resolve(state.evidence)),
  fetchResearchFindings: vi.fn(() => Promise.resolve(state.findings)),
  fetchResearchFinding: vi.fn(() => Promise.resolve(state.findingDetail)),
  searchResearchContent: vi.fn((_, query: string) => {
    const hits = state.searchResults.get(query.toLowerCase()) ?? [];
    return Promise.resolve({ hits, total: hits.length });
  }),
}));

function renderSection(locale: "en" | "ar") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return renderWithI18n(
    <QueryClientProvider client={queryClient}>
      <ResearchSection businessId="biz-1" />
    </QueryClientProvider>,
    locale
  );
}

describe("ResearchSection", () => {
  beforeEach(() => {
    state.searchResults = new Map([
      [
        "free shipping",
        [
          {
            entity_type: "evidence",
            entity_id: "e1",
            title: "trust_signal",
            statement: "Free shipping above SAR 200",
            source_id: "s1",
            source_title: "Acme homepage",
            source_domain: "acme.example",
            evidence_type: "trust_signal",
            classification: "observed",
            captured_at: "2026-08-15T10:00:00Z",
          },
          {
            entity_type: "finding",
            entity_id: "f1",
            title: "Free shipping",
            statement: "Free shipping appears in offer copy",
            source_id: null,
            source_title: null,
            source_domain: null,
            evidence_type: null,
            classification: "inferred",
            captured_at: "2026-08-15T10:00:00Z",
          },
        ],
      ],
      [
        "acme inc",
        [
          {
            entity_type: "competitor",
            entity_id: "c1",
            title: "Acme Inc",
            statement: "Direct competitor",
            source_id: null,
            source_title: null,
            source_domain: "acme.example",
            evidence_type: null,
            classification: null,
            captured_at: "2026-08-15T10:00:00Z",
          },
        ],
      ],
    ]);
  });

  it("renders the research dashboard in English", async () => {
    renderSection("en");

    expect(await screen.findByTestId("research-section")).toBeInTheDocument();
    expect(screen.getByText("Research")).toBeInTheDocument();
    expect(await screen.findByText("Q3 competitor scan")).toBeInTheDocument();
    expect((await screen.findAllByText("Acme Inc")).length).toBeGreaterThan(0);
    expect((await screen.findAllByText("Acme homepage")).length).toBeGreaterThan(0);
    expect((await screen.findAllByText("Free shipping above SAR 200")).length).toBeGreaterThan(0);
    expect(await screen.findByText("Free shipping")).toBeInTheDocument();
  });

  it("renders the Arabic dashboard", async () => {
    renderSection("ar");

    expect(await screen.findByText("الأبحاث")).toBeInTheDocument();
    expect((await screen.findAllByText("Acme Inc")).length).toBeGreaterThan(0);
  });

  it("searches and filters evidence deterministically", async () => {
    renderSection("en");

    const evidenceCard = await screen.findByTestId("evidence-list");
    const input = await within(evidenceCard).findByPlaceholderText(
      "Search sources, evidence, findings or competitors"
    );
    await userEvent.type(input, "Free shipping above");

    expect((await within(evidenceCard).findAllByText("Free shipping above SAR 200")).length).toBeGreaterThan(0);
    expect(within(evidenceCard).queryByText("SAR 200 threshold")).toBeNull();
  });

  it("shows combined search results", async () => {
    renderSection("en");

    const searchCard = await screen.findByTestId("research-search");
    const input = await within(searchCard).findByPlaceholderText(
      "Search sources, evidence, findings or competitors"
    );
    await userEvent.type(input, "free shipping");

    expect(await within(searchCard).findByText("Evidence")).toBeInTheDocument();
    expect(await within(searchCard).findByText("Finding")).toBeInTheDocument();
  });

  it("shows the empty state when data is empty", async () => {
    state.projects = { projects: [], total: 0 };
    state.competitors = { competitors: [], total: 0 };
    state.sources = { sources: [], total: 0 };
    state.evidence = { evidence: [], total: 0 };
    state.findings = { findings: [], total: 0 };
    state.searchResults = new Map();

    renderSection("en");

    expect(await screen.findByText("No research projects yet.")).toBeInTheDocument();
    expect(await screen.findByText("No competitors tracked yet.")).toBeInTheDocument();
    expect(await screen.findByText("No research sources yet.")).toBeInTheDocument();
    expect(await screen.findByText("No evidence yet.")).toBeInTheDocument();
    expect(await screen.findByText("No findings yet.")).toBeInTheDocument();
  });
});
