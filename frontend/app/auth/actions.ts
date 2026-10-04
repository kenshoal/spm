"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { sessionCookie, workspaceForRoles } from "@/lib/auth";

export type AuthFormState = { message?: string; success?: boolean };

const authServiceUrl = process.env.AUTH_SERVICE_URL ?? "http://127.0.0.1:8001";

async function submitCredentials(
  path: "register" | "login",
  formData: FormData,
): Promise<AuthFormState> {
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  if (!email || password.length < 8) {
    return { message: "Enter an email and a password of at least 8 characters." };
  }

  let response: Response;
  let destination = "/unauthorised";
  try {
    response = await fetch(`${authServiceUrl}/auth/${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
      cache: "no-store",
    });
  } catch {
    return { message: "The authentication service is unavailable. Please try again." };
  }
  if (!response.ok) {
    return {
      message:
        path === "login" && (response.status === 401 || response.status === 403)
          ? "Invalid credentials or email confirmation is required."
          : path === "register" && response.status < 500
            ? "Registration failed. Check your details or try another email."
            : "The authentication service is unavailable. Please try again.",
    };
  }

  try {
    if (path === "register") {
      const user = (await response.json()) as { email_confirmation_required?: boolean };
      return {
        success: true,
        message: user.email_confirmation_required
          ? "Account created. Check your email before logging in."
          : "Account created. You can log in now.",
      };
    }
    const session = (await response.json()) as { access_token?: string; expires_in?: number };
    if (!session.access_token || !Number.isFinite(session.expires_in) || !session.expires_in) {
      return { message: "The authentication service returned an invalid session." };
    }

    const userResponse = await fetch(`${authServiceUrl}/auth/me`, {
      headers: { Authorization: `Bearer ${session.access_token}` },
      cache: "no-store",
    });
    if (!userResponse.ok) {
      return { message: "The authentication service could not verify your workspace access." };
    }
    const user = (await userResponse.json()) as { role?: string; roles?: string[] };
    const roles = Array.isArray(user.roles)
      ? user.roles.filter((role): role is string => typeof role === "string")
      : typeof user.role === "string"
        ? [user.role]
        : [];
    destination = workspaceForRoles(roles);

    (await cookies()).set(sessionCookie, session.access_token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/",
      maxAge: Math.max(1, Math.min(session.expires_in, 3600)),
    });
  } catch {
    return { message: "The authentication service is unavailable. Please try again." };
  }
  redirect(destination);
}

export async function register(
  _state: AuthFormState,
  formData: FormData,
): Promise<AuthFormState> {
  return submitCredentials("register", formData);
}

export async function login(
  _state: AuthFormState,
  formData: FormData,
): Promise<AuthFormState> {
  return submitCredentials("login", formData);
}

export async function logout(): Promise<void> {
  (await cookies()).delete(sessionCookie);
  redirect("/auth");
}
