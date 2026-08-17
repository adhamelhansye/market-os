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
  fetchResearchEvidence,
  fetchResearchSources,
  type ResearchEvidenceResponse,
} from "./api";
import { ClassificationBadge } from "./status-badges";

interface EvidenceListProps {
  businessId: string;
}

export function EvidenceList({ businessId }: EvidenceListProps) {
  const t = useTranslations("research");
  const [filter, setFilter] = useState("");
  const [classification, setClassification] = useState("all");
  const [evidenceType, setEvidenceType] = useState("all");
  const [sourceId, setSourceId] = useState("all");

  const evidenceQuery = useQuery({
    queryKey: ["research-evidence", businessId],
    queryFn: () => fetchResearchEvidence(businessId),
    enabled: Boolean(businessId),
  });
  const sourcesQuery = useQuery({
    queryKey: ["research-sources", businessId],
    queryFn: () => fetchResearchSources(businessId),
    enabled: Boolean(businessId),
  });

  const evidence = evidenceQuery.data?.evidence ?? [];
  const sources = sourcesQuery.data?.sources ?? [];
  const sourceById = useMemo(
    () => Object.fromEntries(sources.map((source) => [source.id, source])),
    [sources]
  );

  const rows = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    return evidence.filter((row) => {
      const matchesNeedle =
        needle.length === 0 ||
        row.statement.toLowerCase().includes(needle) ||
        (row.raw_excerpt ?? "").toLowerCase().includes(needle);
      const matchesClassification =
        classification === "all" || row.classification === classification;
      const matchesType = evidenceType === "all" || row.evidence_type === evidenceType;
      const matchesSource = sourceId === "all" || String(row.source_id) === sourceId;
      return matchesNeedle && matchesClassification && matchesType && matchesSource;
    });
  }, [classification, evidence, evidenceType, filter, sourceId]);

  if (evidenceQuery.isLoading || sourcesQuery.isLoading) {
    return (
      <Card>
        <CardContent className="flex items-center gap-2 py-8 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> {t("loading")}
        </CardContent>
      </Card>
    );
  }

  if (evidenceQuery.isError || sourcesQuery.isError) {
    return (
      <Card>
        <CardContent className="space-y-2 py-8 text-center">
          <p className="text-muted-foreground">{t("error")}</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card data-testid="evidence-list">
      <CardHeader className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <CardTitle>{t("tabs.evidence")}</CardTitle>
          <span className="text-xs text-muted-foreground">
            {evidence.length} {t("evidenceCount")}
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
          <Select value={evidenceType} onValueChange={setEvidenceType}>
            <SelectTrigger>
              <SelectValue placeholder={t("type")} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t("all")}</SelectItem>
              <SelectItem value="pricing">{t("evidence_type_pricing")}</SelectItem>
              <SelectItem value="offer">{t("evidence_type_offer")}</SelectItem>
              <SelectItem value="product">{t("evidence_type_product")}</SelectItem>
              <SelectItem value="positioning">{t("evidence_type_positioning")}</SelectItem>
              <SelectItem value="messaging">{t("evidence_type_messaging")}</SelectItem>
              <SelectItem value="trust_signal">{t("evidence_type_trust_signal")}</SelectItem>
            </SelectContent>
          </Select>
          <Select value={sourceId} onValueChange={setSourceId}>
            <SelectTrigger>
              <SelectValue placeholder={t("selectSource")} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t("all")}</SelectItem>
              {sources.map((source) => (
                <SelectItem key={source.id} value={source.id}>
                  {source.title}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("noEvidence")}</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-start text-muted-foreground">
                <th className="py-2 pe-2 font-normal">{t("type")}</th>
                <th className="py-2 pe-2 font-normal">{t("statement")}</th>
                <th className="py-2 pe-2 font-normal">{t("source")}</th>
                <th className="py-2 pe-2 font-normal">{t("capturedAt")}</th>
                <th className="py-2 pe-2 font-normal">{t("classification")}</th>
                <th className="py-2 font-normal">{t("provenance")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row: ResearchEvidenceResponse) => {
                const source = sourceById[row.source_id];
                return (
                  <tr key={row.id} className="border-b last:border-b-0">
                    <td className="py-2 pe-2">{row.evidence_type}</td>
                    <td className="py-2 pe-2">
                      <div className="font-medium">{row.statement}</div>
                      {row.raw_excerpt ? (
                        <div className="text-xs text-muted-foreground">{row.raw_excerpt}</div>
                      ) : null}
                    </td>
                    <td className="py-2 pe-2">
                      <div className="font-medium">{source?.title ?? row.source_id}</div>
                      <div className="text-xs text-muted-foreground">
                        {source?.domain ?? source?.url ?? "-"}
                      </div>
                    </td>
                    <td className="py-2 pe-2">
                      {new Date(row.captured_at).toLocaleDateString()}
                    </td>
                    <td className="py-2 pe-2">
                      <ClassificationBadge classification={row.classification} />
                    </td>
                    <td className="py-2">{row.provenance}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}
