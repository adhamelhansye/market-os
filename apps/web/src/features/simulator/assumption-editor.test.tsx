import { renderWithI18n, screen } from "../../test/render";
import { fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

import type { AssumptionRead } from "./api";
import { AssumptionEditor } from "./assumption-editor";

function assumptionFixture(overrides: Partial<AssumptionRead> = {}): AssumptionRead {
  return {
    name: "ctr",
    value: "0.0100",
    unit: "",
    source: "campaign_history",
    source_entity: "campaign",
    historical_value: "0.0090",
    override: false,
    confidence: "strong",
    unavailable_reason: null,
    ...overrides,
  };
}

function renderEditor(
  assumptions: AssumptionRead[],
  overrides: Partial<Record<string, string>> = {},
  onOverrideChange: (key: string, value: string) => void = vi.fn()
) {
  renderWithI18n(
    <AssumptionEditor
      assumptions={assumptions}
      overrides={overrides}
      onOverrideChange={onOverrideChange}
    />,
    "en"
  );
  return { onOverrideChange };
}

describe("AssumptionEditor", () => {
  it("shows name, simulated value, historical value, source entity and confidence", () => {
    renderEditor([assumptionFixture()]);
    expect(screen.getAllByText("ctr").length).toBeGreaterThan(0);
    expect(screen.getByText("0.0100")).toBeInTheDocument();
    expect(screen.getByText("0.0090")).toBeInTheDocument();
    expect(screen.getByText("Campaign history · campaign")).toBeInTheDocument();
    expect(screen.getByTestId("confidence-ctr")).toHaveTextContent("Strong");
  });

  it("falls back to Unknown label for unrecognised sources", () => {
    renderEditor([assumptionFixture({ source: "mystery_source", source_entity: null })]);
    expect(screen.getByText("Unknown")).toBeInTheDocument();
  });

  it("renders - for missing historical values", () => {
    renderEditor([assumptionFixture({ historical_value: null })]);
    expect(screen.getByText("-")).toBeInTheDocument();
  });

  it("renders override inputs for supported keys and propagates changes", () => {
    const onOverrideChange = vi.fn();
    renderEditor([assumptionFixture()], {}, onOverrideChange);
    const input = screen.getByTestId("override-ctr") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "0.0120" } });
    expect(onOverrideChange).toHaveBeenLastCalledWith("ctr", "0.0120");
  });

  it("shows the stored override value in the input", () => {
    renderEditor([assumptionFixture()], { ctr: "0.0130" });
    expect(screen.getByTestId("override-ctr")).toHaveValue("0.0130");
  });

  it("renders a dash for unsupported override keys", () => {
    renderEditor([assumptionFixture({ name: "impressions" })]);
    expect(screen.getByTestId("override-not-supported-impressions")).toBeInTheDocument();
    expect(screen.queryByTestId("override-impressions")).not.toBeInTheDocument();
  });
});