"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
import type { RangeKind } from "@/features/metrics/api";

import {
  fetchRecommendations,
  generateRecommendations,
  type DecisionRead,
} from "@/features/recommendations/api";

const DECISION_TYPES = [
  "tracking_issue",
  "data_quality_issue",
  "insufficient_data",
  "learning",
  "kill_review",
  "scale_review",
  "optimize",
  "maintain",
] as const;
const ENTITY_TYPES = ["business", "campaign"] as const;

const DECISION_CLASSES: Record<string, string> = {
  tracking_issue: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  data_quality_issue: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300",
  insufficient_data: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  learning: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  kill_review: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  scale_review: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  optimize: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  maintain: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
};

const STRENGTH_CLASSES: Record<string, string> = {
  strong: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  moderate: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  weak: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  insufficient: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
};

function labelKey(prefix: string, value: string): string {
  const pascal = value
    .split("_")
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
    .join("");
  return `${prefix}${pascal}`;
}

function decisionLabelKey(value: string): string {
  const pascal = labelKey("", value);
  return `${pascal.charAt(0).toLowerCase()}${pascal.slice(1)}`;
}

function DecisionBadge({ decision, t }: { decision: string; t: (key: string) => string }) {
  return (
    <span
      data-testid={`decision-${decision}`}
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${DECISION_CLASSES[decision] ?? DECISION_CLASSES.maintain}`}
    >
      {t(decisionLabelKey(decision))}
    </span>
  );
}

function StrengthBadge({ strength, t }: { strength: string; t: (key: string) => string }) {
  return (
    <span
      data-testid={`strength-${strength}`}
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STRENGTH_CLASSES[strength] ?? STRENGTH_CLASSES.weak}`}
    >
      {t(labelKey("strength", strength))}
    </span>
  );
}

function DecisionCard({
  decision,
  t,
}: {
  decision: DecisionRead;
  t: (key: string) => string;
}) {
  const reasonKey = labelKey("reason", decision.primary_reason);
  const suggestions = decision.review_suggestions ?? [];

  return (
    <Card data-testid="decision-card">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <DecisionBadge decision={decision.decision} t={t} />
              <StrengthBadge strength={decision.evidence_strength} t={t} />
            </div>
            <CardDescription className="text-xs">
              {t("entityType")}:{" "}
              {decision.entity_name ?? t(labelKey("entity", decision.entity_type))}
            </CardDescription>
          </div>
          <span className="text-xs text-muted-foreground">
            {decision.range.start} – {decision.range.end}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <p className="text-xs text-muted-foreground">
          {t("reasons")}: {t(reasonKey)}
        </p>
        {suggestions.length > 0 ? (
          <div className="space-y-1">
            <p className="text-xs font-medium">{t("suggestions")}</p>
            <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
              {suggestions.map((suggestion) => (
                <li key={suggestion} data-testid={`suggestion-${suggestion}`}>
                  {suggestion.startsWith("test_") || suggestion.startsWith("review_")
                    ? suggestion
                    : suggestion}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        <p className="text-xs text-muted-foreground">
          v{decision.rules_version} · {t("entityType")}:{" "}
          {t(labelKey("entity", decision.entity_type))}
        </p>
      </CardContent>
    </Card>
  );
}

export function RecommendationsSection({
  businessId,
  rangeKind,
}: {
  businessId: string;
  rangeKind: RangeKind;
}) {
  const t = useTranslations("recommendations");
  const queryClient = useQueryClient();
  const [entityType, setEntityType] = useState<string>("all");
  const [decisionType, setDecisionType] = useState<string>("all");

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["recommendations", businessId, rangeKind],
    queryFn: () => fetchRecommendations(businessId, rangeKind),
    enabled: Boolean(businessId),
  });

  const { mutate: generate, isPending: generating } = useMutation({
    mutationFn: () => generateRecommendations(businessId, rangeKind),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["recommendations", businessId] });
    },
  });

  const decisions = useMemo(() => {
    const list = data?.decisions ?? [];
    return list.filter(
      (d) =>
        (entityType === "all" || d.entity_type === entityType) &&
        (decisionType === "all" || d.decision === decisionType)
    );
  }, [data, entityType, decisionType]);

  const summary = data?.summary;

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
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">{t("title")}</h2>
          <p className="text-sm text-muted-foreground">{t("subtitle")}</p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => generate()}
          disabled={generating}
          data-testid="generate-button"
        >
          {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          {t("generate")}
        </Button>
      </div>

      <p className="text-xs font-medium text-muted-foreground" data-testid="review-only-note">
        {t("reviewOnly")}
      </p>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">{t("total")}</CardTitle>
          </CardHeader>
          <CardContent data-testid="summary-total" className="text-lg font-medium">
            {summary?.total ?? 0}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">{t("scaleReview")}</CardTitle>
          </CardHeader>
          <CardContent data-testid="summary-scale" className="text-lg font-medium">
            {summary?.scale_review ?? 0}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">{t("killReview")}</CardTitle>
          </CardHeader>
          <CardContent data-testid="summary-kill" className="text-lg font-medium">
            {summary?.kill_review ?? 0}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">{t("optimize")}</CardTitle>
          </CardHeader>
          <CardContent data-testid="summary-optimize" className="text-lg font-medium">
            {summary?.optimize ?? 0}
          </CardContent>
        </Card>
      </div>

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
            <span className="text-xs text-muted-foreground">{t("decision")}</span>
            <Select value={decisionType} onValueChange={setDecisionType}>
              <SelectTrigger className="w-40" data-testid="filter-decision">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("all")}</SelectItem>
                {DECISION_TYPES.map((value) => (
                  <SelectItem key={value} value={value}>
                    {t(decisionLabelKey(value))}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      <div className="space-y-3" data-testid="decisions-list">
        {decisions.length === 0 ? (
          <Card className="border-dashed">
            <CardContent className="py-6 text-center">
              <p className="text-sm font-medium">{t("noDecisions")}</p>
              <p className="text-xs text-muted-foreground">{t("noDecisionsBody")}</p>
            </CardContent>
          </Card>
        ) : (
          decisions.map((decision) => (
            <DecisionCard
              key={decision.id}
              decision={decision}
              t={t}
            />
          ))
        )}
      </div>
    </div>
  );
}