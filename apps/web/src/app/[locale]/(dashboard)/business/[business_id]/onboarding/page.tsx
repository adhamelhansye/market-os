"use client";

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";

import {
  BusinessPageHeader,
  useBusinessIdFromPath,
} from "@/components/business/business-page";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { OnboardingWizard } from "@/features/onboarding/onboarding-wizard";
import { fetchBusiness } from "@/features/businesses/api";
import { localePath } from "@/lib/locale";

export default function OnboardingPage() {
  const t = useTranslations("onboarding");
  const locale = useLocale();
  const businessId = useBusinessIdFromPath();

  const { data: business, isLoading } = useQuery({
    queryKey: ["business", businessId ?? ""],
    queryFn: () => fetchBusiness(businessId as string),
    enabled: Boolean(businessId),
  });

  if (!businessId) return null;

  if (isLoading) {
    return (
      <div className="space-y-6">
        <BusinessPageHeader title={t("title")} />
        <Card>
          <CardContent className="text-muted-foreground">{t("emptyStage")}</CardContent>
        </Card>
      </div>
    );
  }

  if (!business) {
    return (
      <div className="space-y-6">
        <BusinessPageHeader title={t("title")} />
        <Card>
          <CardContent className="text-muted-foreground">
            {t("selectBusinessFirst")}
          </CardContent>
        </Card>
      </div>
    );
  }

  if (business.onboarding_status === "completed") {
    return (
      <div className="space-y-6">
        <BusinessPageHeader title={t("title")} />
        <Card>
          <CardHeader>
            <CardTitle>{t("reviewCompletedOn")}</CardTitle>
            <CardDescription>{t("reviewStepSubtitle")}</CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild variant="outline">
              <Link href={localePath(`/business/${businessId}/economics`, locale)}>
                {t("next")}
              </Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <BusinessPageHeader title={t("title")} />
      <OnboardingWizard businessId={businessId} business={business} />
    </div>
  );
}