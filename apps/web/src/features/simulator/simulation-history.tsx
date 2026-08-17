"use client";

import { useLocale, useTranslations } from "next-intl";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { formatMoney } from "@/lib/money";
import type { SimulationRead } from "./api";
import { formatDate, formatDateTime } from "./format";
import { StrengthBadge } from "./status-badges";

const ENTITY_LABELS: Record<string, string> = {
  business: "scopeBusiness",
  campaign: "scopeCampaign",
};

const PROFITABILITY_LABELS: Record<string, string> = {
  profitable: "profitable",
  near_break_even: "nearBreakEven",
  unprofitable: "unprofitable",
  unavailable: "unavailable",
};

const PROFITABILITY_CLASSES: Record<string, string> = {
  profitable: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  near_break_even:
    "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  unprofitable: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  unavailable: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
};

interface SimulationHistoryProps {
  simulations?: SimulationRead[];
  activeId?: string | null;
  rerunning?: boolean;
  onOpen: (simulationId: string) => void;
  onRerun: (simulationId: string) => void;
}

export function SimulationHistory({
  simulations,
  activeId,
  rerunning,
  onOpen,
  onRerun,
}: SimulationHistoryProps) {
  const locale = useLocale();
  const t = useTranslations("simulator");
  const rows = simulations ?? [];

  if (rows.length === 0) {
    return (
      <Card className="border-dashed">
        <CardContent className="py-6 text-center">
          <p className="text-sm font-medium">{t("historyEmpty")}</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-3" data-testid="simulation-history">
      {rows.map((simulation) => {
        const budget = simulation.scenarios?.expected?.metrics?.budget;
        const expectedRevenue = simulation.scenarios?.expected?.metrics?.revenue;
        const expectedProfit = simulation.scenarios?.expected?.metrics?.contribution_profit;
        const profitability = simulation.profitability?.status ?? "unavailable";
        const referenceWindow = simulation.reference_window
          ? `${formatDate(locale, simulation.reference_window.start)} – ${formatDate(
              locale,
              simulation.reference_window.end
            )}`
          : "-";

        return (
          <Card key={simulation.id} data-testid="simulation-row">
            <CardContent className="space-y-2 py-3 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs text-muted-foreground">
                  {formatDateTime(locale, simulation.created_at)}
                </span>
                <span className="text-xs text-muted-foreground">
                  {t(ENTITY_LABELS[simulation.entity_type] ?? "entityType")}
                  {simulation.entity_id ? ` · ${simulation.entity_id}` : ""}
                </span>
              </div>
              <div className="grid gap-x-4 gap-y-1 sm:grid-cols-2 lg:grid-cols-4">
                <div>
                  <span className="text-xs text-muted-foreground">{t("period")}: </span>
                  {referenceWindow}
                </div>
                <div>
                  <span className="text-xs text-muted-foreground">{t("modelShort")}: </span>
                  {simulation.model_used}
                </div>
                <div>
                  <span className="text-xs text-muted-foreground">{t("budgetLabel")}: </span>
                  {simulation.currency} {formatMoney(budget ?? "", simulation.currency, locale)}
                </div>
                <div>
                  <span className="text-xs text-muted-foreground">{t("revenue")}: </span>
                  {formatMoney(expectedRevenue ?? "", simulation.currency, locale)}
                </div>
                <div>
                  <span className="text-xs text-muted-foreground">{t("profit")}: </span>
                  {formatMoney(expectedProfit ?? "", simulation.currency, locale)}
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">{t("profitability")}: </span>
                  <span
                    data-testid={`profitability-${simulation.profitability?.status ?? "unavailable"}`}
                    className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                      PROFITABILITY_CLASSES[profitability] ?? PROFITABILITY_CLASSES.unavailable
                    }`}
                  >
                    {t(PROFITABILITY_LABELS[profitability] ?? "unavailable")}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">{t("evidenceStrength")}: </span>
                  <StrengthBadge strength={simulation.evidence_strength} />
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  data-testid={`open-${simulation.id}`}
                  onClick={() => onOpen(simulation.id)}
                >
                  {t("open")}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  data-testid={`rerun-${simulation.id}`}
                  onClick={() => onRerun(simulation.id)}
                  disabled={rerunning && activeId === simulation.id}
                >
                  {rerunning && activeId === simulation.id ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : null}
                  {t("rerun")}
                </Button>
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}