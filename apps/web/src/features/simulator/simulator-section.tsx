"use client";

import { useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { fetchMetricsCampaigns } from "@/features/metrics/api";
import type { RangeKind } from "@/features/metrics/api";
import { formatMoney } from "@/lib/money";

import {
  createSimulation,
  fetchSimulations,
  rerunSimulation,
  simulateCampaign,
  SIMULATION_WINDOWS,
  type OverrideKey,
  type SimulationCreateRequest,
  type SimulationRead,
} from "./api";
import { AssumptionEditor } from "./assumption-editor";
import { ScenarioCard } from "./scenario-results";
import { SensitivityTable } from "./sensitivity-table";
import { SimulationHistory } from "./simulation-history";
import { StrengthBadge } from "./status-badges";
import { formatDate, formatMultiplier, formatPercent } from "./format";

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

const QUALITY_CLASSES: Record<string, string> = {
  strong: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  moderate: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  weak: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  insufficient: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
};

const TARGET_LABELS: Record<string, string> = {
  cpa: "targetCpa",
  roas: "targetRoas",
  revenue: "targetRevenue",
  profit: "targetProfit",
};

function nullableDecimal(value: string): string | null {
  const trimmed = value.trim();
  if (trimmed === "") return null;
  return trimmed;
}

function TargetStatusBadge({ status }: { status: string }) {
  const t = useTranslations("simulator");
  const classes =
    status === "met"
      ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
      : status === "not_met"
        ? "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300"
        : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300";
  return (
    <span
      data-testid={`target-status-${status}`}
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${classes}`}
    >
      {t(status === "met" ? "met" : status === "not_met" ? "notMet" : "unavailable")}
    </span>
  );
}

function BreakEvenBlock({
  simulation,
  currency,
}: {
  simulation: SimulationRead;
  currency: string;
}) {
  const locale = useLocale();
  const t = useTranslations("simulator");
  const be = simulation.break_even;
  if (!be) return null;
  const rows = [
    { label: t("breakEvenCpa"), value: be.break_even_cpa },
    { label: t("breakEvenRoas"), value: be.break_even_roas },
    { label: t("simulatedCpa"), value: be.simulated_cpa },
    { label: t("simulatedRoas"), value: be.simulated_roas },
    { label: t("minimumCvr"), value: be.minimum_cvr, rate: true },
    { label: t("maximumCpc"), value: be.maximum_cpc },
    { label: t("minimumAov"), value: be.minimum_aov },
    { label: t("maximumCpa"), value: be.maximum_cpa },
    { label: t("minimumRoas"), value: be.minimum_roas },
  ];
  return (
    <Card data-testid="break-even">
      <CardHeader>
        <CardTitle className="text-sm">{t("breakEven")}</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-x-4 gap-y-1 sm:grid-cols-2 lg:grid-cols-3">
        {rows.map(({ label, value, rate }) => (
          <div key={label} className="text-sm">
            <span className="text-xs text-muted-foreground">{label}: </span>
            {value === null || value === undefined || value === ""
              ? "-"
              : rate
                ? formatPercent(locale, value)
                : formatMoney(value, currency, locale)}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function ProfitabilityBlock({
  simulation,
  currency,
}: {
  simulation: SimulationRead;
  currency: string;
}) {
  const locale = useLocale();
  const t = useTranslations("simulator");
  const p = simulation.profitability;
  if (!p) return null;
  const status = p.status;
  return (
    <Card data-testid="profitability">
      <CardHeader>
        <CardTitle className="text-sm">{t("profitability")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <div className="flex items-center gap-2">
          <span
            data-testid={`profitability-status-${status}`}
            className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
              PROFITABILITY_CLASSES[status] ?? PROFITABILITY_CLASSES.unavailable
            }`}
          >
            {t(PROFITABILITY_LABELS[status] ?? "unavailable")}
          </span>
          {p.reason ? <span className="text-xs text-muted-foreground">{p.reason}</span> : null}
        </div>
        <div className="grid gap-x-4 gap-y-1 sm:grid-cols-3">
          <div>
            <span className="text-xs text-muted-foreground">ROAS: </span>
            {formatMultiplier(locale, p.roas)}
          </div>
          <div>
            <span className="text-xs text-muted-foreground">{t("breakEvenRoas")}: </span>
            {formatMultiplier(locale, p.break_even_roas)}
          </div>
          <div>
            <span className="text-xs text-muted-foreground">{t("profit")}: </span>
            {formatMoney(p.contribution_profit ?? "", currency, locale)}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function TargetsBlock({ simulation, currency }: { simulation: SimulationRead; currency: string }) {
  const locale = useLocale();
  const t = useTranslations("simulator");
  const targets = simulation.targets ?? [];
  if (targets.length === 0) return null;
  return (
    <Card data-testid="targets">
      <CardHeader>
        <CardTitle className="text-sm">{t("targetsTitle")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {targets.map((target) => (
          <div key={target.metric_code} className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-medium">{target.metric_code.toUpperCase()}</span>
            <span className="text-xs text-muted-foreground">
              {t("targetValue")}: {target.target_value ?? "-"}
            </span>
            <span className="text-xs text-muted-foreground">
              {t("simulatedValue")}: {formatMoney(target.simulated_value ?? "", currency, locale)}
            </span>
            <TargetStatusBadge status={target.status} />
            {target.reason ? (
              <span className="text-xs text-muted-foreground">{target.reason}</span>
            ) : null}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

interface SimulatorSectionProps {
  businessId: string;
}

export function SimulatorSection({ businessId }: SimulatorSectionProps) {
  const locale = useLocale();
  const t = useTranslations("simulator");
  const queryClient = useQueryClient();

  const [scope, setScope] = useState<"business" | "campaign">("business");
  const [campaignId, setCampaignId] = useState<string>("");
  const [windowDays, setWindowDays] = useState<string>("30");
  const [budget, setBudget] = useState<string>("");
  const [targets, setTargets] = useState<Record<string, string>>({});
  const [overrides, setOverrides] = useState<Partial<Record<OverrideKey, string>>>({});
  const [active, setActive] = useState<SimulationRead | null>(null);
  const [rerunningId, setRerunningId] = useState<string | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  const { data: history, isLoading, isError, refetch } = useQuery({
    queryKey: ["simulator-history", businessId],
    queryFn: () => fetchSimulations(businessId),
    enabled: Boolean(businessId),
  });

  const { data: campaignsData } = useQuery({
    queryKey: ["metrics-campaigns", businessId, "last_30_days" as RangeKind],
    queryFn: () => fetchMetricsCampaigns(businessId, "last_30_days"),
    enabled: Boolean(businessId) && scope === "campaign",
  });
  const campaigns = useMemo(
    () => campaignsData?.campaigns ?? [],
    [campaignsData]
  );

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ["simulator-history", businessId] });
  };

  const { mutate: run, isPending: running } = useMutation({
    mutationFn: async (): Promise<SimulationRead> => {
      const payload: SimulationCreateRequest = {
        budget: budget.trim(),
        duration_days: 30,
        historical_window_days: Number(windowDays),
        entity_type: scope === "campaign" ? "campaign" : "business",
        entity_id: scope === "campaign" ? campaignId : null,
        target_cpa: nullableDecimal(targets.cpa ?? ""),
        target_roas: nullableDecimal(targets.roas ?? ""),
        target_revenue: nullableDecimal(targets.revenue ?? ""),
        target_profit: nullableDecimal(targets.profit ?? ""),
        overrides: overrides,
      };
      if (scope === "campaign" && campaignId !== "") {
        return simulateCampaign(businessId, campaignId, payload);
      }
      return createSimulation(businessId, payload);
    },
    onSuccess: (simulation) => {
      setActive(simulation);
      setRunError(null);
      invalidateAll();
    },
    onError: (error: Error) => {
      setRunError(error.message ?? t("runFailed"));
    },
  });

  const { mutate: rerun, isPending: rerunning } = useMutation({
    mutationFn: async (simulationId: string): Promise<SimulationRead> => {
      setRerunningId(simulationId);
      const refreshed = await rerunSimulation(businessId, simulationId);
      setRerunningId(null);
      return refreshed;
    },
    onSuccess: (simulation) => {
      setActive(simulation);
      setRunError(null);
      invalidateAll();
    },
    onError: (error: Error) => {
      setRerunningId(null);
      setRunError(error.message ?? t("runFailed"));
    },
  });

  if (isLoading) {
    return (
      <Card>
        <CardContent className="flex items-center gap-2 py-8 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> {t("loading")}
        </CardContent>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card>
        <CardContent className="space-y-2 py-8 text-center">
          <p className="text-muted-foreground">{t("error")}</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            {t("retry")}
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6" data-testid="simulator-section">
      <div>
        <h2 className="text-lg font-semibold">{t("title")}</h2>
        <p className="text-sm text-muted-foreground">{t("subtitle")}</p>
      </div>

      <Card>
        <CardContent className="grid gap-3 py-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-1">
            <span className="text-xs text-muted-foreground">{t("scope")}</span>
            <Select
              value={scope}
              onValueChange={(value) => {
                setScope(value as "business" | "campaign");
                setCampaignId("");
              }}
            >
              <SelectTrigger className="w-full" data-testid="scope-select">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="business">{t("scopeBusiness")}</SelectItem>
                <SelectItem value="campaign">{t("scopeCampaign")}</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {scope === "campaign" ? (
            <div className="space-y-1">
              <span className="text-xs text-muted-foreground">{t("campaign")}</span>
              <Select value={campaignId} onValueChange={setCampaignId}>
                <SelectTrigger className="w-full" data-testid="campaign-select">
                  <SelectValue placeholder={t("campaignPlaceholder")} />
                </SelectTrigger>
                <SelectContent>
                  {campaigns.length === 0 ? (
                    <SelectItem value="__none" disabled>
                      {t("noCampaigns")}
                    </SelectItem>
                  ) : (
                    campaigns.map((campaign) =>
                      campaign.id ? (
                        <SelectItem key={campaign.id} value={campaign.id}>
                          {campaign.name ?? campaign.id}
                        </SelectItem>
                      ) : null
                    )
                  )}
                </SelectContent>
              </Select>
            </div>
          ) : null}

          <div className="space-y-1">
            <span className="text-xs text-muted-foreground">{t("windowDays")}</span>
            <Select value={windowDays} onValueChange={setWindowDays}>
              <SelectTrigger className="w-full" data-testid="window-select">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SIMULATION_WINDOWS.map((window) => (
                  <SelectItem key={window} value={String(window)}>
                    {t(`window${window}` as string)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <span className="text-xs text-muted-foreground">{t("budget")}</span>
            <Input
              data-testid="budget-input"
              type="text"
              inputMode="decimal"
              value={budget}
              onChange={(event) => setBudget(event.target.value)}
              placeholder={t("budgetPlaceholder")}
            />
          </div>

          {(["cpa", "roas", "revenue", "profit"] as const).map((key) => (
            <div key={key} className="space-y-1">
              <span className="text-xs text-muted-foreground">{t(TARGET_LABELS[key] as string)}</span>
              <Input
                data-testid={`target-${key}`}
                type="text"
                inputMode="decimal"
                value={targets[key] ?? ""}
                onChange={(event) =>
                  setTargets((current) => ({ ...current, [key]: event.target.value }))
                }
                placeholder={t("targetPlaceholder")}
              />
            </div>
          ))}

          <div className="flex items-end">
            <Button
              data-testid="run-button"
              onClick={() => run()}
              disabled={running || budget.trim() === ""}
            >
              {running ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {t(running ? "running" : "run")}
            </Button>
          </div>
          {runError ? (
            <p
              className="text-sm text-red-500 sm:col-span-2 lg:col-span-4"
              data-testid="run-error"
            >
              {runError}
            </p>
          ) : null}
        </CardContent>
      </Card>

      {active ? (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">{t("scenarios")}</CardTitle>
            </CardHeader>
            <CardContent>
              {active.scenarios?.expected?.available === false ? (
                <p className="text-xs text-muted-foreground" data-testid="unavailable-note">
                  {t("unavailableNote")}
                </p>
              ) : null}
              <div className="grid gap-4 sm:grid-cols-3">
                <ScenarioCard
                  scenario={active.scenarios?.downside}
                  currency={active.currency}
                  label={t("downside")}
                />
                <ScenarioCard
                  scenario={active.scenarios?.expected}
                  currency={active.currency}
                  label={t("expected")}
                />
                <ScenarioCard
                  scenario={active.scenarios?.upside}
                  currency={active.currency}
                  label={t("upside")}
                />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm">{t("model")}</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-2">
              <div data-testid="model-used">
                <span className="text-xs text-muted-foreground">{t("model")}: </span>
                {active.model_used}
              </div>
              <div data-testid="calculation-path">
                <span className="text-xs text-muted-foreground">{t("calculationPath")}: </span>
                <span className="break-all">{active.calculation_path}</span>
              </div>
              <div>
                <span className="text-xs text-muted-foreground">{t("modelVersion")}: </span>
                {active.model_version}
              </div>
              <div>
                <span className="text-xs text-muted-foreground">{t("referenceWindow")}: </span>
                {active.reference_window
                  ? `${formatDate(locale, active.reference_window.start)} – ${formatDate(
                      locale,
                      active.reference_window.end
                    )}`
                  : "-"}
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">{t("dataQuality")}: </span>
                <span
                  data-testid={`data-quality-${active.data_quality}`}
                  className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                    QUALITY_CLASSES[active.data_quality] ?? QUALITY_CLASSES.insufficient
                  }`}
                >
                  {t(active.data_quality)}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">{t("evidenceStrength")}: </span>
                <StrengthBadge strength={active.evidence_strength} />
              </div>
              <div className="sm:col-span-2">
                <span className="text-xs text-muted-foreground">
                  {t("assumptionsHash")}:{" "}
                </span>
                <span className="break-all text-xs">{active.assumptions_hash}</span>
              </div>
            </CardContent>
          </Card>

          <ProfitabilityBlock simulation={active} currency={active.currency} />
          <BreakEvenBlock simulation={active} currency={active.currency} />
          <TargetsBlock simulation={active} currency={active.currency} />

          <SensitivityTable tables={active.sensitivity} currency={active.currency} />

          <Card>
            <CardContent className="py-4">
              <AssumptionEditor
                assumptions={active.assumptions}
                overrides={overrides}
                onOverrideChange={(key, value) =>
                  setOverrides((current) => ({ ...current, [key]: value }))
                }
              />
            </CardContent>
          </Card>
        </div>
      ) : null}

      <div>
        <h3 className="mb-3 text-lg font-semibold">{t("history")}</h3>
        <SimulationHistory
          simulations={history?.simulations}
          activeId={active?.id ?? null}
          rerunning={rerunning}
          onOpen={(simulationId) => {
            const row = history?.simulations?.find((item) => item.id === simulationId);
            if (row) setActive(row);
          }}
          onRerun={(simulationId) => rerun(simulationId)}
        />
      </div>
    </div>
  );
}