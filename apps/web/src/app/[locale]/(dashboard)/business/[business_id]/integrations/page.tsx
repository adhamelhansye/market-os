"use client";

import { useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link as LinkIcon, RefreshCw, Unplug } from "lucide-react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

import {
  BusinessPageHeader,
  useBusinessIdFromPath,
} from "@/components/business/business-page";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { isApiError } from "@/context/auth-context";
import {
  connectShopify,
  disconnectConnection,
  fetchConnections,
  syncConnection,
  type Connection,
} from "@/features/integrations/api";

const connectSchema = z.object({
  shopDomain: z.string().min(1),
});

export default function IntegrationsPage() {
  const t = useTranslations("integrations");
  const businessId = useBusinessIdFromPath();
  const queryClient = useQueryClient();

  const { data: connections = [] } = useQuery({
    queryKey: ["integrations", businessId ?? ""],
    queryFn: () => fetchConnections(businessId as string),
    enabled: Boolean(businessId),
    refetchInterval: (query) =>
      query.state.data?.some((c) => c.latest_sync?.status === "running") ? 3000 : false,
  });

  const [connectError, setConnectError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [banner, setBanner] = useState<"success" | "error" | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("connected") === "1") {
      setBanner("success");
      window.history.replaceState({}, "", window.location.pathname);
    } else if (params.get("error") === "connect_failed") {
      setBanner("error");
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, []);

  const connect = useMutation({
    mutationFn: (domain: string) => connectShopify(businessId as string, domain),
    onSuccess: (result) => {
      setConnectError(null);
      window.location.assign(result.auth_url);
    },
    onError: () => setConnectError(t("connectError")),
  });

  const sync = useMutation({
    mutationFn: (connectionId: string) =>
      syncConnection(businessId as string, connectionId),
    onSuccess: () => {
      setActionError(null);
      void queryClient.invalidateQueries({ queryKey: ["integrations", businessId ?? ""] });
    },
    onError: () => setActionError(t("syncFailedMessage")),
  });

  const disconnect = useMutation({
    mutationFn: (connectionId: string) =>
      disconnectConnection(businessId as string, connectionId),
    onSuccess: () => {
      setActionError(null);
      void queryClient.invalidateQueries({ queryKey: ["integrations", businessId ?? ""] });
    },
    onError: (error) => setActionError(isApiError(error) ? error.message : t("connectError")),
  });

  if (!businessId) return null;

  return (
    <div className="space-y-6">
      <BusinessPageHeader title={t("title")} subtitle={t("subtitle")} />

      {banner === "success" ? (
        <p className="rounded-md border border-border bg-accent px-4 py-3 text-sm" role="status">
          {t("connectedSuccess")}
        </p>
      ) : null}
      {banner === "error" ? (
        <p className="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive" role="alert">
          {t("connectFailed")}
        </p>
      ) : null}

      {connections.length === 0 ? (
        <ConnectCard
          error={connectError}
          pending={connect.isPending}
          onConnect={(domain) => connect.mutate(domain)}
        />
      ) : (
        connections.map((connection) => (
          <ConnectionCard
            key={connection.id}
            connection={connection}
            t={t}
            syncing={sync.isPending}
            disconnecting={disconnect.isPending}
            onSync={() => sync.mutate(connection.id)}
            onDisconnect={() => {
              if (window.confirm(t("disconnectConfirm"))) disconnect.mutate(connection.id);
            }}
          />
        ))
      )}

      {actionError ? (
        <p className="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive" role="alert">
          {actionError}
        </p>
      ) : null}
    </div>
  );
}

function ConnectCard({
  error,
  pending,
  onConnect,
}: {
  error: string | null;
  pending: boolean;
  onConnect: (domain: string) => void;
}) {
  const t = useTranslations("integrations");
  const {
    register,
    handleSubmit,
    formState: { isDirty },
  } = useForm<{ shopDomain: string }>({
    resolver: zodResolver(connectSchema),
    defaultValues: { shopDomain: "" },
  });

  return (
    <Card className="border-dashed">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <LinkIcon className="h-4 w-4" />
          {t("emptyTitle")}
        </CardTitle>
        <CardDescription>{t("emptyBody")}</CardDescription>
      </CardHeader>
      <CardContent>
        <form
          onSubmit={handleSubmit((values) => onConnect(values.shopDomain))}
          className="space-y-4"
          noValidate
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="shop-domain">{t("shopDomain")}</Label>
              <Input
                id="shop-domain"
                placeholder={t("shopDomainPlaceholder")}
                inputMode="url"
                autoComplete="off"
                {...register("shopDomain")}
              />
            </div>
          </div>
          {error ? (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          ) : null}
          <Button type="submit" disabled={pending || !isDirty}>
            {pending ? t("connecting") : t("connect")}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

const SYNC_STATUS_KEY: Record<string, string> = {
  running: "syncRunning",
  success: "syncSuccess",
  partial: "syncPartial",
  failed: "syncFailed",
};

function ConnectionCard({
  connection,
  t,
  syncing,
  disconnecting,
  onSync,
  onDisconnect,
}: {
  connection: Connection;
  t: (key: string) => string;
  syncing: boolean;
  disconnecting: boolean;
  onSync: () => void;
  onDisconnect: () => void;
}) {
  const locale = useLocale();
  const lastSync = connection.last_sync_at
    ? new Date(connection.last_sync_at).toLocaleString(locale)
    : t("never");
  const latestStatus = connection.latest_sync?.status
    ? (SYNC_STATUS_KEY[connection.latest_sync.status] ?? "syncFailed")
    : null;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2">
              <LinkIcon className="h-4 w-4" />
              {t("providerShopify")}
            </CardTitle>
            <CardDescription>
              {connection.external_account_name ?? connection.external_account_id ?? "-"}
            </CardDescription>
          </div>
          <span className="rounded-full border px-3 py-1 text-xs">
            {t(`status${capitalize(connection.status)}`)}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
          <Stat label={t("products")} value={connection.products_count} />
          <Stat label={t("orders")} value={connection.orders_count} />
          <Stat label={t("customers")} value={connection.customers_count} />
          <Stat label={t("inventory")} value={connection.inventory_count} />
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
          <p className="text-muted-foreground">
            {t("lastSync")}: {lastSync}
            {latestStatus ? <> · {t("syncStatus")}: {t(latestStatus)}</> : null}
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={syncing || connection.status !== "connected"}
              onClick={onSync}
            >
              <RefreshCw className={`me-2 h-4 w-4 ${syncing ? "animate-spin" : ""}`} />
              {syncing ? t("syncing") : t("syncNow")}
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={disconnecting || connection.status === "disconnected"}
              onClick={onDisconnect}
            >
              <Unplug className="me-2 h-4 w-4" />
              {disconnecting ? t("disconnecting") : t("disconnect")}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <p className="text-muted-foreground">{label}</p>
      <p className="text-lg font-medium">{value}</p>
    </div>
  );
}

function capitalize(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}