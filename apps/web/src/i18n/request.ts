import { getRequestConfig } from "next-intl/server";

import { isSupportedLocale } from "@/lib/locale";
import { messagesByLocale } from "@/i18n/messages";

export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale = isSupportedLocale(requested) ? requested : "en";

  return {
    locale,
    messages: messagesByLocale[locale],
    timeZone: "UTC",
    formats: {
      dateTime: {
        short: { day: "numeric", month: "short", year: "numeric" },
      },
    },
  };
});