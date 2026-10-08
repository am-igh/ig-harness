export const money = (n: number | null | undefined, cur = "CHF") => (n == null ? "–" : `${n.toLocaleString("en-GB", { maximumFractionDigits: 0 })} ${cur}`);
export const rate = (r: number | null | undefined) => (r == null ? "–" : r.toFixed(4));
export const signedChf = (n: number) => `${n > 0 ? "+" : n < 0 ? "−" : ""}${Math.abs(n).toLocaleString("en-GB", { maximumFractionDigits: 0 })} CHF`;
export const monthKey = (iso: string) => iso.slice(0, 7);
export const monthName = (key: string) => new Date(key + "-15T12:00:00").toLocaleDateString("en-GB", { month: "long", year: "numeric" });
export const KIND: Record<string, string> = { grant: "Grant", amendment: "Amendment", subgrant: "Sub-grant (money out)" };
export const STATUS_LABEL: Record<string, string> = { todo: "To do", drafting: "Drafting", submitted: "Submitted", accepted: "Accepted" };
