import { renderWithI18n, screen } from "../../test/render";
import { describe, it, expect } from "vitest";

import type { SensitivityRowRead, SensitivityTableRead } from "./api";
import { SensitivityTable } from "./sensitivity-table";

function rowFixture(overrides: Partial<SensitivityRowRead> = {}): SensitivityRowRead {
  return {
    variable: "ctr",
    change_percent: "-0.20",
    new_value: "0.0080",
    revenue: "2400.00",
    profit: "400.00",
    cpa: "41.67",
    roas: "2.40",
    ...overrides,
  };
}

function tableFixture(overrides: Partial<SensitivityTableRead> = {}): SensitivityTableRead {
  return {
    variable: "ctr",
    baseline_profit: "800.00",
    rows: [rowFixture()],
    ...overrides,
  };
}

function renderTable(tables: SensitivityTableRead[]) {
  return renderWithI18n(<SensitivityTable tables={tables} currency="USD" />, "en");
}

describe("SensitivityTable", () => {
  it("renders backend-provided values without calculating anything", () => {
    renderTable([tableFixture()]);
    expect(screen.getByTestId("sensitivity-table")).toBeInTheDocument();
    expect(screen.getByText("CTR")).toBeInTheDocument();
    expect(screen.getByText("Baseline profit: $800.00")).toBeInTheDocument();
    expect(screen.getByText("-20.00%")).toBeInTheDocument();
    expect(screen.getByText("$2,400.00")).toBeInTheDocument();
    expect(screen.getByText("$400.00")).toBeInTheDocument();
    expect(screen.getByText("$41.67")).toBeInTheDocument();
    expect(screen.getByText("2.40×")).toBeInTheDocument();
  });

  it("formats budget-style variables as money in the new-value column", () => {
    renderTable([
      tableFixture({
        variable: "budget",
        rows: [rowFixture({ variable: "budget", new_value: "1200.00" })],
      }),
    ]);
    expect(screen.getByText("$1,200.00")).toBeInTheDocument();
  });

  it("formats rate variables as percent in the new-value column", () => {
    renderTable([
      tableFixture({
        variable: "cvr",
        rows: [rowFixture({ variable: "cvr", new_value: "0.0200" })],
      }),
    ]);
    expect(screen.getByText("2.00%")).toBeInTheDocument();
  });

  it("renders nothing when no tables exist", () => {
    renderTable([]);
    expect(screen.queryByText("Sensitivity")).not.toBeInTheDocument();
  });

  it("renders a dash when baseline profit is missing", () => {
    renderTable([tableFixture({ baseline_profit: null })]);
    expect(screen.getByText("Baseline profit: -")).toBeInTheDocument();
  });
});