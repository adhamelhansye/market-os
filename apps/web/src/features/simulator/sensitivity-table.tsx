"use client";

import { useLocale, useTranslations } from "next-intl";

import { formatMoney } from "@/lib/money";
import type { SensitivityTableRead } from "./api";
import { formatMultiplier, formatPercent } from "./format";

function variableLabel(value: string): string {
  const translated: Record<string, string> = {
    budget: "Budget",
    ctr: "CTR",
    cpc: "CPC",
    cpm: "CPM",
    cvr: "CVR",
    aov: "AOV",
    refund_rate: "Refund rate",
    contribution_margin: "Contribution margin",
    shipping_cost: "Shipping cost",
    payment_fees: "Payment fees",
  };
  return translated[value] ?? value;
}

/**
 * Display-only sensitivity tables. Every value comes precomputed from the
 * backend — this component performs no calculation.
 */
export function SensitivityTable({
  tables,
  currency,
}: {
  tables?: SensitivityTableRead[];
  currency: string;
}) {
  const locale = useLocale();
  const t = useTranslations("simulator");

  if (!tables || tables.length === 0) {
    return null;
  }

  return (
    <div className="space-y-4">
      <div>
        <h4 className="text-sm font-medium text-muted-foreground">{t("sensitivity")}</h4>
        <p className="text-xs text-muted-foreground">{t("sensitivitySubtitle")}</p>
      </div>
      {tables.map((table) => (
        <div key={table.variable} data-testid="sensitivity-table" className="space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold">{variableLabel(table.variable)}</span>
            <span className="text-xs text-muted-foreground">
              {t("baselineProfit")}:{" "}
              {table.baseline_profit !== null && table.baseline_profit !== undefined
                ? formatMoney(table.baseline_profit, currency, locale)
                : "-"}
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left rtl:text-right text-muted-foreground">
                  <th className="py-2 pe-2 font-normal">{t("change")}</th>
                  <th className="py-2 pe-2 font-normal text-end">{t("newValue")}</th>
                  <th className="py-2 pe-2 font-normal text-end">{t("rowRevenue")}</th>
                  <th className="py-2 pe-2 font-normal text-end">{t("rowProfit")}</th>
                  <th className="py-2 pe-2 font-normal text-end">CPA</th>
                  <th className="py-2 font-normal text-end">ROAS</th>
                </tr>
              </thead>
              <tbody>
                {(table.rows ?? []).map((row) => (
                  <tr key={`${table.variable}-${row.change_percent}`} className="border-b">
                    <td className="py-2 pe-2 tabular-nums">
                      {formatPercent(locale, row.change_percent)}
                    </td>
                    <td className="py-2 pe-2 text-end tabular-nums">
                      {table.variable === "budget" ||
                      table.variable === "cpc" ||
                      table.variable === "cpm" ||
                      table.variable === "aov" ? (
                        formatMoney(row.new_value ?? "", currency, locale)
                      ) : row.new_value !== null && row.new_value !== undefined ? (
                        formatPercent(locale, row.new_value)
                      ) : (
                        "-"
                      )}
                    </td>
                    <td className="py-2 pe-2 text-end tabular-nums">
                      {formatMoney(row.revenue ?? "", currency, locale)}
                    </td>
                    <td className="py-2 pe-2 text-end tabular-nums">
                      {formatMoney(row.profit ?? "", currency, locale)}
                    </td>
                    <td className="py-2 pe-2 text-end tabular-nums">
                      {formatMoney(row.cpa ?? "", currency, locale)}
                    </td>
                    <td className="py-2 text-end tabular-nums">
                      {formatMultiplier(locale, row.roas)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  );
}