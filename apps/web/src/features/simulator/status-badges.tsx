"use client";

import { useTranslations } from "next-intl";

const STRENGTH_CLASSES: Record<string, string> = {
  strong: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  moderate: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  weak: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  insufficient: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
};

export function StrengthBadge({ strength }: { strength: string }) {
  const t = useTranslations("simulator");
  return (
    <span
      data-testid={`strength-${strength}`}
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
        STRENGTH_CLASSES[strength] ?? STRENGTH_CLASSES.insufficient
      }`}
    >
      {t(strength)}
    </span>
  );
}