"use client";

import { apiGet, apiPatch, apiPost } from "@/lib/api-client";
import type { components } from "@marketing-os/shared-types";
export {
  CLASSIFICATION_VALUES,
  EVIDENCE_STRENGTHS,
  EVIDENCE_TYPES,
  FINDING_CATEGORIES,
  IMPORTANCE_VALUES,
  PROJECT_STATUSES,
  PROJECT_TYPES,
  PROVENANCE_VALUES,
  SOURCE_TYPES,
} from "./constants";
export type {
  Classification,
  EvidenceStrength,
  EvidenceType,
  FindingCategory,
  Importance,
  ProjectStatus,
  ProjectType,
  Provenance,
  SourceType,
} from "./constants";

export type ResearchProjectResponse = components["schemas"]["ResearchProjectResponse"];
export type ResearchProjectDetailResponse =
  components["schemas"]["ResearchProjectDetailResponse"];
export type ResearchProjectListResponse =
  components["schemas"]["ResearchProjectListResponse"];
export type ResearchProjectCreateRequest =
  components["schemas"]["ResearchProjectCreateRequest"];
export type ResearchProjectStatusRequest =
  components["schemas"]["ResearchProjectStatusRequest"];

export type ResearchCompetitorResponse = components["schemas"]["ResearchCompetitorResponse"];
export type ResearchCompetitorListResponse =
  components["schemas"]["ResearchCompetitorListResponse"];
export type ResearchCompetitorCreateRequest =
  components["schemas"]["ResearchCompetitorCreateRequest"];

export type ResearchSourceResponse = components["schemas"]["ResearchSourceResponse"];
export type ResearchSourceDetailResponse =
  components["schemas"]["ResearchSourceDetailResponse"];
export type ResearchSourceListResponse = components["schemas"]["ResearchSourceListResponse"];
export type ResearchSourceCreateRequest =
  components["schemas"]["ResearchSourceCreateRequest"];

export type ResearchEvidenceResponse = components["schemas"]["ResearchEvidenceResponse"];
export type ResearchEvidenceListResponse =
  components["schemas"]["ResearchEvidenceListResponse"];
export type ResearchEvidenceCreateRequest =
  components["schemas"]["ResearchEvidenceCreateRequest"];
export type ResearchEvidenceSummary = components["schemas"]["ResearchEvidenceSummary"];

export type ResearchSearchHitResponse = components["schemas"]["ResearchSearchHitResponse"];
export type ResearchSearchResponse = components["schemas"]["ResearchSearchResponse"];

export type ResearchFindingResponse = components["schemas"]["ResearchFindingResponse"];
export type ResearchFindingDetailResponse =
  components["schemas"]["ResearchFindingDetailResponse"];
export type ResearchFindingListResponse =
  components["schemas"]["ResearchFindingListResponse"];
export type ResearchFindingCreateRequest =
  components["schemas"]["ResearchFindingCreateRequest"];
export type ResearchCollectionRequest = components["schemas"]["ResearchCollectionRequest"];
export type ResearchCollectionJobResponse =
  components["schemas"]["ResearchCollectionJobResponse"];
export type ResearchCollectionJobListResponse =
  components["schemas"]["ResearchCollectionJobListResponse"];

export const CONFIDENCE_VALUES = ["observed", "supported", "inferred", "hypothesis"] as const;
export type Confidence = (typeof CONFIDENCE_VALUES)[number];

function researchUrl(businessId: string, path: string): string {
  return `/api/v1/businesses/${businessId}/research/${path}`;
}

export function fetchResearchProjects(businessId: string): Promise<ResearchProjectListResponse> {
  return apiGet<ResearchProjectListResponse>(researchUrl(businessId, "projects"));
}

export function fetchResearchProject(
  businessId: string,
  projectId: string
): Promise<ResearchProjectDetailResponse> {
  return apiGet<ResearchProjectDetailResponse>(
    researchUrl(businessId, `projects/${projectId}`)
  );
}

export function createResearchProject(
  businessId: string,
  payload: ResearchProjectCreateRequest
): Promise<ResearchProjectResponse> {
  return apiPost<ResearchProjectResponse>(
    researchUrl(businessId, "projects"),
    payload
  );
}

export function setResearchProjectStatus(
  businessId: string,
  projectId: string,
  payload: ResearchProjectStatusRequest
): Promise<ResearchProjectResponse> {
  return apiPatch<ResearchProjectResponse>(
    researchUrl(businessId, `projects/${projectId}/status`),
    payload
  );
}

export function fetchResearchCompetitors(
  businessId: string
): Promise<ResearchCompetitorListResponse> {
  return apiGet<ResearchCompetitorListResponse>(researchUrl(businessId, "competitors"));
}

export function createResearchCompetitor(
  businessId: string,
  payload: ResearchCompetitorCreateRequest
): Promise<ResearchCompetitorResponse> {
  return apiPost<ResearchCompetitorResponse>(
    researchUrl(businessId, "competitors"),
    payload
  );
}

export function fetchResearchSources(
  businessId: string,
  params?: { source_type?: string; competitor_id?: string; status?: string }
): Promise<ResearchSourceListResponse> {
  const search = new URLSearchParams();
  if (params?.source_type) search.set("source_type", params.source_type);
  if (params?.competitor_id) search.set("competitor_id", params.competitor_id);
  if (params?.status) search.set("status", params.status);
  const query = search.toString();
  return apiGet<ResearchSourceListResponse>(
    researchUrl(businessId, `sources${query ? `?${query}` : ""}`)
  );
}

export function createResearchSource(
  businessId: string,
  payload: ResearchSourceCreateRequest
): Promise<ResearchSourceResponse> {
  return apiPost<ResearchSourceResponse>(researchUrl(businessId, "sources"), payload);
}

export function fetchResearchEvidence(
  businessId: string,
  params?: {
    evidence_type?: string;
    source_id?: string;
    classification?: string;
    provenance?: string;
  }
): Promise<ResearchEvidenceListResponse> {
  const search = new URLSearchParams();
  if (params?.evidence_type) search.set("evidence_type", params.evidence_type);
  if (params?.source_id) search.set("source_id", params.source_id);
  if (params?.classification) search.set("classification", params.classification);
  if (params?.provenance) search.set("provenance", params.provenance);
  const query = search.toString();
  return apiGet<ResearchEvidenceListResponse>(
    researchUrl(businessId, `evidence${query ? `?${query}` : ""}`)
  );
}

export function searchResearchContent(
  businessId: string,
  query: string
): Promise<ResearchSearchResponse> {
  const search = new URLSearchParams({ q: query });
  return apiGet<ResearchSearchResponse>(
    researchUrl(businessId, `search?${search.toString()}`)
  );
}

export function createResearchEvidence(
  businessId: string,
  payload: ResearchEvidenceCreateRequest
): Promise<ResearchEvidenceResponse> {
  return apiPost<ResearchEvidenceResponse>(researchUrl(businessId, "evidence"), payload);
}

export function fetchResearchFindings(
  businessId: string,
  params?: {
    research_project_id?: string;
    category?: string;
    classification?: string;
    importance?: string;
  }
): Promise<ResearchFindingListResponse> {
  const search = new URLSearchParams();
  if (params?.research_project_id)
    search.set("research_project_id", params.research_project_id);
  if (params?.category) search.set("category", params.category);
  if (params?.classification) search.set("classification", params.classification);
  if (params?.importance) search.set("importance", params.importance);
  const query = search.toString();
  return apiGet<ResearchFindingListResponse>(
    researchUrl(businessId, `findings${query ? `?${query}` : ""}`)
  );
}

export function fetchResearchFinding(
  businessId: string,
  findingId: string
): Promise<ResearchFindingDetailResponse> {
  return apiGet<ResearchFindingDetailResponse>(
    researchUrl(businessId, `findings/${findingId}`)
  );
}

export function createResearchFinding(
  businessId: string,
  payload: ResearchFindingCreateRequest
): Promise<ResearchFindingResponse> {
  return apiPost<ResearchFindingResponse>(researchUrl(businessId, "findings"), payload);
}

export function fetchResearchCollections(
  businessId: string
): Promise<ResearchCollectionJobListResponse> {
  return apiGet<ResearchCollectionJobListResponse>(researchUrl(businessId, "collections"));
}

export function collectResearchProject(
  businessId: string,
  projectId: string,
  payload: ResearchCollectionRequest
): Promise<ResearchCollectionJobResponse> {
  return apiPost<ResearchCollectionJobResponse>(
    researchUrl(businessId, `projects/${projectId}/collect`),
    payload
  );
}

export function refreshResearchSource(
  businessId: string,
  sourceId: string,
  payload: ResearchCollectionRequest
): Promise<ResearchCollectionJobResponse> {
  return apiPost<ResearchCollectionJobResponse>(
    researchUrl(businessId, `sources/${sourceId}/refresh`),
    payload
  );
}

export function cancelResearchCollection(
  businessId: string,
  collectionId: string
): Promise<{ collection: ResearchCollectionJobResponse }> {
  return apiPost<{ collection: ResearchCollectionJobResponse }>(
    researchUrl(businessId, `collections/${collectionId}/cancel`),
    {}
  );
}
