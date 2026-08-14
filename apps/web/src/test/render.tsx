import { NextIntlClientProvider } from "next-intl";
import { render, screen, type RenderResult } from "@testing-library/react";

import { messagesByLocale } from "@/i18n/messages";

export function renderWithI18n(ui: React.ReactElement, locale: "en" | "ar"): RenderResult {
  return render(
    <NextIntlClientProvider locale={locale} messages={messagesByLocale[locale]}>
      {ui}
    </NextIntlClientProvider>
  );
}

export { screen };