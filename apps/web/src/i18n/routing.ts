import { defineRouting } from "next-intl/routing";

import { defaultLocale, locales } from "@/lib/locale";

export const routing = defineRouting({
  locales,
  defaultLocale,
  localePrefix: "always",
});