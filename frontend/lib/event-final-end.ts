/** Final-end input is Singapore local time, independent of browser/server locale. */
export function finalEndInput(value?: string | null): string {
  if (!value) return "";
  const instant = new Date(value);
  if (Number.isNaN(instant.getTime())) return "";
  return new Date(instant.getTime() + 8 * 60 * 60 * 1000).toISOString().slice(0, 16);
}

export function parseFinalEndInput(value: FormDataEntryValue | null): string | null {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) return null;
  const instant = new Date(`${value}:00+08:00`);
  if (Number.isNaN(instant.getTime()) || finalEndInput(instant.toISOString()) !== value) return null;
  return instant.toISOString();
}
