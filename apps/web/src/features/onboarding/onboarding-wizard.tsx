"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError } from "@/lib/api-client";
import { isApiError } from "@/context/auth-context";
import { formatMoney } from "@/lib/money";
import { localePath } from "@/lib/locale";
import { CURRENCIES, COUNTRIES, TIMEZONES } from "@/lib/select-options";
import { cn } from "@/lib/utils";
import {
  updateBusiness,
  type Business,
  type BusinessUpdate,
} from "@/features/businesses/api";
import {
  fetchEconomicsProducts,
  type ProductEconomics,
} from "@/features/economics/api";
import {
  createGoal,
  fetchGoals,
} from "@/features/goals/api";
import {
  createCost,
  createPrice,
  createProduct,
  fetchProducts,
  type Product,
  type ProductDetail,
} from "@/features/products/api";
import {
  createShippingRule,
  fetchShippingRules,
  updateShippingRule,
  type ShippingRule,
} from "@/features/shipping/api";

const STAGES = [
  "business",
  "products",
  "economics",
  "shipping",
  "goals",
  "review",
] as const;

type Stage = (typeof STAGES)[number];

interface ProductDraft {
  name: string;
  price: string;
  cogs: string;
}

const emptyProductDraft = (): ProductDraft => ({
  name: "",
  price: "",
  cogs: "",
});

export function OnboardingWizard({
  businessId,
  business,
}: {
  businessId: string;
  business: Business;
}) {
  const t = useTranslations("onboarding");
  const econT = useTranslations("economics");
  const locale = useLocale();
  const router = useRouter();
  const queryClient = useQueryClient();

  const [stageIndex, setStageIndex] = useState(0);
  const stage: Stage = STAGES[stageIndex];

  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Business stage form.
  const [name, setName] = useState(business.name ?? "");
  const [currency, setCurrency] = useState(business.currency ?? "USD");
  const [timezone, setTimezone] = useState(business.timezone ?? "UTC");
  const [country, setCountry] = useState(business.country ?? "");
  const [industry, setIndustry] = useState(business.industry ?? "");
  const [websiteUrl, setWebsiteUrl] = useState(business.website_url ?? "");
  const [description, setDescription] = useState(business.description ?? "");

  // Products stage drafts.
  const [drafts, setDrafts] = useState<ProductDraft[]>([]);

  const { data: products = [] } = useQuery({
    queryKey: ["products", businessId],
    queryFn: () => fetchProducts(businessId),
    enabled: stageIndex >= 1,
  });

  const { data: economics = [] } = useQuery({
    queryKey: ["economics-products", businessId],
    queryFn: () => fetchEconomicsProducts(businessId),
    enabled: stageIndex >= 2,
  });

  const { data: shippingRules = [] } = useQuery({
    queryKey: ["shipping-rules", businessId],
    queryFn: () => fetchShippingRules(businessId),
    enabled: stageIndex >= 3,
  });

  const { data: goals = [] } = useQuery({
    queryKey: ["goals", businessId],
    queryFn: () => fetchGoals(businessId),
    enabled: stageIndex >= 4,
  });

  // Shipping form.
  const [shippingName, setShippingName] = useState("");
  const [shippingCountry, setShippingCountry] = useState("");
  const [shippingMethod, setShippingMethod] = useState("");
  const [shippingCost, setShippingCost] = useState("");
  const [shippingCustomerPrice, setShippingCustomerPrice] = useState("");

  // Goals form.
  const [goalTargetRevenue, setGoalTargetRevenue] = useState("");
  const [goalTargetProfit, setGoalTargetProfit] = useState("");
  const [goalAdBudget, setGoalAdBudget] = useState("");
  const [goalMaximumCpa, setGoalMaximumCpa] = useState("");
  const [goalTargetRoas, setGoalTargetRoas] = useState("");

  const flashError = (error: unknown) => {
    if (isApiError(error)) setErrorMessage(error.message);
    else setErrorMessage(t("saveFailed"));
  };

  const saveBusiness = useMutation({
    mutationFn: (payload: BusinessUpdate) => updateBusiness(businessId, payload),
    onSuccess: (updated) => {
      queryClient.setQueryData(["business", businessId], updated);
      setStatusMessage(t("saved"));
      setErrorMessage(null);
    },
    onError: flashError,
  });

  const createProducts = useMutation({
    mutationFn: async (list: ProductDraft[]) => {
      const created: Product[] = [];
      for (const draft of list) {
        const product = await createProduct(businessId, {
          name: draft.name,
          currency: business.currency ?? "USD",
          status: "active",
        });
        await createPrice(businessId, product.id, {
          price: draft.price,
          currency: business.currency ?? "USD",
          effective_from: new Date().toISOString(),
        });
        await createCost(businessId, product.id, {
          cogs: draft.cogs,
          packaging_cost: "0",
          payment_fee_fixed: "0",
          payment_fee_percent: "0",
          effective_from: new Date().toISOString(),
        });
        created.push(product);
      }
      return created;
    },
    onSuccess: () => {
      setDrafts([]);
      setStatusMessage(t("saved"));
      setErrorMessage(null);
      void queryClient.invalidateQueries({ queryKey: ["products", businessId] });
    },
    onError: flashError,
  });

  const saveShipping = useMutation({
    mutationFn: async () => {
      const defaultRule = shippingRules.find((rule) => rule.is_default);
      const payload = {
        name: shippingName,
        country: shippingCountry,
        method: shippingMethod,
        cost: shippingCost || "0",
        customer_price: shippingCustomerPrice || "0",
        is_default: true,
        active: true,
      };
      if (defaultRule) return updateShippingRule(businessId, defaultRule.id, payload);
      return createShippingRule(businessId, payload);
    },
    onSuccess: () => {
      setStatusMessage(t("saved"));
      setErrorMessage(null);
      void queryClient.invalidateQueries({ queryKey: ["shipping-rules", businessId] });
    },
    onError: flashError,
  });

  const saveGoal = useMutation({
    mutationFn: () =>
      createGoal(businessId, {
        period_start: new Date(Date.UTC(2026, 0, 1)).toISOString(),
        period_end: new Date(Date.UTC(2026, 11, 31)).toISOString(),
        target_revenue: goalTargetRevenue || "0",
        target_profit: goalTargetProfit || null,
        ad_budget: goalAdBudget || null,
        maximum_cpa: goalMaximumCpa || null,
        target_roas: goalTargetRoas || null,
        currency: business.currency ?? "USD",
      }),
    onSuccess: () => {
      setStatusMessage(t("saved"));
      setErrorMessage(null);
      void queryClient.invalidateQueries({ queryKey: ["goals", businessId] });
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === "conflict") {
        setErrorMessage(error.message);
      } else flashError(error);
    },
  });

  const completeOnboarding = useMutation({
    mutationFn: () =>
      updateBusiness(businessId, { onboarding_status: "completed" }),
    onSuccess: () => {
      void router.push(localePath(`/business/${businessId}/economics`, locale));
    },
    onError: flashError,
  });

  const canAdvance = () => {
    if (stage === "business") return name.trim().length > 0;
    return true;
  };

  const goNext = async () => {
    setErrorMessage(null);
    setStatusMessage(null);
    if (stage === "business") {
      try {
        await saveBusiness.mutateAsync({
          name,
          currency,
          timezone,
          country: country || null,
          industry: industry || null,
          website_url: websiteUrl || null,
          description: description || null,
          onboarding_status: "in_progress",
        });
        setStageIndex(1);
      } catch {
        // Mutation onError already surfaced the message.
      }
      return;
    }
    if (stage === "products") {
      const valid = drafts.filter((d) => d.name.trim() && d.price && d.cogs);
      try {
        if (valid.length > 0) await createProducts.mutateAsync(valid);
        setStageIndex(2);
      } catch {
        // Message already surfaced.
      }
      return;
    }
    if (stage === "goals") {
      if (goalTargetRevenue.trim() === "") {
        setStageIndex(5);
        return;
      }
      try {
        await saveGoal.mutateAsync();
        setStageIndex(5);
      } catch {
        // Message already surfaced.
      }
      return;
    }
    setStageIndex((i) => Math.min(i + 1, STAGES.length - 1));
  };

  const setDraft = (index: number, field: keyof ProductDraft, value: string) => {
    setDrafts((list) =>
      list.map((draft, i) => (i === index ? { ...draft, [field]: value } : draft))
    );
  };

  const defaultShippingRule = shippingRules.find((rule) => rule.is_default);
  const currentGoal = goals.find((goal) => goal.id);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>{t("title")}</CardTitle>
          <CardDescription>
            {t("step", { current: stageIndex + 1, total: STAGES.length })}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Stage tabs */}
          <div className="flex flex-wrap gap-2">
            {STAGES.map((s, i) => (
              <span
                key={s}
                className={cn(
                  "rounded-full px-3 py-1 text-xs",
                  i === stageIndex
                    ? "bg-primary text-primary-foreground"
                    : i < stageIndex
                      ? "bg-accent text-foreground"
                      : "bg-muted text-muted-foreground"
                )}
              >
                {t(`stages.${s}`)}
              </span>
            ))}
          </div>

          {errorMessage ? (
            <p className="text-sm text-destructive" role="alert">
              {errorMessage}
            </p>
          ) : null}
          {statusMessage ? (
            <p className="text-sm text-muted-foreground" data-testid="wizard-status">
              {statusMessage}
            </p>
          ) : null}

          {stage === "business" ? (
            <section className="space-y-4">
              <h2 className="text-lg font-semibold">{t("businessStepTitle")}</h2>
              <p className="text-sm text-muted-foreground">{t("businessStepSubtitle")}</p>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="wizard-name">{t("productName")}</Label>
                  <Input
                    id="wizard-name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="wizard-industry">{t("industry")}</Label>
                  <Input
                    id="wizard-industry"
                    value={industry}
                    onChange={(e) => setIndustry(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="wizard-currency">{t("currency")}</Label>
                  <Select value={currency} onValueChange={setCurrency}>
                    <SelectTrigger id="wizard-currency">
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
                  <Label htmlFor="wizard-timezone">{t("timezone")}</Label>
                  <Select value={timezone} onValueChange={setTimezone}>
                    <SelectTrigger id="wizard-timezone">
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
                <div className="space-y-2">
                  <Label htmlFor="wizard-country">{t("country")}</Label>
                  <Select
                    value={country || "__none__"}
                    onValueChange={(value) => setCountry(value === "__none__" ? "" : value)}
                  >
                    <SelectTrigger id="wizard-country">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {COUNTRIES.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="wizard-website">{t("websiteUrl")}</Label>
                  <Input
                    id="wizard-website"
                    type="url"
                    value={websiteUrl}
                    onChange={(e) => setWebsiteUrl(e.target.value)}
                  />
                </div>
                <div className="space-y-2 sm:col-span-2">
                  <Label htmlFor="wizard-description">{t("description")}</Label>
                  <Input
                    id="wizard-description"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                  />
                </div>
              </div>
            </section>
          ) : null}

          {stage === "products" ? (
            <section className="space-y-4">
              <h2 className="text-lg font-semibold">{t("productsStepTitle")}</h2>
              <p className="text-sm text-muted-foreground">{t("productsStepSubtitle")}</p>

              {products.length > 0 ? (
                <ul className="space-y-1 text-sm">
                  {products.map((product: ProductDetail) => (
                    <li
                      key={product.id}
                      className="flex items-center justify-between rounded-md border px-3 py-2"
                    >
                      <span>{product.name}</span>
                      <span className="text-muted-foreground">
                        {product.active_price
                          ? formatMoney(product.active_price, product.currency, locale)
                          : "-"}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : null}

              <div className="space-y-3">
                {drafts.map((draft, i) => (
                  <div key={i} className="grid gap-3 rounded-md border p-3 sm:grid-cols-3">
                    <div className="space-y-1">
                      <Label>{t("productName")}</Label>
                      <Input
                        value={draft.name}
                        onChange={(e) => setDraft(i, "name", e.target.value)}
                        placeholder="T-Shirt"
                      />
                    </div>
                    <div className="space-y-1">
                      <Label>{t("productPrice")}</Label>
                      <Input
                        inputMode="decimal"
                        value={draft.price}
                        onChange={(e) => setDraft(i, "price", e.target.value)}
                      />
                    </div>
                    <div className="space-y-1">
                      <Label>{t("productCogs")}</Label>
                      <Input
                        inputMode="decimal"
                        value={draft.cogs}
                        onChange={(e) => setDraft(i, "cogs", e.target.value)}
                      />
                    </div>
                    <div className="sm:col-span-3">
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() =>
                          setDrafts((list) => list.filter((_, idx) => idx !== i))
                        }
                      >
                        {t("removeProduct")}
                      </Button>
                    </div>
                  </div>
                ))}
              </div>

              <Button
                type="button"
                variant="outline"
                onClick={() => setDrafts((list) => [...list, emptyProductDraft()])}
              >
                {t("addProduct")}
              </Button>
            </section>
          ) : null}

          {stage === "economics" ? (
            <section className="space-y-4">
              <h2 className="text-lg font-semibold">{t("economicsStepTitle")}</h2>
              <p className="text-sm text-muted-foreground">{t("economicsStepSubtitle")}</p>
              {economics.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t("emptyStage")}</p>
              ) : (
                <ul className="space-y-1 text-sm">
                  {economics.map((row: ProductEconomics) => (
                    <li
                      key={row.product_id}
                      className="flex items-center justify-between rounded-md border px-3 py-2"
                    >
                      <span>{row.name}</span>
                      <span className="text-muted-foreground">
                        {row.break_even_cpa
                          ? `${econT("cpa")}: ${formatMoney(
                              row.break_even_cpa,
                              row.currency,
                              locale
                            )}`
                          : "-"}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          ) : null}

          {stage === "shipping" ? (
            <section className="space-y-4">
              <h2 className="text-lg font-semibold">{t("shippingStepTitle")}</h2>
              <p className="text-sm text-muted-foreground">{t("shippingStepSubtitle")}</p>
              {defaultShippingRule ? (
                <div className="rounded-md border px-3 py-2 text-sm">
                  {defaultShippingRule.name} · {defaultShippingRule.method} ·{" "}
                  {formatMoney(
                    defaultShippingRule.customer_price,
                    business.currency ?? "USD",
                    locale
                  )}
                </div>
              ) : null}
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="shipping-name">{t("shippingName")}</Label>
                  <Input
                    id="shipping-name"
                    value={shippingName}
                    onChange={(e) => setShippingName(e.target.value)}
                    placeholder="Standard"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="shipping-country">{t("shippingCountry")}</Label>
                  <Input
                    id="shipping-country"
                    value={shippingCountry}
                    onChange={(e) => setShippingCountry(e.target.value)}
                    placeholder="EG"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="shipping-method">{t("shippingMethod")}</Label>
                  <Input
                    id="shipping-method"
                    value={shippingMethod}
                    onChange={(e) => setShippingMethod(e.target.value)}
                    placeholder="flat"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="shipping-cost">{t("shippingCost")}</Label>
                  <Input
                    id="shipping-cost"
                    inputMode="decimal"
                    value={shippingCost}
                    onChange={(e) => setShippingCost(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="shipping-customer-price">
                    {t("shippingCustomerPrice")}
                  </Label>
                  <Input
                    id="shipping-customer-price"
                    inputMode="decimal"
                    value={shippingCustomerPrice}
                    onChange={(e) => setShippingCustomerPrice(e.target.value)}
                  />
                </div>
              </div>
            </section>
          ) : null}

          {stage === "goals" ? (
            <section className="space-y-4">
              <h2 className="text-lg font-semibold">{t("goalsStepTitle")}</h2>
              <p className="text-sm text-muted-foreground">{t("goalsStepSubtitle")}</p>
              {currentGoal ? (
                <div className="rounded-md border px-3 py-2 text-sm">
                  {t("goalTargetRevenue")}:{" "}
                  {formatMoney(
                    currentGoal.target_revenue,
                    currentGoal.currency,
                    locale
                  )}
                </div>
              ) : null}
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="goal-revenue">{t("goalTargetRevenue")}</Label>
                  <Input
                    id="goal-revenue"
                    inputMode="decimal"
                    value={goalTargetRevenue}
                    onChange={(e) => setGoalTargetRevenue(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="goal-profit">{t("goalTargetProfit")}</Label>
                  <Input
                    id="goal-profit"
                    inputMode="decimal"
                    value={goalTargetProfit}
                    onChange={(e) => setGoalTargetProfit(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="goal-budget">{t("goalAdBudget")}</Label>
                  <Input
                    id="goal-budget"
                    inputMode="decimal"
                    value={goalAdBudget}
                    onChange={(e) => setGoalAdBudget(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="goal-cpa">{t("goalMaximumCpa")}</Label>
                  <Input
                    id="goal-cpa"
                    inputMode="decimal"
                    value={goalMaximumCpa}
                    onChange={(e) => setGoalMaximumCpa(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="goal-roas">{t("goalTargetRoas")}</Label>
                  <Input
                    id="goal-roas"
                    inputMode="decimal"
                    value={goalTargetRoas}
                    onChange={(e) => setGoalTargetRoas(e.target.value)}
                  />
                </div>
              </div>
            </section>
          ) : null}

          {stage === "review" ? (
            <section className="space-y-4">
              <h2 className="text-lg font-semibold">{t("reviewStepTitle")}</h2>
              <p className="text-sm text-muted-foreground">{t("reviewStepSubtitle")}</p>
              <div className="space-y-3 text-sm">
                <div className="rounded-md border p-3">
                  <p className="font-medium">{t("reviewBusiness")}</p>
                  <p className="text-muted-foreground">{name}</p>
                </div>
                <div className="rounded-md border p-3">
                  <p className="font-medium">{t("reviewProducts")}</p>
                  <p className="text-muted-foreground">
                    {products.length > 0
                      ? products.map((p) => p.name).join(", ")
                      : t("emptyStage")}
                  </p>
                </div>
                <div className="rounded-md border p-3">
                  <p className="font-medium">{t("reviewShipping")}</p>
                  <p className="text-muted-foreground">
                    {defaultShippingRule
                      ? `${defaultShippingRule.name} · ${defaultShippingRule.method}`
                      : t("emptyStage")}
                  </p>
                </div>
                <div className="rounded-md border p-3">
                  <p className="font-medium">{t("reviewGoals")}</p>
                  <p className="text-muted-foreground">
                    {currentGoal
                      ? formatMoney(currentGoal.target_revenue, currentGoal.currency, locale)
                      : t("noGoalSet")}
                  </p>
                </div>
              </div>
            </section>
          ) : null}
        </CardContent>
        <div className="flex items-center justify-between border-t p-4">
          <Button
            type="button"
            variant="ghost"
            onClick={() => setStageIndex((i) => Math.max(i - 1, 0))}
            disabled={stageIndex === 0}
          >
            {t("back")}
          </Button>
          {stage === "goals" ? (
            <div className="flex gap-2">
              <Button
                type="button"
                variant="ghost"
                onClick={() => setStageIndex(5)}
              >
                {t("skipGoal")}
              </Button>
              <Button
                type="button"
                disabled={saveGoal.isPending}
                onClick={() => void goNext()}
              >
                {saveGoal.isPending ? t("saving") : t("next")}
              </Button>
            </div>
          ) : null}
          {stage === "review" ? (
            <Button
              type="button"
              disabled={completeOnboarding.isPending}
              onClick={() => completeOnboarding.mutate()}
            >
              <CheckCircle2 className="me-2 h-4 w-4" />
              {completeOnboarding.isPending ? t("saving") : t("complete")}
            </Button>
          ) : null}
          {stage !== "goals" && stage !== "review" ? (
            <Button type="button" disabled={!canAdvance()} onClick={() => void goNext()}>
              {t("next")}
            </Button>
          ) : null}
        </div>
      </Card>
    </div>
  );
}