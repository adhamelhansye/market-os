"use client";

import { useState } from "react";
import type { ReactNode } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { BusinessPageHeader, useBusinessIdFromPath } from "@/components/business/business-page";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  fetchMetricsCampaigns,
  fetchMetricsComparison,
  fetchMetricsDataQuality,
  fetchMetricsFunnel,
  fetchMetricsSummary,
  fetchMetricsTimeseries,
  type MeasureRead,
  type RangeKind,
  type SummaryRead,
} from "@/features/metrics/api";
import { DiagnosticsSection } from "@/features/diagnostics/diagnostics-section";
import { formatMoney, formatRatio } from "@/lib/money";

const RANGE_OPTIONS: { value: RangeKind; labelKey: string }[] = [
  { value: "today", labelKey: "rangeToday" },
  { value: "yesterday", labelKey: "rangeYesterday" },
  { value: "last_7_days", labelKey: "rangeLast7" },
  { value: "last_14_days", labelKey: "rangeLast14" },
  { value: "last_30_days", labelKey: "rangeLast30" },
  { value: "month_to_date", labelKey: "rangeMonthToDate" },
];

type AnyMeasure = {
  value?: number | string | null;
  status: string;
  reason?: string | null;
};

function MeasureValue({
  measure,
  format,
}: {
  measure: AnyMeasure | undefined;
  format: (value: string) => string;
}) {
  if (!measure || measure.status !== "available" || measure.value === null || measure.value === undefined) {
    return (
      <span className="text-muted-foreground">{measure?.reason ?? "-"}</span>
    );
  }
  return <span>{format(String(measure.value))}</span>;
}

function formatCount(locale: string, value: string): string {
  try {
    return new Intl.NumberFormat(locale).format(Number(value));
  } catch {
    return value;
  }
}

function formatMultiplier(locale: string, value: string): string {
  try {
    const number = new Intl.NumberFormat(locale, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(Number(value));
    return `${number}×`;
  } catch {
    return `${value}×`;
  }
}

function KpiCard({
  label,
  children,
  comparison,
  comparisonLabel,
}: {
  label: string;
  children: ReactNode;
  comparison?: string | null;
  comparisonLabel?: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm text-muted-foreground">{label}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1">
        <div className="text-lg font-medium">{children}</div>
        {comparison ? (
          <p className="text-xs text-muted-foreground">
            {comparisonLabel}: {comparison}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

type ComparisonMetricKey =
  | "revenue"
  | "spend"
  | "purchases"
  | "roas"
  | "mer"
  | "cpa"
  | "aov"
  | "ctr"
  | "contribution_profit";

function percentageLabel(locale: string, value: string): string {
  // percentage_change is already in percent units (25.00 = 25%).
  try {
    const number = Number(value.replace(/[^0-9.-]/g, ""));
    return new Intl.NumberFormat(locale, {
      style: "percent",
      maximumFractionDigits: 2,
    }).format(number / 100);
  } catch {
    return value;
  }
}

export default function MetricsPage() {
  const t = useTranslations("metrics");
  const locale = useLocale();
  const businessId = useBusinessIdFromPath();
  const [rangeKind, setRangeKind] = useState<RangeKind>("last_30_days");

  const options = { enabled: Boolean(businessId) };

  const { data: summary } = useQuery({
    queryKey: ["metrics-summary", businessId ?? "", rangeKind],
    queryFn: () => fetchMetricsSummary(businessId as string, rangeKind),
    ...options,
  });
  const { data: timeseries } = useQuery({
    queryKey: ["metrics-timeseries", businessId ?? "", rangeKind],
    queryFn: () => fetchMetricsTimeseries(businessId as string, rangeKind),
    ...options,
  });
  const { data: funnel } = useQuery({
    queryKey: ["metrics-funnel", businessId ?? "", rangeKind],
    queryFn: () => fetchMetricsFunnel(businessId as string, rangeKind),
    ...options,
  });
  const { data: campaigns } = useQuery({
    queryKey: ["metrics-campaigns", businessId ?? "", rangeKind],
    queryFn: () => fetchMetricsCampaigns(businessId as string, rangeKind),
    ...options,
  });
  const { data: quality } = useQuery({
    queryKey: ["metrics-quality", businessId ?? "", rangeKind],
    queryFn: () => fetchMetricsDataQuality(businessId as string, rangeKind),
    ...options,
  });
  const { data: comparison } = useQuery({
    queryKey: ["metrics-comparison", businessId ?? "", rangeKind],
    queryFn: () => fetchMetricsComparison(businessId as string, rangeKind),
    ...options,
  });

  if (!businessId) return null;

  const currency = summary?.currency ?? "USD";
  const money = (value: string) => formatMoney(value, currency, locale);
  const count = (value: string) => formatCount(locale, value);
  const ratio = (value: string) => formatRatio(value, locale) ?? value;

  const comparisonFor = (key: ComparisonMetricKey) => {
    const item = comparison?.[key];
    if (!item || item.current === null || item.current === undefined) return null;
    const change = item.percentage_change;
    if (!change || change.status !== "available" || change.value === null || change.value === undefined) {
      return "-";
    }
    const sign = Number(change.value) >= 0 ? "+" : "";
    return `${sign}${percentageLabel(locale, change.value)}%`;
  };

  const campaignsList = campaigns?.campaigns ?? [];
  const stages = funnel?.stages ?? [];
  const points = (timeseries?.points ?? []).map((point) => ({
    ...point,
    label: new Date(`${point.date}T00:00:00Z`).toLocaleDateString(locale, {
      day: "numeric",
      month: "short",
    }),
  }));

  const hasSummaryFacts =
    summary &&
    (summary.impressions.status === "available" ||
      summary.revenue.status === "available");

  return (
    <div className="space-y-6">
      <BusinessPageHeader title={t("title")} subtitle={t("subtitle")} />
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground">{t("range")}</span>
        <Select value={rangeKind} onValueChange={(v) => setRangeKind(v as RangeKind)}>
          <SelectTrigger className="w-48">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {RANGE_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {t(option.labelKey)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {!hasSummaryFacts ? (
        <Card className="border-dashed">
          <CardHeader>
            <CardTitle>{t("emptyStateTitle")}</CardTitle>
            <CardDescription>{t("emptyStateBody")}</CardDescription>
          </CardHeader>
          <CardContent />
        </Card>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          label={t("revenue")}
          comparison={comparisonFor("revenue")}
          comparisonLabel={t("vsPrevious")}
        >
          <MeasureValue measure={summary?.revenue} format={money} />
        </KpiCard>
        <KpiCard
          label={t("spend")}
          comparison={comparisonFor("spend")}
          comparisonLabel={t("vsPrevious")}
        >
          <MeasureValue measure={summary?.spend} format={money} />
        </KpiCard>
        <KpiCard
          label={t("purchases")}
          comparison={comparisonFor("purchases")}
          comparisonLabel={t("vsPrevious")}
        >
          <MeasureValue measure={summary?.purchases} format={(v) => count(v)} />
        </KpiCard>
        <KpiCard
          label={t("contributionProfit")}
          comparison={comparisonFor("contribution_profit")}
          comparisonLabel={t("vsPrevious")}
        >
          <MeasureValue measure={summary?.contribution_profit} format={money} />
        </KpiCard>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard label={t("ctr")} comparison={comparisonFor("ctr")} comparisonLabel={t("vsPrevious")}>
          <MeasureValue measure={summary?.ctr} format={ratio} />
        </KpiCard>
        <KpiCard label={t("cpc")}>
          <MeasureValue measure={summary?.cpc} format={money} />
        </KpiCard>
        <KpiCard label={t("cpm")}>
          <MeasureValue measure={summary?.cpm} format={money} />
        </KpiCard>
        <KpiCard label={t("cvr")}>
          <MeasureValue measure={summary?.cvr} format={ratio} />
        </KpiCard>
        <KpiCard label={t("cpa")} comparison={comparisonFor("cpa")} comparisonLabel={t("vsPrevious")}>
          <MeasureValue measure={summary?.cpa} format={money} />
        </KpiCard>
        <KpiCard label={t("aov")} comparison={comparisonFor("aov")} comparisonLabel={t("vsPrevious")}>
          <MeasureValue measure={summary?.aov} format={money} />
        </KpiCard>
        <KpiCard label={t("roas")} comparison={comparisonFor("roas")} comparisonLabel={t("vsPrevious")}>
          <MeasureValue measure={summary?.roas} format={(v) => formatMultiplier(locale, v)} />
        </KpiCard>
        <KpiCard label={t("mer")} comparison={comparisonFor("mer")} comparisonLabel={t("vsPrevious")}>
          <MeasureValue measure={summary?.mer} format={(v) => formatMultiplier(locale, v)} />
        </KpiCard>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t("trend")}</CardTitle>
          <CardDescription>{t("revenue")} / {t("spend")}</CardDescription>
        </CardHeader>
        <CardContent>
          {points.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("noFacts")}</p>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={points}>
                <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => formatCount(locale, String(v))} />
                <Tooltip
                  formatter={(value: unknown, name: unknown) => [
                    typeof value === "number" ? formatCount(locale, String(value)) : String(value ?? ""),
                    name === "revenue" ? t("revenue") : t("spend"),
                  ]}
                />
                <Line
                  type="monotone"
                  dataKey="revenue"
                  stroke="hsl(var(--primary))"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="spend"
                  stroke="hsl(var(--muted-foreground))"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>{t("funnel")}</CardTitle>
          </CardHeader>
          <CardContent>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left rtl:text-right text-muted-foreground">
                  <th className="py-2 pe-2 font-normal">{t("name")}</th>
                  <th className="py-2 pe-2 font-normal text-end">{t("purchases")}</th>
                  <th className="py-2 pe-2 font-normal text-end">{t("funnelConversion")}</th>
                  <th className="py-2 font-normal text-end">{t("funnelDropoff")}</th>
                </tr>
              </thead>
              <tbody>
                {stages.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="py-4 text-muted-foreground">{t("noFacts")}</td>
                  </tr>
                ) : (
                  stages.map((stage) => {
                    const conversion = stage.conversion_rate;
                    const dropoff = stage.dropoff_rate;
                    return (
                      <tr key={stage.metric} className="border-b">
                        <td className="py-2 pe-2">{t(stage.metric)}</td>
                        <td className="py-2 pe-2 text-end">
                          {stage.status === "available" && stage.value !== null
                            ? count(String(stage.value))
                            : "-"}
                        </td>
                        <td className="py-2 pe-2 text-end">
                          {conversion && conversion.status === "available"
                            ? ratio(String(conversion.value))
                            : "-"}
                        </td>
                        <td className="py-2 text-end">
                          {dropoff && dropoff.status === "available"
                            ? ratio(String(dropoff.value))
                            : "-"}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t("campaigns")}</CardTitle>
          </CardHeader>
          <CardContent>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left rtl:text-right text-muted-foreground">
                  <th className="py-2 pe-2 font-normal">{t("name")}</th>
                  <th className="py-2 pe-2 font-normal text-end">{t("spend")}</th>
                  <th className="py-2 pe-2 font-normal text-end">{t("impressions")}</th>
                  <th className="py-2 pe-2 font-normal text-end">{t("ctr")}</th>
                  <th className="py-2 font-normal text-end">{t("roas")}</th>
                </tr>
              </thead>
              <tbody>
                {campaignsList.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="py-4 text-muted-foreground">{t("noFacts")}</td>
                  </tr>
                ) : (
                  campaignsList.map((campaign) => (
                    <tr key={campaign.id} className="border-b">
                      <td className="py-2 pe-2">{campaign.name ?? "-"}</td>
                      <td className="py-2 pe-2 text-end">
                        {campaign.spend !== null ? money(String(campaign.spend)) : "-"}
                      </td>
                      <td className="py-2 pe-2 text-end">
                        {campaign.impressions !== null ? count(String(campaign.impressions)) : "-"}
                      </td>
                      <td className="py-2 pe-2 text-end">
                        {campaign.ctr?.status === "available"
                          ? ratio(String(campaign.ctr.value))
                          : "-"}
                      </td>
                      <td className="py-2 text-end">
                        {campaign.roas?.status === "available"
                          ? formatMultiplier(locale, String(campaign.roas.value))
                          : "-"}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t("dataQuality")}</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          {(quality?.providers ?? []).map((provider) => (
            <div key={provider.provider} className="space-y-1 text-sm">
              <div className="flex items-center justify-between">
                <span className="font-medium">{provider.provider}</span>
                <span
                  className={
                    provider.freshness_status === "fresh"
                      ? "text-emerald-600"
                      : provider.freshness_status === "stale"
                        ? "text-destructive"
                        : "text-muted-foreground"
                  }
                >
                  {provider.freshness_status === "fresh"
                    ? t("fresh")
                    : provider.freshness_status === "delayed"
                      ? t("delayed")
                      : provider.freshness_status === "stale"
                        ? t("stale")
                        : t("unavailable")}
                </span>
              </div>
              <p className="text-muted-foreground">
                {provider.connected ? (
                  provider.coverage_start && provider.coverage_end
                    ? `${provider.coverage_start} – ${provider.coverage_end} · ${
                        (provider.covered_days ?? 0) + (provider.missing_days ?? 0)
                      } ${t("coverage").toLowerCase()}`
                    : provider.reason
                ) : (
                  t("notConnected")
                )}
                {provider.reason ? ` · ${provider.reason}` : ""}
              </p>
            </div>
          ))}
        </CardContent>
      </Card>

      <DiagnosticsSection businessId={businessId as string} rangeKind={rangeKind} />
    </div>
  );
}

export type { SummaryRead };