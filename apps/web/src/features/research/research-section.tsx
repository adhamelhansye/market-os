"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, Search } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ResearchProjects } from "./research-projects";
import { CompetitorList } from "./competitor-list";
import { SourceList } from "./source-list";
import { EvidenceList } from "./evidence-list";
import { FindingsList } from "./findings-list";
import { CollectionPanel } from "./collection-panel";
import { IntelligencePanel } from "./intelligence-panel";
import { StrategySection } from "@/features/strategy/strategy-section";
import {
  fetchResearchProject,
  fetchResearchProjects,
  searchResearchContent,
} from "./api";

interface ResearchSectionProps {
  businessId: string;
}

interface ResearchDataQuality {
  source_count?: number;
  evidence_count?: number;
  finding_count?: number;
  freshness?: string | null;
  missing_areas?: string[];
  coverage?: {
    status?: string;
    covered_categories?: number;
    total_categories?: number;
    missing_areas?: string[];
    reason?: string;
  };
}

function SummaryCard({ label, value }: { label: string; value: string | number }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm text-muted-foreground">{label}</CardTitle>
      </CardHeader>
      <CardContent className="text-lg font-medium">{value}</CardContent>
    </Card>
  );
}

export function ResearchSection({ businessId }: ResearchSectionProps) {
  const t = useTranslations("research");
  const locale = useLocale();
  const [query, setQuery] = useState("");

  const projectsQuery = useQuery({
    queryKey: ["research-projects", businessId],
    queryFn: () => fetchResearchProjects(businessId),
    enabled: Boolean(businessId),
  });
  const activeProjectId = projectsQuery.data?.projects[0]?.id ?? null;
  const projectDetailQuery = useQuery({
    queryKey: ["research-project-detail", businessId, activeProjectId ?? ""],
    queryFn: () => fetchResearchProject(businessId, activeProjectId as string),
    enabled: Boolean(activeProjectId),
  });
  const searchQuery = useQuery({
    queryKey: ["research-search", businessId, query],
    queryFn: () => searchResearchContent(businessId, query.trim()),
    enabled: query.trim().length >= 2,
  });

  const project = projectsQuery.data?.projects ?? [];
  const summary = (projectDetailQuery.data?.data_quality ?? {}) as ResearchDataQuality;
  const coverage = summary.coverage;

  const searchHits = useMemo(() => searchQuery.data?.hits ?? [], [searchQuery.data]);

  if (projectsQuery.isLoading) {
    return (
      <Card>
        <CardContent className="flex items-center gap-2 py-8 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> {t("loading")}
        </CardContent>
      </Card>
    );
  }

  if (projectsQuery.isError) {
    return (
      <Card>
        <CardContent className="space-y-2 py-8 text-center">
          <p className="text-muted-foreground">{t("error")}</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6" data-testid="research-section">
      <Card data-testid="research-search">
        <CardHeader className="space-y-2">
          <CardTitle>{t("title")}</CardTitle>
          <CardDescription>{t("subtitle")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="relative">
            <Search className="absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t("searchPlaceholder")}
              className="ps-9"
            />
          </div>
          {searchQuery.isLoading ? (
            <p className="text-sm text-muted-foreground">{t("loadingSearch")}</p>
          ) : searchQuery.isError ? (
            <p className="text-sm text-muted-foreground">{t("error")}</p>
          ) : query.trim().length >= 2 ? (
            searchHits.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("noSearchResults")}</p>
            ) : (
              <div className="space-y-2">
                {searchHits.map((hit) => (
                  <div key={`${hit.entity_type}-${hit.entity_id}`} className="rounded-md border p-3">
                    <div className="flex items-center justify-between gap-3">
                      <div className="font-medium">
                        {t(`searchEntity_${hit.entity_type}`)}
                      </div>
                      <span className="text-xs text-muted-foreground">
                        {hit.captured_at ? new Date(hit.captured_at).toLocaleDateString(locale) : ""}
                      </span>
                    </div>
                    <div className="text-sm text-muted-foreground">{hit.title}</div>
                    {hit.statement ? (
                      <div className="text-sm text-muted-foreground">{hit.statement}</div>
                    ) : null}
                    <div className="mt-1 text-xs text-muted-foreground">
                      {hit.source_title ?? hit.source_domain ?? "-"}
                    </div>
                  </div>
                ))}
              </div>
            )
          ) : (
            <p className="text-sm text-muted-foreground">{t("searchHint")}</p>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <SummaryCard label={t("projectCount")} value={project.length} />
        <SummaryCard label={t("sourceCount")} value={summary.source_count ?? 0} />
        <SummaryCard label={t("evidenceCount")} value={summary.evidence_count ?? 0} />
        <SummaryCard label={t("findingCount")} value={summary.finding_count ?? 0} />
      </div>

      <Card>
        <CardHeader className="space-y-2">
          <CardTitle>{t("dataQuality")}</CardTitle>
          <CardDescription>{t("researchStatus")}</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <div>
            <div className="text-xs uppercase text-muted-foreground">{t("coverage")}</div>
            <div className="text-sm">
              {coverage?.status === "available"
                ? `${coverage.covered_categories ?? 0}/${coverage.total_categories ?? 0}`
                : t("coverageUnavailable")}
            </div>
          </div>
          <div>
            <div className="text-xs uppercase text-muted-foreground">{t("freshness")}</div>
            <div className="text-sm">
              {summary.freshness ? new Date(summary.freshness).toLocaleString(locale) : t("unavailable")}
            </div>
          </div>
          <div className="md:col-span-2">
            <div className="text-xs uppercase text-muted-foreground">{t("missingAreas")}</div>
            <div className="text-sm text-muted-foreground">
              {Array.isArray(summary.missing_areas) && summary.missing_areas.length > 0
                ? summary.missing_areas.join(", ")
                : t("none")}
            </div>
          </div>
        </CardContent>
      </Card>

      <ResearchProjects businessId={businessId} />
      <CollectionPanel businessId={businessId} projectId={activeProjectId} />
      <IntelligencePanel businessId={businessId} projectId={activeProjectId} />
      <StrategySection businessId={businessId} />
      <CompetitorList businessId={businessId} />
      <SourceList businessId={businessId} />
      <EvidenceList businessId={businessId} />
      <FindingsList businessId={businessId} />
    </div>
  );
}
