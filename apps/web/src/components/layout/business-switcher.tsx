"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useBusiness } from "@/context/business-context";
import { fetchBusinesses } from "@/features/businesses/api";

/**
 * Business selector. The active business is persisted in the client/session
 * context and sent to the API as X-Business-Id; the backend re-validates
 * agency/business access on every request.
 */
export function BusinessSwitcher() {
  const t = useTranslations("common");
  const { activeOrganizationId, activeBusinessId, setActiveBusiness } = useBusiness();

  const { data: businesses = [] } = useQuery({
    queryKey: ["businesses", activeOrganizationId],
    queryFn: fetchBusinesses,
    enabled: Boolean(activeOrganizationId),
  });

  if (!activeOrganizationId) return null;

  const active = businesses.find((business) => business.id === activeBusinessId);

  return (
    <div className="flex items-center gap-2" data-testid="business-switcher">
      <span className="text-xs text-muted-foreground">{t("business")}:</span>
      <Select value={active?.id ?? ""} onValueChange={setActiveBusiness}>
        <SelectTrigger className="h-8 w-52" aria-label={t("business")}>
          <SelectValue placeholder={t("noBusiness")} />
        </SelectTrigger>
        <SelectContent>
          {businesses.length === 0 ? (
            <SelectItem value="__none__" disabled>
              {t("noBusiness")}
            </SelectItem>
          ) : (
            businesses.map((business) => (
              <SelectItem key={business.id} value={business.id}>
                {business.name}
              </SelectItem>
            ))
          )}
        </SelectContent>
      </Select>
    </div>
  );
}