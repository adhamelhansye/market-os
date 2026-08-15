"use client";

import { useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { formatMoney, formatRatio } from "@/lib/money";

import {
  fetchDiagnostics,
  type CampaignStateRead,
  type DiagnosticsRead,
  type FindingRead,
} from "@/features/diagnostics/api";
import type { RangeKind } from "@/features/metrics/api";

const SEVERITIES = ["info", "low", "medium", "high", "critical"] as const;
const CATEGORIES = [
  "traffic",
  "creative",
  "conversion",
  "offer",
  "funnel",
  "economics",
  "tracking",
  "data_quality",
  "performance",
  "scaling_readiness",
] as const;
const STATUSES = ["detected", "resolved", "insufficient_data"] as const;
const ENTITY_TYPES = ["business", "campaign", "ad_set", "ad"] as const;

const SEVERITY_CLASSES: Record<string, string> = {
  info: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  low: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  medium: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  high: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300",
  critical: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
};

type Severity = (typeof SEVERITIES)[number];

function labelKey(prefix: string, value: string): string {
  const pascal = value
    .split("_")
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
    .join("");
  return `${prefix}${pascal}`;
}

function formatValue(value: number | string | null | undefined, unit: string, currency: string, locale: string): string {
  if (value === null || value === undefined) return "-";
  const raw = String(value);
  if (unit === "money") return formatMoney(raw, currency, locale);
  if (unit === "ratio") return formatRatio(raw, locale) ?? raw;
  if (unit === "percent") {
    try {
      return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(Number(raw))}%`;
    } catch {
      return `${raw}%`;
    }
  }
  if (unit === "multiplier") {
    try {
      return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(Number(raw))}×`;
    } catch {
      return `${raw}×`;
    }
  }
  return new Intl.NumberFormat(locale).format(Number(raw));
}

function SeverityBadge({ severity, t }: { severity: string; t: (key: string) => string }) {
  return (
    <span
      data-testid={`severity-${severity}`}
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${SEVERITY_CLASSES[severity] ?? SEVERITY_CLASSES.info}`}
    >
      {t(labelKey("severity", severity))}
    </span>
  );
}

function StateBadge({ state, t }: { state: string; t: (key: string) => string }) {
  return (
    <span
      data-testid={`state-${state}`}
      className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium dark:bg-slate-800"
    >
      {t(labelKey("state", state))}
    </span>
  );
}

function FindingCard({
  finding,
  currency,
  locale,
  t,
}: {
  finding: FindingRead;
  currency: string;
  locale: string;
  t: (key: string) => string;
}) {
  const evidence = finding.evidence;
  const threshold = evidence.threshold?.value;
  const metricCurrent = evidence.metric?.current;
  const unit = evidence.threshold?.unit ?? "count";
  return (
    <Card data-testid="finding-card">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <div className="space-y-1">
            <CardTitle className="text-sm">{t(finding.title_key)}</CardTitle>
            <CardDescription className="text-xs">{t(finding.description_key)}</CardDescription>
          </div>
          <SeverityBadge severity={finding.severity} t={t} />
        </div>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span>
            {t("category")}: {t(labelKey("category", finding.category))}
          </span>
          {finding.entity_type !== "business" ? (
            <span>
              {t("entityType")}: {finding.entity_name ?? finding.entity_type}
            </span>
          ) : null}
          {finding.affected_stage ? (
            <span>
              {t("affectedStage")}: {t(labelKey("stage", finding.affected_stage))}
            </span>
          ) : null}
          <span>{finding.range.start} – {finding.range.end}</span>
        </div>

        {evidence.metric?.code ? (
          <div className="grid gap-1 sm:grid-cols-2">
            <p className="text-xs">
              {t("metric")}: {evidence.metric.code}
              {metricCurrent !== null && metricCurrent !== undefined
                ? ` — ${formatValue(metricCurrent, unit, currency, locale)}`
                : ` (${t("insufficientData")})`}
            </p>
            {threshold !== null && threshold !== undefined ? (
              <p className="text-xs" data-testid="threshold-value">
                {t("threshold")}: {formatValue(threshold, unit, currency, locale)}
              </p>
            ) : null}
          </div>
        ) : null}

        {evidence.comparison?.change_percent !== null &&
        evidence.comparison?.change_percent !== undefined ? (
          <p className="text-xs">
            {t("comparison")}: {formatValue(evidence.comparison.change_percent, "percent", currency, locale)}
          </p>
        ) : null}

        {evidence.funnel ? (
          <p className="text-xs text-muted-foreground">
            {t("fromStage")} <strong>{evidence.funnel.from_stage}</strong> → {t("toStage")}{" "}
            <strong>{evidence.funnel.to_stage}</strong> · {t("conversionRate")}:{" "}
            {formatValue(evidence.funnel.conversion_rate, "ratio", currency, locale)}
            {evidence.funnel.previous_rate !== null
              ? ` · ${t("previousRate")}: ${formatValue(evidence.funnel.previous_rate, "ratio", currency, locale)}`
              : ""}
          </p>
        ) : null}

        {evidence.facts && evidence.facts.length > 0 ? (
          <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            {evidence.facts.map((fact) => (
              <li key={fact.code} data-testid={`fact-${fact.code}`}>
                {fact.code}: {formatValue(fact.value, fact.unit, currency, locale)}
              </li>
            ))}
          </ul>
        ) : null}

        {finding.review_status ? (
          <p
            data-testid="review-status"
            className={`text-xs font-medium ${finding.review_status === "review_required" ? "text-amber-600" : "text-muted-foreground"}`}
          >
            {finding.review_status === "review_required" ? t("reviewRequired") : t("reviewReady")}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function DiagnosticsSection({
  businessId,
  rangeKind,
}: {
  businessId: string;
  rangeKind: RangeKind;
}) {
  const t = useTranslations("diagnostics");
  const locale = useLocale();
  const [entityType, setEntityType] = useState<string>("all");
  const [severity, setSeverity] = useState<string>("all");
  const [category, setCategory] = useState<string>("all");
  const [status, setStatus] = useState<string>("all");

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["diagnostics", businessId, rangeKind],
    queryFn: () => fetchDiagnostics(businessId, rangeKind),
    enabled: Boolean(businessId),
  });

  const findings = useMemo(() => {
    const list = data?.findings ?? [];
    return list.filter(
      (f) =>
        (entityType === "all" || f.entity_type === entityType) &&
        (severity === "all" || f.severity === severity) &&
        (category === "all" || f.category === category) &&
        (status === "all" || f.status === status)
    );
  }, [data, entityType, severity, category, status]);
  const dataQualityFindings = useMemo(
    () => (data?.findings ?? []).filter((f) => f.category === "data_quality"),
    [data]
  );
  const bottleneck = useMemo(
    () => (data?.findings ?? []).find((f) => f.code === "funnel_bottleneck"),
    [data]
  );
  const campaignStates = data?.campaign_states ?? [];
  const currency = data?.currency ?? "USD";
  const summary = data?.summary;

  const clearFilters = () => {
    setEntityType("all");
    setSeverity("all");
    setCategory("all");
    setStatus("all");
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold">{t("title")}</h2>
        <p className="text-sm text-muted-foreground">{t("subtitle")}</p>
      </div>

      {isLoading ? (
        <Card>
          <CardContent className="flex items-center gap-2 py-8 text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> {t("loading")}
          </CardContent>
        </Card>
      ) : isError ? (
        <Card>
          <CardContent className="py-8 text-center space-y-2">
            <p className="text-muted-foreground">{t("error")}</p>
            <Button variant="outline" size="sm" onClick={() => refetch()}>
              {t("retry")}
            </Button>
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm text-muted-foreground">{t("totalFindings")}</CardTitle>
              </CardHeader>
              <CardContent data-testid="summary-total" className="text-lg font-medium">
                {summary?.total_findings ?? 0}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-sm text-muted-foreground">{t("severityCritical")}</CardTitle>
              </CardHeader>
              <CardContent data-testid="summary-critical" className="text-lg font-medium">
                {summary?.critical ?? 0}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-sm text-muted-foreground">{t("affectedEntities")}</CardTitle>
              </CardHeader>
              <CardContent data-testid="summary-entities" className="text-lg font-medium">
                {summary?.affected_entities ?? 0}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-sm text-muted-foreground">{t("insufficientData")}</CardTitle>
              </CardHeader>
              <CardContent data-testid="summary-insufficient" className="text-lg font-medium">
                {summary?.insufficient_data ?? 0}
              </CardContent>
            </Card>
          </div>

          {bottleneck ? (
            <Card className="border-amber-300 dark:border-amber-800">
              <CardHeader>
                <CardTitle className="text-sm">{t("funnelBottleneck")}</CardTitle>
                <CardDescription className="text-xs">{t("funnelBottleneckBody")}</CardDescription>
              </CardHeader>
              <CardContent data-testid="funnel-bottleneck" className="text-sm">
                {t(bottleneck.title_key)} — {bottleneck.evidence.funnel?.from_stage} →{" "}
                {bottleneck.evidence.funnel?.to_stage}
              </CardContent>
            </Card>
          ) : null}

          <Card>
            <CardHeader>
              <CardTitle className="text-sm">{t("filters")}</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-wrap items-end gap-3">
              <div className="space-y-1">
                <span className="text-xs text-muted-foreground">{t("entityType")}</span>
                <Select value={entityType} onValueChange={setEntityType}>
                  <SelectTrigger className="w-40" data-testid="filter-entity">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">{t("all")}</SelectItem>
                    {ENTITY_TYPES.map((value) => (
                      <SelectItem key={value} value={value}>
                        {t(labelKey("entity", value))}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <span className="text-xs text-muted-foreground">{t("severity")}</span>
                <Select value={severity} onValueChange={setSeverity}>
                  <SelectTrigger className="w-40" data-testid="filter-severity">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">{t("all")}</SelectItem>
                    {SEVERITIES.map((value) => (
                      <SelectItem key={value} value={value}>
                        {t(labelKey("severity", value))}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <span className="text-xs text-muted-foreground">{t("category")}</span>
                <Select value={category} onValueChange={setCategory}>
                  <SelectTrigger className="w-40" data-testid="filter-category">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">{t("all")}</SelectItem>
                    {CATEGORIES.map((value) => (
                      <SelectItem key={value} value={value}>
                        {t(labelKey("category", value))}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <span className="text-xs text-muted-foreground">{t("status")}</span>
                <Select value={status} onValueChange={setStatus}>
                  <SelectTrigger className="w-40" data-testid="filter-status">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">{t("all")}</SelectItem>
                    {STATUSES.map((value) => (
                      <SelectItem key={value} value={value}>
                        {t(labelKey("status", value))}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <Button variant="ghost" size="sm" onClick={clearFilters}>
                {t("clearFilters")}
              </Button>
            </CardContent>
          </Card>

          <div className="space-y-3" data-testid="findings-list">
            {findings.length === 0 ? (
              <Card className="border-dashed">
                <CardContent className="py-6 text-center">
                  <p className="text-sm font-medium">{t("noFindings")}</p>
                  <p className="text-xs text-muted-foreground">{t("noFindingsBody")}</p>
                </CardContent>
              </Card>
            ) : (
              findings.map((finding) => (
                <FindingCard
                  key={finding.id}
                  finding={finding}
                  currency={currency}
                  locale={locale}
                  t={t}
                />
              ))
            )}
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm">{t("campaignStates")}</CardTitle>
            </CardHeader>
            <CardContent>
              {campaignStates.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t("noCampaignStates")}</p>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left rtl:text-right text-muted-foreground">
                      <th className="py-2 pe-2 font-normal">{t("entityType")}</th>
                      <th className="py-2 pe-2 font-normal">{t("campaignStates")}</th>
                      <th className="py-2 pe-2 font-normal">{t("scalingStatus")}</th>
                      <th className="py-2 pe-2 font-normal text-end">{t("findingCount")}</th>
                      <th className="py-2 font-normal text-end">{t("highestSeverity")}</th>
                    </tr>
                  </thead>
                  <tbody data-testid="campaign-states-body">
                    {campaignStates.map((state: CampaignStateRead) => (
                      <tr key={state.campaign_id} className="border-b">
                        <td className="py-2 pe-2">{state.name ?? "-"}</td>
                        <td className="py-2 pe-2">
                          <StateBadge state={state.performance_state} t={t} />
                        </td>
                        <td className="py-2 pe-2 text-xs text-muted-foreground">
                          {state.scaling_readiness
                            ? t(labelKey("scaling", state.scaling_readiness.status))
                            : "-"}
                        </td>
                        <td className="py-2 pe-2 text-end">{state.finding_count}</td>
                        <td className="py-2 text-end">
                          {state.highest_severity ? (
                            <SeverityBadge severity={state.highest_severity} t={t} />
                          ) : (
                            "-"
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm">{t("dataQualityWarnings")}</CardTitle>
            </CardHeader>
            <CardContent data-testid="data-quality-warnings">
              {dataQualityFindings.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t("noDataQualityWarnings")}</p>
              ) : (
                <ul className="space-y-1 text-sm">
                  {dataQualityFindings.map((finding) => (
                    <li key={finding.id} className="flex items-center justify-between gap-2">
                      <span>{t(finding.title_key)}</span>
                      <SeverityBadge severity={finding.severity} t={t} />
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

export type { DiagnosticsRead, FindingRead };