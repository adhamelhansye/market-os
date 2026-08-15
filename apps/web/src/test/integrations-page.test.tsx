import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent } from "@testing-library/react";

import { renderWithI18n, screen } from "@/test/render";
import IntegrationsPage from "@/app/[locale]/(dashboard)/business/[business_id]/integrations/page";
import type { Connection, MetaAccount } from "@/features/integrations/api";

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    prefetch: vi.fn(),
    refresh: vi.fn(),
    forward: vi.fn(),
  }),
  usePathname: () => "/business/biz-1/integrations",
  useParams: () => ({ business_id: "biz-1" }),
  useSearchParams: () => new URLSearchParams(),
  redirect: vi.fn(),
}));

const state = vi.hoisted(() => ({
  connections: [] as Connection[],
  metaAccounts: null as null | {
    connection_id: string | null;
    accounts: MetaAccount[];
  },
}));

const api = vi.hoisted(() => ({
  connectShopify: vi.fn(),
  connectMeta: vi.fn(),
  disconnectConnection: vi.fn(),
  fetchConnections: vi.fn(),
  fetchMetaAccounts: vi.fn(),
  selectMetaAccount: vi.fn(),
  syncConnection: vi.fn(),
}));

vi.mock("@/features/integrations/api", () => ({
  connectShopify: api.connectShopify,
  connectMeta: api.connectMeta,
  disconnectConnection: api.disconnectConnection,
  fetchConnections: api.fetchConnections,
  fetchMetaAccounts: api.fetchMetaAccounts,
  selectMetaAccount: api.selectMetaAccount,
  syncConnection: api.syncConnection,
}));

const connection: Connection = {
  id: "conn-1",
  business_id: "biz-1",
  provider: "shopify",
  status: "connected",
  external_account_id: "demo.myshopify.com",
  external_account_name: "Demo Store",
  scopes: ["read_products"],
  metadata: null,
  connected_at: "2026-08-14T09:00:00Z",
  last_sync_at: "2026-08-14T10:00:00Z",
  created_at: "2026-08-14T09:00:00Z",
  updated_at: "2026-08-14T10:00:00Z",
  products_count: 12,
  orders_count: 345,
  customers_count: 89,
  inventory_count: 23,
  campaigns_count: 0,
  ad_sets_count: 0,
  ads_count: 0,
  daily_records_count: 0,
  latest_sync: {
    id: "r-1",
    resource_type: "orders",
    status: "success",
    started_at: "2026-08-14T10:00:00Z",
    finished_at: "2026-08-14T10:01:00Z",
    records_processed: 10,
    error_summary: null,
  },
};

const metaConnection: Connection = {
  ...connection,
  id: "conn-meta-1",
  provider: "meta",
  external_account_id: "act_111222333",
  external_account_name: "My Ads Account",
  campaigns_count: 3,
  ad_sets_count: 12,
  ads_count: 45,
  daily_records_count: 500,
  latest_sync: {
    ...connection.latest_sync!,
    resource_type: "insights",
  },
};

const metaAccounts = [
  {
    external_account_id: "111222333",
    name: "My Ads Account",
    currency: "USD",
    status: "ACTIVE",
    timezone: "Asia/Riyadh",
  },
];

function renderPage(locale: "en" | "ar") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return renderWithI18n(
    <QueryClientProvider client={queryClient}>
      <IntegrationsPage />
    </QueryClientProvider>,
    locale
  );
}

describe("integrations page", () => {
  beforeEach(() => {
    state.connections = [];
    state.metaAccounts = null;
    api.connectShopify.mockReset();
    api.connectMeta.mockReset();
    api.syncConnection.mockReset();
    api.disconnectConnection.mockReset();
    api.selectMetaAccount.mockReset();
    api.fetchConnections.mockImplementation(() => Promise.resolve(state.connections));
    api.fetchMetaAccounts.mockImplementation(() =>
      Promise.resolve(
        state.metaAccounts ?? { connection_id: null, accounts: [] }
      )
    );
  });

  it("shows the connect forms when nothing is connected", async () => {
    renderPage("en");
    expect(await screen.findByLabelText("Shopify store domain")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Connect" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Connect Meta Ads" })).toBeInTheDocument();
  });

  it("shows the Arabic connect state with RTL text", async () => {
    renderPage("ar");
    expect(
      await screen.findByText("امنح وصولًا للقراءة فقط لمتجرك لمزامنة المنتجات والطلبات والعملاء والمخزون تلقائيًا.")
    ).toBeInTheDocument();
    expect(screen.getByText("ربط إعلانات ميتا")).toBeInTheDocument();
  });

  it("starts the store connect flow with the entered shop domain", async () => {
    api.connectShopify.mockResolvedValue({ auth_url: "https://shopify.com/auth" });
    renderPage("en");
    const input = await screen.findByLabelText("Shopify store domain");
    fireEvent.change(input, { target: { value: "demo.myshopify.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));
    await vi.waitFor(() =>
      expect(api.connectShopify).toHaveBeenCalledWith("biz-1", "demo.myshopify.com")
    );
  });

  it("starts the Meta connect flow", async () => {
    api.connectMeta.mockResolvedValue({
      auth_url: "https://facebook.com/dialog/oauth/authorize",
    });
    renderPage("en");
    fireEvent.click(await screen.findByRole("button", { name: "Connect Meta Ads" }));
    await vi.waitFor(() => expect(api.connectMeta).toHaveBeenCalledWith("biz-1", "en"));
  });

  it("shows the Meta account chooser after authorization", async () => {
    state.metaAccounts = { connection_id: "pc-1", accounts: metaAccounts };
    api.selectMetaAccount.mockResolvedValue(metaConnection);
    renderPage("en");
    expect(await screen.findByText("Choose an ad account")).toBeInTheDocument();
    expect(screen.getByText("My Ads Account")).toBeInTheDocument();
    expect(screen.getByText("111222333 · USD · ACTIVE")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Select account" }));
    await vi.waitFor(() =>
      expect(api.selectMetaAccount).toHaveBeenCalledWith("biz-1", "111222333")
    );
  });

  it("shows store info and sync actions for a connected store", async () => {
    state.connections = [connection];
    renderPage("en");
    expect(await screen.findByText("Demo Store")).toBeInTheDocument();
    expect(screen.getByText("Connected")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("345")).toBeInTheDocument();
    expect(screen.getByText("89")).toBeInTheDocument();
    expect(screen.getByText("23")).toBeInTheDocument();
    expect(screen.getByText(/Last sync:/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sync now" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Disconnect" })).toBeInTheDocument();
  });

  it("shows Meta campaign stats for a connected ad account", async () => {
    state.connections = [metaConnection];
    renderPage("en");
    expect(await screen.findByText("My Ads Account")).toBeInTheDocument();
    expect(screen.getByText("Meta Ads")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("45")).toBeInTheDocument();
    expect(screen.getByText("500")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sync now" })).toBeInTheDocument();
  });

  it("triggers a sync for the connected store", async () => {
    api.syncConnection.mockResolvedValue(null);
    state.connections = [connection];
    renderPage("en");
    fireEvent.click(await screen.findByRole("button", { name: "Sync now" }));
    await vi.waitFor(() => expect(api.syncConnection).toHaveBeenCalledWith("biz-1", "conn-1"));
  });

  it("disconnects after confirmation", async () => {
    api.disconnectConnection.mockResolvedValue({ ...connection, status: "disconnected" });
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    state.connections = [connection];
    renderPage("en");
    fireEvent.click(await screen.findByRole("button", { name: "Disconnect" }));
    await vi.waitFor(() =>
      expect(api.disconnectConnection).toHaveBeenCalledWith("biz-1", "conn-1")
    );
    expect(confirmSpy).toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it("shows a success banner after a successful callback", async () => {
    window.history.replaceState({}, "", "/business/biz-1/integrations?connected=1");
    renderPage("en");
    expect(
      await screen.findByText("Connected successfully. Initial sync started.")
    ).toBeInTheDocument();
  });
});