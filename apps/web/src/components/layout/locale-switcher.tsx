"use client";

import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";

import { getDirection, localePath, stripLocale, locales, type Locale } from "@/lib/locale";

export function LocaleSwitcher() {
  const t = useTranslations("common");
  const locale = useLocale() as Locale;
  const pathname = usePathname();
  const router = useRouter();

  const switchTo = (target: Locale) => {
    const path = stripLocale(pathname, locale);
    router.replace(localePath(path, target));
  };

  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="text-muted-foreground">{t("language")}:</span>
      <select
        value={locale}
        onChange={(event) => switchTo(event.target.value as Locale)}
        className="rounded-md border border-input bg-background px-2 py-1 text-sm"
        data-testid="locale-switcher"
      >
        {locales.map((option) => (
          <option key={option} value={option} dir={getDirection(option)}>
            {option === "en" ? "English" : "العربية"}
          </option>
        ))}
      </select>
    </label>
  );
}

export { Link as LocaleLink };