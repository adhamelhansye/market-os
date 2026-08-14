"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/auth-context";

export default function LandingPage() {
  const t = useTranslations("common");
  const { status } = useAuth();
  const authenticated = status === "authenticated";

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-8 p-8 text-center">
      <div className="space-y-3">
        <h1 className="text-4xl font-bold tracking-tight">{t("appName")}</h1>
        <p className="text-lg text-muted-foreground">{t("tagline")}</p>
      </div>
      <div className="flex gap-3">
        {authenticated ? (
          <Button asChild>
            <Link href="/dashboard">{t("dashboard")}</Link>
          </Button>
        ) : (
          <>
            <Button asChild variant="outline">
              <Link href="/login">{t("signInLink")}</Link>
            </Button>
            <Button asChild>
              <Link href="/signup">{t("createAccountLink")}</Link>
            </Button>
          </>
        )}
      </div>
    </main>
  );
}