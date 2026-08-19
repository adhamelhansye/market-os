"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError } from "@/lib/api-client";
import {
  fetchFunnel,
  fetchFunnelVersions,
  generateFunnel,
  type FunnelGapRead,
  type FunnelStageRead,
  type FunnelStrategyRead,
} from "./api";

function StageChannels({ stage, t }: { stage: FunnelStageRead; t: (key: string) => string }) {
  const channels = stage.channels ?? [];
  return (
    <div data-testid={`stage-channels-${stage.stage}`}>
      <div className="mb-1 text-xs text-muted-foreground">{t("channels")}</div>
      {channels.length ? (
        <ul className="space-y-1 text-xs">
          {channels.map((channel) => (
            <li key={channel.id} className="flex flex-wrap items-center justify-between gap-2">
              <span>
                {channel.channel} · {channel.role} · {channel.status}
              </span>
              <span className="text-muted-foreground">{channel.weight ?? t("unavailable")}</span>
            </li>
          ))}
        </ul>
      ) : (
        <div className="text-xs text-muted-foreground">{t("unavailable")}</div>
      )}
    </div>
  );
}

function StageKpis({ stage, t }: { stage: FunnelStageRead; t: (key: string) => string }) {
  const kpis = stage.kpis ?? [];
  return (
    <div data-testid={`stage-kpis-${stage.stage}`}>
      <div className="mb-1 text-xs text-muted-foreground">{t("kpis")}</div>
      {kpis.length ? (
        <ul className="space-y-1 text-xs">
          {kpis.map((kpi) => {
            const value = (kpi.value_ref ?? {}) as Record<string, unknown>;
            const raw = value.value != null ? String(value.value) : t("unavailable");
            return (
              <li key={kpi.id} className="flex flex-wrap items-center justify-between gap-2">
                <span>
                  {kpi.kpi_code} · {kpi.role}
                </span>
                <span className="text-muted-foreground">
                  {raw} · {kpi.status}
                </span>
              </li>
            );
          })}
        </ul>
      ) : (
        <div className="text-xs text-muted-foreground">{t("unavailable")}</div>
      )}
    </div>
  );
}

function ConditionView({
  label,
  condition,
  t,
}: {
  label: string;
  condition: Record<string, unknown> | undefined;
  t: (key: string) => string;
}) {
  const hasCondition = condition && Object.keys(condition).length > 0;
  return (
    <div className="text-xs">
      <span className="font-medium">{label}: </span>
      {hasCondition ? (
        <span>
          {String(condition.transition ?? condition.target_stage ?? t("unavailable"))}
          {condition.value != null ? ` · ${String(condition.value)}` : null}
          {condition.status ? ` · ${String(condition.status)}` : null}
          {condition.bottleneck ? ` · ${t("bottleneck")}: ${String(condition.bottleneck)}` : null}
        </span>
      ) : (
        <span className="text-muted-foreground">{t("unavailable")}</span>
      )}
    </div>
  );
}

function FunnelStageCard({ stage, t }: { stage: FunnelStageRead; t: (key: string) => string }) {
  const exitCondition = (stage.exit_condition ?? {}) as Record<string, unknown>;
  const entryCondition = (stage.entry_condition ?? {}) as Record<string, unknown>;
  return (
    <div className="space-y-2 rounded-md border p-3" data-testid={`funnel-stage-${stage.stage}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-medium">{t(`stage.${stage.stage}`)}</span>
        <span className="text-xs text-muted-foreground">
          {stage.status} · {stage.audience_state}
        </span>
      </div>
      <p className="text-sm text-muted-foreground">{stage.objective}</p>
      <div className="grid gap-1 text-xs">
        <div>
          <span className="font-medium">{t("messageDirection")}: </span>
          {stage.message_direction}
        </div>
        <div>
          <span className="font-medium">{t("contentDirection")}: </span>
          {stage.content_direction}
        </div>
        {stage.offer_direction ? (
          <div>
            <span className="font-medium">{t("offerDirection")}: </span>
            {stage.offer_direction}
          </div>
        ) : null}
        {stage.cta_type ? (
          <div>
            <span className="font-medium">{t("cta")}: </span>
            {t(`ctaType.${stage.cta_type}`) || stage.cta_type}
          </div>
        ) : null}
        <ConditionView label={t("entryCondition")} condition={entryCondition} t={t} />
        <ConditionView label={t("exitCondition")} condition={exitCondition} t={t} />
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        <StageChannels stage={stage} t={t} />
        <StageKpis stage={stage} t={t} />
      </div>
    </div>
  );
}

function FunnelHealthCard({ item, t }: { item: FunnelStrategyRead; t: (key: string) => string }) {
  const health = (item.health ?? {}) as Record<string, unknown>;
  const ctaValidation = (health.cta_validation ?? {}) as Record<string, unknown>;
  const breakdown = (health.stage_breakdown ?? {}) as Record<string, Record<string, unknown>>;
  return (
    <Card data-testid="funnel-health-card">
      <CardHeader>
        <CardTitle>{t("health")}</CardTitle>
        <CardDescription>
          {t("score")}: {health.score != null ? String(health.score) : t("unavailable")} ·{" "}
          {t("bucket")}: {health.bucket != null ? String(health.bucket) : t("unavailable")} ·{" "}
          {t("rulesVersion")}: {String(health.rules_version ?? t("unavailable"))}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <div className="flex flex-wrap gap-2">
          {Object.entries(breakdown).map(([stage, info]) => (
            <span key={stage} className="rounded-md border px-2 py-1 text-xs">
              {t(`stage.${stage}`)}: {String(info.status)}
            </span>
          ))}
        </div>
        <div className="text-xs text-muted-foreground">
          {t("ctaValidation")}: {String(ctaValidation.cta_type ?? t("unavailable"))} ·{" "}
          {String(ctaValidation.basis ?? t("unavailable"))}
        </div>
        <div className="text-xs text-muted-foreground">
          {t("performanceClaims")}: {String(health.performance_claims ?? t("unavailable"))}
        </div>
      </CardContent>
    </Card>
  );
}

function FunnelGapList({ gaps, t }: { gaps: FunnelGapRead[]; t: (key: string) => string }) {
  return (
    <Card data-testid="funnel-gaps-card">
      <CardHeader>
        <CardTitle>{t("gaps")}</CardTitle>
        <CardDescription>{t("gapsDescription")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {gaps.length ? (
          gaps.map((gap) => (
            <div key={gap.id} className="rounded-md border p-3 text-sm" data-testid="funnel-gap">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium">
                  {gap.title}
                  {gap.stage_from ? ` · ${t(`stage.${gap.stage_from}`)} → ${t(`stage.${gap.stage_to ?? ""}`) || t("unavailable")}` : null}
                </span>
                <span className="text-xs text-muted-foreground">
                  {gap.severity} · {gap.gap_type}
                </span>
              </div>
              <p className="text-sm text-muted-foreground">{gap.description}</p>
              <div className="text-xs text-muted-foreground">
                {t("recommendedDirection")}: {gap.recommended_direction}
              </div>
            </div>
          ))
        ) : (
          <p className="text-sm text-muted-foreground">{t("noGaps")}</p>
        )}
      </CardContent>
    </Card>
  );
}

function FunnelSnapshotCard({ item, t }: { item: FunnelStrategyRead; t: (key: string) => string }) {
  const snapshot = (item.input_snapshot ?? {}) as Record<string, unknown>;
  const goal = (snapshot.business_goal ?? {}) as Record<string, unknown>;
  const integrations = (snapshot.integrations ?? {}) as Record<string, Record<string, unknown>>;
  const metricsRange = snapshot.metrics_range as Record<string, unknown> | undefined;
  return (
    <Card data-testid="funnel-snapshot-card">
      <CardHeader>
        <CardTitle>{t("snapshot")}</CardTitle>
        <CardDescription>{t("snapshotDescription")}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-1 text-xs text-muted-foreground sm:grid-cols-2">
        <div>
          {t("variant")}: {String(snapshot.variant ?? t("unavailable"))} ·{" "}
          {String(snapshot.variant_signal ?? t("unavailable"))}
        </div>
        <div>
          {t("goalStatus")}: {String(goal.status ?? t("unavailable"))}
        </div>
        <div>
          {t("evidenceIds")}:{" "}
          {Array.isArray(snapshot.evidence_ids) && snapshot.evidence_ids.length
            ? snapshot.evidence_ids.length
            : t("no")}
        </div>
        <div>
          {t("metricsRange")}: {String(metricsRange?.kind ?? t("unavailable"))}
        </div>
        {Object.keys(integrations).length ? (
          <div>
            {t("integrations")}:{" "}
            {Object.entries(integrations)
              .map(([provider, info]) => `${provider} (${String(info.status)})`)
              .join(" · ")}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function FunnelVersionsList({ businessId, t }: { businessId: string; t: (key: string) => string }) {
  const query = useQuery({
    queryKey: ["funnel-versions", businessId],
    queryFn: () => fetchFunnelVersions(businessId),
    enabled: Boolean(businessId),
  });
  if (!query.data?.versions.length) return null;
  return (
    <div className="border-t pt-2 text-xs text-muted-foreground" data-testid="funnel-versions">
      <span className="font-medium">{t("versions")}: </span>
      {query.data.versions.map((version) => `${version.version} ${version.status}`).join(" · ")}
    </div>
  );
}

export function FunnelSection({ businessId }: { businessId: string }) {
  const t = useTranslations("strategy");
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["funnel", businessId],
    queryFn: () => fetchFunnel(businessId),
    enabled: Boolean(businessId),
  });
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["funnel", businessId] });
    void queryClient.invalidateQueries({ queryKey: ["funnel-versions", businessId] });
  };
  const generateMutation = useMutation({ mutationFn: () => generateFunnel(businessId), onSuccess: invalidate });

  const item = query.data;
  return (
    <div className="space-y-4" data-testid="funnel-section">
      <Card>
        <CardHeader>
          <CardTitle>{t("funnel")}</CardTitle>
          <CardDescription>
            {t("funnelDescription")}
            {item ? ` · ${t("version")} ${item.version} · ${item.funnel_version} · ${item.status}` : null}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Button type="button" variant="outline" onClick={() => generateMutation.mutate()} disabled={generateMutation.isPending}>
            {generateMutation.isPending ? t("generating") : t("generateFunnel")}
          </Button>
          {generateMutation.isError ? <p className="text-sm text-destructive">{t("generateError")}</p> : null}
          {query.isLoading ? <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> {t("loadingFunnel")}</div> : null}
          {query.isError && !(query.error instanceof ApiError && query.error.status === 404) ? <p className="text-sm text-destructive">{t("funnelError")}</p> : null}
          {!item ? <p className="text-sm text-muted-foreground">{t("noFunnel")}</p> : (
            <>
              <FunnelHealthCard item={item} t={t} />
              {item.stages?.length ? (
                <div className="grid gap-2 xl:grid-cols-2">
                  {item.stages.map((stage) => <FunnelStageCard key={stage.id} stage={stage} t={t} />)}
                </div>
              ) : null}
              <FunnelGapList gaps={item.gaps ?? []} t={t} />
              <FunnelSnapshotCard item={item} t={t} />
            </>
          )}
          <FunnelVersionsList businessId={businessId} t={t} />
        </CardContent>
      </Card>
    </div>
  );
}
