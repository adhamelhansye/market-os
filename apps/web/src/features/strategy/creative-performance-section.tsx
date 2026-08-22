"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError } from "@/lib/api-client";
import {
  createCreativePerformanceSnapshot,
  fetchCreativePerformanceReport,
  type CreativePerformanceReport,
  type PerformanceEntityResult,
  type PerformanceSignal,
} from "./api";

function signalValueOrState(signal: PerformanceSignal, t: (key: string) => string): string {
  if (signal.status === "available" && signal.value != null) return String(signal.value);
  if (signal.status === "insufficient_data") return t("insufficientData");
  if (signal.reason) return `${t("unavailable")} (${signal.reason})`;
  return t("unavailable");
}

function SignalsTable({ entity, t }: { entity: PerformanceEntityResult; t: (key: string) => string }) {
  const signals = entity.signals ?? [];
  return (
    <div className="grid gap-1 text-xs" data-testid="performance-signals">
      {signals.map((signal) => (
        <div key={signal.code} className="flex flex-wrap items-center justify-between gap-2">
          <span className="font-medium">
            {signal.code}
            <span className="ml-1 text-muted-foreground">· {signal.source}</span>
          </span>
          <span
          className={
            signal.status === "available"
              ? "text-muted-foreground"
              : "text-amber-600 dark:text-amber-400"
          }
          >
            {signalValueOrState(signal, t)}
          </span>
        </div>
      ))}
    </div>
  );
}

function TrendBlock({ entity, t }: { entity: PerformanceEntityResult; t: (key: string) => string }) {
  const metrics = entity.trend?.metrics ?? {};
  return (
    <div className="text-xs text-muted-foreground" data-testid="performance-trend">
      <span className="font-medium">{t("trend")}: </span>
      {Object.keys(metrics).length ? (
        Object.entries(metrics).map(([code, info]) => (
          <span key={code} className="mr-2">
            {code}: {info.direction ?? t("unavailable")}
          </span>
        ))
      ) : (
        <span>{t("insufficientData")}</span>
      )}
    </div>
  );
}

function FatigueBlock({ entity, t }: { entity: PerformanceEntityResult; t: (key: string) => string }) {
  const fatigue = entity.fatigue;
  if (!fatigue) return null;
  const triggered = (fatigue.signals ?? []).filter((s) => s.triggered).map((s) => s.code);
  return (
    <div className="text-xs" data-testid="performance-fatigue">
      <span className="font-medium">{t("fatigue")}: </span>
      <span
        className={
          fatigue.status === "fatigue_signal"
            ? "text-destructive"
            : fatigue.status === "watch"
              ? "text-amber-600 dark:text-amber-400"
              : "text-muted-foreground"
        }
      >
        {fatigue.status}
      </span>
      {triggered.length ? <span> · {t("signals")}: {triggered.join(", ")}</span> : null}
      {fatigue.status === "insufficient_data" ? (
        <span className="text-muted-foreground"> · {t("insufficientWindows")}</span>
      ) : null}
    </div>
  );
}

function ReadinessBlock({ entity, t }: { entity: PerformanceEntityResult; t: (key: string) => string }) {
  const readiness = entity.scaling_readiness;
  if (!readiness) return null;
  return (
    <div className="text-xs" data-testid="performance-readiness">
      <span className="font-medium">{t("readiness")}: </span>
      <span>{readiness.status}</span>
      {readiness.gates?.length ? (
        <span className="ml-2 text-muted-foreground">
          {readiness.gates.map((gate) => `${gate.code}${gate.met ? "✓" : "✗"}`).join(" · ")}
        </span>
      ) : null}
    </div>
  );
}

function ProvenanceChain({ entity, t }: { entity: PerformanceEntityResult; t: (key: string) => string }) {
  const steps = entity.provenance?.chain ?? [];
  if (!steps.length) return null;
  return (
    <div className="border-t pt-2 text-xs text-muted-foreground">
      <div className="font-medium">{t("provenance")}</div>
      <div>{steps.map((step) => step.id ?? step.step).join(" → ")}</div>
    </div>
  );
}

function EntityCard({ entity, t }: { entity: PerformanceEntityResult; t: (key: string) => string }) {
  const classification = entity.classification;
  return (
    <div className="space-y-3 rounded-md border p-3" data-testid="performance-entity">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-medium text-sm">
          {entity.entity.type} · {entity.entity.id.slice(0, 8)}
        </span>
        <span className="flex gap-2 text-xs">
          {classification ? (
            <span className="rounded-md border px-2 py-0.5" data-testid="performance-classification">
              {classification.status}
            </span>
          ) : null}
          {entity.attribution?.status !== "linked" ? (
            <span className="rounded-md border px-2 py-0.5 text-destructive">
              {entity.attribution?.reason ?? entity.attribution?.status}
            </span>
          ) : null}
        </span>
      </div>
      <SignalsTable entity={entity} t={t} />
      <TrendBlock entity={entity} t={t} />
      <FatigueBlock entity={entity} t={t} />
      <ReadinessBlock entity={entity} t={t} />
      {classification?.rule ? (
        <div className="text-xs text-muted-foreground">
          {t("rule")}: {classification.rule}
          {classification.reasons?.length ? ` · ${classification.reasons.join("; ")}` : null}
        </div>
      ) : null}
      <ProvenanceChain entity={entity} t={t} />
    </div>
  );
}

function Comparisons({
  comparisons,
  t,
}: {
  comparisons: CreativePerformanceReport["comparisons"];
  t: (key: string) => string;
}) {
  const dimensions = Object.entries(comparisons ?? {});
  if (!dimensions.length) return null;
  return (
    <div className="space-y-3" data-testid="performance-comparisons">
      <div className="text-sm font-medium">{t("comparisons")}</div>
      {dimensions.map(([dimension, groups]) => (
        <div key={dimension}>
          <div className="mb-1 text-xs font-medium text-muted-foreground">{dimension}</div>
          <div className="grid gap-2 xl:grid-cols-2">
            {Object.entries(groups as Record<string, { ranked?: { rank: number; entity: { id: string }; value: string | null }[] }>).map(
              ([group, result]) => (
                <div key={group} className="rounded-md border p-2 text-xs">
                  <div className="mb-1 text-muted-foreground">{group}</div>
                  {(result.ranked ?? []).map((item) => (
                    <div key={item.entity.id} className="flex justify-between">
                      <span>
                        #{item.rank} · {item.entity.id.slice(0, 8)}
                      </span>
                      <span className="text-muted-foreground">
                        {item.value ?? t("unavailable")}
                      </span>
                    </div>
                  ))}
                </div>
              )
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

export function CreativePerformanceSection({ businessId }: { businessId: string }) {
  const t = useTranslations("strategy");
  const [rangeKind, setRangeKind] = useState("last_30_days");
  const query = useQuery({
    queryKey: ["creative-performance", businessId, rangeKind],
    queryFn: () => fetchCreativePerformanceReport(businessId, rangeKind),
    enabled: Boolean(businessId),
  });
  const snapshotMutation = useMutation({
    mutationFn: () => createCreativePerformanceSnapshot(businessId, rangeKind),
  });

  const report = query.data;

  return (
    <Card data-testid="creative-performance-section">
      <CardHeader>
        <CardTitle>{t("creativePerformance")}</CardTitle>
        <CardDescription>{t("creativePerformanceDescription")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <select
            aria-label={t("range")}
            className="rounded-md border bg-background px-2 py-1 text-sm"
            value={rangeKind}
            onChange={(event) => setRangeKind(event.target.value)}
          >
            <option value="last_7_days">last_7_days</option>
            <option value="last_14_days">last_14_days</option>
            <option value="last_30_days">last_30_days</option>
          </select>
          <Button
            type="button"
            variant="outline"
            onClick={() => snapshotMutation.mutate()}
            disabled={snapshotMutation.isPending || !report}
          >
            {snapshotMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : t("saveSnapshot")}
          </Button>
          {snapshotMutation.isSuccess ? (
            <span className="text-xs text-muted-foreground">
              {t("snapshotSaved")} · {snapshotMutation.data.fingerprint.slice(0, 12)}
            </span>
          ) : null}
        </div>

        {query.isLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> {t("loadingPerformance")}
          </div>
        ) : null}
        {query.isError && !(query.error instanceof ApiError && query.error.status === 404) ? (
          <p className="text-sm text-destructive">{t("performanceError")}</p>
        ) : null}

        {report ? (
          <>
            <div className="text-xs text-muted-foreground" data-testid="performance-attribution">
              {t("attribution")}:{" "}
              {report.attribution.status === "linked"
                ? t("attributionLinked", { count: report.attribution.linked_entities })
                : t("attributionUnavailable", {
                    reason: report.attribution.reason ?? report.attribution.status,
                  })}
            </div>
            {report.entities.length ? (
              <div className="grid gap-2 xl:grid-cols-2">
                {report.entities.map((entity) => (
                  <EntityCard key={entity.link_id ?? entity.entity.id} entity={entity} t={t} />
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground" data-testid="performance-empty">
                {t("noLinkedEntities")}
              </p>
            )}
            <Comparisons comparisons={report.comparisons} t={t} />
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
