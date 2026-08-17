"use client";

import { useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ArrowRight, BarChart3, Package, PlugZap, Search, Settings } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAuth } from "@/context/auth-context";
import { useBusiness } from "@/context/business-context";
import { createBusiness, fetchBusinesses } from "@/features/businesses/api";
import { isApiError } from "@/context/auth-context";
import { localePath } from "@/lib/locale";
import { CURRENCIES, TIMEZONES } from "@/lib/select-options";

const businessSchema = z.object({
  name: z.string().min(1, "nameRequired"),
  currency: z.string().min(1, "currencyRequired"),
  timezone: z.string().min(1, "timezoneRequired"),
});

type BusinessValues = z.infer<typeof businessSchema>;

export default function DashboardPage() {
  const t = useTranslations("dashboard");
  const locale = useLocale();
  const { user, memberships } = useAuth();
  const { activeOrganizationId, activeBusinessId, setActiveBusiness } = useBusiness();
  const queryClient = useQueryClient();

  const [createError, setCreateError] = useState<string | null>(null);

  const { data: businesses = [] } = useQuery({
    queryKey: ["businesses", activeOrganizationId],
    queryFn: fetchBusinesses,
    enabled: Boolean(activeOrganizationId),
  });

  const activeMembership = memberships.find((m) => m.organization.id === activeOrganizationId);
  const activeBusiness = businesses.find((business) => business.id === activeBusinessId);

  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors },
  } = useForm<BusinessValues>({
    resolver: zodResolver(businessSchema),
    defaultValues: { name: "", currency: "USD", timezone: "UTC" },
  });

  const creation = useMutation({
    mutationFn: (values: BusinessValues) =>
      createBusiness({
        name: values.name,
        currency: values.currency,
        timezone: values.timezone,
        onboarding_status: "not_started",
      }),
    onSuccess: (business) => {
      setCreateError(null);
      setActiveBusiness(business.id);
      void queryClient.invalidateQueries({ queryKey: ["businesses", activeOrganizationId] });
    },
    onError: () => setCreateError(t("createBusinessFailed")),
  });

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

      {activeBusiness ? (
        <Card>
          <CardHeader>
            <CardTitle>{t("businessActions")}</CardTitle>
            <CardDescription>{activeBusiness.name}</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2">
            {activeBusiness.onboarding_status !== "completed" ? (
              <Button asChild variant="default">
                <Link
                  href={localePath(`/business/${activeBusiness.id}/onboarding`, locale)}
                >
                  {activeBusiness.onboarding_status === "in_progress"
                    ? t("continueOnboarding")
                    : t("startOnboarding")}
                  <ArrowRight className="ms-2 h-4 w-4 rtl:rotate-180" />
                </Link>
              </Button>
            ) : null}
            <Button asChild variant="outline">
              <Link href={localePath(`/business/${activeBusiness.id}/metrics`, locale)}>
                <BarChart3 className="me-2 h-4 w-4" />
                {t("viewMetrics")}
              </Link>
            </Button>
            <Button asChild variant="outline">
              <Link href={localePath(`/business/${activeBusiness.id}/research`, locale)}>
                <Search className="me-2 h-4 w-4" />
                {t("viewResearch")}
              </Link>
            </Button>
            <Button asChild variant="outline">
              <Link href={localePath(`/business/${activeBusiness.id}/economics`, locale)}>
                <BarChart3 className="me-2 h-4 w-4" />
                {t("viewEconomics")}
              </Link>
            </Button>
            <Button asChild variant="outline">
              <Link href={localePath(`/business/${activeBusiness.id}/products`, locale)}>
                <Package className="me-2 h-4 w-4" />
                {t("manageProducts")}
              </Link>
            </Button>
            <Button asChild variant="outline">
              <Link href={localePath(`/business/${activeBusiness.id}/integrations`, locale)}>
                <PlugZap className="me-2 h-4 w-4" />
                {t("viewIntegrations")}
              </Link>
            </Button>
            <Button asChild variant="outline">
              <Link href={localePath(`/business/${activeBusiness.id}/settings`, locale)}>
                <Settings className="me-2 h-4 w-4" />
                {t("businessSettings")}
              </Link>
            </Button>
          </CardContent>
        </Card>
      ) : null}

      {!activeBusiness && businesses.length > 0 ? (
        <Card className="border-dashed">
          <CardHeader>
            <CardTitle>{t("businessActions")}</CardTitle>
            <CardDescription>{t("noActiveBusiness")}</CardDescription>
          </CardHeader>
          <CardContent />
        </Card>
      ) : null}

      {businesses.length === 0 ? (
        <Card className="border-dashed">
          <CardHeader>
            <CardTitle>{t("createBusinessTitle")}</CardTitle>
            <CardDescription>{t("createBusinessHint")}</CardDescription>
          </CardHeader>
          <CardContent>
            <form
              onSubmit={handleSubmit((values) => creation.mutate(values))}
              className="grid gap-4 sm:grid-cols-2"
              noValidate
            >
              {createError ? (
                <p className="text-sm text-destructive sm:col-span-2" role="alert">
                  {createError}
                </p>
              ) : null}
              <div className="space-y-2">
                <Label htmlFor="new-business-name">{t("businessName")}</Label>
                <Input id="new-business-name" {...register("name")} />
                {errors.name ? (
                  <p className="text-sm text-destructive">{t("businessName")}</p>
                ) : null}
              </div>
              <div className="space-y-2">
                <Label htmlFor="new-business-currency">{t("businessCurrency")}</Label>
                <Select
                  defaultValue="USD"
                  onValueChange={(value) =>
                    setValue("currency", value, { shouldValidate: true })
                  }
                >
                  <SelectTrigger id="new-business-currency">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {CURRENCIES.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="new-business-timezone">{t("businessTimezone")}</Label>
                <Select
                  defaultValue="UTC"
                  onValueChange={(value) =>
                    setValue("timezone", value, { shouldValidate: true })
                  }
                >
                  <SelectTrigger id="new-business-timezone">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {TIMEZONES.map((tz) => (
                      <SelectItem key={tz} value={tz}>
                        {tz}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-end">
                <Button type="submit" disabled={creation.isPending}>
                  {creation.isPending
                    ? t("creatingBusiness")
                    : t("createBusinessCta")}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
