"use client";

import { useTranslations } from "next-intl";

const STATUS_CLASSES: Record<string, string> = {
  draft: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  collecting: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  processing: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  completed: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  failed: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  archived: "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400",
};

const STRENGTH_CLASSES: Record<string, string> = {
  strong: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  moderate: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  weak: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  insufficient: "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400",
};

const IMPORTANCE_CLASSES: Record<string, string> = {
  high: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  medium: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  low: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
};

const CONFIDENCE_CLASSES: Record<string, string> = {
  observed: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  supported: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  inferred: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  hypothesis: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
};

function Badge({ testId, className, label }: { testId: string; className: string; label: string }) {
  return (
    <span
      data-testid={testId}
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${className}`}
    >
      {label}
    </span>
  );
}

export function ProjectStatusBadge({ status }: { status: string }) {
  const t = useTranslations("research");
  return (
    <Badge
      testId={`status-${status}`}
      className={STATUS_CLASSES[status] ?? STATUS_CLASSES.draft}
      label={t(`status_${status}`)}
    />
  );
}

export function EvidenceStrengthBadge({ strength }: { strength: string }) {
  const t = useTranslations("research");
  return (
    <Badge
      testId={`strength-${strength}`}
      className={STRENGTH_CLASSES[strength] ?? STRENGTH_CLASSES.insufficient}
      label={t(`strength_${strength}`)}
    />
  );
}

export function ImportanceBadge({ importance }: { importance: string }) {
  const t = useTranslations("research");
  return (
    <Badge
      testId={`importance-${importance}`}
      className={IMPORTANCE_CLASSES[importance] ?? IMPORTANCE_CLASSES.medium}
      label={t(`importance_${importance}`)}
    />
  );
}

export function ConfidenceBadge({ confidence }: { confidence: string }) {
  const t = useTranslations("research");
  return (
    <Badge
      testId={`confidence-${confidence}`}
      className={CONFIDENCE_CLASSES[confidence] ?? CONFIDENCE_CLASSES.hypothesis}
      label={t(`confidence_${confidence}`)}
    />
  );
}

export function ClassificationBadge({ classification }: { classification: string }) {
  const t = useTranslations("research");
  return (
    <Badge
      testId={`classification-${classification}`}
      className="bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300"
      label={t(`classification_${classification}`)}
    />
  );
}
