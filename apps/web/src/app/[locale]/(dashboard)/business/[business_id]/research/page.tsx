"use client";

import { BusinessPageHeader, useBusinessIdFromPath } from "@/components/business/business-page";
import { ResearchSection } from "@/features/research/research-section";
import { useTranslations } from "next-intl";

export default function ResearchPage() {
  const t = useTranslations("research");
  const businessId = useBusinessIdFromPath();

  if (!businessId) return null;

  return (
    <div className="space-y-6">
      <BusinessPageHeader title={t("title")} subtitle={t("subtitle")} />
      <ResearchSection businessId={businessId} />
    </div>
  );
}
