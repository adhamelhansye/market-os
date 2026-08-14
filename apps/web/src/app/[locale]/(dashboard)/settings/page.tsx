"use client";

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

export default function SettingsPage() {
  const t = useTranslations("dashboard");
  const common = useTranslations("common");
  const { user, memberships } = useAuth();
  const { activeOrganizationId } = useBusiness();

  const activeMembership = memberships.find((m) => m.organization.id === activeOrganizationId);

  if (!user) return null;

  const canReadSettings = activeMembership?.permissions.includes("settings:read") ?? false;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">{t("settingsTitle")}</h1>
        <p className="text-muted-foreground">{t("settingsSubtitle")}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t("profileSection")}</CardTitle>
          <CardDescription>{user.email}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-1 text-sm">
          <p>
            <span className="text-muted-foreground">{common("role")}:</span>{" "}
            {activeMembership?.role_name ?? "-"}
          </p>
          <p>
            <span className="text-muted-foreground">{common("language")}:</span>{" "}
            {user.locale}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("organizationSection")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 text-sm">
          {canReadSettings && activeMembership ? (
            <>
              <p>
                <span className="text-muted-foreground">{common("organization")}:</span>{" "}
                {activeMembership.organization.name}
              </p>
              <p>
                <span className="text-muted-foreground">{t("orgType")}:</span>{" "}
                {activeMembership.organization.type}
              </p>
            </>
          ) : (
            <p className="text-muted-foreground">{t("noMemberships")}</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("membershipSection")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 text-sm">
          {memberships.length === 0 ? (
            <p className="text-muted-foreground">{t("noMemberships")}</p>
          ) : (
            memberships.map((membership) => (
              <p key={membership.organization.id}>
                {membership.organization.name} · {membership.role_name}
              </p>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}