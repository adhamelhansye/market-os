"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  fetchDecisionPlanItems,
  fetchDecisionPlanSummary,
  generateDecisionPlan,
  reviewDecisionItem,
  type DecisionPlanItem,
} from "./api";

function ItemRow({
  item,
  businessId,
  t,
}: {
  item: Record<string, unknown>;
  businessId: string;
  t: (key: string) => string;
}) {
  const queryClient = useQueryClient();
  const decision_item = item as unknown as DecisionPlanItem;
  const reviewMutation = useMutation({
    mutationFn: (review_state: "acknowledged" | "dismissed" | "deferred") =>
      reviewDecisionItem(businessId, decision_item.opportunity_id, { review_state }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["decision-plan-summary", businessId],
      });
      void queryClient.invalidateQueries({
        queryKey: ["decision-plan-items", businessId],
      });
    },
  });

  const stateChip = (value: string, destructive = false) => (
    <span
      className={`rounded-md border px-2 py-0.5 text-xs ${
        destructive ? "text-destructive" : "text-muted-foreground"
      }`}
    >
      {value}
    </span>
  );

  return (
    <div
      className="rounded-md border p-3 text-sm"
      data-testid={`decision-item-${decision_item.opportunity_id}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-medium">{decision_item.type}</span>
        <span className="flex flex-wrap items-center gap-2 text-xs">
          <span className="rounded-md border px-2 py-0.5">{decision_item.priority}</span>
          <span className="text-muted-foreground">
            {decision_item.evidence_strength} · {decision_item.learning_value}
          </span>
          <span
            className="rounded-md border px-2 py-0.5"
            data-testid={`decision-review-state-${decision_item.opportunity_id}`}
          >
            {decision_item.review_state}
          </span>
          <span className="rounded-md border border-dashed px-2 py-0.5 text-muted-foreground">
            review_only
          </span>
        </span>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">{decision_item.rationale}</p>
      <div className="mt-1 text-xs text-muted-foreground">
        {decision_item.dimension}: {decision_item.target_reference} ·{" "}
        {t("suggestedReviewFocus")}: {decision_item.suggested_review_focus}
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        {(["acknowledged", "dismissed", "deferred"] as const).map((state) => (
          <Button
            key={state}
            type="button"
            variant="outline"
            size="sm"
            disabled={reviewMutation.isPending || decision_item.review_state === state}
            onClick={() => reviewMutation.mutate(state)}
            data-testid={`decision-${state}-${decision_item.opportunity_id}`}
          >
            {reviewMutation.isPending && reviewMutation.variables === state ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              t(`reviewAction_${state}`)
            )}
          </Button>
        ))}
      </div>
      <p className="mt-2 text-[10px] uppercase tracking-wide text-muted-foreground">
        {t("reviewOnlyNothingExecutes")}
      </p>
    </div>
  );
}

export function CreativeDecisionPlanSection({ businessId }: { businessId: string }) {
  const t = useTranslations("strategy");
  const queryClient = useQueryClient();
  const summaryQuery = useQuery({
    queryKey: ["decision-plan-summary", businessId],
    queryFn: () => fetchDecisionPlanSummary(businessId),
    enabled: Boolean(businessId),
  });
  const itemsQuery = useQuery({
    queryKey: ["decision-plan-items", businessId],
    queryFn: () => fetchDecisionPlanItems(businessId),
    enabled: Boolean(businessId),
  });
  const generateMutation = useMutation({
    mutationFn: () => generateDecisionPlan(businessId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["decision-plan-summary", businessId],
      });
      void queryClient.invalidateQueries({
        queryKey: ["decision-plan-items", businessId],
      });
    },
  });

  const summary = summaryQuery.data;

  return (
    <Card data-testid="creative-decision-plan-section">
      <CardHeader>
        <CardTitle>{t("decisionPlan")}</CardTitle>
        <CardDescription>{t("decisionPlanDescription")}</CardDescription>
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
              t("generateDecisionPlan")
            )}
          </Button>
          {summary?.fingerprint ? (
            <span className="text-xs text-muted-foreground" data-testid="decision-fingerprint">
              {t("snapshotFingerprint")}: {summary.fingerprint.slice(0, 12)}
            </span>
          ) : null}
        </div>

        {summary && summary.status === "available" ? (
          <>
            <div
              className="grid gap-1 rounded-md border p-3 text-xs sm:grid-cols-3"
              data-testid="decision-summary"
            >
              <div>
                {t("planStatus")}:{" "}
                <span className="rounded-md border px-2 py-0.5">{summary.plan_status}</span>
              </div>
              <div>
                {t("totalItems")}: {summary.total_items ?? 0} ·{" "}
                {t("blockedCount")}: {summary.blocked_count ?? 0}
              </div>
              <div>
                {t("reviewedItems")}: {summary.review_progress?.reviewed_items ?? 0} /{" "}
                {summary.total_items ?? 0} · {t("remainingItems")}:{" "}
                {summary.review_progress?.remaining_items ?? 0}
              </div>
              <div className="text-muted-foreground sm:col-span-3">
                {t("sourceOptimizationFingerprint")}:{" "}
                {summary.source_optimization_fingerprint?.slice(0, 12) ?? t("unavailable")}
              </div>
            </div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {t("reviewOnlyNothingExecutes")}
            </p>
            <div className="space-y-2" data-testid="decision-items-list">
              {(itemsQuery.data?.items ?? []).map((item, index) => (
                <ItemRow key={index} item={item} businessId={businessId} t={t} />
              ))}
            </div>
          </>
        ) : summary && summary.status !== "available" ? (
          <div
            className="rounded-md border border-dashed p-3 text-sm text-muted-foreground"
            data-testid="decision-empty"
          >
            {summary.status === "no_snapshot" || summary.reason === "no_optimization_snapshot"
              ? t("noDecisionSnapshot")
              : t("unavailable")}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
