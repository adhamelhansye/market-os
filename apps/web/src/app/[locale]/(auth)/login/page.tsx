"use client";

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
import { useAuth, isApiError } from "@/context/auth-context";

const loginSchema = z.object({
  email: z.string().email("emailInvalid").min(1, "emailRequired"),
  password: z.string().min(1, "passwordRequired"),
});

type LoginValues = z.infer<typeof loginSchema>;

export default function LoginPage() {
  const t = useTranslations("auth");
  const router = useRouter();
  const { login } = useAuth();

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  const onSubmit = async (values: LoginValues) => {
    try {
      await login(values);
      router.push("/dashboard");
    } catch (error) {
      if (isApiError(error) && error.code === "invalid_credentials") {
        setError("root", { message: t("invalidCredentials") });
      } else {
        setError("root", { message: t("genericError") });
      }
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("loginTitle")}</CardTitle>
        <CardDescription>{t("loginSubtitle")}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
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
              autoComplete="current-password"
              {...register("password")}
              aria-invalid={Boolean(errors.password)}
            />
            {errors.password ? <p className="text-sm text-destructive">{t(errors.password.message ?? "passwordRequired")}</p> : null}
          </div>
          {errors.root ? <p className="text-sm text-destructive">{errors.root.message}</p> : null}
          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {t("loginSubmit")}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}