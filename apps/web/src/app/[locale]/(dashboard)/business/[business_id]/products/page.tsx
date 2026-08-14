"use client";

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";

import {
  BusinessPageHeader,
  useBusinessIdFromPath,
} from "@/components/business/business-page";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { fetchProducts } from "@/features/products/api";
import { formatMoney, formatRatio } from "@/lib/money";
import { localePath } from "@/lib/locale";

export default function ProductsPage() {
  const t = useTranslations("products");
  const locale = useLocale();
  const businessId = useBusinessIdFromPath();

  const { data: products = [], isLoading } = useQuery({
    queryKey: ["products", businessId ?? ""],
    queryFn: () => fetchProducts(businessId as string),
    enabled: Boolean(businessId),
  });

  if (!businessId) return null;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <BusinessPageHeader title={t("title")} />
        <Button asChild>
          <Link href={localePath(`/business/${businessId}/products/new`, locale)}>
            <Plus className="me-2 h-4 w-4" />
            {t("newProduct")}
          </Link>
        </Button>
      </div>

      {!isLoading && products.length === 0 ? (
        <Card className="border-dashed">
          <CardHeader>
            <CardTitle>{t("emptyStateTitle")}</CardTitle>
            <CardDescription>{t("emptyStateBody")}</CardDescription>
          </CardHeader>
          <CardContent />
        </Card>
      ) : (
        <Card>
          <CardContent className="p-0">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-start text-muted-foreground">
                  <th className="px-4 py-3 text-start font-medium">{t("name")}</th>
                  <th className="px-4 py-3 text-start font-medium">{t("sku")}</th>
                  <th className="px-4 py-3 text-start font-medium">{t("price")}</th>
                  <th className="px-4 py-3 text-start font-medium">{t("inventoryQuantity")}</th>
                  <th className="px-4 py-3 text-start font-medium">{t("contributionProfit")}</th>
                  <th className="px-4 py-3 text-start font-medium">{t("contributionMargin")}</th>
                </tr>
              </thead>
              <tbody>
                {products.map((product) => (
                  <tr key={product.id} className="border-b last:border-b-0">
                    <td className="px-4 py-3">
                      <Link
                        href={localePath(
                          `/business/${businessId}/products/${product.id}`,
                          locale
                        )}
                        className="font-medium hover:underline"
                      >
                        {product.name}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{product.sku ?? "-"}</td>
                    <td className="px-4 py-3">
                      {product.active_price
                        ? formatMoney(product.active_price, product.currency, locale)
                        : "-"}
                    </td>
                    <td className="px-4 py-3">{product.inventory_quantity}</td>
                    <td className="px-4 py-3">
                      {product.contribution_profit
                        ? formatMoney(product.contribution_profit, product.currency, locale)
                        : "-"}
                    </td>
                    <td className="px-4 py-3">
                      {product.contribution_margin
                        ? formatRatio(product.contribution_margin, locale)
                        : "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}