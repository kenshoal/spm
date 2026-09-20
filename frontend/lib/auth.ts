import { cookies } from "next/headers";
import { redirect } from "next/navigation";

export const sessionCookie = "cs_access_token";
const authServiceUrl = process.env.AUTH_SERVICE_URL ?? "http://127.0.0.1:8001";

export async function requireAccessToken(): Promise<string> {
  const token = (await cookies()).get(sessionCookie)?.value;
  if (!token) redirect("/auth");
  return token;
}

export async function requireAuthenticatedUser(): Promise<void> {
  const token = await requireAccessToken();
  const response = await fetch(`${authServiceUrl}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (response.status === 401) redirect("/auth");
  if (!response.ok) throw new Error("Authentication service unavailable");
}
