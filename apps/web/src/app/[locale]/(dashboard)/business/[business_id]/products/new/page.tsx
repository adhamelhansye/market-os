"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

import {
  BusinessPageHeader,
  useBusinessIdFromPath,
} from "@/components/business/business-page";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { fetchBusiness } from "@/features/businesses/api";
import {
  createCost,
  createPrice,
  createProduct,
} from "@/features/products/api";
import { isApiError } from "@/context/auth-context";
import { localePath } from "@/lib/locale";

const productSchema = z.object({
  name: z.string().min(1, "nameRequired"),
  sku: z.string().optional(),
  description: z.string().optional(),
  status: z.enum(["active", "inactive"]),
  price: z.string().optional(),
  cogs: z.string().optional(),
});

type ProductValues = z.infer<typeof productSchema>;

export default function NewProductPage() {
  const t = useTranslations("products");
  const locale = useLocale();
  const router = useRouter();
  const businessId = useBusinessIdFromPath();
  const queryClient = useQueryClient();

  const { data: business } = useQuery({
    queryKey: ["business", businessId ?? ""],
    queryFn: () => fetchBusiness(businessId as string),
    enabled: Boolean(businessId),
  });

  const [rootError, setRootError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors },
  } = useForm<ProductValues>({
    resolver: zodResolver(productSchema),
    defaultValues: {
      name: "",
      sku: "",
      description: "",
      status: "active",
      price: "",
      cogs: "",
    },
  });

  const mutation = useMutation({
    mutationFn: async (values: ProductValues) => {
      if (!businessId) throw new Error("missing business");
      const currency = business?.currency ?? "USD";
      const product = await createProduct(businessId, {
        name: values.name,
        sku: values.sku || null,
        description: values.description || null,
        status: values.status,
        currency,
      });
      if (values.price) {
        await createPrice(businessId, product.id, {
          price: values.price,
          currency,
          effective_from: new Date().toISOString(),
        });
      }
      if (values.cogs) {
        await createCost(businessId, product.id, {
          cogs: values.cogs,
          packaging_cost: "0",
          payment_fee_fixed: "0",
          payment_fee_percent: "0",
          effective_from: new Date().toISOString(),
        });
      }
      return product;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["products", businessId] });
      void router.push(localePath(`/business/${businessId}/products`, locale));
    },
    onError: (error) => {
      if (isApiError(error) && error.code === "conflict") {
        setRootError(t("skuConflict"));
      } else {
        setRootError(t("createFailed"));
      }
    },
  });

  if (!businessId) return null;

  return (
    <div className="space-y-6">
      <BusinessPageHeader title={t("newProduct")} />
      <Card>
        <CardHeader>
          <CardTitle>{t("productDetails")}</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={handleSubmit((values) => mutation.mutate(values))}
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
                <Input
                  id="product-name"
                  {...register("name")}
                  aria-invalid={Boolean(errors.name)}
                />
                {errors.name ? (
                  <p className="text-sm text-destructive">{t("nameRequired")}</p>
                ) : null}
              </div>
              <div className="space-y-2">
                <Label htmlFor="product-sku">{t("sku")}</Label>
                <Input id="product-sku" {...register("sku")} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="product-currency">{t("currency")}</Label>
                <Input
                  id="product-currency"
                  value={business?.currency ?? "USD"}
                  readOnly
                  aria-readonly
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="product-status">{t("status")}</Label>
                <Select
                  defaultValue="active"
                  onValueChange={(value) =>
                    setValue("status", value as "active" | "inactive", {
                      shouldValidate: true,
                    })
                  }
                >
                  <SelectTrigger id="product-status">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="active">{t("active")}</SelectItem>
                    <SelectItem value="inactive">{t("inactive")}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="product-price">{t("price")}</Label>
                <Input
                  id="product-price"
                  inputMode="decimal"
                  {...register("price")}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="product-cogs">{t("costOfGoods")}</Label>
                <Input
                  id="product-cogs"
                  inputMode="decimal"
                  {...register("cogs")}
                />
              </div>
              <div className="space-y-2 sm:col-span-2">
                <Label htmlFor="product-description">{t("description")}</Label>
                <Input id="product-description" {...register("description")} />
              </div>
            </div>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? t("saving") : t("newProduct")}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}