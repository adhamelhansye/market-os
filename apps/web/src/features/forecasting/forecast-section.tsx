import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import type { ForecastSummaryRead } from "./api";
import { fetchForecastSummary } from "./api";

import type { RangeKind } from "@/features/metrics/api";

interface ForecastSectionProps {
  businessId: string;
  rangeKind: RangeKind;
  onClose?: () => void;
}

export function ForecastSection({ businessId, rangeKind }: ForecastSectionProps) {
  const t = useTranslations("forecasting");
  
  const { data: summary, isLoading, isError } = useQuery<ForecastSummaryRead>({
    queryKey: ["forecast-summary", businessId, rangeKind],
    queryFn: () => fetchForecastSummary(businessId, 30),
    enabled: Boolean(businessId),
  });
  
  if (isLoading) {
    return (
      <div className="flex flex-col h-full items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
        <p className="mt-2 text-sm text-gray-500">{t("loading") || "Loading forecast data..."}</p>
      </div>
    );
  }
  
  if (isError) {
    return (
      <div className="flex flex-col h-full items-center justify-center">
        <p className="text-sm text-red-500">{t("error") || "Failed to load forecast data."}</p>
      </div>
    );
  }
  
  if (!summary) {
    return (
      <div className="flex flex-col h-full items-center justify-center">
        <p className="text-sm text-gray-500">{t("insufficientData") || "No forecast data available."}</p>
      </div>
    );
  }
  
  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h3 className="font-semibold text-lg">{t("forecast") || "Forecast"}</h3>
      </div>
      
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div className="space-y-2">
          <h4 className="text-sm font-medium text-gray-500">{t("revenueForecast") || "Revenue Forecast"}</h4>
          <p className="text-lg font-semibold">
            {summary.currency || "USD"} {summary.metrics?.find((m: { metric_code: string }) => m.metric_code === "revenue")?.expected_value || "N/A"}
          </p>
        </div>
        
        <div className="space-y-2">
          <h4 className="text-sm font-medium text-gray-500">{t("spendForecast") || "Spend Forecast"}</h4>
          <p className="text-lg font-semibold">
            {summary.currency || "USD"} {summary.metrics?.find((m: { metric_code: string }) => m.metric_code === "spend")?.expected_value || "N/A"}
          </p>
        </div>
        
        <div className="space-y-2">
          <h4 className="text-sm font-medium text-gray-500">{t("profitForecast") || "Profit Forecast"}</h4>
          <p className="text-lg font-semibold">
            {summary.currency || "USD"} {summary.metrics?.find((m: { metric_code: string }) => m.metric_code === "contribution_profit")?.expected_value || "N/A"}
          </p>
        </div>
      </div>
      
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="space-y-2">
          <h4 className="text-sm font-medium text-gray-500">{t("best") || "Best"}</h4>
          <p className="text-lg font-semibold">
            {summary.currency || "USD"} {summary.scenario_totals?.revenue?.upper || "N/A"}
          </p>
        </div>
        
        <div className="space-y-2">
          <h4 className="text-sm font-medium text-gray-500">{t("expected") || "Expected"}</h4>
          <p className="text-lg font-semibold">
            {summary.currency || "USD"} {summary.scenario_totals?.revenue?.expected || "N/A"}
          </p>
        </div>
        
        <div className="space-y-2">
          <h4 className="text-sm font-medium text-gray-500">{t("worst") || "Worst"}</h4>
          <p className="text-lg font-semibold">
            {summary.currency || "USD"} {summary.scenario_totals?.revenue?.lower || "N/A"}
          </p>
        </div>
        
        <div className="space-y-2">
          <h4 className="text-sm font-medium text-gray-500">{t("confidence") || "Confidence"}</h4>
          <p className="text-lg font-semibold">
            {(Number(summary.confidence_level) * 100).toFixed(0)}%
          </p>
        </div>
      </div>
      
      <div className="space-y-4">
        <div className="space-y-2">
          <h4 className="text-sm font-medium text-gray-500">{t("model") || "Model"}</h4>
          <p className="text-sm">
            {summary.metrics?.find((m: { metric_code: string }) => m.metric_code === "revenue")?.model || "N/A"}
          </p>
        </div>
        
        <div className="space-y-2">
          <h4 className="text-sm font-medium text-gray-500">{t("dataQuality") || "Data Quality"}</h4>
          <p className="text-sm">
            {summary.metrics?.find((m: { metric_code: string; observations_used: number }) => m.metric_code === "revenue")?.observations_used || 0} observations
          </p>
        </div>
      </div>
    </div>
  );
}