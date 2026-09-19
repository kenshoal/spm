import type { Metadata } from "next";
import { AppShell } from "../components/app-shell";
import { AuthForm } from "./auth-form";

export const metadata: Metadata = { title: "Account | ConnectSphere" };

export default function AuthPage() {
  return <AppShell><AuthForm /></AppShell>;
}
