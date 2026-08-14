"use client";

import { useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Plus, Trash2 } from "lucide-react";

import {
  BusinessPageHeader,
  useBusinessIdFromPath,
} from "@/components/business/business-page";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  fetchBusiness,
  fetchBusinessProfile,
  updateBusiness,
  updateBusinessProfile,
} from "@/features/businesses/api";
import { createGoal, deleteGoal, fetchGoals } from "@/features/goals/api";
import { isApiError } from "@/context/auth-context";
import { formatMoney } from "@/lib/money";
import { localePath } from "@/lib/locale";
import { CURRENCIES, TIMEZONES } from "@/lib/select-options";

const generalSchema = z.object({
  name: z.string().min(1, "nameRequired"),
  description: z.string().optional(),
  website_url: z.string().url("urlInvalid").optional().or(z.literal("")),
});

type GeneralValues = z.infer<typeof generalSchema>;

const profileSchema = z.object({
  industry: z.string().optional(),
  business_model: z.string().optional(),
  target_market: z.string().optional(),
  brand_positioning: z.string().optional(),
  average_order_value: z.string().optional(),
  primary_customer_type: z.string().optional(),
  brand_voice: z.string().optional(),
});

type ProfileValues = z.infer<typeof profileSchema>;

const goalSchema = z.object({
  target_revenue: z.string().optional(),
  target_profit: z.string().optional(),
  ad_budget: z.string().optional(),
  maximum_cpa: z.string().optional(),
  target_roas: z.string().optional(),
});

type GoalValues = z.infer<typeof goalSchema>;

export default function BusinessSettingsPage() {
  const t = useTranslations("settings");
  const locale = useLocale();
  const businessId = useBusinessIdFromPath();
  const queryClient = useQueryClient();

  const [generalStatus, setGeneralStatus] = useState<string | null>(null);
  const [profileStatus, setProfileStatus] = useState<string | null>(null);
  const [goalStatus, setGoalStatus] = useState<string | null>(null);
  const [goalError, setGoalError] = useState<string | null>(null);
  const [goalOpen, setGoalOpen] = useState(false);

  const { data: business } = useQuery({
    queryKey: ["business", businessId ?? ""],
    queryFn: () => fetchBusiness(businessId as string),
    enabled: Boolean(businessId),
  });

  const { data: profile } = useQuery({
    queryKey: ["business-profile", businessId ?? ""],
    queryFn: () => fetchBusinessProfile(businessId as string),
    enabled: Boolean(businessId),
  });

  const { data: goals = [] } = useQuery({
    queryKey: ["goals", businessId ?? ""],
    queryFn: () => fetchGoals(businessId as string),
    enabled: Boolean(businessId),
  });

  const key = businessId ?? "";

  const { register: registerGeneral, handleSubmit: handleGeneral } =
    useForm<GeneralValues>({
      resolver: zodResolver(generalSchema),
      values: {
        name: business?.name ?? "",
        description: business?.description ?? "",
        website_url: business?.website_url ?? "",
      },
    });

  const { register: registerProfile, handleSubmit: handleProfile } =
    useForm<ProfileValues>({
      resolver: zodResolver(profileSchema),
      values: {
        industry: profile?.industry ?? "",
        business_model: profile?.business_model ?? "",
        target_market: profile?.target_market ?? "",
        brand_positioning: profile?.brand_positioning ?? "",
        average_order_value: profile?.average_order_value ?? "",
        primary_customer_type: profile?.primary_customer_type ?? "",
        brand_voice: profile?.brand_voice ?? "",
      },
    });

  const { register: registerGoal, handleSubmit: handleGoal, reset: resetGoal } =
    useForm<GoalValues>({
      resolver: zodResolver(goalSchema),
      defaultValues: {
        target_revenue: "",
        target_profit: "",
        ad_budget: "",
        maximum_cpa: "",
        target_roas: "",
      },
    });

  const [currency, setCurrency] = useState<string | null>(null);
  const [timezone, setTimezone] = useState<string | null>(null);

  const updateGeneral = useMutation({
    mutationFn: (values: GeneralValues) =>
      updateBusiness(key, {
        name: values.name,
        description: values.description || null,
        website_url: values.website_url || null,
        currency: currency ?? undefined,
        timezone: timezone ?? undefined,
      }),
    onSuccess: () => {
      setGeneralStatus(t("updateSuccess"));
      void queryClient.invalidateQueries({ queryKey: ["business", key] });
    },
    onError: () => setGeneralStatus(t("updateFailed")),
  });

  const updateProfile = useMutation({
    mutationFn: (values: ProfileValues) =>
      updateBusinessProfile(key, {
        industry: values.industry || null,
        business_model: values.business_model || null,
        target_market: values.target_market || null,
        brand_positioning: values.brand_positioning || null,
        average_order_value: values.average_order_value || null,
        primary_customer_type: values.primary_customer_type || null,
        brand_voice: values.brand_voice || null,
      }),
    onSuccess: () => {
      setProfileStatus(t("updateSuccess"));
      void queryClient.invalidateQueries({ queryKey: ["business-profile", key] });
    },
    onError: () => setProfileStatus(t("updateFailed")),
  });

  const saveGoal = useMutation({
    mutationFn: (values: GoalValues) => {
      const period = currentYearGoalPeriod();
      return createGoal(key, {
        period_start: period.start,
        period_end: period.end,
        target_revenue: values.target_revenue || null,
        target_profit: values.target_profit || null,
        ad_budget: values.ad_budget || null,
        maximum_cpa: values.maximum_cpa || null,
        target_roas: values.target_roas || null,
        currency: business?.currency ?? "USD",
      });
    },
    onSuccess: () => {
      setGoalError(null);
      setGoalStatus(t("goalCreated"));
      setGoalOpen(false);
      resetGoal();
      void queryClient.invalidateQueries({ queryKey: ["goals", key] });
    },
    onError: (error) => {
      if (isApiError(error)) setGoalError(error.message);
      else setGoalError(t("goalCreateFailed"));
    },
  });

  const removeGoal = useMutation({
    mutationFn: (goalId: string) => deleteGoal(key, goalId),
    onSuccess: () => {
      setGoalStatus(t("goalDeleted"));
      void queryClient.invalidateQueries({ queryKey: ["goals", key] });
    },
    onError: () => setGoalStatus(t("goalDeleteFailed")),
  });

  if (!businessId) return null;

  const effectiveCurrency = currency ?? business?.currency ?? "USD";
  const effectiveTimezone = timezone ?? business?.timezone ?? "UTC";

  return (
    <div className="space-y-6">
      <BusinessPageHeader title={t("title")} subtitle={t("subtitle", { name: business?.name ?? "" })} />

      {business && business.onboarding_status !== "completed" ? (
        <Card className="border-dashed">
          <CardHeader>
            <CardTitle>{t("onboardingStatus")}: {t(business.onboarding_status)}</CardTitle>
            <CardDescription>{t("continueOnboarding")}</CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild variant="outline">
              <Link href={localePath(`/business/${businessId}/onboarding`, locale)}>
                {t("continueOnboarding")}
              </Link>
            </Button>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>{t("generalSection")}</CardTitle>
          <CardDescription>{t("generalSubtitle")}</CardDescription>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={handleGeneral((values) => updateGeneral.mutate(values))}
            className="space-y-4"
            noValidate
          >
            {generalStatus ? (
              <p className="text-sm text-muted-foreground" data-testid="general-status">
                {generalStatus}
              </p>
            ) : null}
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="settings-name">{t("name")}</Label>
                <Input id="settings-name" {...registerGeneral("name")} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="settings-website">{t("websiteUrl")}</Label>
                <Input id="settings-website" {...registerGeneral("website_url")} />
              </div>
              <div className="space-y-2 sm:col-span-2">
                <Label htmlFor="settings-description">{t("description")}</Label>
                <Input id="settings-description" {...registerGeneral("description")} />
              </div>
            </div>
            <Button type="submit" disabled={updateGeneral.isPending}>
              {updateGeneral.isPending ? t("save") : t("save")}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("currencySection")}</CardTitle>
          <CardDescription>{t("currencySubtitle")}</CardDescription>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={handleGeneral((values) => updateGeneral.mutate(values))}
            className="space-y-4"
          >
            <div className="space-y-2">
              <Label htmlFor="settings-currency">{t("currency")}</Label>
              <Select value={effectiveCurrency} onValueChange={setCurrency}>
                <SelectTrigger id="settings-currency">
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
            <Button type="submit" disabled={updateGeneral.isPending || !currency}>
              {updateGeneral.isPending ? t("save") : t("save")}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("timezoneSection")}</CardTitle>
          <CardDescription>{t("timezoneSubtitle")}</CardDescription>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={handleGeneral((values) => updateGeneral.mutate(values))}
            className="space-y-4"
          >
            <div className="space-y-2">
              <Label htmlFor="settings-timezone">{t("timezone")}</Label>
              <Select value={effectiveTimezone} onValueChange={setTimezone}>
                <SelectTrigger id="settings-timezone">
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
            <Button type="submit" disabled={updateGeneral.isPending || !timezone}>
              {updateGeneral.isPending ? t("save") : t("save")}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("profileSection")}</CardTitle>
          <CardDescription>{t("profileSubtitle")}</CardDescription>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={handleProfile((values) => updateProfile.mutate(values))}
            className="space-y-4"
            noValidate
          >
            {profileStatus ? (
              <p className="text-sm text-muted-foreground" data-testid="profile-status">
                {profileStatus}
              </p>
            ) : null}
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="profile-industry">{t("industryProfile")}</Label>
                <Input id="profile-industry" {...registerProfile("industry")} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="profile-model">{t("businessModel")}</Label>
                <Input id="profile-model" {...registerProfile("business_model")} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="profile-market">{t("targetMarket")}</Label>
                <Input id="profile-market" {...registerProfile("target_market")} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="profile-positioning">{t("brandPositioning")}</Label>
                <Input
                  id="profile-positioning"
                  {...registerProfile("brand_positioning")}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="profile-aov">{t("averageOrderValue")}</Label>
                <Input
                  id="profile-aov"
                  inputMode="decimal"
                  {...registerProfile("average_order_value")}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="profile-customer">{t("primaryCustomerType")}</Label>
                <Input
                  id="profile-customer"
                  {...registerProfile("primary_customer_type")}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="profile-voice">{t("brandVoice")}</Label>
                <Input id="profile-voice" {...registerProfile("brand_voice")} />
              </div>
            </div>
            <Button type="submit" disabled={updateProfile.isPending}>
              {updateProfile.isPending ? t("save") : t("save")}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-1">
              <CardTitle>{t("goalsSection")}</CardTitle>
              <CardDescription>{t("goalsSubtitle")}</CardDescription>
            </div>
            <Button size="sm" variant="outline" onClick={() => setGoalOpen((v) => !v)}>
              <Plus className="me-2 h-4 w-4" />
              {t("newGoal")}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {goalStatus ? (
            <p className="text-sm text-muted-foreground" data-testid="goal-status">
              {goalStatus}
            </p>
          ) : null}
          {goalError ? (
            <p className="text-sm text-destructive" role="alert">
              {goalError}
            </p>
          ) : null}

          {goalOpen ? (
            <form
              onSubmit={handleGoal((values) => saveGoal.mutate(values))}
              className="grid gap-4 rounded-md border p-4 sm:grid-cols-2"
              noValidate
            >
              <div className="space-y-2">
                <Label htmlFor="goal-revenue">{t("goalTargetRevenue")}</Label>
                <Input
                  id="goal-revenue"
                  inputMode="decimal"
                  {...registerGoal("target_revenue")}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="goal-profit">{t("goalTargetProfit")}</Label>
                <Input
                  id="goal-profit"
                  inputMode="decimal"
                  {...registerGoal("target_profit")}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="goal-budget">{t("goalAdBudget")}</Label>
                <Input
                  id="goal-budget"
                  inputMode="decimal"
                  {...registerGoal("ad_budget")}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="goal-cpa">{t("goalMaximumCpa")}</Label>
                <Input
                  id="goal-cpa"
                  inputMode="decimal"
                  {...registerGoal("maximum_cpa")}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="goal-roas">{t("goalTargetRoas")}</Label>
                <Input
                  id="goal-roas"
                  inputMode="decimal"
                  {...registerGoal("target_roas")}
                />
              </div>
              <div className="flex items-end">
                <Button type="submit" disabled={saveGoal.isPending}>
                  {saveGoal.isPending ? t("save") : t("newGoal")}
                </Button>
              </div>
            </form>
          ) : null}

          {goals.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("noGoals")}</p>
          ) : (
            <ul className="space-y-1 text-sm">
              {goals.map((goal) => (
                <li
                  key={goal.id}
                  className="flex items-center justify-between rounded-md border px-3 py-2"
                >
                  <span>
                    {formatMoney(goal.target_revenue, goal.currency, locale)}
                    <span className="text-muted-foreground">
                      {" "}
                      · {new Date(goal.period_start).toLocaleDateString(locale)} –{" "}
                      {new Date(goal.period_end).toLocaleDateString(locale)}
                    </span>
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={removeGoal.isPending}
                    onClick={() => removeGoal.mutate(goal.id)}
                    aria-label={t("goalDeleted")}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

/** Current calendar year goal period (2026 style, matching backend tests). */
function currentYearGoalPeriod(): { start: string; end: string } {
  const now = new Date();
  return {
    start: new Date(Date.UTC(now.getUTCFullYear(), 0, 1)).toISOString(),
    end: new Date(Date.UTC(now.getUTCFullYear(), 11, 31)).toISOString(),
  };
}