"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Archive } from "lucide-react";

import {
  BusinessPageHeader,
  useBusinessIdFromPath,
} from "@/components/business/business-page";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { isApiError } from "@/context/auth-context";
import { formatMoney } from "@/lib/money";
import { localePath } from "@/lib/locale";
import {
  archiveProduct,
  createCost,
  createPrice,
  fetchCosts,
  fetchInventory,
  fetchPrices,
  fetchProduct,
  setInventory,
  updateProduct,
  type ProductCostCreate,
  type ProductPriceCreate,
} from "@/features/products/api";

const productSchema = z.object({
  name: z.string().min(1, "nameRequired"),
  sku: z.string().optional(),
  description: z.string().optional(),
});

type ProductValues = z.infer<typeof productSchema>;

const periodSchema = z.object({
  price: z.string().optional(),
  cogs: z.string().optional(),
  packaging_cost: z.string().optional(),
  payment_fee_fixed: z.string().optional(),
  payment_fee_percent: z.string().optional(),
});

type PeriodValues = z.infer<typeof periodSchema>;

function todayIso(): string {
  return new Date().toISOString();
}

export default function ProductDetailPage() {
  const t = useTranslations("products");
  const locale = useLocale();
  const router = useRouter();
  const businessId = useBusinessIdFromPath();
  const params = useParams();
  const rawProductId = params.product_id;
  const productId = typeof rawProductId === "string" ? rawProductId : null;
  const queryClient = useQueryClient();

  const [rootError, setRootError] = useState<string | null>(null);
  const [priceError, setPriceError] = useState<string | null>(null);
  const [costError, setCostError] = useState<string | null>(null);
  const [inventoryError, setInventoryError] = useState<string | null>(null);
  const [inventoryInput, setInventoryInput] = useState("");

  const enabled = Boolean(businessId && productId);
  const businessKey = businessId ?? "";
  const productKey = productId ?? "";

  const { data: product } = useQuery({
    queryKey: ["product", businessKey, productKey],
    queryFn: () => fetchProduct(businessKey, productKey),
    enabled,
  });

  const { data: prices = [] } = useQuery({
    queryKey: ["prices", businessKey, productKey],
    queryFn: () => fetchPrices(businessKey, productKey),
    enabled,
  });

  const { data: costs = [] } = useQuery({
    queryKey: ["costs", businessKey, productKey],
    queryFn: () => fetchCosts(businessKey, productKey),
    enabled,
  });

  const { data: inventory } = useQuery({
    queryKey: ["inventory", businessKey, productKey],
    queryFn: () => fetchInventory(businessKey, productKey),
    enabled,
  });

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ProductValues>({
    resolver: zodResolver(productSchema),
    values: {
      name: product?.name ?? "",
      sku: product?.sku ?? "",
      description: product?.description ?? "",
    },
  });

  const { register: registerPeriod, handleSubmit: handlePeriodSubmit } =
    useForm<PeriodValues>({
      resolver: zodResolver(periodSchema),
      defaultValues: {
        price: "",
        cogs: "",
        packaging_cost: "",
        payment_fee_fixed: "",
        payment_fee_percent: "",
      },
    });

  const updateMutation = useMutation({
    mutationFn: (values: ProductValues) =>
      updateProduct(businessKey, productKey, {
        name: values.name,
        sku: values.sku || null,
        description: values.description || null,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["product", businessKey, productKey],
      });
      void queryClient.invalidateQueries({ queryKey: ["products", businessKey] });
    },
    onError: (error) => {
      if (isApiError(error) && error.code === "conflict") {
        setRootError(t("skuConflict"));
      } else setRootError(t("updateFailed"));
    },
  });

  const priceMutation = useMutation({
    mutationFn: (values: PeriodValues) => {
      const payload: ProductPriceCreate = {
        price: values.price || "0",
        currency: product?.currency ?? "USD",
        effective_from: todayIso(),
      };
      return createPrice(businessKey, productKey, payload);
    },
    onSuccess: () => {
      setPriceError(null);
      void queryClient.invalidateQueries({ queryKey: ["prices", businessKey, productKey] });
      void queryClient.invalidateQueries({ queryKey: ["products", businessKey] });
    },
    onError: (error) => {
      if (isApiError(error) && error.code === "conflict") {
        setPriceError(error.message);
      } else setPriceError(t("priceFailed"));
    },
  });

  const costMutation = useMutation({
    mutationFn: (values: PeriodValues) => {
      const payload: ProductCostCreate = {
        cogs: values.cogs || "0",
        packaging_cost: values.packaging_cost || "0",
        payment_fee_fixed: values.payment_fee_fixed || "0",
        payment_fee_percent: values.payment_fee_percent || "0",
        effective_from: todayIso(),
      };
      return createCost(businessKey, productKey, payload);
    },
    onSuccess: () => {
      setCostError(null);
      void queryClient.invalidateQueries({ queryKey: ["costs", businessKey, productKey] });
      void queryClient.invalidateQueries({ queryKey: ["products", businessKey] });
    },
    onError: (error) => {
      if (isApiError(error) && error.code === "conflict") {
        setCostError(error.message);
      } else setCostError(t("costFailed"));
    },
  });

  const archiveMutation = useMutation({
    mutationFn: () => archiveProduct(businessKey, productKey),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["products", businessKey] });
      void router.push(localePath(`/business/${businessKey}/products`, locale));
    },
    onError: () => setRootError(t("updateFailed")),
  });

  const inventoryMutation = useMutation({
    mutationFn: () => setInventory(businessKey, productKey, Number(inventoryInput)),
    onSuccess: () => {
      setInventoryError(null);
      setInventoryInput("");
      void queryClient.invalidateQueries({
        queryKey: ["inventory", businessKey, productKey],
      });
      void queryClient.invalidateQueries({ queryKey: ["products", businessKey] });
    },
    onError: () => setInventoryError(t("inventoryFailed")),
  });

  if (!enabled) return null;

  if (!product) {
    return (
      <div className="space-y-6">
        <BusinessPageHeader title={t("editProduct")} />
        <Card>
          <CardContent className="text-muted-foreground">{t("notFound")}</CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <BusinessPageHeader title={product.name} />
        <Button
          variant="destructive"
          size="sm"
          disabled={archiveMutation.isPending}
          onClick={() => archiveMutation.mutate()}
        >
          <Archive className="me-2 h-4 w-4" />
          {t("productDeleted")}
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t("productDetails")}</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={handleSubmit((values) => updateMutation.mutate(values))}
            className="space-y-4"
            noValidate
          >
            {rootError ? (
              <p className="text-sm text-destructive" role="alert">
                {rootError}
              </p>
            ) : null}
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="product-name">{t("name")}</Label>
                <Input id="product-name" {...register("name")} />
                {errors.name ? (
                  <p className="text-sm text-destructive">{t("nameRequired")}</p>
                ) : null}
              </div>
              <div className="space-y-2">
                <Label htmlFor="product-sku">{t("sku")}</Label>
                <Input id="product-sku" {...register("sku")} />
              </div>
              <div className="space-y-2 sm:col-span-2">
                <Label htmlFor="product-description">{t("description")}</Label>
                <Input id="product-description" {...register("description")} />
              </div>
            </div>
            <Button type="submit" disabled={updateMutation.isPending}>
              {updateMutation.isPending ? t("saving") : t("editProduct")}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("priceHistory")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <ul className="space-y-1 text-sm">
            {prices.map((price) => (
              <li
                key={price.id}
                className="flex items-center justify-between rounded-md border px-3 py-2"
              >
                <span>{formatMoney(price.price, price.currency, locale)}</span>
                <span className="text-muted-foreground">
                  {new Date(price.effective_from).toLocaleDateString(locale)}
                </span>
              </li>
            ))}
          </ul>
          {priceError ? (
            <p className="text-sm text-destructive" role="alert">
              {priceError}
            </p>
          ) : null}
          <form
            onSubmit={handlePeriodSubmit((values) => priceMutation.mutate(values))}
            className="flex flex-wrap items-end gap-3"
            noValidate
          >
            <div className="space-y-1">
              <Label htmlFor="new-price">{t("price")}</Label>
              <Input
                id="new-price"
                inputMode="decimal"
                {...registerPeriod("price")}
              />
            </div>
            <Button type="submit" disabled={priceMutation.isPending}>
              {priceMutation.isPending ? t("saving") : t("addPrice")}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("costHistory")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <ul className="space-y-1 text-sm">
            {costs.map((cost) => (
              <li
                key={cost.id}
                className="flex items-center justify-between rounded-md border px-3 py-2"
              >
                <span>{formatMoney(cost.cogs, product.currency, locale)}</span>
                <span className="text-muted-foreground">
                  {new Date(cost.effective_from).toLocaleDateString(locale)}
                </span>
              </li>
            ))}
          </ul>
          {costError ? (
            <p className="text-sm text-destructive" role="alert">
              {costError}
            </p>
          ) : null}
          <form
            onSubmit={handlePeriodSubmit((values) => costMutation.mutate(values))}
            className="grid gap-3 sm:grid-cols-4"
            noValidate
          >
            <div className="space-y-1">
              <Label htmlFor="new-cogs">{t("costOfGoods")}</Label>
              <Input id="new-cogs" inputMode="decimal" {...registerPeriod("cogs")} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="new-packaging">{t("packagingCost")}</Label>
              <Input
                id="new-packaging"
                inputMode="decimal"
                {...registerPeriod("packaging_cost")}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="new-fee-fixed">{t("paymentFeeFixed")}</Label>
              <Input
                id="new-fee-fixed"
                inputMode="decimal"
                {...registerPeriod("payment_fee_fixed")}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="new-fee-percent">{t("paymentFeePercent")}</Label>
              <Input
                id="new-fee-percent"
                inputMode="decimal"
                {...registerPeriod("payment_fee_percent")}
              />
            </div>
            <Button
              type="submit"
              disabled={costMutation.isPending}
              className="w-fit sm:col-span-4"
            >
              {costMutation.isPending ? t("saving") : t("addCost")}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("inventory")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm">
            {t("inventoryQuantity")}:{" "}
            <span className="font-medium" data-testid="inventory-quantity">
              {inventory?.quantity ?? 0}
            </span>
          </p>
          {inventoryError ? (
            <p className="text-sm text-destructive" role="alert">
              {inventoryError}
            </p>
          ) : null}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              inventoryMutation.mutate();
            }}
            className="flex flex-wrap items-end gap-3"
          >
            <div className="space-y-1">
              <Label htmlFor="inventory-set">{t("setInventory")}</Label>
              <Input
                id="inventory-set"
                type="number"
                min={0}
                value={inventoryInput}
                onChange={(e) => setInventoryInput(e.target.value)}
              />
            </div>
            <Button
              type="submit"
              disabled={inventoryMutation.isPending || inventoryInput === ""}
            >
              {inventoryMutation.isPending ? t("saving") : t("setInventory")}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}