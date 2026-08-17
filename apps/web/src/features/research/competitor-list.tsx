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
  fetchResearchCompetitors,
  fetchResearchSources,
  searchResearchContent,
  type ResearchSourceResponse,
} from "./api";

interface CompetitorListProps {
  businessId: string;
}

function countLinkedSources(
  competitorId: string,
  sources: ResearchSourceResponse[]
): number {
  return sources.filter((source) => source.competitor_id === competitorId).length;
}

export function CompetitorList({ businessId }: CompetitorListProps) {
  const t = useTranslations("research");
  const [filter, setFilter] = useState("");
  const [status, setStatus] = useState("all");

  const competitorsQuery = useQuery({
    queryKey: ["research-competitors", businessId],
    queryFn: () => fetchResearchCompetitors(businessId),
    enabled: Boolean(businessId),
  });
  const sourcesQuery = useQuery({
    queryKey: ["research-sources", businessId],
    queryFn: () => fetchResearchSources(businessId),
    enabled: Boolean(businessId),
  });

  const competitors = competitorsQuery.data?.competitors ?? [];
  const sources = sourcesQuery.data?.sources ?? [];

  const searchQueries = useQueries({
    queries: competitors.map((competitor) => ({
      queryKey: ["research-competitor-search", businessId, competitor.id],
      queryFn: () => searchResearchContent(businessId, competitor.name),
      enabled: Boolean(businessId && competitor.name),
    })),
  });

  const findingCountByCompetitor = useMemo(() => {
    const map: Record<string, number> = {};
    competitors.forEach((competitor, index) => {
      const hits = searchQueries[index]?.data?.hits ?? [];
      map[competitor.id] = hits.filter((hit) => hit.entity_type === "finding").length;
    });
    return map;
  }, [competitors, searchQueries]);

  const rows = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    return competitors.filter((competitor) => {
      const matchesFilter =
        needle.length === 0 ||
        competitor.name.toLowerCase().includes(needle) ||
        (competitor.domain ?? "").toLowerCase().includes(needle) ||
        (competitor.market ?? "").toLowerCase().includes(needle);
      const matchesStatus = status === "all" || competitor.status === status;
      return matchesFilter && matchesStatus;
    });
  }, [competitors, filter, status]);

  if (competitorsQuery.isLoading) {
    return (
      <Card>
        <CardContent className="flex items-center gap-2 py-8 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> {t("loading")}
        </CardContent>
      </Card>
    );
  }

  if (competitorsQuery.isError) {
    return (
      <Card>
        <CardContent className="space-y-2 py-8 text-center">
          <p className="text-muted-foreground">{t("error")}</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card data-testid="competitor-list">
      <CardHeader className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <CardTitle>{t("tabs.competitors")}</CardTitle>
          <span className="text-xs text-muted-foreground">
            {competitors.length} {t("competitorCount")}
          </span>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="relative">
            <Search className="absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              placeholder={t("searchPlaceholder")}
              className="ps-9"
            />
          </div>
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger>
              <SelectValue placeholder={t("statusFilter")} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t("all")}</SelectItem>
              <SelectItem value="active">{t("competitorStatusActive")}</SelectItem>
              <SelectItem value="archived">{t("competitorStatusArchived")}</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("noCompetitors")}</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-start text-muted-foreground">
                <th className="py-2 pe-2 font-normal">{t("name")}</th>
                <th className="py-2 pe-2 font-normal">{t("domain")}</th>
                <th className="py-2 pe-2 font-normal">{t("sourceCount")}</th>
                <th className="py-2 pe-2 font-normal">{t("findingCount")}</th>
                <th className="py-2 font-normal">{t("status")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((competitor) => (
                <tr key={competitor.id} className="border-b last:border-b-0">
                  <td className="py-2 pe-2">
                    <div className="font-medium">{competitor.name}</div>
                    <div className="text-xs text-muted-foreground">
                      {competitor.description ?? competitor.market ?? "-"}
                    </div>
                  </td>
                  <td className="py-2 pe-2">{competitor.domain ?? "-"}</td>
                  <td className="py-2 pe-2">{countLinkedSources(competitor.id, sources)}</td>
                  <td className="py-2 pe-2">{findingCountByCompetitor[competitor.id] ?? 0}</td>
                  <td className="py-2">{competitor.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}
