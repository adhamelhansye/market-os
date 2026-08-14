"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

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
import { useAuth, isApiError } from "@/context/auth-context";

const signupSchema = z.object({
  name: z.string().min(1, "nameRequired"),
  email: z.string().email("emailInvalid").min(1, "emailRequired"),
  password: z.string().min(8, "passwordMin"),
  organization_name: z.string().min(1, "organizationNameRequired"),
  organization_type: z.enum(["agency", "business"], {
    message: "organizationTypeRequired",
  }),
});

type SignupValues = z.infer<typeof signupSchema>;

export default function SignupPage() {
  const t = useTranslations("auth");
  const router = useRouter();
  const { signup } = useAuth();
  const [organizationType, setOrganizationType] = useState<"agency" | "business">("business");

  const {
    register,
    handleSubmit,
    setError,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<SignupValues>({
    resolver: zodResolver(signupSchema),
    defaultValues: {
      name: "",
      email: "",
      password: "",
      organization_name: "",
      organization_type: "business",
    },
  });

  const onSubmit = async (values: SignupValues) => {
    try {
      await signup(values);
      router.push("/dashboard");
    } catch (error) {
      if (isApiError(error) && error.code === "conflict") {
        setError("root", { message: t("emailAlreadyExists") });
      } else {
        setError("root", { message: t("genericError") });
      }
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("signupTitle")}</CardTitle>
        <CardDescription>{t("signupSubtitle")}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="name">{t("nameLabel")}</Label>
            <Input
              id="name"
              autoComplete="name"
              placeholder={t("namePlaceholder")}
              {...register("name")}
              aria-invalid={Boolean(errors.name)}
            />
            {errors.name ? <p className="text-sm text-destructive">{t(errors.name.message ?? "nameRequired")}</p> : null}
          </div>
          <div className="space-y-2">
            <Label htmlFor="email">{t("emailLabel")}</Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              {...register("email")}
              aria-invalid={Boolean(errors.email)}
            />
            {errors.email ? <p className="text-sm text-destructive">{t(errors.email.message ?? "emailRequired")}</p> : null}
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">{t("passwordLabel")}</Label>
            <Input
              id="password"
              type="password"
              autoComplete="new-password"
              {...register("password")}
              aria-invalid={Boolean(errors.password)}
            />
            {errors.password ? <p className="text-sm text-destructive">{t(errors.password.message ?? "passwordMin")}</p> : null}
          </div>
          <div className="space-y-2">
            <Label htmlFor="organization_name">{t("organizationNameLabel")}</Label>
            <Input
              id="organization_name"
              autoComplete="organization"
              {...register("organization_name")}
              aria-invalid={Boolean(errors.organization_name)}
            />
            {errors.organization_name ? (
              <p className="text-sm text-destructive">{t(errors.organization_name.message ?? "organizationNameRequired")}</p>
            ) : null}
          </div>
          <div className="space-y-2">
            <Label htmlFor="organization_type">{t("organizationTypeLabel")}</Label>
            <Select
              value={organizationType}
              onValueChange={(value) => {
                setOrganizationType(value as "agency" | "business");
                setValue("organization_type", value as "agency" | "business", {
                  shouldValidate: true,
                });
              }}
            >
              <SelectTrigger id="organization_type" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="business">{t("organizationTypeBusiness")}</SelectItem>
                <SelectItem value="agency">{t("organizationTypeAgency")}</SelectItem>
              </SelectContent>
            </Select>
            {errors.organization_type ? (
              <p className="text-sm text-destructive">{t(errors.organization_type.message ?? "organizationTypeRequired")}</p>
            ) : null}
          </div>
          {errors.root ? <p className="text-sm text-destructive">{errors.root.message}</p> : null}
          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {t("signupSubmit")}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}