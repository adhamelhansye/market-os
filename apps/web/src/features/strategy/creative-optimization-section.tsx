"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  fetchOptimizationSection,
  fetchOptimizationSummary,
  generateCreativeOptimization,
  type OptimizationOpportunity,
} from "./api";

function OpportunityRow({ item }: { item: Record<string, unknown> }) {
  const opportunity = item as unknown as OptimizationOpportunity;
  return (
    <div
      className="rounded-md border p-2 text-sm"
      data-testid={`optimization-opportunity-${opportunity.type}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-medium">{opportunity.type}</span>
        <span className="flex flex-wrap items-center gap-2 text-xs">
          <span className="rounded-md border px-2 py-0.5">{opportunity.priority}</span>
          <span className="text-muted-foreground">
            {opportunity.evidence_strength} · {opportunity.data_sufficiency}
          </span>
          <span
            className="rounded-md border border-dashed px-2 py-0.5 text-muted-foreground"
            data-testid="optimization-review-only"
          >
            review_only
          </span>
        </span>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">{opportunity.rationale}</p>
      <div className="mt-1 text-xs text-muted-foreground">
        {opportunity.dimension}: {opportunity.target_reference} ·{" "}
        {opportunity.learning_value}
      </div>
      {opportunity.contradicting_entity_ids?.length ? (
        <div className="mt-1 text-xs text-destructive">
          contradicting: {opportunity.contradicting_entity_ids.length}
        </div>
      ) : null}
    </div>
  );
}

function ProjectionList({
  query,
  render,
  testId,
}: {
  query: { isLoading: boolean; data?: { status: string; reason?: string | null; items?: Record<string, unknown>[] } };
  render: (items: Record<string, unknown>[]) => React.ReactNode;
  testId: string;
}) {
  const t = useTranslations("strategy");
  if (query.isLoading) {
    return <div className="text-xs text-muted-foreground">{t("loadingPerformance")}</div>;
  }
  if (!query.data || query.data.status !== "available") {
    return (
      <div className="rounded-md border border-dashed p-2 text-xs text-muted-foreground">
        {query.data?.status === "no_snapshot"
          ? t("noOptimizationSnapshot")
          : (query.data?.reason ?? t("unavailable"))}
      </div>
    );
  }
  const items = query.data.items ?? [];
  if (!items.length) {
    return <div className="text-xs text-muted-foreground">{t("noLearningItems")}</div>;
  }
  return <div data-testid={testId}>{render(items)}</div>;
}

export function CreativeOptimizationSection({ businessId }: { businessId: string }) {
  const t = useTranslations("strategy");
  const queryClient = useQueryClient();

  const summaryQuery = useQuery({
    queryKey: ["creative-optimization-summary", businessId],
    queryFn: () => fetchOptimizationSummary(businessId),
    enabled: Boolean(businessId),
  });
  const opportunitiesQuery = useQuery({
    queryKey: ["creative-optimization-opportunities", businessId],
    queryFn: () => fetchOptimizationSection(businessId, "opportunities"),
    enabled: Boolean(businessId),
  });
  const blockedQuery = useQuery({
    queryKey: ["creative-optimization-blocked", businessId],
    queryFn: () => fetchOptimizationSection(businessId, "blocked"),
    enabled: Boolean(businessId),
  });

  const generateMutation = useMutation({
    mutationFn: () => generateCreativeOptimization(businessId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["creative-optimization-summary", businessId],
      });
      void queryClient.invalidateQueries({
        queryKey: ["creative-optimization-opportunities", businessId],
      });
      void queryClient.invalidateQueries({
        queryKey: ["creative-optimization-blocked", businessId],
      });
    },
  });

  const summary = summaryQuery.data;

  return (
    <Card data-testid="creative-optimization-section">
      <CardHeader>
        <CardTitle>{t("creativeOptimization")}</CardTitle>
        <CardDescription>{t("creativeOptimizationDescription")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={() => generateMutation.mutate()}
            disabled={generateMutation.isPending}
          >
            {generateMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              t("generateOptimization")
            )}
          </Button>
          {summary?.fingerprint ? (
            <span className="text-xs text-muted-foreground" data-testid="optimization-fingerprint">
              {t("snapshotFingerprint")}: {summary.fingerprint.slice(0, 12)}
            </span>
          ) : null}
        </div>

        {summary && summary.status === "available" ? (
          <div className="grid gap-1 rounded-md border p-3 text-xs sm:grid-cols-2" data-testid="optimization-summary">
            <div>
              {t("optimizationStatus")}:{" "}
              <span className="rounded-md border px-2 py-0.5">
                {summary.optimization_status}
              </span>
            </div>
            <div>
              {t("observedEntities")}: {summary.entities_sufficient ?? t("unavailable")} /{" "}
              {summary.entities_total ?? t("unavailable")}
            </div>
            <div>
              {t("opportunitiesCount")}: {summary.opportunities_total ?? 0}
            </div>
            <div className="text-muted-foreground">{summary.note}</div>
          </div>
        ) : summary && summary.status !== "available" ? (
          <div
            className="rounded-md border border-dashed p-3 text-sm text-muted-foreground"
            data-testid="optimization-empty"
          >
            {summary.status === "no_snapshot"
              ? t("noOptimizationSnapshot")
              : (summary.reason ?? t("unavailable"))}
          </div>
        ) : null}

        <div>
          <div className="mb-1 text-sm font-medium">{t("opportunitiesTitle")}</div>
          <ProjectionList
            query={opportunitiesQuery}
            testId="optimization-opportunities-list"
            render={(items) => (
              <div className="space-y-2">
                {items.map((item, index) => (
                  <OpportunityRow key={index} item={item} />
                ))}
              </div>
            )}
          />
        </div>

        <div>
          <div className="mb-1 text-sm font-medium">{t("blockedTitle")}</div>
          <ProjectionList
            query={blockedQuery}
            testId="optimization-blocked-list"
            render={(items) => (
              <div className="space-y-1 text-xs">
                {items.map((raw, index) => {
                  const blocked = raw as {
                    type?: string;
                    target_reference?: string;
                    blocked_by_gate?: string;
                    statement?: string;
                  };
                  return (
                    <div key={index} className="rounded-md border border-dashed p-2" data-testid="optimization-blocked-item">
                      <span className="font-medium">{blocked.type}</span> ·{" "}
                      {blocked.target_reference} ·{" "}
                      <span className="text-destructive">
                        {blocked.blocked_by_gate}
                      </span>
                      <div className="text-muted-foreground">{blocked.statement}</div>
                    </div>
                  );
                })}
              </div>
            )}
          />
        </div>
      </CardContent>
    </Card>
  );
}
