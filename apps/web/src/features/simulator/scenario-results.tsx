"use client";

import { useLocale, useTranslations } from "next-intl";

import { formatMoney } from "@/lib/money";
import type { ScenarioMetricsRead, ScenarioResultRead } from "./api";
import { formatCount, formatMultiplier, formatPercent } from "./format";

interface ScenarioMetricsRow {
  key: keyof ScenarioMetricsRead;
  kind: "money" | "count" | "rate" | "multiplier";
}

const SCENARIO_METRIC_ROWS: ScenarioMetricsRow[] = [
  { key: "budget", kind: "money" },
  { key: "impressions", kind: "count" },
  { key: "clicks", kind: "count" },
  { key: "ctr", kind: "rate" },
  { key: "cpc", kind: "money" },
  { key: "cpm", kind: "money" },
  { key: "purchases", kind: "count" },
  { key: "cvr", kind: "rate" },
  { key: "cpa", kind: "money" },
  { key: "aov", kind: "money" },
  { key: "revenue", kind: "money" },
  { key: "roas", kind: "multiplier" },
  { key: "mer", kind: "multiplier" },
  { key: "gross_revenue", kind: "money" },
  { key: "refund_amount", kind: "money" },
  { key: "net_revenue", kind: "money" },
  { key: "contribution_profit", kind: "money" },
  { key: "contribution_margin", kind: "rate" },
];

function labelKey(metricKey: string): string | null {
  const translated: Record<string, string> = {
    budget: "budgetLabel",
    impressions: "impressions",
    clicks: "clicks",
    purchases: "purchases",
    revenue: "revenue",
    contribution_profit: "profit",
  };
  return translated[metricKey] ?? null;
}

/**
 * Displays one scenario column. Unavailable metrics are rendered as a dash —
 * never as zero — because the backend marks them unavailable for a reason.
 */
export function ScenarioCard({
  scenario,
  currency,
  label,
}: {
  scenario?: ScenarioResultRead;
  currency: string;
  label: string;
}) {
  const locale = useLocale();
  const t = useTranslations("simulator");
  const available = scenario?.available ?? false;
  const metrics = scenario?.metrics;

  function formatValue(key: keyof ScenarioMetricsRead, value: string | number | null | undefined) {
    if (value === null || value === undefined || value === "") return null;
    const row = SCENARIO_METRIC_ROWS.find((item) => item.key === key);
    switch (row?.kind) {
      case "money":
        return formatMoney(String(value), currency, locale);
      case "count":
        return formatCount(locale, value);
      case "rate":
        return formatPercent(locale, value);
      case "multiplier":
        return formatMultiplier(locale, value);
      default:
        return String(value);
    }
  }

  if (!available || !metrics) {
    return (
      <div data-testid="scenario-unavailable" className="space-y-2">
        <h4 className="text-sm font-semibold">{label}</h4>
        <p className="text-sm text-muted-foreground">
          {scenario?.reason ?? t("unavailable")}
        </p>
      </div>
    );
  }

  return (
    <div data-testid="scenario-card" className="space-y-2">
      <h4 className="text-sm font-semibold">{label}</h4>
      <table className="w-full text-sm">
        <tbody>
          {SCENARIO_METRIC_ROWS.map(({ key }) => {
            const raw = metrics[key];
            const formatted = formatValue(key, raw);
            return (
              <tr key={key} className="border-b last:border-0">
                <td
                  data-testid={`scenario-metric-${key}`}
                  className="py-1 pe-2 text-xs text-muted-foreground"
                >
                  {labelKey(key) ? t(labelKey(key) as string) : key.toUpperCase()}
                </td>
                <td className="py-1 text-end tabular-nums" data-testid={`scenario-value-${key}`}>
                  {formatted ?? "-"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}