import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithI18n, screen } from "@/test/render";
import { CreativeActionPreparationSection } from "./creative-action-preparation-section";

const draft = {
  id: "draft-row-1",
  source_opportunity_id: "expand_supported_angle:angle:problem_agitation",
  draft_test_id: "draft_abc123",
  draft_kind: "expansion" as const,
  review_state: "proposed" as const,
  note: null,
};

const reviewMock = vi.fn(() =>
  Promise.resolve({ id: "draft-row-1", review_state: "acknowledged" })
);

vi.mock("./api", () => ({
  generateActionDrafts: vi.fn(() =>
    Promise.resolve({
      business_id: "b1",
      created_count: 1,
      report: { summary: {}, drafts: [], skipped: [], excluded: [] },
    })
  ),
  fetchActionDrafts: vi.fn(() => Promise.resolve([draft])),
  reviewDecisionItem: vi.fn(),
  reviewActionDraft: (...args: unknown[]) => reviewMock(...(args as [])),
}));

function renderSection(locale: "en" | "ar") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithI18n(
    <QueryClientProvider client={client}>
      <CreativeActionPreparationSection businessId="business-1" />
    </QueryClientProvider>,
    locale
  );
}

describe("CreativeActionPreparationSection", () => {
  beforeEach(() => {
    reviewMock.mockClear();
    reviewMock.mockImplementation(() =>
      Promise.resolve({ id: "draft-row-1", review_state: "acknowledged" })
    );
  });

  it("renders the draft with source opportunity and second-stage state", async () => {
    renderSection("en");
    const row = await screen.findByTestId(
      "action-draft-expand_supported_angle:angle:problem_agitation"
    );
    expect(row).toHaveTextContent("Expansion");
    expect(row).toHaveTextContent("proposed");
    expect(row).toHaveTextContent(/Source opportunity/);
    expect(screen.getByTestId("action-review-state")).toBeInTheDocument();
  });

  it("acknowledge calls review with the draft row id", async () => {
    const user = userEvent.setup();
    renderSection("en");
    const button = await screen.findByRole("button", { name: "Acknowledge" });
    await user.click(button);
    expect(reviewMock).toHaveBeenCalledWith("business-1", "draft-row-1", {
      review_state: "acknowledged",
    });
  });

  it("never renders execution controls or winner language", async () => {
    renderSection("en");
    await screen.findByTestId("action-drafts-list");
    // No button may carry execution semantics.
    for (const forbidden of [
      /launch/i,
      /^execute$/i,
      /^approve$/i,
      /^scale$/i,
      /^kill$/i,
    ]) {
      expect(screen.queryByRole("button", { name: forbidden })).not.toBeInTheDocument();
    }
    // No standalone execution/winner claims in text.
    for (const forbidden of [/^launch$/i, /^execute$/i, /winning creative/i]) {
      expect(screen.queryByText(forbidden)).not.toBeInTheDocument();
    }
    expect(screen.getAllByText(/Still a draft - nothing executes/i).length).toBeGreaterThan(0);
  });

  it("renders Arabic labels including draft kinds and actions", async () => {
    renderSection("ar");
    expect(await screen.findByText("تجهيز الإجراءات الإبداعية")).toBeInTheDocument();
    await screen.findByTestId("action-drafts-list");
    expect(screen.getByRole("button", { name: "إقرار" })).toBeInTheDocument();
    expect(screen.getByTestId("action-drafts-list")).toHaveTextContent("توسيع");
    await screen.findByTestId("action-drafts-list");
    expect(screen.getAllByText(/لا تزال مسودة/).length).toBeGreaterThan(0);
  });

  it("renders explicit empty state when no drafts exist", async () => {
    const api = await import("./api");
    (api.fetchActionDrafts as ReturnType<typeof vi.fn>).mockResolvedValueOnce([]);
    renderSection("en");
    expect(await screen.findByTestId("action-empty")).toHaveTextContent(
      /No action drafts yet/
    );
  });
});
