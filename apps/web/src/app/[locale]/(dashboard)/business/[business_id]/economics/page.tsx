"use client";

import type { ReactNode } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";

import {
  BusinessPageHeader,
  useBusinessIdFromPath,
} from "@/components/business/business-page";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  fetchEconomicsProducts,
  fetchEconomicsSummary,
  type ProductEconomics,
} from "@/features/economics/api";
import { formatMoney, formatRatio } from "@/lib/money";

export default function EconomicsPage() {
  const t = useTranslations("economics");
  const locale = useLocale();
  const businessId = useBusinessIdFromPath();

  const { data: summary, isLoading } = useQuery({
    queryKey: ["economics-summary", businessId ?? ""],
    queryFn: () => fetchEconomicsSummary(businessId as string),
    enabled: Boolean(businessId),
  });

  const { data: products = [] } = useQuery({
    queryKey: ["economics-products", businessId ?? ""],
    queryFn: () => fetchEconomicsProducts(businessId as string),
    enabled: Boolean(businessId),
  });

  if (!businessId) return null;

  const currency: string = summary?.currency ?? "USD";

  const kpi = (label: string, value?: ReactNode) => (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm text-muted-foreground">{label}</CardTitle>
      </CardHeader>
      <CardContent className="text-lg font-medium">{value ?? "-"}</CardContent>
    </Card>
  );

  const cpaRange = summary?.break_even_cpa_range;
  const cpaRangeLabel =
    cpaRange && cpaRange.length === 2
      ? `${formatMoney(cpaRange[0], currency, locale)} – ${formatMoney(
          cpaRange[1],
          currency,
          locale
        )}`
      : null;

  return (
    <div className="space-y-6">
      <BusinessPageHeader
        title={t("title")}
        subtitle={t("subtitle", { name: summary?.business_name ?? "" })}
      />

      {!isLoading && !summary ? (
        <Card className="border-dashed">
          <CardHeader>
            <CardTitle>{t("emptyStateTitle")}</CardTitle>
            <CardDescription>{t("emptyStateBody")}</CardDescription>
          </CardHeader>
          <CardContent />
        </Card>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {kpi(
              t("activeProducts"),
              summary ? `${summary.active_products} (${t("pricedProducts")}: ${summary.priced_products})` : undefined
            )}
            {kpi(
              t("averageProductPrice"),
              summary
                ? formatMoney(summary.average_product_price, currency, locale)
                : undefined
            )}
            {kpi(
              t("averageContributionProfit"),
              summary
                ? formatMoney(summary.average_contribution_profit, currency, locale)
                : undefined
            )}
            {kpi(
              t("averageContributionMargin"),
              summary
                ? formatRatio(summary.average_contribution_margin, locale)
                : undefined
            )}
            {kpi(t("breakEvenCpaRange"), cpaRangeLabel)}
            {kpi(
              t("breakEvenRoas"),
              summary ? formatRatio(summary.break_even_roas, locale) : undefined
            )}
            {kpi(
              t("inventoryValue"),
              summary ? formatMoney(summary.inventory_value, currency, locale) : undefined
            )}
            <Card>
              <CardHeader>
                <CardTitle className="text-sm text-muted-foreground">
                  {t("currentGoal")}
                </CardTitle>
              </CardHeader>
              <CardContent className="text-lg font-medium">
                {summary?.current_goal
                  ? formatMoney(
                      summary.current_goal.target_revenue,
                      summary.current_goal.currency,
                      locale
                    )
                  : t("noGoal")}
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>{t("productsTable")}</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {products.length === 0 ? (
                <div className="p-4 text-sm text-muted-foreground">
                  {t("noPricedProducts")}
                </div>
              ) : (
                <ProductsTable
                  products={products}
                  currency={currency}
                  locale={locale}
                  translations={t}
                />
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function ProductsTable({
  products,
  currency,
  locale,
  translations: t,
}: {
  products: ProductEconomics[];
  currency: string;
  locale: string;
  translations: (key: string) => string;
}) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b text-muted-foreground">
          <th className="px-4 py-3 text-start font-medium">{t("productName")}</th>
          <th className="px-4 py-3 text-start font-medium">{t("price")}</th>
          <th className="px-4 py-3 text-start font-medium">{t("cost")}</th>
          <th className="px-4 py-3 text-start font-medium">{t("profit")}</th>
          <th className="px-4 py-3 text-start font-medium">{t("margin")}</th>
          <th className="px-4 py-3 text-start font-medium">{t("cpa")}</th>
          <th className="px-4 py-3 text-start font-medium">{t("roas")}</th>
          <th className="px-4 py-3 text-start font-medium">{t("inventory")}</th>
        </tr>
      </thead>
      <tbody>
        {products.map((product) => (
          <tr key={product.product_id} className="border-b last:border-b-0">
            <td className="px-4 py-3 font-medium">{product.name}</td>
            <td className="px-4 py-3">
              {product.product_revenue
                ? formatMoney(product.product_revenue, product.currency ?? currency, locale)
                : "-"}
            </td>
            <td className="px-4 py-3">
              {formatMoney(product.product_cost, product.currency ?? currency, locale)}
            </td>
            <td className="px-4 py-3">
              {product.contribution_profit
                ? formatMoney(
                    product.contribution_profit,
                    product.currency ?? currency,
                    locale
                  )
                : "-"}
            </td>
            <td className="px-4 py-3">
              {product.contribution_margin
                ? formatRatio(product.contribution_margin, locale)
                : "-"}
            </td>
            <td className="px-4 py-3">
              {product.break_even_cpa
                ? formatMoney(
                    product.break_even_cpa,
                    product.currency ?? currency,
                    locale
                  )
                : "-"}
            </td>
            <td className="px-4 py-3">
              {product.break_even_roas ? formatRatio(product.break_even_roas, locale) : "-"}
            </td>
            <td className="px-4 py-3">{product.inventory_quantity}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}