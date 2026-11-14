import { create } from "zustand";
import { vault } from "../lib/session";

let storageQueue: Promise<void> = Promise.resolve();
function serialize(work: () => Promise<void>) {
  const next = storageQueue.then(work, work);
  storageQueue = next.catch(() => {});
  return next;
}
type State = {
  access: string | null;
  refresh: string | null;
  ready: boolean;
  generation: number;
  setTokens: (a: string, r: string) => Promise<void>;
  clear: () => Promise<void>;
  hydrate: () => Promise<void>;
};
export const useAuth = create<State>((set, get) => ({
  access: null,
  refresh: null,
  ready: false,
  generation: 0,
  setTokens: async (access, refresh) => {
    const generation = get().generation;
    await serialize(async () => {
      if (get().generation !== generation) return;
      await vault.set("refresh", refresh);
      if (get().generation === generation)
        set({ access, refresh, ready: true });
    });
  },
  clear: async () => {
    set({
      access: null,
      refresh: null,
      ready: true,
      generation: get().generation + 1,
    });
    await serialize(() => vault.remove("refresh"));
  },
  hydrate: async () => {
    const generation = get().generation;
    try {
      const refresh = await vault.get("refresh");
      if (get().generation === generation) set({ refresh, ready: true });
    } catch {
      if (get().generation === generation) set({ ready: true });
    }
  },
}));
