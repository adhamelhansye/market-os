"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

import { useAuth } from "@/context/auth-context";

/**
 * (auth) group layout: kicks authenticated users to the dashboard.
 */
export default function AuthLayout({ children }: { children: React.ReactNode }) {
  const t = useTranslations("common");
  const router = useRouter();
  const { status } = useAuth();

  useEffect(() => {
    if (status === "authenticated") router.replace("/dashboard");
  }, [status, router]);

  if (status === "loading") {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground">{t("empty")}</p>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-6">
      <div className="w-full max-w-sm space-y-6">{children}</div>
    </main>
  );
}