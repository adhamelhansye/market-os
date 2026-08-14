import { act, render, screen } from "@testing-library/react";
import { createRoot } from "react-dom/client";
import { describe, expect, it } from "vitest";

import { LocaleLayout } from "@/components/layout/locale-layout";
import { getDirection, isSupportedLocale, localePath, stripLocale } from "@/lib/locale";

describe("locale helpers", () => {
  it("maps en to LTR and ar to RTL", () => {
    expect(getDirection("en")).toBe("ltr");
    expect(getDirection("ar")).toBe("rtl");
    expect(getDirection("fr")).toBe("ltr");
  });

  it("recognizes supported locales", () => {
    expect(isSupportedLocale("en")).toBe(true);
    expect(isSupportedLocale("ar")).toBe(true);
    expect(isSupportedLocale("fr")).toBe(false);
    expect(isSupportedLocale(undefined)).toBe(false);
  });

  it("builds locale-prefixed paths", () => {
    expect(localePath("/dashboard", "en")).toBe("/en/dashboard");
    expect(localePath("/login", "ar")).toBe("/ar/login");
    expect(localePath("/", "ar")).toBe("/ar/");
  });

  it("strips locale prefixes", () => {
    expect(stripLocale("/ar/dashboard", "ar")).toBe("/dashboard");
    expect(stripLocale("/en", "en")).toBe("/");
    expect(stripLocale("/en/login", "en")).toBe("/login");
  });
});

describe("LocaleLayout (locale routing and direction)", () => {
  async function renderRootLayout(locale: "en" | "ar", dir: "ltr" | "rtl") {
    const root = createRoot(document.documentElement);
    await act(async () => {
      root.render(
        <LocaleLayout locale={locale} dir={dir} fontClass="">
          <p data-testid="child">child-content</p>
        </LocaleLayout>
      );
    });
    return root;
  }

  it("renders html lang=en dir=ltr and renders children", async () => {
    const root = await renderRootLayout("en", "ltr");
    const html = document.documentElement;
    expect(html.getAttribute("lang")).toBe("en");
    expect(html.getAttribute("dir")).toBe("ltr");
    expect(screen.getByTestId("child")).toHaveTextContent("child-content");
    await act(async () => root.unmount());
  });

  it("renders html lang=ar dir=rtl for Arabic (RTL rendering)", async () => {
    const root = await renderRootLayout("ar", "rtl");
    const html = document.documentElement;
    expect(html.getAttribute("lang")).toBe("ar");
    expect(html.getAttribute("dir")).toBe("rtl");
    await act(async () => root.unmount());
  });
});