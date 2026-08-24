"use client";

import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useState } from "react";
import { useTranslations } from "next-intl";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  fetchActionDrafts,
  fetchTestReport,
  type TestReportResponse,
} from "./api";

function SignalGrid({ signals }: { signals: Record<string, unknown>[] }) {
  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-3" data-testid="report-signals">
      {signals.map((signal) => {
        const s = signal as { code: string; value: string | null; status: string; source: string };
        return (
          <div key={s.code} className="flex justify-between">
            <span className="font-medium">{s.code}</span>
            <span className={s.status === "available" ? "text-muted-foreground" : "text-amber-600"}>
              {s.status === "available" ? String(s.value) : "unavailable"}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function ReportPanel({ report }: { report: TestReportResponse }) {
  const t = useTranslations("strategy");
  const test = (report.test ?? {}) as Record<string, unknown>;
  const lifecycle = (report.lifecycle ?? {}) as Record<string, unknown>;
  const measurement = (report.measurement ?? {}) as Record<string, unknown>;
  const learning = (report.learning ?? {}) as Record<string, unknown>;
  const entities = (measurement.entities ?? []) as Record<string, unknown>[];

  return (
    <div className="space-y-3" data-testid="test-report-panel">
      <div className="grid gap-1 rounded-md border p-3 text-xs sm:grid-cols-2">
        <div><span className="font-medium">{t("planStatus")}:</span> {String(test.status ?? "unavailable")}</div>
        <div><span className="font-medium">{t("observationStatus")}:</span>{" "}
          <span className={measurement.observation_status === "sufficient" ? "" : "text-amber-600"}>
            {String(measurement.observation_status ?? "insufficient_data")}
          </span>
        </div>
        {measurement.reason ? (
          <div className="text-muted-foreground sm:col-span-2">{String(measurement.reason)}</div>
        ) : null}
      </div>

      {entities.map((entity) => {
        const e = entity as Record<string, unknown> & {
          observation_status?: string;
          signals?: Record<string, unknown>[];
          fatigue?: Record<string, unknown>;
          classification?: Record<string, unknown>;
        };
        const attribution = (e.attribution ?? {}) as Record<string, unknown>;
        if (attribution.status !== "linked") return null;
        return (
          <div key={String(entity.entity_id)} className="space-y-2 rounded-md border p-3">
            <div className="text-xs font-medium text-muted-foreground">
              {String(entity.entity_id ?? "").slice(0, 8)} · {e.observation_status}
            </div>
            {e.signals ? <SignalGrid signals={e.signals} /> : null}
            {e.fatigue ? (
              <div className="text-xs">
                <span className="font-medium">{t("fatigue")}: </span>
                <span className={(e.fatigue as { status?: string }).status === "fatigue_signal" ? "text-destructive" : "text-muted-foreground"}>
                  {String((e.fatigue as { status?: string }).status)}
                </span>
              </div>
            ) : null}
            {e.classification ? (
              <div className="text-xs">
                <span className="font-medium">{t("classification")}: </span>
                <span className="text-muted-foreground">
                  {String((e.classification as { status?: string }).status)}
                </span>
              </div>
            ) : null}
          </div>
        );
      })}

      <div className="rounded-md border p-3 text-xs" data-testid="report-learning">
        <div className="mb-1 font-medium">{t("learningTitle")}</div>
        {(learning as { status?: string }).status === "available" ? (
          <>
            {((learning.learnings ?? []) as { statement?: string }[]).map((l, i) => (
              <p key={i} className="text-muted-foreground">{l.statement}</p>
            ))}
          </>
        ) : (
          <div className="text-muted-foreground">{t("noLearningItems")}</div>
        )}
      </div>

      <div className="border-t pt-2 text-[10px] text-muted-foreground">
        {report.completion_note}
      </div>
    </div>
  );
}

export function CreativeTestReportSection({ businessId }: { businessId: string }) {
  const t = useTranslations("strategy");
  const [selectedRef, setSelectedRef] = useState<string | null>(null);

  const draftsQuery = useQuery({
    queryKey: ["action-drafts", businessId],
    queryFn: () => fetchActionDrafts(businessId),
    enabled: Boolean(businessId),
  });

  const activatedDrafts = (draftsQuery.data ?? []).filter(
    (d) => d.review_state === "acknowledged"
  );

  const activeDraft =
    selectedRef !== null
      ? activatedDrafts.find((d) => d.draft_test_id === selectedRef)
      : activatedDrafts[0];

  const reportQuery = useQuery({
    queryKey: ["test-report", businessId, activeDraft?.draft_test_id],
    queryFn: () => fetchTestReport(businessId, activeDraft!.draft_test_id),
    enabled: Boolean(businessId && activeDraft),
  });

  const report = reportQuery.data;

  return (
    <Card data-testid="creative-test-report-section">
      <CardHeader>
        <CardTitle>{t("creativeTestReport")}</CardTitle>
        <CardDescription>{t("creativeTestReportDescription")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {activatedDrafts.length > 1 ? (
          <select
            aria-label={t("planStatus")}
            className="rounded-md border bg-background px-2 py-1 text-sm"
            value={activeDraft?.draft_test_id ?? ""}
            onChange={(e) => setSelectedRef(e.target.value || null)}
          >
            {activatedDrafts.map((d) => (
              <option key={d.draft_test_id} value={d.draft_test_id}>
                {d.draft_kind} · {d.draft_test_id.slice(0, 18)}
              </option>
            ))}
          </select>
        ) : null}

        {draftsQuery.isLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> {t("loadingPerformance")}
          </div>
        ) : activatedDrafts.length === 0 ? (
          <div className="rounded-md border border-dashed p-3 text-sm text-muted-foreground" data-testid="report-empty">
            {t("noActionDrafts")}
          </div>
        ) : reportQuery.isLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> {t("loadingPerformance")}
          </div>
        ) : report ? (
          <ReportPanel report={report} />
        ) : null}
      </CardContent>
    </Card>
  );
}
