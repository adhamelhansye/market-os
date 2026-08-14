import { DashboardShell } from "@/components/layout/dashboard-shell";

export default function DashboardGroupLayout({ children }: { children: React.ReactNode }) {
  return <DashboardShell>{children}</DashboardShell>;
}