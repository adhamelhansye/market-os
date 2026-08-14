import { NextIntlClientProvider } from "next-intl";

import { Locale, defaultLocale, isSupportedLocale } from "@/lib/locale";
import { messagesByLocale } from "@/i18n/messages";
import { Providers } from "@/components/providers";

/**
 * Renders <html lang dir> plus the i18n and app providers.
 * Kept as a plain component so tests can assert lang/dir and rendering.
 */
export function LocaleLayout({
  locale,
  dir,
  fontClass,
  children,
}: {
  locale: string;
  dir: "ltr" | "rtl";
  fontClass: string;
  children: React.ReactNode;
}) {
  const normalized: Locale = isSupportedLocale(locale) ? locale : defaultLocale;
  return (
    <html lang={normalized} dir={dir} className={fontClass}>
      <body>
        <NextIntlClientProvider locale={normalized} messages={messagesByLocale[normalized]}>
          <Providers>{children}</Providers>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}