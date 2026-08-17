"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
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
  fetchResearchCompetitors,
  fetchResearchEvidence,
  fetchResearchSources,
} from "./api";

interface SourceListProps {
  businessId: string;
}

export function SourceList({ businessId }: SourceListProps) {
  const t = useTranslations("research");
  const [filter, setFilter] = useState("");
  const [sourceType, setSourceType] = useState("all");
  const [competitorId, setCompetitorId] = useState("all");

  const sourcesQuery = useQuery({
    queryKey: ["research-sources", businessId],
    queryFn: () => fetchResearchSources(businessId),
    enabled: Boolean(businessId),
  });
  const evidenceQuery = useQuery({
    queryKey: ["research-evidence", businessId],
    queryFn: () => fetchResearchEvidence(businessId),
    enabled: Boolean(businessId),
  });
  const competitorsQuery = useQuery({
    queryKey: ["research-competitors", businessId],
    queryFn: () => fetchResearchCompetitors(businessId),
    enabled: Boolean(businessId),
  });

  const sources = sourcesQuery.data?.sources ?? [];
  const competitors = competitorsQuery.data?.competitors ?? [];
  const evidence = evidenceQuery.data?.evidence ?? [];
  const competitorLabelById = useMemo(
    () => Object.fromEntries(competitors.map((competitor) => [competitor.id, competitor.name])),
    [competitors]
  );
  const evidenceCountBySource = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const source of sources) counts[source.id] = 0;
    for (const item of evidence) counts[item.source_id] = (counts[item.source_id] ?? 0) + 1;
    return counts;
  }, [evidence, sources]);

  const rows = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    return sources.filter((source) => {
      const matchesNeedle =
        needle.length === 0 ||
        source.title.toLowerCase().includes(needle) ||
        (source.domain ?? "").toLowerCase().includes(needle) ||
        (source.url ?? "").toLowerCase().includes(needle);
      const matchesType = sourceType === "all" || source.source_type === sourceType;
      const matchesCompetitor =
        competitorId === "all" || String(source.competitor_id ?? "") === competitorId;
      return matchesNeedle && matchesType && matchesCompetitor;
    });
  }, [competitorId, filter, sourceType, sources]);

  if (sourcesQuery.isLoading || competitorsQuery.isLoading || evidenceQuery.isLoading) {
    return (
      <Card>
        <CardContent className="flex items-center gap-2 py-8 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> {t("loading")}
        </CardContent>
      </Card>
    );
  }

  if (sourcesQuery.isError || competitorsQuery.isError || evidenceQuery.isError) {
    return (
      <Card>
        <CardContent className="space-y-2 py-8 text-center">
          <p className="text-muted-foreground">{t("error")}</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card data-testid="source-list">
      <CardHeader className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <CardTitle>{t("tabs.sources")}</CardTitle>
          <span className="text-xs text-muted-foreground">
            {sources.length} {t("sourceCount")}
          </span>
        </div>
        <div className="grid gap-3 lg:grid-cols-3">
          <div className="relative lg:col-span-1">
            <Search className="absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              placeholder={t("searchPlaceholder")}
              className="ps-9"
            />
          </div>
          <Select value={sourceType} onValueChange={setSourceType}>
            <SelectTrigger>
              <SelectValue placeholder={t("sourceTypeFilter")} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t("all")}</SelectItem>
              <SelectItem value="website">{t("source_type_website")}</SelectItem>
              <SelectItem value="product_page">{t("source_type_product_page")}</SelectItem>
              <SelectItem value="landing_page">{t("source_type_landing_page")}</SelectItem>
              <SelectItem value="advertisement">{t("source_type_advertisement")}</SelectItem>
              <SelectItem value="review">{t("source_type_review")}</SelectItem>
              <SelectItem value="manual">{t("source_type_manual")}</SelectItem>
              <SelectItem value="other">{t("source_type_other")}</SelectItem>
            </SelectContent>
          </Select>
          <Select value={competitorId} onValueChange={setCompetitorId}>
            <SelectTrigger>
              <SelectValue placeholder={t("selectCompetitor")} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t("all")}</SelectItem>
              {competitors.map((competitor) => (
                <SelectItem key={competitor.id} value={competitor.id}>
                  {competitor.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("noSources")}</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-start text-muted-foreground">
                <th className="py-2 pe-2 font-normal">{t("type")}</th>
                <th className="py-2 pe-2 font-normal">{t("title_field")}</th>
                <th className="py-2 pe-2 font-normal">{t("domain")}</th>
                <th className="py-2 pe-2 font-normal">{t("source")}</th>
                <th className="py-2 pe-2 font-normal">{t("evidenceCount")}</th>
                <th className="py-2 pe-2 font-normal">{t("capturedAt")}</th>
                <th className="py-2 font-normal">{t("status")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((source) => (
                <tr key={source.id} className="border-b last:border-b-0">
                  <td className="py-2 pe-2">{source.source_type}</td>
                  <td className="py-2 pe-2">
                    <div className="font-medium">{source.title}</div>
                    <div className="text-xs text-muted-foreground">
                      {source.url ?? source.content_hash ?? "-"}
                    </div>
                  </td>
                  <td className="py-2 pe-2">{source.domain ?? "-"}</td>
                  <td className="py-2 pe-2">
                    {source.competitor_id ? competitorLabelById[source.competitor_id] ?? "-" : "-"}
                  </td>
                  <td className="py-2 pe-2">{evidenceCountBySource[source.id] ?? 0}</td>
                  <td className="py-2 pe-2">
                    {new Date(source.captured_at).toLocaleDateString()}
                  </td>
                  <td className="py-2">{source.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}
