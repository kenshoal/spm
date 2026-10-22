/** Client-safe minute labels, including the valid booking endpoint 24:00. */
export function formatBookingMinute(value: number): string {
  return `${String(Math.floor(value / 60)).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}`;
}
