import type { Metadata } from "next";
import { AppShell } from "../components/app-shell";

export const metadata: Metadata = { title: "Access unavailable | ConnectSphere" };

export default function UnauthorisedPage() {
  return (
    <AppShell signedIn>
      <section className="mx-auto max-w-xl rounded-2xl border border-[#dce4e0] bg-white p-8 shadow-sm">
        <p className="text-sm font-semibold uppercase tracking-[0.14em] text-[#0f6b5b]">
          Access unavailable
        </p>
        <h1 className="mt-3 text-3xl font-bold tracking-[-0.03em] text-[#17211d]">
          Your role can&apos;t use this page
        </h1>
        <p className="mt-4 leading-7 text-[#52635c]">
          Your account is signed in, but none of its roles give access to this page.
          Contact an administrator if you need access.
        </p>
      </section>
    </AppShell>
  );
}
