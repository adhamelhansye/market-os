import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { screen } from "@/test/render";
import { renderWithI18n } from "@/test/render";
import LoginPage from "@/app/[locale]/(auth)/login/page";
import SignupPage from "@/app/[locale]/(auth)/signup/page";

vi.mock("@/context/auth-context", () => ({
  useAuth: () => ({
    status: "anonymous",
    user: null,
    memberships: [],
    activeOrganizationId: null,
    login: vi.fn(),
    signup: vi.fn(),
    logout: vi.fn(),
    refresh: vi.fn(),
  }),
  isApiError: (error: unknown) => error instanceof Error,
}));

describe("login page", () => {
  it("renders English labels and submit button", () => {
    renderWithI18n(<LoginPage />, "en");
    expect(screen.getByText("Sign in to MarketingOS")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("renders Arabic labels and submit button (RTL locale)", () => {
    renderWithI18n(<LoginPage />, "ar");
    expect(screen.getByText("تسجيل الدخول إلى ماركتينج أو إس")).toBeInTheDocument();
    expect(screen.getByLabelText("البريد الإلكتروني")).toBeInTheDocument();
    expect(screen.getByLabelText("كلمة المرور")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "تسجيل الدخول" })).toBeInTheDocument();
  });
});

describe("signup page", () => {
  it("renders all required fields", () => {
    renderWithI18n(<SignupPage />, "en");
    expect(screen.getByText("Create your account")).toBeInTheDocument();
    expect(screen.getByLabelText("Full name")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.getByLabelText("Organization name")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create account" })).toBeInTheDocument();
  });

  it("validates short passwords using localized messages", async () => {
    const user = userEvent.setup();
    renderWithI18n(<SignupPage />, "en");
    await user.type(screen.getByLabelText("Password"), "short");
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findAllByText("Password must be at least 8 characters.")).not.toHaveLength(0);
  });
});