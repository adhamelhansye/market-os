import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithI18n, screen } from "@/test/render";
import { CreativeActionPreparationSection } from "./creative-action-preparation-section";

const acknowledgedDraft = {
  id: "draft-row-1",
  source_opportunity_id: "expand_supported_angle:angle:C",
  draft_test_id: "draft_abc123",
  draft_kind: "expansion" as const,
  review_state: "acknowledged" as const,
  note: null,
};

const activateMock = vi.fn(() =>
  Promise.resolve({ id: "draft-row-1", review_state: "acknowledged" })
);

vi.mock("./api", () => ({
  generateActionDrafts: vi.fn(),
  reviewActionDraft: vi.fn(),
  fetchActionDrafts: vi.fn(() => Promise.resolve([acknowledgedDraft])),
  activateCreativeTest: (...args: unknown[]) =>
    activateMock(...(args as [])),
  fetchLifecycleHistory: vi.fn(() => Promise.resolve([])),
  transitionCreativeTestLifecycle: vi.fn(() =>
    Promise.resolve({ previous_status: "active", new_status: "completed" })
  ),
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

describe("Activation controls (Phase 8H)", () => {
  beforeEach(() => {
    activateMock.mockClear();
    activateMock.mockImplementation(() =>
      Promise.resolve({ id: "draft-row-1", review_state: "acknowledged" })
    );
  });

  it("shows Activate only for acknowledged drafts and calls the API with the row id", async () => {
    const user = userEvent.setup();
    renderSection("en");
    const button = await screen.findByTestId(
      "action-activate-draft-row-1"
    );
    await user.click(button);
    expect(activateMock).toHaveBeenCalledWith("business-1", "draft-row-1");
  });

  it("shows lifecycle transitions once events exist", async () => {
    const api = await import("./api");
    // Post-activation state: an event row exists for this test.
    (api.fetchLifecycleHistory as ReturnType<typeof vi.fn>).mockResolvedValue([
      {
        id: "evt-1",
        creative_test_external_ref: "draft_abc123",
        previous_status: "active",
        new_status: "active",
        source_opportunity_id: "op-1",
        source_plan_fingerprint: "fp",
        created_at: "2026-01-01T00:00:00Z",
      },
    ]);
    const user = userEvent.setup();
    renderSection("en");
    // Activation still available per review state; click it (no-op on mocks).
    const button = await screen.findByTestId("action-activate-draft-row-1");
    await user.click(button);
    await vi.waitFor(() => {
      expect(screen.getByTestId("activation-controls")).toBeInTheDocument();
    });
    const controls = screen.getByTestId("activation-controls");
    expect(controls).toHaveTextContent("active");
    expect(controls).toHaveTextContent("active -> active");
    expect(screen.getByRole("button", { name: "Mark completed" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mark cancelled" })).toBeInTheDocument();
  });

  it("renders Arabic activation label", async () => {
    renderSection("ar");
    expect(
      await screen.findByRole("button", { name: "تنشيط الاختبار" })
    ).toBeInTheDocument();
  });
});
