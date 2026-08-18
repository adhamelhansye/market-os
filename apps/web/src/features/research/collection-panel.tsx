"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Play, X } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  cancelResearchCollection,
  collectResearchProject,
  fetchResearchCollections,
} from "./api";

export function CollectionPanel({ businessId, projectId }: { businessId: string; projectId: string | null }) {
  const t = useTranslations("research");
  const locale = useLocale();
  const queryClient = useQueryClient();
  const [url, setUrl] = useState("");
  const collectionsQuery = useQuery({
    queryKey: ["research-collections", businessId],
    queryFn: () => fetchResearchCollections(businessId),
    enabled: Boolean(businessId),
  });
  const collectMutation = useMutation({
    mutationFn: () =>
      collectResearchProject(businessId, projectId as string, {
        research_project_id: projectId as string,
        source_url: url,
        mode: "single_page",
        max_pages: 1,
        max_depth: 0,
        same_domain: true,
        refresh: true,
        specific_urls: [],
      }),
    onSuccess: () => {
      setUrl("");
      void queryClient.invalidateQueries({ queryKey: ["research-collections", businessId] });
      void queryClient.invalidateQueries({ queryKey: ["research-sources", businessId] });
    },
  });
  const cancelMutation = useMutation({
    mutationFn: (collectionId: string) => cancelResearchCollection(businessId, collectionId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["research-collections", businessId] }),
  });

  return (
    <Card data-testid="research-collection-panel">
      <CardHeader>
        <CardTitle>{t("collectionTitle")}</CardTitle>
        <CardDescription>{t("collectionDescription")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input value={url} onChange={(event) => setUrl(event.target.value)} placeholder={t("urlPlaceholder")} />
          <Button disabled={!projectId || !url.trim() || collectMutation.isPending} onClick={() => collectMutation.mutate()}>
            {collectMutation.isPending ? <Loader2 className="me-2 h-4 w-4 animate-spin" /> : <Play className="me-2 h-4 w-4" />}
            {t("collect")}
          </Button>
        </div>
        {collectMutation.isError ? <p className="text-sm text-destructive">{t("collectionError")}</p> : null}
        {collectionsQuery.isLoading ? <p className="text-sm text-muted-foreground">{t("loading")}</p> : null}
        {collectionsQuery.isError ? <p className="text-sm text-destructive">{t("error")}</p> : null}
        {!collectionsQuery.isLoading && (collectionsQuery.data?.collections.length ?? 0) === 0 ? (
          <p className="text-sm text-muted-foreground">{t("noCollections")}</p>
        ) : (
          <div className="space-y-2">
            {collectionsQuery.data?.collections.map((collection) => (
              <div key={collection.id} className="flex items-center justify-between rounded-md border p-3 text-sm">
                <div>
                  <div className="font-medium">{t(`collectionStatus_${collection.status}`)}</div>
                  <div className="text-xs text-muted-foreground">
                    {new Date(collection.created_at).toLocaleString(locale)} · {collection.pages_collected} {t("pages")}
                  </div>
                  {collection.error ? <div className="text-xs text-destructive">{collection.error}</div> : null}
                </div>
                {collection.status === "queued" || collection.status === "running" ? (
                  <Button variant="ghost" size="sm" onClick={() => cancelMutation.mutate(collection.id)}>
                    <X className="me-1 h-4 w-4" /> {t("cancel")}
                  </Button>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
