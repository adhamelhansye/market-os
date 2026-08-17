import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithI18n, screen } from "@/test/render";
import { ProjectsPanel } from "./projects-panel";

const state = vi.hoisted(() => ({
  loading: false,
  error: false,
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
}));

vi.mock("./api", () => ({
  fetchResearchProjects: vi.fn(() => {
    if (state.loading) return new Promise(() => undefined);
    if (state.error) return Promise.reject(new Error("boom"));
    return Promise.resolve(state.projects);
  }),
  createResearchProject: vi.fn(),
  setResearchProjectStatus: vi.fn(),
}));

function renderPanel(locale: "en" | "ar") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return renderWithI18n(
    <QueryClientProvider client={queryClient}>
      <ProjectsPanel businessId="biz-1" />
    </QueryClientProvider>,
    locale
  );
}

describe("ProjectsPanel", () => {
  beforeEach(() => {
    state.loading = false;
    state.error = false;
    state.projects = {
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
    };
  });

  it("shows the loading state", async () => {
    state.loading = true;
    renderPanel("en");
    expect(screen.getByText("Loading research data…")).toBeInTheDocument();
  });

  it("shows the error state", async () => {
    state.error = true;
    renderPanel("en");
    expect(await screen.findByText("Failed to load research data.")).toBeInTheDocument();
  });

  it("shows the empty state when there are no projects", async () => {
    state.projects = { projects: [], total: 0 };
    renderPanel("en");
    expect(await screen.findByText("No research projects yet.")).toBeInTheDocument();
  });

  it("renders project rows in Arabic", async () => {
    renderPanel("ar");
    expect(await screen.findByText("Q3 competitor scan")).toBeInTheDocument();
    expect(screen.getByText("مشروع جديد")).toBeInTheDocument();
  });
});
