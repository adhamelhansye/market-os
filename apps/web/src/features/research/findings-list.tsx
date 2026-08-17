"use client";

import { useMemo, useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { Loader2, Search } from "lucide-react";
import { useTranslations } from "next-intl";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  fetchResearchFindings,
  fetchResearchFinding,
  fetchResearchSources,
  type ResearchFindingResponse,
} from "./api";
import { ClassificationBadge, EvidenceStrengthBadge, ImportanceBadge } from "./status-badges";

interface FindingsListProps {
  businessId: string;
}

export function FindingsList({ businessId }: FindingsListProps) {
  const t = useTranslations("research");
  const [filter, setFilter] = useState("");
  const [classification, setClassification] = useState("all");
  const [category, setCategory] = useState("all");
  const [importance, setImportance] = useState("all");

  const findingsQuery = useQuery({
    queryKey: ["research-findings", businessId],
    queryFn: () => fetchResearchFindings(businessId),
    enabled: Boolean(businessId),
  });
  const sourcesQuery = useQuery({
    queryKey: ["research-sources", businessId],
    queryFn: () => fetchResearchSources(businessId),
    enabled: Boolean(businessId),
  });

  const findings = findingsQuery.data?.findings ?? [];
  const sources = sourcesQuery.data?.sources ?? [];
  const sourceById = useMemo(
    () => Object.fromEntries(sources.map((source) => [source.id, source])),
    [sources]
  );

  const detailQueries = useQueries({
    queries: findings.map((finding) => ({
      queryKey: ["research-finding-detail", businessId, finding.id],
      queryFn: () => fetchResearchFinding(businessId, finding.id),
      enabled: Boolean(businessId),
    })),
  });

  const detailById = useMemo(() => {
    const map = new Map<string, (typeof detailQueries)[number]["data"]>();
    findings.forEach((finding, index) => {
      const detail = detailQueries[index]?.data;
      if (detail) map.set(finding.id, detail);
    });
    return map;
  }, [detailQueries, findings]);

  const rows = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    return findings.filter((finding) => {
      const matchesNeedle =
        needle.length === 0 ||
        finding.title.toLowerCase().includes(needle) ||
        finding.statement.toLowerCase().includes(needle);
      const matchesClassification =
        classification === "all" || finding.classification === classification;
      const matchesCategory = category === "all" || finding.category === category;
      const matchesImportance = importance === "all" || finding.importance === importance;
      return matchesNeedle && matchesClassification && matchesCategory && matchesImportance;
    });
  }, [category, classification, filter, findings, importance]);

  if (findingsQuery.isLoading || sourcesQuery.isLoading) {
    return (
      <Card>
        <CardContent className="flex items-center gap-2 py-8 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> {t("loading")}
        </CardContent>
      </Card>
    );
  }

  if (findingsQuery.isError || sourcesQuery.isError) {
    return (
      <Card>
        <CardContent className="space-y-2 py-8 text-center">
          <p className="text-muted-foreground">{t("error")}</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card data-testid="findings-list">
      <CardHeader className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <CardTitle>{t("tabs.findings")}</CardTitle>
          <span className="text-xs text-muted-foreground">
            {findings.length} {t("findingCount")}
          </span>
        </div>
        <div className="grid gap-3 lg:grid-cols-4">
          <div className="relative lg:col-span-1">
            <Search className="absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              placeholder={t("searchPlaceholder")}
              className="ps-9"
            />
          </div>
          <Select value={classification} onValueChange={setClassification}>
            <SelectTrigger>
              <SelectValue placeholder={t("classification")} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t("all")}</SelectItem>
              <SelectItem value="observed">{t("classification_observed")}</SelectItem>
              <SelectItem value="inferred">{t("classification_inferred")}</SelectItem>
              <SelectItem value="hypothesis">{t("classification_hypothesis")}</SelectItem>
            </SelectContent>
          </Select>
          <Select value={category} onValueChange={setCategory}>
            <SelectTrigger>
              <SelectValue placeholder={t("category")} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t("all")}</SelectItem>
              <SelectItem value="market">{t("category_market")}</SelectItem>
              <SelectItem value="customer">{t("category_customer")}</SelectItem>
              <SelectItem value="competitor">{t("category_competitor")}</SelectItem>
              <SelectItem value="offer">{t("category_offer")}</SelectItem>
              <SelectItem value="pricing">{t("category_pricing")}</SelectItem>
              <SelectItem value="positioning">{t("category_positioning")}</SelectItem>
              <SelectItem value="messaging">{t("category_messaging")}</SelectItem>
              <SelectItem value="creative">{t("category_creative")}</SelectItem>
              <SelectItem value="funnel">{t("category_funnel")}</SelectItem>
              <SelectItem value="product">{t("category_product")}</SelectItem>
              <SelectItem value="retention">{t("category_retention")}</SelectItem>
            </SelectContent>
          </Select>
          <Select value={importance} onValueChange={setImportance}>
            <SelectTrigger>
              <SelectValue placeholder={t("importance")} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t("all")}</SelectItem>
              <SelectItem value="low">{t("importance_low")}</SelectItem>
              <SelectItem value="medium">{t("importance_medium")}</SelectItem>
              <SelectItem value="high">{t("importance_high")}</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("noFindings")}</p>
        ) : (
          <div className="space-y-3">
            {rows.map((finding: ResearchFindingResponse) => {
              const detail = detailById.get(finding.id);
              const evidenceSummaries = detail?.evidence ?? [];
              const sourceIds = Array.from(new Set(evidenceSummaries.map((item) => item.source_id)));
              const sourceLabels = sourceIds.map((sourceId) => sourceById[sourceId]?.title ?? sourceId);
              return (
                <div key={finding.id} className="rounded-lg border p-4" data-testid="finding-card">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <ClassificationBadge classification={finding.classification} />
                        <EvidenceStrengthBadge strength={finding.evidence_strength} />
                        <ImportanceBadge importance={finding.importance} />
                      </div>
                      <div>
                        <h4 className="font-medium">{finding.title}</h4>
                        <p className="text-sm text-muted-foreground">{finding.statement}</p>
                      </div>
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {finding.created_at ? new Date(finding.created_at).toLocaleDateString() : ""}
                    </div>
                  </div>
                  <div className="mt-3 grid gap-3 text-sm sm:grid-cols-3">
                    <div>
                      <div className="text-xs uppercase text-muted-foreground">
                        {t("evidenceCount")}
                      </div>
                      <div>{evidenceSummaries.length}</div>
                    </div>
                    <div>
                      <div className="text-xs uppercase text-muted-foreground">
                        {t("sourceCount")}
                      </div>
                      <div>{sourceIds.length}</div>
                    </div>
                    <div>
                      <div className="text-xs uppercase text-muted-foreground">
                        {t("source")}
                      </div>
                      <div className="text-sm text-muted-foreground">
                        {sourceLabels.length > 0 ? sourceLabels.join(", ") : "-"}
                      </div>
                    </div>
                  </div>
                  {evidenceSummaries.length > 0 ? (
                    <div className="mt-3 space-y-2">
                      {evidenceSummaries.map((item) => (
                        <div key={item.id} className="rounded-md bg-muted/40 px-3 py-2 text-sm">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-medium">{item.evidence_type}</span>
                            <span className="text-xs text-muted-foreground">
                              {sourceById[item.source_id]?.title ?? item.source_id}
                            </span>
                          </div>
                          <p className="text-muted-foreground">{item.statement}</p>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
