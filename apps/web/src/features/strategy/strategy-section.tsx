"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  createOfferCandidate,
  createPositioningCandidate,
  evaluateStrategyDecision,
  fetchStrategyDecisions,
  fetchStrategySummary,
  recommendOffer,
  recommendPositioning,
  validateOffer,
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
    </div>
  );
}
