import type { AbstractIntlMessages } from "next-intl";

import commonEn from "../../messages/en/common.json";
import authEn from "../../messages/en/auth.json";
import dashboardEn from "../../messages/en/dashboard.json";
import commonAr from "../../messages/ar/common.json";
import authAr from "../../messages/ar/auth.json";
import dashboardAr from "../../messages/ar/dashboard.json";

export const messagesByLocale: Record<string, AbstractIntlMessages> = {
  en: {
    common: commonEn,
    auth: authEn,
    dashboard: dashboardEn,
  },
  ar: {
    common: commonAr,
    auth: authAr,
    dashboard: dashboardAr,
  },
};