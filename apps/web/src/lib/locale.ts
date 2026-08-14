export const locales = ["en", "ar"] as const;
export type Locale = (typeof locales)[number];

export const defaultLocale: Locale = "en";

export const localeNames: Record<Locale, string> = {
  en: "English",
  ar: "العربية",
};

const DIRECTIONS: Record<Locale, "ltr" | "rtl"> = {
  en: "ltr",
  ar: "rtl",
};

export function getDirection(locale: string): "ltr" | "rtl" {
  return DIRECTIONS[locale as Locale] ?? "ltr";
}

export function isSupportedLocale(value: string | undefined): value is Locale {
  return value === "en" || value === "ar";
}

export function localePath(path: string, locale: Locale): string {
  if (!path.startsWith("/")) {
    throw new Error("localePath expects a path starting with '/'");
  }
  return `/${locale}${path}`;
}

export function stripLocale(path: string, locale: Locale): string {
  const prefix = `/${locale}`;
  return path === prefix ? "/" : path.replace(prefix, "") || "/";
}