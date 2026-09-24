import Link from "next/link";
import { requireRole } from "@/lib/auth";
import { AppShell, workspaceLinks } from "../../components/app-shell";
import { EquipmentForm } from "../equipment-form";

export default async function NewEquipmentPage() {
  const user = await requireRole("technical_support");
  return (
    <AppShell signedIn navLinks={workspaceLinks(user.roles)}>
      <div className="mx-auto max-w-3xl">
        <Link href="/equipment" className="mb-5 inline-block text-sm font-semibold text-[#0f6b5b] hover:underline">← Back to equipment</Link>
        <h1 className="mb-6 text-3xl font-bold tracking-[-0.035em] text-[#17211d]">Add equipment</h1>
        <EquipmentForm />
      </div>
    </AppShell>
  );
}
