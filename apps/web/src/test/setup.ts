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

// jsdom does not implement pointer capture; radix-ui primitives call
// hasPointerCapture during pointer event dispatch and would crash.
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.setPointerCapture = () => {};
  Element.prototype.releasePointerCapture = () => {};
}

// jsdom does not implement scrollIntoView; radix select viewport uses it.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}