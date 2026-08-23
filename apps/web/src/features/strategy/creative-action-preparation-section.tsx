"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  fetchActionDrafts,
  generateActionDrafts,
  reviewActionDraft,
  type ActionDraft,
} from "./api";

function DraftRow({
  draft,
  businessId,
  t,
}: {
  draft: ActionDraft;
  businessId: string;
  t: (key: string) => string;
}) {
  const queryClient = useQueryClient();
  const reviewMutation = useMutation({
    mutationFn: (review_state: "acknowledged" | "dismissed" | "deferred") =>
      reviewActionDraft(businessId, draft.id, { review_state }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["action-drafts", businessId],
      });
    },
  });

  return (
    <div
      className="rounded-md border p-3 text-sm"
      data-testid={`action-draft-${draft.source_opportunity_id}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-medium">
          {t(`draftKind.${draft.draft_kind}`)} · {draft.draft_test_id.slice(0, 18)}
        </span>
        <span className="flex flex-wrap items-center gap-2 text-xs">
          <span className="rounded-md border px-2 py-0.5" data-testid="action-review-state">
            {draft.review_state}
          </span>
          <span className="rounded-md border border-dashed px-2 py-0.5 text-muted-foreground">
            review_only
          </span>
        </span>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        {t("sourceOpportunity")}: {draft.source_opportunity_id}
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        {(["acknowledged", "dismissed", "deferred"] as const).map((state) => (
          <Button
            key={state}
            type="button"
            variant="outline"
            size="sm"
            disabled={reviewMutation.isPending || draft.review_state === state}
            onClick={() => reviewMutation.mutate(state)}
            data-testid={`action-${state}-${draft.id}`}
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
        {t("stillADraft")}
      </p>
    </div>
  );
}

export function CreativeActionPreparationSection({
  businessId,
}: {
  businessId: string;
}) {
  const t = useTranslations("strategy");
  const queryClient = useQueryClient();

  const draftsQuery = useQuery({
    queryKey: ["action-drafts", businessId],
    queryFn: () => fetchActionDrafts(businessId),
    enabled: Boolean(businessId),
  });
  const generateMutation = useMutation({
    mutationFn: () => generateActionDrafts(businessId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["action-drafts", businessId],
      });
    },
  });

  const drafts = draftsQuery.data ?? [];

  return (
    <Card data-testid="creative-action-section">
      <CardHeader>
        <CardTitle>{t("creativeActionPreparation")}</CardTitle>
        <CardDescription>{t("creativeActionDescription")}</CardDescription>
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
              t("prepareDrafts")
            )}
          </Button>
          {generateMutation.isSuccess ? (
            <span className="text-xs text-muted-foreground" data-testid="action-generate-result">
              {t("draftsPrepared", { count: generateMutation.data.created_count })}
            </span>
          ) : null}
        </div>

        {draftsQuery.isLoading ? (
          <div className="text-xs text-muted-foreground">{t("loadingPerformance")}</div>
        ) : null}

        {!draftsQuery.isLoading && drafts.length === 0 ? (
          <div className="rounded-md border border-dashed p-3 text-sm text-muted-foreground" data-testid="action-empty">
            {t("noActionDrafts")}
          </div>
        ) : (
          <div className="space-y-2" data-testid="action-drafts-list">
            {drafts.map((draft) => (
              <DraftRow key={draft.id} draft={draft} businessId={businessId} t={t} />
            ))}
          </div>
        )}

        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {t("stillADraft")}
        </p>
      </CardContent>
    </Card>
  );
}
