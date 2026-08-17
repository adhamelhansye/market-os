"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { PROJECT_STATUSES, PROJECT_TYPES } from "./constants";
import {
  createResearchProject,
  fetchResearchProjects,
  setResearchProjectStatus,
  type ResearchProjectListResponse,
} from "./api";
import { ProjectStatusBadge } from "./status-badges";

interface ProjectsPanelProps {
  businessId: string;
}

export function ProjectsPanel({ businessId }: ProjectsPanelProps) {
  const t = useTranslations("research");
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [type, setType] = useState<string>("market");
  const [scope, setScope] = useState("");
  const [error, setError] = useState<string | null>(null);

  const queryKey = ["research-projects", businessId];
  const { data, isLoading, isError, refetch } = useQuery<ResearchProjectListResponse>({
    queryKey,
    queryFn: () => fetchResearchProjects(businessId),
    enabled: Boolean(businessId),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey });

  const { mutate: create, isPending } = useMutation({
    mutationFn: () =>
      createResearchProject(businessId, {
        name: name.trim(),
        type,
        scope: scope.trim() || null,
      }),
    onSuccess: () => {
      setName("");
      setScope("");
      setShowForm(false);
      setError(null);
      invalidate();
    },
    onError: (err: Error) => setError(err.message ?? t("createFailed")),
  });

  const { mutate: setStatus, isPending: statusPending } = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      setResearchProjectStatus(businessId, id, { status }),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (err: Error) => setError(err.message ?? t("statusFailed")),
  });

  if (isLoading) {
    return (
      <Card>
        <CardContent className="flex items-center gap-2 py-8 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> {t("loading")}
        </CardContent>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card>
        <CardContent className="space-y-2 py-8 text-center">
          <p className="text-muted-foreground">{t("error")}</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            {t("retry")}
          </Button>
        </CardContent>
      </Card>
    );
  }

  const projects = data?.projects ?? [];

  return (
    <div className="space-y-4" data-testid="research-projects-panel">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold">{t("tabs.projects")}</h3>
        <Button variant="outline" size="sm" onClick={() => setShowForm((v) => !v)}>
          {t("addProject")}
        </Button>
      </div>

      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      {showForm ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t("createProject")}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <span className="text-xs text-muted-foreground">{t("name")}</span>
              <Input
                data-testid="project-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t("namePlaceholder")}
              />
            </div>
            <div className="space-y-1">
              <span className="text-xs text-muted-foreground">{t("type")}</span>
              <Select value={type} onValueChange={setType}>
                <SelectTrigger className="w-full" data-testid="project-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PROJECT_TYPES.map((value) => (
                    <SelectItem key={value} value={value}>
                      {t(`type_${value}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1 sm:col-span-2">
              <span className="text-xs text-muted-foreground">{t("scope")}</span>
              <Input
                data-testid="project-scope"
                value={scope}
                onChange={(e) => setScope(e.target.value)}
                placeholder={t("scopePlaceholder")}
              />
            </div>
            <div className="flex gap-2 sm:col-span-2">
              <Button
                data-testid="project-submit"
                disabled={isPending || name.trim() === ""}
                onClick={() => create()}
              >
                {isPending ? t("loading") : t("create")}
              </Button>
              <Button variant="ghost" onClick={() => setShowForm(false)}>
                {t("cancel")}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardContent className="py-4">
          {projects.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("noProjects")}</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-start text-muted-foreground">
                  <th className="py-2 pe-2 font-normal">{t("name")}</th>
                  <th className="py-2 pe-2 font-normal">{t("type")}</th>
                  <th className="py-2 pe-2 font-normal">{t("setStatus")}</th>
                  <th className="py-2 font-normal"></th>
                </tr>
              </thead>
              <tbody>
                {projects.map((project) => (
                  <tr key={project.id} className="border-b">
                    <td className="py-2 pe-2">{project.name}</td>
                    <td className="py-2 pe-2">{t(`type_${project.type}`)}</td>
                    <td className="py-2 pe-2">
                      <ProjectStatusBadge status={project.status} />
                    </td>
                    <td className="py-2 text-end">
                      <Select
                        value=""
                        onValueChange={(value) =>
                          setStatus({ id: project.id, status: value })
                        }
                      >
                        <SelectTrigger className="w-40" data-testid={`status-select-${project.id}`}>
                          <SelectValue placeholder={t("changeStatus")} />
                        </SelectTrigger>
                        <SelectContent>
                          {PROJECT_STATUSES.map((value) => (
                            <SelectItem key={value} value={value}>
                              {t(`status_${value}`)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      {statusPending ? (
                        <Loader2 className="ms-2 inline h-3 w-3 animate-spin" />
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
