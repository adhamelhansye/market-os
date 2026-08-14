"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

const ACTIVE_ORG_KEY = "mos.activeOrg";
const ACTIVE_BUSINESS_KEY = "mos.activeBusiness";

function readStorage(key: string): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(key);
}

interface BusinessContextValue {
  activeOrganizationId: string | null;
  activeBusinessId: string | null;
  setActiveOrganization: (organizationId: string) => void;
  setActiveBusiness: (businessId: string) => void;
  clear: () => void;
}

const BusinessContext = createContext<BusinessContextValue | null>(null);

/**
 * Client/session context for the active organization and business.
 * Values are persisted locally; the backend re-validates everything.
 */
export function BusinessProvider({ children }: { children: React.ReactNode }) {
  const [activeOrganizationId, setActiveOrganizationId] = useState<string | null>(() =>
    readStorage(ACTIVE_ORG_KEY)
  );
  const [activeBusinessId, setActiveBusinessId] = useState<string | null>(() =>
    readStorage(ACTIVE_BUSINESS_KEY)
  );

  useEffect(() => {
    if (activeOrganizationId) window.localStorage.setItem(ACTIVE_ORG_KEY, activeOrganizationId);
    else window.localStorage.removeItem(ACTIVE_ORG_KEY);
  }, [activeOrganizationId]);

  useEffect(() => {
    if (activeBusinessId) window.localStorage.setItem(ACTIVE_BUSINESS_KEY, activeBusinessId);
    else window.localStorage.removeItem(ACTIVE_BUSINESS_KEY);
  }, [activeBusinessId]);

  const setActiveOrganization = useCallback((organizationId: string) => {
    setActiveOrganizationId(organizationId);
    setActiveBusinessId(null);
  }, []);

  const setActiveBusiness = useCallback((businessId: string) => {
    setActiveBusinessId(businessId);
  }, []);

  const clear = useCallback(() => {
    setActiveOrganizationId(null);
    setActiveBusinessId(null);
  }, []);

  const value = useMemo(
    () => ({
      activeOrganizationId,
      activeBusinessId,
      setActiveOrganization,
      setActiveBusiness,
      clear,
    }),
    [activeOrganizationId, activeBusinessId, setActiveOrganization, setActiveBusiness, clear]
  );

  return <BusinessContext.Provider value={value}>{children}</BusinessContext.Provider>;
}

export function useBusiness(): BusinessContextValue {
  const context = useContext(BusinessContext);
  if (!context) throw new Error("useBusiness must be used within BusinessProvider");
  return context;
}