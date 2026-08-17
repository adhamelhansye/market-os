import { renderWithI18n, screen } from "../../test/render";
import { describe, it, expect, vi } from "vitest";
import userEvent from "@testing-library/user-event";

import type { BreakEvenRead, SimulationRead } from "./api";
import { SimulationHistory } from "./simulation-history";

type SimulationOverrides = Omit<Partial<SimulationRead>, "break_even"> & {
  break_even?: BreakEvenRead | null;
};

function simulationFixture(overrides: SimulationOverrides = {}): SimulationRead {
  return {
    id: "sim-1",
    business_id: "biz-1",
    organization_id: "org-1",
    entity_type: "business",
    entity_id: null,
    model_version: "1.0.0",
    assumptions_hash: "abc123",
    model_used: "funnel-model",
    calculation_path: "budget → impressions",
    assumptions: [],
    reference_window: {
      kind: "last_n_days",
      start: "2026-07-01",
      end: "2026-07-30",
    },
    scenarios: {
      expected: {
        label: "expected",
        available: true,
        metrics: {
          budget: "1000.00",
          revenue: "3000.00",
          contribution_profit: "800.00",
        },
      },
    },
    break_even: null,
    profitability: {
      status: "profitable",
      roas: "3.00",
      break_even_roas: "1.67",
      contribution_profit: "800.00",
      reason: null,
    },
    sensitivity: [],
    targets: [],
    data_quality: "strong",
    evidence_strength: "strong",
    currency: "USD",
    created_by: "user-1",
    created_at: "2026-08-15T10:00:00Z",
    updated_at: "2026-08-15T10:00:00Z",
    assumptions_snapshot: [],
    results_snapshot: {},
    ...overrides,
  } as SimulationRead;
}

function renderHistory(
  simulations: SimulationRead[],
  onOpen: (id: string) => void = vi.fn(),
  onRerun: (id: string) => void = vi.fn()
) {
  const user = userEvent.setup();
  renderWithI18n(
    <SimulationHistory
      simulations={simulations}
      activeId={null}
      rerunning={false}
      onOpen={onOpen}
      onRerun={onRerun}
    />,
    "en"
  );
  return { user, onOpen, onRerun };
}

describe("SimulationHistory", () => {
  it("shows the empty state when there are no simulations", () => {
    renderHistory([]);
    expect(screen.getByText("No simulations yet — run one above.")).toBeInTheDocument();
  });

  it("renders period, model, budget, expected revenue, profit, profitability and evidence", () => {
    renderHistory([simulationFixture()]);
    expect(screen.getByTestId("simulation-row")).toBeInTheDocument();
    expect(
      screen.getByText((_, el) => el?.textContent === "Model: funnel-model")
    ).toBeInTheDocument();
    expect(
      screen.getByText((_, el) => el?.textContent === "Budget: USD $1,000.00")
    ).toBeInTheDocument();
    expect(
      screen.getByText((_, el) => el?.textContent === "Revenue: $3,000.00")
    ).toBeInTheDocument();
    expect(
      screen.getByText((_, el) => el?.textContent === "Profit: $800.00")
    ).toBeInTheDocument();
    expect(screen.getByTestId("profitability-profitable")).toHaveTextContent("Profitable");
    expect(screen.getByTestId("strength-strong")).toBeInTheDocument();
    expect(screen.getByText(/Aug 15, 2026/)).toBeInTheDocument();
  });

  it("renders the created date in the created_at field", () => {
    renderHistory([simulationFixture()]);
    expect(screen.getByText(/Aug 15, 2026/)).toBeInTheDocument();
  });

  it("fires onOpen when Open is clicked", async () => {
    const onOpen = vi.fn();
    const { user } = renderHistory([simulationFixture()], onOpen);
    await user.click(screen.getByTestId("open-sim-1"));
    expect(onOpen).toHaveBeenCalledWith("sim-1");
  });

  it("fires onRerun when Rerun is clicked", async () => {
    const onRerun = vi.fn();
    const { user } = renderHistory([simulationFixture()], vi.fn(), onRerun);
    await user.click(screen.getByTestId("rerun-sim-1"));
    expect(onRerun).toHaveBeenCalledWith("sim-1");
  });

  it("renders the campaign entity label for campaign simulations", () => {
    renderHistory([
      simulationFixture({ entity_type: "campaign", entity_id: "camp-1" }),
    ]);
    expect(screen.getByText("Campaign · camp-1")).toBeInTheDocument();
  });
});