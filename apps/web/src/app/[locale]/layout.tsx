import { Inter, Noto_Sans_Arabic } from "next/font/google";
import { getLocale } from "next-intl/server";

import { getDirection } from "@/lib/locale";
import { LocaleLayout } from "@/components/layout/locale-layout";

const latinFont = Inter({ subsets: ["latin"], variable: "--font-latin" });
const arabicFont = Noto_Sans_Arabic({
  subsets: ["arabic"],
  variable: "--font-arabic",
});

export function generateStaticParams() {
  return [{ locale: "en" }, { locale: "ar" }];
}

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const locale = await getLocale();
  const dir = getDirection(locale);
  const fontClass = locale === "ar" ? arabicFont.variable : latinFont.variable;

  return (
    <LocaleLayout locale={locale} dir={dir} fontClass={fontClass}>
      {children}
    </LocaleLayout>
  );
}