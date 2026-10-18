import { cookies } from "next/headers";
import { redirect } from "next/navigation";

export const sessionCookie = "cs_access_token";
const authServiceUrl = process.env.AUTH_SERVICE_URL ?? "http://127.0.0.1:8001";

export interface AuthenticatedUser {
  id: string;
  email: string | null;
  role: string;
  roles: string[];
}

export function workspaceForRoles(roles: string[]): string {
  if (roles.includes("event_organiser")) return "/event-requests";
  if (roles.includes("event_coordinator")) return "/coordination/requests";
  if (roles.includes("event_operations_manager")) return "/operations/assignments";
  if (roles.includes("venue_staff")) return "/venues";
  if (roles.includes("technical_support")) return "/equipment";
  if (roles.includes("safety_officer")) return "/safety";
  return "/unauthorised";
}

export async function requireAccessToken(): Promise<string> {
  const token = (await cookies()).get(sessionCookie)?.value;
  if (!token) redirect("/auth");
  return token;
}

export async function requireAuthenticatedUser(): Promise<AuthenticatedUser> {
  const token = await requireAccessToken();
  const response = await fetch(`${authServiceUrl}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (response.status === 401) redirect("/auth");
  if (!response.ok) throw new Error("Authentication service unavailable");
  const user = await response.json();
  return { ...user, roles: user.roles ?? [user.role] };
}

export async function requireRole(role: string): Promise<AuthenticatedUser> {
  const user = await requireAuthenticatedUser();
  if (!user.roles.includes(role)) redirect("/unauthorised");
  return user;
}

export function requireEventOrganiser(): Promise<AuthenticatedUser> {
  return requireRole("event_organiser");
}

export async function requireAnyRole(roles: readonly string[]): Promise<AuthenticatedUser> {
  const user = await requireAuthenticatedUser();
  if (!roles.some((role) => user.roles.includes(role))) redirect("/unauthorised");
  return user;
}
