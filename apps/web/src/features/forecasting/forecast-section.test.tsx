import { renderWithI18n, screen } from "../../test/render";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { waitFor } from "@testing-library/react";
import type { ForecastSummaryRead } from "./api";
import { ForecastSection } from "./forecast-section";

const summaryFixture: ForecastSummaryRead = {
  business_id: "biz-1",
  currency: "USD",
  timezone: "UTC",
  horizon_days: 30,
  forecast_start: "2026-08-15",
  forecast_end: "2026-09-13",
  training_start: "2026-05-17",
  training_end: "2026-08-14",
  confidence_level: "0.80",
  metrics: [],
  goals: [],
  budget: null,
  scenario_totals: {},
};

import type { RangeKind } from "@/features/metrics/api";

function renderForecastSection(businessId: string, locale: "en" | "ar" = "en", rangeKind: RangeKind = "last_30_days") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return renderWithI18n(
    <QueryClientProvider client={queryClient}>
      <ForecastSection businessId={businessId} rangeKind={rangeKind} />
    </QueryClientProvider>,
    locale
  );
}

describe("ForecastSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders loading state initially", () => {
    renderForecastSection("biz-1");
    expect(screen.getByText(/Loading/)).toBeInTheDocument();
  });

  it("renders forecast data when available", async () => {
    const mockFetch = vi.fn().mockResolvedValue(summaryFixture);
    vi.mock("./api", () => ({
      fetchForecastSummary: mockFetch,
    }));

    renderForecastSection("biz-1", "en", "last_30_days");

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
  });

  it("renders error state on fetch failure", async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error("Network error"));
    vi.mock("./api", () => ({
      fetchForecastSummary: mockFetch,
    }));

    renderForecastSection("biz-1");

    await waitFor(() => {
      expect(screen.getByText(/Failed to load forecast data/)).toBeInTheDocument();
    });
  });

  it("renders empty state when no data", async () => {
    const emptyFixture = {
      ...summaryFixture,
      metrics: [],
      goals: [],
      budget: null,
      scenario_totals: {},
    };
    const mockFetch = vi.fn().mockResolvedValue(emptyFixture);
    vi.mock("./api", () => ({
      fetchForecastSummary: mockFetch,
    }));

    renderForecastSection("biz-1");

    await waitFor(() => {
      expect(screen.getByText(/No forecast data available/)).toBeInTheDocument();
    });
  });

  it("renders with Arabic locale", async () => {
    const mockFetch = vi.fn().mockResolvedValue(summaryFixture);
    vi.mock("./api", () => ({
      fetchForecastSummary: mockFetch,
    }));

    renderForecastSection("biz-1", "ar");

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
  });

  it("renders with English locale", async () => {
    const mockFetch = vi.fn().mockResolvedValue(summaryFixture);
    vi.mock("./api", () => ({
      fetchForecastSummary: mockFetch,
    }));

    renderForecastSection("biz-1", "en");

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
  });

  it("handles invalid business ID gracefully", () => {
    renderForecastSection("");
    expect(screen.getByText(/Loading/)).toBeInTheDocument();
  });
});