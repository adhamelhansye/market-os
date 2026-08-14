"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useAuth } from "@/context/auth-context";
import { useBusiness } from "@/context/business-context";
import { fetchBusinesses } from "@/features/businesses/api";

export default function DashboardPage() {
  const t = useTranslations("dashboard");
  const { user, memberships } = useAuth();
  const { activeOrganizationId, activeBusinessId } = useBusiness();

  const { data: businesses = [] } = useQuery({
    queryKey: ["businesses", activeOrganizationId],
    queryFn: fetchBusinesses,
    enabled: Boolean(activeOrganizationId),
  });

  const activeMembership = memberships.find((m) => m.organization.id === activeOrganizationId);
  const activeBusiness = businesses.find((business) => business.id === activeBusinessId);

  if (!user) return null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">{t("greeting", { name: user.name })}</h1>
        <p className="text-muted-foreground">{t("title")}</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">{t("currentOrganization")}</CardTitle>
          </CardHeader>
          <CardContent className="text-lg font-medium">
            {activeMembership?.organization.name ?? t("noMemberships")}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">{t("currentRole")}</CardTitle>
          </CardHeader>
          <CardContent className="text-lg font-medium">
            {activeMembership?.role_name ?? "-"}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">{t("currentBusiness")}</CardTitle>
          </CardHeader>
          <CardContent className="text-lg font-medium">
            {activeBusiness?.name ?? t("noBusinessYet")}
          </CardContent>
        </Card>
      </div>

      <Card className="border-dashed">
        <CardHeader>
          <CardTitle>{t("emptyStateTitle")}</CardTitle>
          <CardDescription>{t("emptyStateBody")}</CardDescription>
        </CardHeader>
        <CardContent>{/* No real marketing metrics in Phase 0. */}</CardContent>
      </Card>
    </div>
  );
}