export type Category = {
  id: string;
  label: string;
  group: string;
  kind: "income" | "expense";
};
export type Entry = {
  id: number;
  request_id: string;
  kind: "income" | "expense";
  category: string;
  amount_cents: number;
  on_date: string;
  description: string;
  essential: boolean;
  payment_method: string;
};
export type Movement = Entry | (Omit<Entry, "kind"> & { kind: "contribution"; goal_id: number });
export type Budget = {
  id: number;
  month: string;
  category: string;
  limit_cents: number;
};
export type Goal = {
  id: number;
  title: string;
  motivation: string;
  target_cents: number;
  deadline: string;
};
export type Contribution = {
  id: number;
  goal_id: number;
  request_id: string;
  amount_cents: number;
  on_date: string;
};
export type Report = {
  available_cents?: number;
  reserved_total_cents?: number;
  recorded_total_cents?: number;
  week_start: string;
  week_end: string;
  partial: boolean;
  income_cents: number;
  expense_cents: number;
  net_cents: number;
  reserved_cents: number;
  unreserved_flow_cents: number;
  required_weekly_cents: number;
  goal_gap_cents: number;
  note: string;
  categories: {
    category: string;
    amount_cents: number;
    essential_cents?: number;
  }[];
  budgets: (Budget & {
    spent_cents: number;
    remaining_cents: number;
    status: string;
  })[];
  goals: (Goal & {
    saved_cents: number;
    remaining_cents: number;
    required_weekly_cents: number;
    status: string;
  })[];
};
export type Insight = { summary: string; suggestions: string[] };
export const money = (cents: number) =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(
    cents / 100,
  );
export const localDate = () =>
  new Intl.DateTimeFormat("sv-SE", { timeZone: "America/Sao_Paulo" }).format(
    new Date(),
  );
export const month = () => localDate().slice(0, 7) + "-01";
export function cents(text: string): number {
  if (!/^\d{1,9}([,.]\d{1,2})?$/.test(text.trim()))
    throw new Error("Informe um valor como 125,50, sem separador de milhar.");
  const [whole, fraction = ""] = text.trim().replace(",", ".").split(".");
  const result = Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
  if (!Number.isSafeInteger(result) || result <= 0 || result > 10_000_000_000)
    throw new Error("Informe um valor positivo dentro do limite.");
  return result;
}
export const inputMoney = (value: number) =>
  (value / 100).toFixed(2).replace(".", ",");
export function isoDate(text: string): string {
  if (
    !/^\d{4}-\d{2}-\d{2}$/.test(text) ||
    !Number.isFinite(Date.parse(text)) ||
    new Date(text).toISOString().slice(0, 10) !== text
  )
    throw new Error("Use uma data válida no formato AAAA-MM-DD.");
  return text;
}
