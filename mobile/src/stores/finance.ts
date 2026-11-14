import { create } from "zustand";
import { api } from "../lib/api";
import { useAuth } from "./auth";
import { Category, Movement, Goal, Budget, Report, month } from "../lib/types";

type State = {
  categories: Category[];
  entries: Movement[];
  goals: Goal[];
  budgets: Budget[];
  report: Report | null;
  loading: boolean;
  error: string | null;
  load: () => Promise<void>;
  loadMore: () => Promise<void>;
  more: boolean;
  reset: () => void;
};
const empty = {
  categories: [],
  entries: [],
  goals: [],
  budgets: [],
  report: null,
  loading: false,
  error: null,
  more: true,
};
export const useFinance = create<State>((set, get) => ({
  ...empty,
  reset: () => set(empty),
  load: async () => {
    const generation = useAuth.getState().generation;
    set({ loading: true, error: null });
    try {
      const [categories, entries, goals, budgets, report] = await Promise.allSettled([
        api<Category[]>("/categories"),
        api<Movement[]>("/movements"),
        api<Goal[]>("/goals"),
        api<Budget[]>("/budgets?month=" + month()),
        api<Report>("/reports/weekly"),
      ]);
      if (useAuth.getState().generation === generation)
        set({
          categories: categories.status === "fulfilled" ? categories.value : [],
          entries: entries.status === "fulfilled" ? entries.value : [],
          goals: goals.status === "fulfilled" ? goals.value : [],
          budgets: budgets.status === "fulfilled" ? budgets.value : [],
          report: report.status === "fulfilled" ? report.value : null,
          more: entries.status === "fulfilled" && entries.value.length === 50,
          error: [categories, entries, goals, budgets, report].some(r => r.status === "rejected")
            ? "Alguns dados não puderam ser atualizados. Tente atualizar novamente." : null,
        });
    } catch (e) {
      if (useAuth.getState().generation === generation)
        set({ error: e instanceof Error ? e.message : "Erro ao atualizar" });
    } finally {
      if (useAuth.getState().generation === generation) set({ loading: false });
    }
  },
  loadMore: async () => {
    if (get().loading || !get().more) return;
    const generation = useAuth.getState().generation;
    set({ loading: true });
    try {
      const next = await api<Movement[]>(
        "/movements?offset=" + get().entries.length,
      );
      if (useAuth.getState().generation === generation)
        set({ entries: [...get().entries, ...next], more: next.length === 50 });
    } catch (e) {
      if (useAuth.getState().generation === generation)
        set({ error: e instanceof Error ? e.message : "Erro ao carregar" });
    } finally {
      if (useAuth.getState().generation === generation) set({ loading: false });
    }
  },
}));
useAuth.subscribe((state, prev) => {
  if (state.generation !== prev.generation) useFinance.getState().reset();
});
