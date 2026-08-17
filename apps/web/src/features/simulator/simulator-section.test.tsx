import { renderWithI18n, screen } from "../../test/render";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { SimulationRead, SimulationSummaryRead } from "./api";

import { SimulatorSection } from "./simulator-section";

const hooks = vi.hoisted(() => ({
  fetchSimulations: vi.fn(),
  createSimulation: vi.fn(),
  simulateCampaign: vi.fn(),
  rerunSimulation: vi.fn(),
  fetchMetricsCampaigns: vi.fn(),
}));

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return {
    ...actual,
    fetchSimulations: hooks.fetchSimulations,
    createSimulation: hooks.createSimulation,
    simulateCampaign: hooks.simulateCampaign,
    rerunSimulation: hooks.rerunSimulation,
  };
});

vi.mock("@/features/metrics/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/metrics/api")>();
  return {
    ...actual,
    fetchMetricsCampaigns: hooks.fetchMetricsCampaigns,
  };
});

function simulationFixture(overrides: Partial<SimulationRead> = {}): SimulationRead {
  return {
    id: "sim-1",
    business_id: "biz-1",
    organization_id: "org-1",
    entity_type: "business",
    entity_id: null,
    model_version: "1.0.0",
    assumptions_hash: "abc123",
    model_used: "funnel-model",
    calculation_path: "budget → impressions → clicks → purchases → revenue",
    assumptions: [
      {
        name: "ctr",
        value: "0.0100",
        unit: "",
        source: "campaign_history",
        source_entity: "campaign",
        historical_value: "0.0090",
        override: false,
        confidence: "strong",
      },
      {
        name: "budget",
        value: "1000.00",
        unit: "",
        source: "user_input",
        source_entity: null,
        historical_value: null,
        override: false,
        confidence: "strong",
      },
    ],
    reference_window: {
      kind: "last_n_days",
      start: "2026-07-01",
      end: "2026-07-30",
    },
    scenarios: {
      downside: {
        label: "downside",
        available: true,
        metrics: {
          budget: "1000.00",
          impressions: 100000,
          clicks: 1000,
          purchases: 20,
          revenue: "2000.00",
          roas: "2.00",
          cpa: "50.00",
          ctr: "0.0100",
          contribution_profit: "500.00",
        },
      },
      expected: {
        label: "expected",
        available: true,
        metrics: {
          budget: "1000.00",
          impressions: 120000,
          clicks: 1200,
          purchases: 30,
          revenue: "3000.00",
          roas: "3.00",
          cpa: "33.33",
          ctr: "0.0100",
          contribution_profit: "800.00",
        },
      },
      upside: {
        label: "upside",
        available: true,
        metrics: {
          budget: "1000.00",
          impressions: 140000,
          clicks: 1500,
          purchases: 45,
          revenue: "4500.00",
          roas: "4.50",
          cpa: "22.22",
          ctr: "0.0100",
          contribution_profit: "1200.00",
        },
      },
    },
    break_even: {
      break_even_cpa: "60.00",
      break_even_roas: "1.67",
      simulated_cpa: "33.33",
      simulated_roas: "3.00",
      minimum_cvr: "0.0050",
      maximum_cpc: "0.50",
      minimum_aov: "30.00",
      maximum_cpa: "60.00",
      minimum_roas: "1.67",
    },
    profitability: {
      status: "profitable",
      roas: "3.00",
      break_even_roas: "1.67",
      contribution_profit: "800.00",
      reason: null,
    },
    sensitivity: [
      {
        variable: "ctr",
        baseline_profit: "800.00",
        rows: [
          { variable: "ctr", change_percent: "-0.20", new_value: "0.0080", revenue: "2400.00", profit: "400.00", cpa: "41.00", roas: "2.40" },
        ],
      },
    ],
    targets: [
      { metric_code: "cpa", target_value: "40.00", simulated_value: "33.33", status: "met", reason: null },
    ],
    data_quality: "strong",
    evidence_strength: "strong",
    currency: "USD",
    created_by: "user-1",
    created_at: "2026-08-15T10:00:00Z",
    updated_at: "2026-08-15T10:00:00Z",
    assumptions_snapshot: [],
    results_snapshot: {},
    ...overrides,
  };
}

function summaryFixture(simulations: SimulationRead[]): SimulationSummaryRead {
  return {
    business_id: "biz-1",
    total: simulations.length,
    simulations,
  };
}

function renderSection(locale: "en" | "ar" = "en") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return {
    user: userEvent.setup(),
    ...renderWithI18n(
      <QueryClientProvider client={queryClient}>
        <SimulatorSection businessId="biz-1" />
      </QueryClientProvider>,
      locale
    ),
  };
}

describe("SimulatorSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    hooks.fetchSimulations.mockResolvedValue(summaryFixture([]));
    hooks.createSimulation.mockResolvedValue(simulationFixture());
    hooks.simulateCampaign.mockResolvedValue(simulationFixture({ entity_type: "campaign", entity_id: "camp-1" }));
    hooks.rerunSimulation.mockResolvedValue(simulationFixture({ model_version: "1.0.1" }));
    hooks.fetchMetricsCampaigns.mockResolvedValue({
      business_id: "biz-1",
      currency: "USD",
      timezone: "UTC",
      range: { kind: "last_30_days", start: "2026-07-01", end: "2026-07-30" },
      campaigns: [{ id: "camp-1", name: "Spring Launch" }],
    });
  });

  it("renders the title", async () => {
    renderSection();
    expect(await screen.findByText("Campaign Simulator")).toBeInTheDocument();
    await waitFor(() => expect(hooks.fetchSimulations).toHaveBeenCalled());
  });

  it("renders empty history when no simulations exist", async () => {
    renderSection();
    await waitFor(() => {
      expect(screen.getByText("No simulations yet — run one above.")).toBeInTheDocument();
    });
  });

  it("renders error state on fetch failure and retries", async () => {
    hooks.fetchSimulations.mockRejectedValue(new Error("Network error"));
    const { user } = renderSection();
    await waitFor(() => {
      expect(screen.getByText("Failed to load simulation data.")).toBeInTheDocument();
    });
    hooks.fetchSimulations.mockResolvedValue(summaryFixture([]));
    await user.click(screen.getByText("Retry"));
    await waitFor(() => expect(screen.getByText("No simulations yet — run one above.")).toBeInTheDocument());
  });

  it("runs a business simulation and shows results", async () => {
    const { user } = renderSection();
    await user.type(await screen.findByTestId("budget-input"), "1500");
    await user.click(screen.getByTestId("run-button"));
    await waitFor(() => {
      expect(hooks.createSimulation).toHaveBeenCalledWith("biz-1", expect.objectContaining({ budget: "1500" }));
    });
    expect(await screen.findByText("funnel-model")).toBeInTheDocument();
    expect(screen.getByText("budget → impressions → clicks → purchases → revenue")).toBeInTheDocument();
  });

  it("runs a campaign simulation through the campaign endpoint", async () => {
    const { user } = renderSection();
    await user.click(await screen.findByTestId("scope-select"));
    await waitFor(async () => {
      const option = await screen.findByText("Campaign");
      await user.click(option);
    });
    await waitFor(() => {
      expect(hooks.fetchMetricsCampaigns).toHaveBeenCalledWith("biz-1", "last_30_days");
    });
    await user.click(await screen.findByTestId("campaign-select"));
    await waitFor(async () => {
      const option = await screen.findByText("Spring Launch");
      await user.click(option);
    });
    await user.type(await screen.findByTestId("budget-input"), "800");
    await user.click(screen.getByTestId("run-button"));
    await waitFor(() => {
      expect(hooks.simulateCampaign).toHaveBeenCalledWith(
        "biz-1",
        "camp-1",
        expect.objectContaining({ entity_type: "campaign", budget: "800" })
      );
    });
  });

  it("submits the target values to the backend", async () => {
    const { user } = renderSection();
    await user.type(await screen.findByTestId("budget-input"), "1000");
    await user.type(await screen.findByTestId("target-cpa"), "40");
    await user.click(screen.getByTestId("run-button"));
    await waitFor(() => {
      expect(hooks.createSimulation).toHaveBeenCalledWith(
        "biz-1",
        expect.objectContaining({ target_cpa: "40" })
      );
    });
  });

  it("opens a simulation from history", async () => {
    hooks.fetchSimulations.mockResolvedValue(summaryFixture([simulationFixture()]));
    const { user } = renderSection();
    await waitFor(() => expect(screen.getByTestId("open-sim-1")).toBeInTheDocument());
    await user.click(screen.getByTestId("open-sim-1"));
    expect(await screen.findAllByText("funnel-model")).toHaveLength(2);
    expect(screen.getByTestId("model-used")).toHaveTextContent("funnel-model");
  });

  it("reruns a simulation through the rerun endpoint", async () => {
    hooks.fetchSimulations.mockResolvedValue(summaryFixture([simulationFixture()]));
    const { user } = renderSection();
    await waitFor(() => expect(screen.getByTestId("rerun-sim-1")).toBeInTheDocument());
    await user.click(screen.getByTestId("rerun-sim-1"));
    await waitFor(() => {
      expect(hooks.rerunSimulation).toHaveBeenCalledWith("biz-1", "sim-1");
    });
  });

  it("renders profitability, break-even and target comparison blocks with statuses", async () => {
    hooks.fetchSimulations.mockResolvedValue(summaryFixture([simulationFixture()]));
    const { user } = renderSection();
    await waitFor(() => expect(screen.getByTestId("open-sim-1")).toBeInTheDocument());
    await user.click(screen.getByTestId("open-sim-1"));
    expect(await screen.findByTestId("profitability")).toBeInTheDocument();
    expect(screen.getByTestId("break-even")).toBeInTheDocument();
    expect(screen.getByTestId("targets")).toBeInTheDocument();
    expect(screen.getByTestId("profitability-status-profitable")).toBeInTheDocument();
    expect(screen.getByTestId("target-status-met")).toBeInTheDocument();
    expect(screen.getByText("$2,000.00")).toBeInTheDocument();
  });

  it("renders data quality and evidence strength badges for the active simulation", async () => {
    hooks.createSimulation.mockResolvedValue(simulationFixture());
    const { user } = renderSection();
    await user.type(await screen.findByTestId("budget-input"), "1000");
    await user.click(screen.getByTestId("run-button"));
    expect(await screen.findByTestId("data-quality-strong")).toBeInTheDocument();
    expect(screen.getByTestId("strength-strong")).toBeInTheDocument();
  });

  it("renders in Arabic locale", async () => {
    renderSection("ar");
    expect(await screen.findByText("محاكي الحملات")).toBeInTheDocument();
  });

  it("shows the run error when the backend call fails", async () => {
    hooks.createSimulation.mockRejectedValue(new Error("boom"));
    const { user } = renderSection();
    await user.type(await screen.findByTestId("budget-input"), "1000");
    await user.click(screen.getByTestId("run-button"));
    expect(await screen.findByTestId("run-error")).toBeInTheDocument();
  });
});