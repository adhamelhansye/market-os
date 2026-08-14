import "@testing-library/jest-dom/vitest";

import { vi } from "vitest";

// next/navigation is unavailable in jsdom; provide a minimal router mock.
const routerMock = {
  push: vi.fn(),
  replace: vi.fn(),
  back: vi.fn(),
  prefetch: vi.fn(),
  refresh: vi.fn(),
  forward: vi.fn(),
};

vi.mock("next/navigation", () => ({
  useRouter: () => routerMock,
  usePathname: () => "/dashboard",
  useParams: () => ({}),
  useSearchParams: () => new URLSearchParams(),
  redirect: vi.fn(),
}));

// next/font/google performs network/build-time work; avoid loading in tests.
vi.mock("next/font/google", () => ({
  Inter: () => ({ variable: "--font-latin" }),
  Noto_Sans_Arabic: () => ({ variable: "--font-arabic" }),
}));