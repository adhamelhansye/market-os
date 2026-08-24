"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError } from "@/lib/api-client";
import { CreativeLearningSection } from "./creative-learning-section";
import { CreativeDecisionPlanSection } from "./creative-decision-plan-section";
import { CreativeTestReportSection } from "./creative-test-report-section";
import { CreativeActionPreparationSection } from "./creative-action-preparation-section";
import { CreativeOptimizationSection } from "./creative-optimization-section";
import { CreativePerformanceSection } from "./creative-performance-section";
import { FunnelSection } from "./funnel-section";
import {
  createOfferCandidate,
  createPositioningCandidate,
  evaluateStrategyDecision,
  fetchMessaging,
  fetchMessagingVersions,
  fetchStrategyDecisions,
  fetchStrategySummary,
  generateMessaging,
  recommendOffer,
  recommendPositioning,
  validateOffer,
  type MessageAngleRead,
  type MessageComponentRead,
  type MessagingStrategyRead,
  type OfferCandidateRead,
  type PositioningCandidateRead,
  type StrategyDecisionRead,
} from "./api";

function Provenance({ item, t }: { item: PositioningCandidateRead | OfferCandidateRead; t: (key: string) => string }) {
  return (
    <div className="border-t pt-2 text-xs text-muted-foreground">
      <div className="font-medium">{t("provenance")}</div>
      {item.provenance.length === 0 ? <div>{t("noProvenance")}</div> : item.provenance.slice(0, 3).map((row) => (
        <div key={`${item.id}-${row.evidence_id ?? row.data_source}`}>
          {row.source_title ?? row.data_source ?? t("businessData")} · {row.statement ?? t("unavailable")}
        </div>
      ))}
    </div>
  );
}

function PositioningCard({ item, t, onEvaluate }: { item: PositioningCandidateRead; t: (key: string) => string; onEvaluate: () => void }) {
  return (
    <div className="space-y-2 rounded-md border p-3" data-testid="positioning-candidate">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="font-medium">{item.name}</div>
        <span className="text-xs text-muted-foreground">{item.status} · {item.classification} · {item.strength}</span>
      </div>
      <dl className="grid gap-1 text-sm sm:grid-cols-2">
        <div><dt className="text-xs text-muted-foreground">{t("who")}</dt><dd>{item.target_customer ?? t("unavailable")}</dd></div>
        <div><dt className="text-xs text-muted-foreground">{t("problem")}</dt><dd>{item.problem ?? t("unavailable")}</dd></div>
        <div><dt className="text-xs text-muted-foreground">{t("solution")}</dt><dd>{item.solution ?? t("unavailable")}</dd></div>
        <div><dt className="text-xs text-muted-foreground">{t("differentiator")}</dt><dd>{item.differentiator ?? t("unavailable")}</dd></div>
        <div><dt className="text-xs text-muted-foreground">{t("promise")}</dt><dd>{item.promise ?? t("unavailable")}</dd></div>
        <div><dt className="text-xs text-muted-foreground">{t("score")}</dt><dd>{item.score ?? t("unavailable")}</dd></div>
      </dl>
      <p className="text-sm text-muted-foreground">{item.positioning_statement ?? t("derivedStatementUnavailable")}</p>
      <Button type="button" size="sm" variant="outline" onClick={onEvaluate}>{t("evaluateDecision")}</Button>
      {item.risks.length > 0 ? <div className="text-xs text-muted-foreground">{t("risks")}: {item.risks.map((risk) => String(risk.code ?? risk.reason)).join(", ")}</div> : null}
      <Provenance item={item} t={t} />
    </div>
  );
}

function OfferCard({ item, t, onValidate, onEvaluate }: { item: OfferCandidateRead; t: (key: string) => string; onValidate: () => void; onEvaluate: () => void }) {
  const economics = item.economics;
  return (
    <div className="space-y-2 rounded-md border p-3" data-testid="offer-candidate">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="font-medium">{item.name}</div>
        <span className="text-xs text-muted-foreground">{item.status} · {item.classification} · {item.strength}</span>
      </div>
      <div className="grid gap-1 text-sm sm:grid-cols-2">
        <div><span className="text-xs text-muted-foreground">{t("sellingPrice")}: </span>{String(economics.selling_price ?? t("unavailable"))}</div>
        <div><span className="text-xs text-muted-foreground">{t("contributionProfit")}: </span>{String(economics.contribution_profit ?? t("unavailable"))}</div>
        <div><span className="text-xs text-muted-foreground">{t("contributionMargin")}: </span>{String(economics.contribution_margin ?? t("unavailable"))}</div>
        <div><span className="text-xs text-muted-foreground">{t("breakEvenCpa")}: </span>{String(economics.break_even_cpa ?? t("unavailable"))}</div>
        <div><span className="text-xs text-muted-foreground">{t("breakEvenRoas")}: </span>{String(economics.break_even_roas ?? t("unavailable"))}</div>
      </div>
      {item.status === "draft" ? <Button type="button" size="sm" variant="outline" onClick={onValidate}>{t("validate")}</Button> : null}
      <Button type="button" size="sm" variant="outline" onClick={onEvaluate}>{t("evaluateDecision")}</Button>
      {item.risks.length > 0 ? <div className="text-xs text-muted-foreground">{t("risks")}: {item.risks.map((risk) => String(risk.code ?? risk.reason)).join(", ")}</div> : null}
      <Provenance item={item} t={t} />
    </div>
  );
}

function DecisionCard({ item, t }: { item: StrategyDecisionRead; t: (key: string) => string }) {
  return (
    <div className="space-y-2 rounded-md border p-3" data-testid="strategy-decision">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-medium">{item.candidate_type} · {item.candidate_id}</span>
        <span className="text-xs text-muted-foreground">{item.status} · {item.overall_score ?? t("unavailable")}</span>
      </div>
      <div className="grid gap-1 text-sm sm:grid-cols-2">
        <div><span className="text-xs text-muted-foreground">{t("goalAlignment")}: </span>{String(item.evaluation.goal_alignment ?? t("unavailable"))}</div>
        <div><span className="text-xs text-muted-foreground">{t("performanceCompatibility")}: </span>{String(item.evaluation.performance_compatibility ?? t("unavailable"))}</div>
        <div><span className="text-xs text-muted-foreground">{t("forecastAlignment")}: </span>{String(item.evaluation.forecast_alignment ?? t("unavailable"))}</div>
        <div><span className="text-xs text-muted-foreground">{t("simulationAlignment")}: </span>{String(item.evaluation.simulation_alignment ?? t("unavailable"))}</div>
      </div>
      {item.reasons.length ? <div className="text-xs text-muted-foreground">{t("decisionReasons")}: {item.reasons.map((reason) => reason.statement).join("; ")}</div> : null}
      <div className="border-t pt-2 text-xs text-muted-foreground">{t("decisionRulesVersion")}: {item.decision_rules_version}</div>
    </div>
  );
}

function CoreMessage({ message, t }: { message: Record<string, unknown>; t: (key: string) => string }) {
  const fields: Array<[string, string]> = [
    ["who", "who"],
    ["problem", "problem"],
    ["desired_outcome", "desiredOutcome"],
    ["solution", "solution"],
    ["differentiator", "differentiator"],
    ["promise", "promise"],
    ["cta", "cta"],
  ];
  return (
    <dl className="grid gap-1 text-sm sm:grid-cols-2" data-testid="core-message">
      {fields.map(([key, label]) => (
        <div key={key}>
          <dt className="text-xs text-muted-foreground">{t(label)}</dt>
          <dd>{message[key] != null && message[key] !== "" ? String(message[key]) : t("unavailable")}</dd>
        </div>
      ))}
      <div>
        <dt className="text-xs text-muted-foreground">{t("proofAvailable")}</dt>
        <dd>{message.proof_available === true ? t("yes") : t("no")}</dd>
      </div>
    </dl>
  );
}

function ComponentCard({ item, t }: { item: MessageComponentRead; t: (key: string) => string }) {
  const details = item.details ?? {};
  const unsupported = Array.isArray(details.unsupported_claims) ? (details.unsupported_claims as string[]) : [];
  return (
    <div className="rounded-md border p-3" data-testid="message-component">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-medium">{t(`component.${item.component_type}`)}</span>
        <span className="text-xs text-muted-foreground">{item.classification} · {item.strength} · {item.claim_status}{item.funnel_stage ? ` · ${t(`stage.${item.funnel_stage}`)}` : null}</span>
      </div>
      <p className="text-sm">{item.statement}</p>
      {unsupported.length ? <p className="text-xs text-destructive">{t("unsupportedClaims")}: {unsupported.join(", ")}</p> : null}
      {item.component_type === "objection" && details.response_available === true ? (
        <p className="text-xs text-muted-foreground">{t("respondWith")}: {String(details.response)}</p>
      ) : null}
    </div>
  );
}

function AngleCard({ item, t }: { item: MessageAngleRead; t: (key: string) => string }) {
  return (
    <div className="rounded-md border p-3" data-testid="message-angle">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-medium">{item.name}</span>
        <span className="text-xs text-muted-foreground">{t(`angle.${item.angle_type}`) || item.angle_type} · {t("hookDirection")}: {item.hook_direction} · {t(`stage.${item.funnel_stage}`)} · {item.strength}</span>
      </div>
      <p className="text-sm">{item.core_message}</p>
      {item.supporting_points.length ? <p className="text-xs text-muted-foreground">{item.supporting_points.join(" · ")}</p> : null}
      {item.cta_type ? <p className="text-xs">{t("cta")}: {t(`ctaType.${item.cta_type}`)}</p> : null}
    </div>
  );
}

function MessagingCard({ businessId, t }: { businessId: string; t: (key: string) => string }) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["messaging", businessId],
    queryFn: () => fetchMessaging(businessId),
    enabled: Boolean(businessId),
  });
  const versionsQuery = useQuery({ queryKey: ["messaging-versions", businessId], queryFn: () => fetchMessagingVersions(businessId), enabled: Boolean(businessId) });
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["messaging", businessId] });
    void queryClient.invalidateQueries({ queryKey: ["messaging-versions", businessId] });
  };
  const generateMutation = useMutation({ mutationFn: () => generateMessaging(businessId), onSuccess: invalidate });

  const item = query.data;
  const quality = (item?.quality ?? {}) as Record<string, unknown>;
  const missingComponents = Array.isArray(quality.missing_components) ? (quality.missing_components as string[]) : [];
  const unsupportedClaims = Array.isArray(quality.unsupported_claims) ? (quality.unsupported_claims as Array<Record<string, unknown>>) : [];
  const competitor = (quality.competitor_messaging ?? {}) as Record<string, unknown>;
  const patterns = Array.isArray(competitor.patterns) ? (competitor.patterns as Array<Record<string, unknown>>) : [];

  return (
    <Card data-testid="messaging-card">
      <CardHeader>
        <CardTitle>{t("messaging")}</CardTitle>
        <CardDescription>
          {t("messagingDescription")}
          {item ? ` · ${t("version")} ${item.version} · ${item.messaging_version} · ${item.status}` : null}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Button type="button" variant="outline" onClick={() => generateMutation.mutate()} disabled={generateMutation.isPending}>
          {generateMutation.isPending ? t("generating") : t("generateMessaging")}
        </Button>
        {generateMutation.isError ? <p className="text-sm text-destructive">{t("generateError")}</p> : null}
        {query.isLoading ? <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> {t("loadingMessaging")}</div> : null}
        {query.isError && !(query.error instanceof ApiError && query.error.status === 404) ? <p className="text-sm text-destructive">{t("messagingError")}</p> : null}
        {!item ? <p className="text-sm text-muted-foreground">{t("noMessaging")}</p> : (
          <>
            {missingComponents.length ? <div className="rounded-md border border-dashed p-3 text-sm"><span className="font-medium">{t("missingComponents")}: </span>{missingComponents.map((name) => t(`component.${name}`)).join(", ")}</div> : null}
            <CoreMessage message={item.core_message as Record<string, unknown>} t={t} />
            {unsupportedClaims.length ? (
              <div className="rounded-md border border-destructive/40 p-3 text-sm" data-testid="claim-validation">
                <div className="font-medium">{t("claimValidation")}</div>
                {unsupportedClaims.map((flag, index) => (
                  <div key={`${flag.component_type}-${index}`} className="text-xs text-muted-foreground">
                    {t(`component.${String(flag.component_type)}`)}: {Array.isArray(flag.claims) ? (flag.claims as string[]).join(", ") : String(flag.claims)}
                  </div>
                ))}
              </div>
            ) : null}
            {item.components?.length ? <div className="space-y-2">{item.components.map((component) => <ComponentCard key={component.id} item={component} t={t} />)}</div> : null}
            {item.angles?.length ? (
              <div>
                <div className="mb-2 font-medium">{t("angles")}</div>
                <div className="space-y-2">{item.angles.map((angle) => <AngleCard key={angle.id} item={angle} t={t} />)}</div>
              </div>
            ) : null}
            <div className="grid gap-1 rounded-md border p-3 text-xs text-muted-foreground sm:grid-cols-2">
              <div>{t("performanceAttribution")}: {String(quality.performance_attribution ?? t("unavailable"))}</div>
              <div>{t("competitorPatterns")}: {patterns.map((pattern) => `${String(pattern.pattern)} (${String(pattern.saturation)})`).join(", ") || t("unavailable")}</div>
              <div>{t("competitorWhitespace")}: {String(competitor.whitespace_claim ?? t("unavailable"))}</div>
              <div>{t("ctaValidation")}: {JSON.stringify(quality.cta_validation ?? t("unavailable"))}</div>
            </div>
          </>
        )}
        {versionsQuery.data?.versions.length ? (
          <div className="border-t pt-2 text-xs text-muted-foreground">
            <span className="font-medium">{t("versions")}: </span>
            {versionsQuery.data.versions.map((version) => `${version.version} ${version.status}`).join(" · ")}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function StrategySection({ businessId }: { businessId: string }) {
  const t = useTranslations("strategy");
  const queryClient = useQueryClient();
  const [positioningName, setPositioningName] = useState("");
  const [offerName, setOfferName] = useState("");
  const [productId, setProductId] = useState("");
  const query = useQuery({ queryKey: ["strategy-summary", businessId], queryFn: () => fetchStrategySummary(businessId), enabled: Boolean(businessId) });
  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ["strategy-summary", businessId] });
  const positioningMutation = useMutation({ mutationFn: () => createPositioningCandidate(businessId, { name: positioningName, candidate_type: "problem_led" }), onSuccess: () => { setPositioningName(""); invalidate(); } });
  const offerMutation = useMutation({ mutationFn: () => createOfferCandidate(businessId, { name: offerName, product_id: productId }), onSuccess: () => { setOfferName(""); setProductId(""); invalidate(); } });
  const recommendPositioningMutation = useMutation({ mutationFn: () => recommendPositioning(businessId), onSuccess: invalidate });
  const recommendOfferMutation = useMutation({ mutationFn: () => recommendOffer(businessId), onSuccess: invalidate });
  const validateMutation = useMutation({ mutationFn: (id: string) => validateOffer(businessId, id), onSuccess: invalidate });
  const decisionsQuery = useQuery({ queryKey: ["strategy-decisions", businessId], queryFn: () => fetchStrategyDecisions(businessId), enabled: Boolean(businessId) });
  const evaluateMutation = useMutation({ mutationFn: (input: { candidate_type: "positioning" | "offer"; candidate_id: string }) => evaluateStrategyDecision(businessId, { ...input, range_kind: "last_30_days" }), onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["strategy-decisions", businessId] }) });

  return (
    <div className="space-y-4" data-testid="strategy-section">
      <Card>
        <CardHeader><CardTitle>{t("title")}</CardTitle><CardDescription>{t("description")}</CardDescription></CardHeader>
        <CardContent className="space-y-3">
          {query.isLoading ? <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> {t("loading")}</div> : null}
          {query.isError ? <p className="text-sm text-destructive">{t("error")}</p> : null}
          {query.data?.missing_research_areas.length ? <div className="rounded-md border border-dashed p-3 text-sm"><div className="font-medium">{t("researchGaps")}</div>{query.data.missing_research_areas.map((gap, index) => <div key={`${String(gap.area)}-${index}`} className="text-muted-foreground">{String(gap.reason)}</div>)}</div> : null}
        </CardContent>
      </Card>
      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>{t("positioning")}</CardTitle><CardDescription>{t("positioningDescription")} · {query.data?.positioning.strategy_version ?? t("unavailable")}</CardDescription></CardHeader>
          <CardContent className="space-y-3">
            <form className="flex gap-2" onSubmit={(event) => { event.preventDefault(); if (positioningName.trim()) positioningMutation.mutate(); }}><input className="min-w-0 flex-1 rounded-md border bg-background px-3 py-2 text-sm" aria-label={t("candidateName")} value={positioningName} onChange={(event) => setPositioningName(event.target.value)} placeholder={t("candidateName")} /><Button type="submit">{t("addCandidate")}</Button></form>
            <Button type="button" variant="outline" onClick={() => recommendPositioningMutation.mutate()}>{t("recommend")}</Button>
            {query.data?.positioning.candidates.length ? query.data.positioning.candidates.map((item) => <PositioningCard key={item.id} item={item} t={t} onEvaluate={() => evaluateMutation.mutate({ candidate_type: "positioning", candidate_id: item.id })} />) : <p className="text-sm text-muted-foreground">{t("noCandidates")}</p>}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>{t("offerStrategy")}</CardTitle><CardDescription>{t("offerDescription")} · {query.data?.offers.strategy_version ?? t("unavailable")}</CardDescription></CardHeader>
          <CardContent className="space-y-3">
            <form className="grid gap-2" onSubmit={(event) => { event.preventDefault(); if (offerName.trim() && productId.trim()) offerMutation.mutate(); }}><input className="rounded-md border bg-background px-3 py-2 text-sm" aria-label={t("candidateName")} value={offerName} onChange={(event) => setOfferName(event.target.value)} placeholder={t("offerName")} /><input className="rounded-md border bg-background px-3 py-2 text-sm" aria-label={t("productId")} value={productId} onChange={(event) => setProductId(event.target.value)} placeholder={t("productId")} /><Button type="submit">{t("addCandidate")}</Button></form>
            <Button type="button" variant="outline" onClick={() => recommendOfferMutation.mutate()}>{t("recommend")}</Button>
            {query.data?.offers.candidates.length ? query.data.offers.candidates.map((item) => <OfferCard key={item.id} item={item} t={t} onValidate={() => validateMutation.mutate(item.id)} onEvaluate={() => evaluateMutation.mutate({ candidate_type: "offer", candidate_id: item.id })} />) : <p className="text-sm text-muted-foreground">{t("noCandidates")}</p>}
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader><CardTitle>{t("decisionSummary")}</CardTitle><CardDescription>{t("decisionDescription")}</CardDescription></CardHeader>
        <CardContent className="space-y-3">
          {decisionsQuery.isLoading ? <div className="text-sm text-muted-foreground">{t("loadingDecisions")}</div> : null}
          {decisionsQuery.isError || evaluateMutation.isError ? <div className="text-sm text-destructive">{t("decisionError")}</div> : null}
          {decisionsQuery.data?.decisions.length ? decisionsQuery.data.decisions.map((item) => <DecisionCard key={item.id} item={item} t={t} />) : <p className="text-sm text-muted-foreground">{t("noDecisions")}</p>}
        </CardContent>
      </Card>
      <MessagingCard businessId={businessId} t={t} />
      <FunnelSection businessId={businessId} />
      <CreativePerformanceSection businessId={businessId} />
      <CreativeLearningSection businessId={businessId} />
      <CreativeOptimizationSection businessId={businessId} />
      <CreativeDecisionPlanSection businessId={businessId} />
      <CreativeActionPreparationSection businessId={businessId} />
      <CreativeTestReportSection businessId={businessId} />
    </div>
  );
}
