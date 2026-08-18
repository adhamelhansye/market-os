"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  fetchResearchIntelligence,
  fetchResearchIntelligenceSummary,
  fetchResearchMessaging,
  fetchResearchPricing,
  type ResearchIntelligenceResponse,
} from "./api";

interface IntelligencePanelProps {
  businessId: string;
  projectId: string | null;
}

function InsightList({
  response,
  title,
  t,
  locale,
}: {
  response: ResearchIntelligenceResponse | undefined;
  title: string;
  t: ReturnType<typeof useTranslations>;
  locale: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>
          {response?.total ?? 0} {t("intelligenceSignals")}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {!response || response.items.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("noIntelligence")}</p>
        ) : (
          response.items.slice(0, 12).map((item) => (
            <div key={item.id} className="rounded-md border p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="font-medium">{item.title}</div>
                <div className="text-xs text-muted-foreground">
                  {t(`classification_${item.classification}`)} · {t(`strength_${item.strength}`)}
                </div>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">{item.statement}</p>
              <div className="mt-2 flex flex-wrap gap-3 text-xs text-muted-foreground">
                <span>{t(`intelligenceCategory_${item.category}`)}</span>
                <span>{item.evidence_count} {t("evidenceCount")}</span>
                <span>{item.source_count} {t("sourceCount")}</span>
                <span>{t(`freshness_${item.freshness}`)}</span>
              </div>
              <div className="mt-2 border-t pt-2 text-xs text-muted-foreground">
                <div>{t("provenance")}</div>
                {item.provenance?.slice(0, 3).map((provenance) => (
                  <div key={`${item.id}-${provenance.evidence_id}`}>
                    {provenance.source_title} · {new Date(provenance.captured_at).toLocaleDateString(locale)}
                  </div>
                ))}
              </div>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}

export function IntelligencePanel({ businessId, projectId }: IntelligencePanelProps) {
  const t = useTranslations("research");
  const locale = useLocale();
  const [classification, setClassification] = useState("");
  const [freshness, setFreshness] = useState("");
  const filters = {
    research_project_id: projectId ?? undefined,
    classification: classification || undefined,
    freshness: freshness || undefined,
  };
  const summaryQuery = useQuery({
    queryKey: ["research-intelligence-summary", businessId, projectId],
    queryFn: () => fetchResearchIntelligenceSummary(businessId, projectId ?? undefined),
    enabled: Boolean(businessId),
  });
  const marketQuery = useQuery({
    queryKey: ["research-intelligence-market", businessId, filters],
    queryFn: () => fetchResearchIntelligence(businessId, "market", filters),
    enabled: Boolean(businessId),
  });
  const customerQuery = useQuery({
    queryKey: ["research-intelligence-customer", businessId, filters],
    queryFn: () => fetchResearchIntelligence(businessId, "customer", filters),
    enabled: Boolean(businessId),
  });
  const competitorQuery = useQuery({
    queryKey: ["research-intelligence-competitors", businessId, filters],
    queryFn: () => fetchResearchIntelligence(businessId, "competitors", filters),
    enabled: Boolean(businessId),
  });
  const pricingQuery = useQuery({
    queryKey: ["research-intelligence-pricing", businessId, filters],
    queryFn: () => fetchResearchPricing(businessId, filters),
    enabled: Boolean(businessId),
  });
  const messagingQuery = useQuery({
    queryKey: ["research-intelligence-messaging", businessId, filters],
    queryFn: () => fetchResearchMessaging(businessId, filters),
    enabled: Boolean(businessId),
  });
  const loading = [marketQuery, customerQuery, competitorQuery, pricingQuery, messagingQuery].some(
    (query) => query.isLoading
  );
  const error = [marketQuery, customerQuery, competitorQuery, pricingQuery, messagingQuery].some(
    (query) => query.isError
  );
  const summary = summaryQuery.data;

  return (
    <div className="space-y-4" data-testid="research-intelligence">
      <Card>
        <CardHeader>
          <CardTitle>{t("intelligenceTitle")}</CardTitle>
          <CardDescription>{t("intelligenceDescription")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div><div className="text-xs text-muted-foreground">{t("marketSignals")}</div><div className="text-lg font-medium">{summary?.market_signal_count ?? 0}</div></div>
            <div><div className="text-xs text-muted-foreground">{t("customerSignals")}</div><div className="text-lg font-medium">{summary?.customer_signal_count ?? 0}</div></div>
            <div><div className="text-xs text-muted-foreground">{t("competitorSignals")}</div><div className="text-lg font-medium">{summary?.competitor_signal_count ?? 0}</div></div>
            <div><div className="text-xs text-muted-foreground">{t("intelligenceFreshness")}</div><div className="text-lg font-medium">{summary ? t(`freshness_${summary.freshness}`) : t("unavailable")}</div></div>
          </div>
          <div className="flex flex-wrap gap-3">
            <select aria-label={t("classification")} value={classification} onChange={(event) => setClassification(event.target.value)} className="rounded-md border bg-background px-3 py-2 text-sm">
              <option value="">{t("all")}</option>
              <option value="observed">{t("classification_observed")}</option>
              <option value="inferred">{t("classification_inferred")}</option>
              <option value="hypothesis">{t("classification_hypothesis")}</option>
            </select>
            <select aria-label={t("freshness")} value={freshness} onChange={(event) => setFreshness(event.target.value)} className="rounded-md border bg-background px-3 py-2 text-sm">
              <option value="">{t("all")}</option>
              <option value="fresh">{t("freshness_fresh")}</option>
              <option value="aging">{t("freshness_aging")}</option>
              <option value="stale">{t("freshness_stale")}</option>
              <option value="unknown">{t("freshness_unknown")}</option>
            </select>
          </div>
          {loading ? <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> {t("loading")}</div> : null}
          {error ? <p className="text-sm text-destructive">{t("intelligenceError")}</p> : null}
          {summary?.missing_research_areas?.length ? (
            <div className="rounded-md border border-dashed p-3 text-sm">
              <div className="font-medium">{t("researchGaps")}</div>
              {summary.missing_research_areas.map((area) => <div key={String(area.area)} className="text-muted-foreground">{String(area.reason)}</div>)}
            </div>
          ) : null}
        </CardContent>
      </Card>
      <div className="grid gap-4 xl:grid-cols-2">
        <InsightList response={marketQuery.data} title={t("marketIntelligence")} t={t} locale={locale} />
        <InsightList response={customerQuery.data} title={t("customerIntelligence")} t={t} locale={locale} />
        <InsightList response={competitorQuery.data} title={t("competitorIntelligence")} t={t} locale={locale} />
        <InsightList response={pricingQuery.data} title={t("pricingIntelligence")} t={t} locale={locale} />
        <InsightList response={messagingQuery.data} title={t("messagingIntelligence")} t={t} locale={locale} />
      </div>
    </div>
  );
}
