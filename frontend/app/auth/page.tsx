import type { Metadata } from "next";
import { AppShell } from "../components/app-shell";
import { AuthForm } from "./auth-form";
import { TestAccounts } from "./test-accounts";

export const metadata: Metadata = { title: "Account | ConnectSphere" };

export default function AuthPage() {
  return (
    <AppShell>
      <div className="flex flex-col items-center gap-6 lg:flex-row lg:items-start lg:justify-center">
        <AuthForm />
        <TestAccounts />
      </div>
    </AppShell>
  );
}
