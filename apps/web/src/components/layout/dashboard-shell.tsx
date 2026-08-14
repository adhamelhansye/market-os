"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { LayoutDashboard, LogOut, Settings } from "lucide-react";

import { Button } from "@/components/ui/button";
import { OrganizationSwitcher } from "@/components/layout/organization-switcher";
import { BusinessSwitcher } from "@/components/layout/business-switcher";
import { LocaleSwitcher } from "@/components/layout/locale-switcher";
import { useAuth } from "@/context/auth-context";
import { useBusiness } from "@/context/business-context";
import { cn } from "@/lib/utils";

export function DashboardShell({ children }: { children: React.ReactNode }) {
  const t = useTranslations("common");
  const locale = useLocale();
  const pathname = usePathname();
  const router = useRouter();
  const { status, user, memberships, logout } = useAuth();
  const { activeOrganizationId, clear } = useBusiness();

  useEffect(() => {
    if (status === "anonymous") router.replace(`/${locale}/login`);
  }, [status, locale, router]);

  if (status !== "authenticated") {
    return (
      <main className="flex min-h-screen items-center justify-center text-muted-foreground">
        {t("empty")}
      </main>
    );
  }

  const activeMembership = memberships.find((m) => m.organization.id === activeOrganizationId);
  const navItems = [
    { href: "/dashboard", label: t("dashboard"), icon: LayoutDashboard },
    { href: "/settings", label: t("settings"), icon: Settings },
  ];

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b">
        <div className="flex h-14 items-center gap-4 px-4">
          <Link href="/dashboard" className="font-semibold">
            {t("appName")}
          </Link>
          <nav className="flex items-center gap-1 text-sm">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "rounded-md px-3 py-1.5 hover:bg-accent",
                  pathname === item.href && "bg-accent"
                )}
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="ms-auto flex items-center gap-4">
            <OrganizationSwitcher />
            <BusinessSwitcher />
            <LocaleSwitcher />
            {user ? (
              <div className="flex items-center gap-2 text-sm">
                <span className="max-w-32 truncate text-muted-foreground">
                  {user.name} · {activeMembership?.role_name ?? ""}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    void logout();
                    clear();
                    void router.push(`/${locale}/login`);
                  }}
                >
                  <LogOut className="h-4 w-4" />
                  <span className="sr-only">{t("logout")}</span>
                </Button>
              </div>
            ) : null}
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 p-6">{children}</main>
    </div>
  );
}