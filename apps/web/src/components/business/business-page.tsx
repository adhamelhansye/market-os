"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { ArrowLeft } from "lucide-react";

import { localePath } from "@/lib/locale";

/**
 * Header for business-scoped pages. The business id comes from the URL
 * path (never trusted as-is): the API re-validates access server-side.
 */
export function BusinessPageHeader({
  title,
  subtitle,
}: {
  title: string;
  subtitle?: string;
}) {
  const locale = useLocale();
  const t = useTranslations("common");
  return (
    <div className="space-y-1">
      <Link
        href={localePath("/dashboard", locale)}
        className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4 rtl:rotate-180" />
        <span>{t("dashboard")}</span>
      </Link>
      <h1 className="text-2xl font-semibold">{title}</h1>
      {subtitle ? <p className="text-muted-foreground">{subtitle}</p> : null}
    </div>
  );
}

/** Extracts the business id from the URL path. */
export function useBusinessIdFromPath(): string | null {
  const params = useParams();
  const raw = params?.business_id;
  return typeof raw === "string" && raw.length > 0 ? raw : null;
}