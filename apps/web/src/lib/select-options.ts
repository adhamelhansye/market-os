/* Static option lists for business settings and onboarding selects. */

export const CURRENCIES = [
  { value: "USD", label: "US Dollar (USD)" },
  { value: "EGP", label: "Egyptian Pound (EGP)" },
  { value: "SAR", label: "Saudi Riyal (SAR)" },
  { value: "AED", label: "UAE Dirham (AED)" },
  { value: "EUR", label: "Euro (EUR)" },
  { value: "GBP", label: "British Pound (GBP)" },
] as const;

export const TIMEZONES = [
  "UTC",
  "Africa/Cairo",
  "Africa/Casablanca",
  "Africa/Lagos",
  "Asia/Riyadh",
  "Asia/Dubai",
  "Asia/Amman",
  "Europe/London",
  "Europe/Paris",
  "America/New_York",
] as const;

export const COUNTRIES = [
  { value: "US", label: "United States" },
  { value: "EG", label: "Egypt" },
  { value: "SA", label: "Saudi Arabia" },
  { value: "AE", label: "United Arab Emirates" },
  { value: "JO", label: "Jordan" },
  { value: "GB", label: "United Kingdom" },
  { value: "FR", label: "France" },
  { value: "DE", label: "Germany" },
] as const;