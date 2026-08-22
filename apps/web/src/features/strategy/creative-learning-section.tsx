"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError } from "@/lib/api-client";
import {
  fetchLearningSection,
  fetchLearningSummary,
  generateCreativeLearning,
  type LearningPatternItem,
  type LearningRecommendationItem,
} from "./api";

const SECTIONS = ["patterns", "learnings", "recommendations", "profiles"] as const;
type Section = (typeof SECTIONS)[number];

function StatusChip({ value }: { value: string }) {
  const negative = value === "conflicting" || value === "fatigue_signal";
  return (
    <span
      className={`rounded-md border px-2 py-0.5 text-xs ${
        negative ? "text-destructive" : "text-muted-foreground"
      }`}
    >
      {value}
    </span>
  );
}

function PatternsList({ items }: { items: Record<string, unknown>[] }) {
  return (
    <div className="space-y-2" data-testid="learning-patterns-list">
      {items.map((item) => {
        const pattern = item as unknown as LearningPatternItem;
        return (
          <div
            key={`${pattern.dimension}-${pattern.value}`}
            className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-2 text-sm"
            data-testid="learning-pattern"
          >
            <span className="font-medium">
              {pattern.dimension}: {pattern.value}
            </span>
            <span className="flex items-center gap-2">
              {pattern.dominant_direction ? (
                <span className="text-xs">{pattern.dominant_direction}</span>
              ) : null}
              <StatusChip value={pattern.status} />
              <span className="text-xs text-muted-foreground">
                n={pattern.observed_entities} · {pattern.evidence_strength}
              </span>
            </span>
          </div>
        );
      })}
    </div>
  );
}

function RecommendationsList({ items }: { items: Record<string, unknown>[] }) {
  return (
    <div className="space-y-2" data-testid="learning-recommendations-list">
      {items.map((item, index) => {
        const rec = item as unknown as LearningRecommendationItem;
        return (
          <div key={`${rec.type}-${index}`} className="rounded-md border p-3 text-sm" data-testid="learning-recommendation">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-medium">{rec.type}</span>
              <span className="flex items-center gap-2 text-xs">
                <span className="rounded-md border px-2 py-0.5">{rec.priority}</span>
                <span className="rounded-md border border-dashed px-2 py-0.5 text-muted-foreground">
                  review_only
                </span>
              </span>
            </div>
            <p className="mt-1 text-muted-foreground">{rec.statement}</p>
          </div>
        );
      })}
    </div>
  );
}

function SectionBlock({
  title,
  query,
  render,
  testId,
}: {
  title: string;
  query: { isLoading: boolean; data?: { status: string; reason?: string | null; items?: Record<string, unknown>[] }; isError: boolean };
  render: (items: Record<string, unknown>[]) => React.ReactNode;
  testId: string;
}) {
  const t = useTranslations("strategy");
  return (
    <div data-testid={testId}>
      <div className="mb-1 text-sm font-medium">{title}</div>
      {query.isLoading ? (
        <div className="text-xs text-muted-foreground">{t("loadingPerformance")}</div>
      ) : null}
      {query.data && query.data.status !== "available" ? (
        <div className="rounded-md border border-dashed p-2 text-xs text-muted-foreground">
          {query.data.status === "no_snapshot"
            ? t("noLearningSnapshot")
            : (query.data.reason ?? t("unavailable"))}
        </div>
      ) : null}
      {query.data?.status === "available" && (query.data.items ?? []).length === 0 ? (
        <div className="text-xs text-muted-foreground">{t("noLearningItems")}</div>
      ) : null}
      {query.data?.status === "available" && (query.data.items ?? []).length > 0
        ? render(query.data.items ?? [])
        : null}
    </div>
  );
}

export function CreativeLearningSection({ businessId }: { businessId: string }) {
  const t = useTranslations("strategy");
  const queryClient = useQueryClient();

  const summaryQuery = useQuery({
    queryKey: ["creative-learning-summary", businessId],
    queryFn: () => fetchLearningSummary(businessId),
    enabled: Boolean(businessId),
  });

  const patternsQuery = useQuery({
    queryKey: ["creative-learning-patterns", businessId],
    queryFn: () => fetchLearningSection(businessId, "patterns"),
    enabled: Boolean(businessId),
  });
  const recommendationsQuery = useQuery({
    queryKey: ["creative-learning-recommendations", businessId],
    queryFn: () => fetchLearningSection(businessId, "recommendations"),
    enabled: Boolean(businessId),
  });

  const generateMutation = useMutation({
    mutationFn: () => generateCreativeLearning(businessId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["creative-learning-summary", businessId],
      });
      void queryClient.invalidateQueries({
        queryKey: ["creative-learning-patterns", businessId],
      });
      void queryClient.invalidateQueries({
        queryKey: ["creative-learning-recommendations", businessId],
      });
    },
  });

  const summary = summaryQuery.data;

  return (
    <Card data-testid="creative-learning-section">
      <CardHeader>
        <CardTitle>{t("creativeLearning")}</CardTitle>
        <CardDescription>{t("creativeLearningDescription")}</CardDescription>
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
              t("generateLearning")
            )}
          </Button>
          {summary?.fingerprint ? (
            <span className="text-xs text-muted-foreground" data-testid="learning-fingerprint">
              {t("snapshotFingerprint")}: {summary.fingerprint.slice(0, 12)}
            </span>
          ) : null}
        </div>

        {generateMutation.isError &&
        !(generateMutation.error instanceof ApiError && generateMutation.error.status === 403) ? (
          <p className="text-sm text-destructive">{t("performanceError")}</p>
        ) : null}

        {summary && summary.status === "available" ? (
          <div className="grid gap-1 rounded-md border p-3 text-xs sm:grid-cols-2" data-testid="learning-summary">
            <div>
              {t("learningStatus")}: <StatusChip value={summary.learning_status ?? "unavailable"} />
            </div>
            <div>
              {t("observedEntities")}: {summary.entities_sufficient ?? t("unavailable")} /{" "}
              {summary.entities_total ?? t("unavailable")}
            </div>
            <div>
              {t("patternsCount")}: {summary.patterns_total ?? t("unavailable")}
            </div>
            <div>
              {t("recommendationsCount")}: {summary.recommendations_total ?? t("unavailable")}
            </div>
          </div>
        ) : summary && summary.status !== "available" ? (
          <div className="rounded-md border border-dashed p-3 text-sm text-muted-foreground" data-testid="learning-empty">
            {summary.status === "no_snapshot"
              ? t("noLearningSnapshot")
              : t("attributionUnavailable", { reason: summary.reason ?? summary.status })}
          </div>
        ) : null}

        <SectionBlock
          title={t("observedPatterns")}
          query={patternsQuery}
          render={(items) => <PatternsList items={items} />}
          testId="learning-section-patterns"
        />
        <SectionBlock
          title={t("recommendationsTitle")}
          query={recommendationsQuery}
          render={(items) => <RecommendationsList items={items} />}
          testId="learning-section-recommendations"
        />
      </CardContent>
    </Card>
  );
}
