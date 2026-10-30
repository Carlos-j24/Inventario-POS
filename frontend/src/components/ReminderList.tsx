import type { Reminder } from "../api";
import { REMINDER_LABELS, dueLabel, reminderTarget } from "../maintenance";
import { todayIso } from "../pages/Sales";

/** Recordatorios de mantenimiento (spec 012): de la moto, o los que creó una orden al entregarse. */
export default function ReminderList({ reminders, label }: { reminders: Reminder[]; label: string }) {
  const today = todayIso();
  return (
    <ul className="plain-list small" aria-label={label}>
      {reminders.map((r) => {
        const open = r.status === "PENDING" || r.status === "NOTIFIED";
        return (
          <li key={r.id} className={open ? "" : "muted"}>
            <strong>{r.plan.name}</strong>: {reminderTarget(r)}
            {" · "}{REMINDER_LABELS[r.status]}
            {open && <> · {dueLabel(r, today)}</>}
            {r.done_order && <> · con la orden {r.done_order}</>}
            {r.note && <> · <em>{r.note}</em></>}
          </li>
        );
      })}
    </ul>
  );
}
