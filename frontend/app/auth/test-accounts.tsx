// Development-only helper: the shared test accounts from
// database/seed_test_accounts.sql. Remove before the product goes live.
const TEST_PASSWORD = "12345678";

const testAccounts = [
  { role: "Admin", email: "admin@example.com" },
  { role: "Attendee", email: "attendee@example.com" },
  { role: "Event Coordinator", email: "event_coordinator1@example.com" },
  { role: "Event Coordinator", email: "event_coordinator2@example.com" },
  { role: "Event Coordinator Lead", email: "event_operations_manager@example.com" },
  { role: "Event Organiser", email: "event_organiser@example.com" },
  { role: "Safety Officer", email: "safety_officer@example.com" },
  { role: "Technical Support", email: "technical_support@example.com" },
  { role: "Venue Staff", email: "venue_staff@example.com" },
];

export function TestAccounts() {
  // Left out of `npm run build`, so these credentials can never ship.
  if (process.env.NODE_ENV === "production") return null;

  return (
    <section aria-labelledby="test-accounts-heading" className="w-full max-w-md rounded-2xl border border-dashed border-[#e0c98f] bg-[#fffaf0] p-6 sm:p-8">
      <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#8a6414]">Testing only</p>
      <h2 id="test-accounts-heading" className="mt-2 text-lg font-bold text-[#17211d]">Test accounts</h2>
      <p className="mt-2 text-sm leading-6 text-[#68776f]">
        Password for every account: <code className="rounded-md bg-white px-2 py-0.5 font-mono font-semibold text-[#17211d]">{TEST_PASSWORD}</code>
      </p>
      <ul className="mt-4 divide-y divide-[#f0e4c4] text-sm">
        {testAccounts.map((account) => (
          <li key={account.email} className="flex flex-col gap-0.5 py-2">
            <span className="select-all break-all font-mono text-xs text-[#273832] sm:text-sm">{account.email}</span>
            <span className="text-xs text-[#68776f]">{account.role}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
