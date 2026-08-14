import { apiDelete, apiGet, apiPatch, apiPost } from "@/lib/api-client";

import type { components } from "@marketing-os/shared-types";

export type Goal = components["schemas"]["GoalRead"];
export type GoalCreate = components["schemas"]["GoalCreate"];
export type GoalUpdate = components["schemas"]["GoalUpdate"];

export function fetchGoals(businessId: string): Promise<Goal[]> {
  return apiGet<Goal[]>(`/api/v1/businesses/${businessId}/goals`);
}

export function createGoal(businessId: string, payload: GoalCreate): Promise<Goal> {
  return apiPost<Goal>(`/api/v1/businesses/${businessId}/goals`, payload);
}

export function updateGoal(
  businessId: string,
  goalId: string,
  payload: GoalUpdate
): Promise<Goal> {
  return apiPatch<Goal>(`/api/v1/businesses/${businessId}/goals/${goalId}`, payload);
}

export function deleteGoal(businessId: string, goalId: string): Promise<void> {
  return apiDelete<void>(`/api/v1/businesses/${businessId}/goals/${goalId}`);
}