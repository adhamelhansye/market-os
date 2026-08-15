import type { AbstractIntlMessages } from "next-intl";

import commonEn from "../../messages/en/common.json";
import authEn from "../../messages/en/auth.json";
import dashboardEn from "../../messages/en/dashboard.json";
import onboardingEn from "../../messages/en/onboarding.json";
import productsEn from "../../messages/en/products.json";
import economicsEn from "../../messages/en/economics.json";
import settingsEn from "../../messages/en/settings.json";
import integrationsEn from "../../messages/en/integrations.json";
import metricsEn from "../../messages/en/metrics.json";
import diagnosticsEn from "../../messages/en/diagnostics.json";
import commonAr from "../../messages/ar/common.json";
import authAr from "../../messages/ar/auth.json";
import dashboardAr from "../../messages/ar/dashboard.json";
import onboardingAr from "../../messages/ar/onboarding.json";
import productsAr from "../../messages/ar/products.json";
import economicsAr from "../../messages/ar/economics.json";
import settingsAr from "../../messages/ar/settings.json";
import integrationsAr from "../../messages/ar/integrations.json";
import metricsAr from "../../messages/ar/metrics.json";
import diagnosticsAr from "../../messages/ar/diagnostics.json";

export const messagesByLocale: Record<string, AbstractIntlMessages> = {
  en: {
    common: commonEn,
    auth: authEn,
    dashboard: dashboardEn,
    onboarding: onboardingEn,
    products: productsEn,
    economics: economicsEn,
    settings: settingsEn,
    integrations: integrationsEn,
    metrics: metricsEn,
    diagnostics: diagnosticsEn,
  },
  ar: {
    common: commonAr,
    auth: authAr,
    dashboard: dashboardAr,
    onboarding: onboardingAr,
    products: productsAr,
    economics: economicsAr,
    settings: settingsAr,
    integrations: integrationsAr,
    metrics: metricsAr,
    diagnostics: diagnosticsAr,
  },
};
