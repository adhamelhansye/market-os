import { renderWithI18n, screen } from "../../test/render";
import { describe, it, expect } from "vitest";

import type { ScenarioMetricsRead, ScenarioResultRead } from "./api";
import { ScenarioCard } from "./scenario-results";

type ScenarioOverrides = Omit<Partial<ScenarioResultRead>, "metrics"> & {
  metrics?: ScenarioMetricsRead | null;
};

function scenarioFixture(overrides: ScenarioOverrides = {}): ScenarioResultRead {
  return {
    label: "expected",
    available: true,
    metrics: {
      budget: "1000.00",
      impressions: 120000,
      clicks: 1200,
      ctr: "0.0100",
      cpc: "0.83",
      cpm: "8.33",
      purchases: 30,
      cvr: "0.0250",
      cpa: "33.33",
      aov: "100.00",
      revenue: "3000.00",
      roas: "3.00",
      mer: "3.00",
      gross_revenue: "3000.00",
      refund_amount: "0.00",
      net_revenue: "3000.00",
      contribution_profit: "800.00",
      contribution_margin: "0.2667",
    },
    reason: null,
    ...overrides,
  } as ScenarioResultRead;
}

function renderCard(scenario?: ScenarioResultRead, label = "Expected") {
  return renderWithI18n(<ScenarioCard scenario={scenario} currency="USD" label={label} />, "en");
}

describe("ScenarioCard", () => {
  it("renders all metrics with their labels", () => {
    renderCard(scenarioFixture());
    expect(screen.getByTestId("scenario-card")).toBeInTheDocument();
    expect(screen.getByTestId("scenario-metric-revenue")).toHaveTextContent("Revenue");
    expect(screen.getByTestId("scenario-metric-budget")).toHaveTextContent("Budget");
    expect(screen.getByTestId("scenario-metric-contribution_profit")).toHaveTextContent("Profit");
    expect(screen.getByTestId("scenario-value-revenue")).toHaveTextContent("$3,000.00");
    expect(screen.getByTestId("scenario-value-impressions")).toHaveTextContent("120,000");
    expect(screen.getByTestId("scenario-value-ctr")).toHaveTextContent("1.00%");
    expect(screen.getByTestId("scenario-value-roas")).toHaveTextContent("3.00×");
  });

  it("renders untranslated metric acronyms verbatim", () => {
    renderCard(scenarioFixture());
    expect(screen.getByTestId("scenario-metric-cpa")).toHaveTextContent("CPA");
    expect(screen.getByTestId("scenario-metric-aov")).toHaveTextContent("AOV");
  });

  it("shows unavailable state with a reason instead of zeros", () => {
    renderCard(
      scenarioFixture({
        available: false,
        metrics: null,
        reason: "insufficient data for this scenario",
      })
    );
    expect(screen.getByTestId("scenario-unavailable")).toBeInTheDocument();
    expect(screen.getByText("insufficient data for this scenario")).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
    expect(screen.queryByText("$0.00")).not.toBeInTheDocument();
    expect(screen.queryByTestId("scenario-card")).not.toBeInTheDocument();
  });

  it("renders a dash for null metric values, never zero", () => {
    renderCard(
      scenarioFixture({
        metrics: {
          budget: "1000.00",
          impressions: null,
          clicks: null,
          ctr: null,
          cpc: "0.83",
          cpm: "8.33",
          purchases: 30,
          cvr: "0.0250",
          cpa: "33.33",
          aov: "100.00",
          revenue: "3000.00",
          roas: "3.00",
          mer: null,
          gross_revenue: "3000.00",
          refund_amount: "0.00",
          net_revenue: "3000.00",
          contribution_profit: "800.00",
          contribution_margin: "0.2667",
        },
      })
    );
    expect(screen.getByTestId("scenario-value-impressions")).toHaveTextContent("-");
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("renders the card label", () => {
    renderCard(scenarioFixture(), "Downside");
    expect(screen.getByText("Downside")).toBeInTheDocument();
  });
});