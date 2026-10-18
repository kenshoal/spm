import { unstable_rethrow } from "next/navigation";
import { Suspense } from "react";
import { requireAuthenticatedUser } from "@/lib/auth";
import { listNotifications, type AppNotification } from "@/lib/notifications";
import { AppShell, workspaceLinks } from "../components/app-shell";
import { NotificationList } from "./notification-list";

async function NotificationData({ roles }: { roles: readonly string[] }) {
  let notifications: AppNotification[];
  try {
    notifications = await listNotifications();
  } catch (error) {
    unstable_rethrow(error);
    return (
      <div role="alert" className="rounded-2xl border border-[#eccdbe] bg-[#fff8f3] px-6 py-8">
        <p className="font-semibold text-[#793f27]">The notification service is unavailable.</p>
        <p className="mt-2 text-sm leading-6 text-[#8b604d]">Start the local API on port 8005, then refresh this page.</p>
      </div>
    );
  }
  const unread = notifications.filter((notification) => notification.read_at === null).length;
  return (
    <div className="space-y-4">
      <p className="text-sm font-semibold text-[#34463f]">{unread === 0 ? "You're all caught up." : `${unread} unread`}</p>
      <NotificationList notifications={notifications} roles={roles} />
    </div>
  );
}

function Loading() {
  return <div aria-label="Loading notifications" className="space-y-3">{[1, 2].map((item) => <div key={item} className="h-28 animate-pulse rounded-2xl border border-[#e1e7e4] bg-white" />)}</div>;
}

export default async function NotificationsPage() {
  const user = await requireAuthenticatedUser();
  return (
    <AppShell signedIn navLinks={workspaceLinks(user.roles)}>
      <div className="mb-8">
        <p className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-[#0f6b5b]">Inbox</p>
        <h1 className="text-3xl font-bold tracking-[-0.035em] text-[#17211d] sm:text-4xl">Notifications</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-[#68776f] sm:text-base">Updates on the event requests you&apos;re responsible for.</p>
      </div>
      <Suspense fallback={<Loading />}>
        <NotificationData roles={user.roles} />
      </Suspense>
    </AppShell>
  );
}
