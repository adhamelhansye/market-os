"use client";

import { useEffect, useRef } from "react";
import { useTranslations } from "next-intl";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAuth } from "@/context/auth-context";
import { useBusiness } from "@/context/business-context";

/**
 * Organization selector for users belonging to multiple organizations.
 * Backend re-validates membership on every request.
 */
export function OrganizationSwitcher() {
  const t = useTranslations("common");
  const { memberships, status } = useAuth();
  const { activeOrganizationId, setActiveOrganization } = useBusiness();
  const initialized = useRef(false);

  useEffect(() => {
    if (!initialized.current && memberships.length > 0 && !activeOrganizationId) {
      initialized.current = true;
      setActiveOrganization(memberships[0].organization.id);
    }
  }, [memberships, activeOrganizationId, setActiveOrganization]);

  if (status !== "authenticated" || memberships.length === 0) return null;

  const active = memberships.find((m) => m.organization.id === activeOrganizationId);

  const handleChange = (organizationId: string) => {
    setActiveOrganization(organizationId);
  };

  return (
    <div className="flex items-center gap-2" data-testid="organization-switcher">
      <span className="text-xs text-muted-foreground">{t("organization")}:</span>
      <Select value={active?.organization.id ?? ""} onValueChange={handleChange}>
        <SelectTrigger className="h-8 w-52" aria-label={t("organization")}>
          <SelectValue placeholder={t("empty")} />
        </SelectTrigger>
        <SelectContent>
          {memberships.map((membership) => (
            <SelectItem key={membership.organization.id} value={membership.organization.id}>
              {membership.organization.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}