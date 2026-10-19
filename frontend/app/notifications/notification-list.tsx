import Link from "next/link";
import { formatDateTime } from "@/lib/event-requests";
import { describeNotification, type AppNotification } from "@/lib/notifications";
import { MarkReadButton } from "./mark-read-button";

export function NotificationList({ notifications, roles = [] }: { notifications: AppNotification[]; roles?: readonly string[] }) {
  if (notifications.length === 0) {
    return <p className="rounded-2xl border border-dashed border-[#cbd7d1] bg-white px-6 py-10 text-center text-sm text-[#718078]">No notifications yet.</p>;
  }
  return (
    <div className="space-y-3">
      {notifications.map((notification) => {
        const { message, href, detail } = describeNotification(notification, roles);
        const unread = notification.read_at === null;
        const headingId = `notification-${notification.id}`;
        return (
          <article
            key={notification.id}
            aria-labelledby={headingId}
            className={`rounded-2xl border p-5 sm:p-6 ${unread ? "border-[#b9dccf] bg-[#f3faf7]" : "border-[#dce4e0] bg-white"}`}
          >
            <div className="flex flex-wrap items-center gap-3">
              <h2 id={headingId} className={`text-base sm:text-lg ${unread ? "font-bold text-[#17211d]" : "font-semibold text-[#3c4d46]"}`}>{message}</h2>
              {unread ? <span className="rounded-full bg-[#0f6b5b] px-2.5 py-1 text-xs font-bold text-white">Unread</span> : null}
            </div>
            {detail ? <p className="mt-2 whitespace-pre-line break-words text-sm text-[#3c4d46]">{detail}</p> : null}
            <p className="mt-2 text-xs font-medium text-[#718078]">
              <time dateTime={notification.created_at}>{formatDateTime(notification.created_at)}</time>
            </p>
            {href || unread ? (
              <div className="mt-4 flex flex-wrap items-center gap-4 border-t border-[#e3ebe7] pt-4">
                {href ? <Link href={href} className="text-sm font-semibold text-[#0f6b5b] hover:underline">View request</Link> : null}
                {unread ? <MarkReadButton notificationId={notification.id} /> : null}
              </div>
            ) : null}
          </article>
        );
      })}
    </div>
  );
}
