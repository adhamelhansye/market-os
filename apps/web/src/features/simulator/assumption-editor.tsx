"use client";

import { useTranslations } from "next-intl";
import { Label } from "@radix-ui/react-label";

import { Input } from "@/components/ui/input";

import type { AssumptionRead } from "./api";
import { OVERRIDE_KEYS, type OverrideKey } from "./api";

const SOURCE_KEYS: Record<string, string> = {
  user_input: "sourceUserInput",
  campaign_history: "sourceCampaignHistory",
  ad_account_history: "sourceAdAccountHistory",
  business_history: "sourceBusinessHistory",
  economics: "sourceEconomics",
  goal: "sourceGoal",
  system_default: "sourceSystemDefault",
};

interface AssumptionEditorProps {
  assumptions?: AssumptionRead[];
  overrides: Partial<Record<OverrideKey, string>>;
  onOverrideChange: (key: OverrideKey, value: string) => void;
}

function sourceLabel(t: (key: string) => string, source: string): string {
  const key = SOURCE_KEYS[source];
  return key ? t(key) : t("sourceUnknown");
}

export function AssumptionEditor({
  assumptions,
  overrides,
  onOverrideChange,
}: AssumptionEditorProps) {
  const t = useTranslations("simulator");
  const rows = assumptions ?? [];

  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between gap-2">
        <h4 className="text-sm font-medium text-muted-foreground">{t("assumptions")}</h4>
        <p className="text-xs text-muted-foreground">{t("overrideHint")}</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left rtl:text-right text-muted-foreground">
              <th className="py-2 pe-2 font-normal">{t("assumptionName")}</th>
              <th className="py-2 pe-2 font-normal text-end">{t("assumptionValue")}</th>
              <th className="py-2 pe-2 font-normal text-end">{t("historicalValue")}</th>
              <th className="py-2 pe-2 font-normal">{t("source")}</th>
              <th className="py-2 pe-2 font-normal">{t("confidence")}</th>
              <th className="py-2 font-normal">{t("override")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-4 text-muted-foreground">
                  {t("unavailable")}
                </td>
              </tr>
            ) : (
              rows.map((assumption) => {
                const key = assumption.name as OverrideKey;
                const editable = OVERRIDE_KEYS.includes(key);
                const overrideValue = overrides[key];
                return (
                  <tr key={`${assumption.name}-${assumption.source}`} className="border-b">
                    <td className="py-2 pe-2 font-medium">{assumption.name}</td>
                    <td className="py-2 pe-2 text-end tabular-nums">
                      {assumption.unavailable_reason
                        ? t("unavailableReason")
                        : assumption.value ?? "-"}
                    </td>
                    <td className="py-2 pe-2 text-end tabular-nums">
                      {assumption.historical_value ?? "-"}
                    </td>
                    <td className="py-2 pe-2 text-xs text-muted-foreground">
                      {sourceLabel(t, assumption.source)}
                      {assumption.source_entity ? ` · ${assumption.source_entity}` : ""}
                    </td>
                    <td className="py-2 pe-2">
                      <span
                        data-testid={`confidence-${assumption.name}`}
                        className="text-xs text-muted-foreground"
                      >
                        {t(assumption.confidence)}
                      </span>
                    </td>
                    <td className="py-2">
                      {editable ? (
                        <div className="flex items-center gap-2">
                          <Label htmlFor={`override-${assumption.name}`} className="sr-only">
                            {assumption.name}
                          </Label>
                          <Input
                            id={`override-${assumption.name}`}
                            data-testid={`override-${assumption.name}`}
                            className="h-8 w-28 text-end"
                            type="text"
                            inputMode="decimal"
                            placeholder={assumption.value ?? ""}
                            value={overrideValue ?? ""}
                            onChange={(event) => onOverrideChange(key, event.target.value)}
                          />
                        </div>
                      ) : (
                        <span
                          data-testid={`override-not-supported-${assumption.name}`}
                          className="text-xs text-muted-foreground"
                        >
                          -
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}