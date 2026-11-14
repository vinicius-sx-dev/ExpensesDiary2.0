import { deviceId } from "./session";
import { useAuth } from "../stores/auth";

const BASE = (
  process.env.EXPO_PUBLIC_API_URL || "http://localhost:8000"
).trim().replace(/\/+$/, "");
let refreshing: { generation: number; promise: Promise<void> } | null = null;
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
async function request<T>(
  path: string,
  method: string,
  body?: unknown,
  access?: string | null,
): Promise<T> {
  if (!/^https?:\/\/[^/\s]+/.test(BASE))
    throw new Error("EXPO_PUBLIC_API_URL deve incluir http:// ou https:// e o endereço da API.");
  if (!__DEV__ && !BASE.startsWith("https://"))
    throw new Error("Configure uma API HTTPS para a versão de produção.");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), path.startsWith("/reports/weekly/insights") ? 50000 : path.startsWith("/imports/preview") ? 45000 : 25000);
  const isForm = typeof FormData !== "undefined" && body instanceof FormData;
  try {
    const response = await fetch(BASE + path, {
      method,
      signal: controller.signal,
      headers: {
        ...(isForm ? {} : { "Content-Type": (typeof Blob !== "undefined" && body instanceof Blob) || body instanceof Uint8Array ? "application/octet-stream" : "application/json" }),
        "X-Device-ID": await deviceId(),
        ...(access ? { Authorization: `Bearer ${access}` } : {}),
      },
      ...(body !== undefined ? { body: isForm || (typeof Blob !== "undefined" && body instanceof Blob) || body instanceof Uint8Array ? body as BodyInit : JSON.stringify(body) } : {}),
    });
    let data: any = null;
    const text = response.status === 204 ? "" : await response.text();
    if (text) {
      try { data = JSON.parse(text); }
      catch {
        throw new ApiError(
          response.status === 400 && text.trim() === "Invalid host header"
            ? "Host da API não permitido. Confira ALLOWED_HOSTS no backend."
            : `A API retornou uma resposta inválida (HTTP ${response.status}).`,
          response.status,
        );
      }
    }
    if (!response.ok)
      throw new ApiError(
        response.status === 429
          ? `Muitas tentativas. Aguarde ${response.headers.get("Retry-After") || "alguns"} segundos.`
          : typeof data?.detail === "string"
            ? data.detail
            : "Não foi possível concluir a solicitação.",
        response.status,
      );
    return data as T;
  } catch (e) {
    if (e instanceof ApiError) throw e;
    throw new Error(
      "Não foi possível conectar. Confira sua conexão e tente novamente.",
    );
  } finally {
    clearTimeout(timer);
  }
}
async function refreshSession() {
  const { refresh, generation } = useAuth.getState();
  if (!refreshing || refreshing.generation !== generation) {
    const promise = (async () => {
      if (!refresh) throw new ApiError("Entre novamente.", 401);
      try {
        const pair = await request<{
          access_token: string;
          refresh_token: string;
        }>("/auth/refresh", "POST", { refresh_token: refresh });
        if (useAuth.getState().generation !== generation)
          throw new ApiError("Sessão encerrada.", 401);
        await useAuth
          .getState()
          .setTokens(pair.access_token, pair.refresh_token);
      } catch (e) {
        if (e instanceof ApiError && e.status === 401 &&
            useAuth.getState().generation === generation)
          await useAuth.getState().clear();
        throw e;
      }
    })().finally(() => {
      if (refreshing?.generation === generation) refreshing = null;
    });
    refreshing = { generation, promise };
  }
  return refreshing.promise;
}
export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const generation = useAuth.getState().generation;
  const checkSession = () => {
    if (useAuth.getState().generation !== generation)
      throw new ApiError("Sessão encerrada. Faça a operação novamente.", 401);
  };
  if (!useAuth.getState().access && useAuth.getState().refresh)
    await refreshSession();
  checkSession();
  try {
    const result = await request<T>(path, method, body, useAuth.getState().access);
    checkSession();
    return result;
  } catch (e) {
    checkSession();
    if (
      !(e instanceof ApiError) ||
      e.status !== 401 ||
      !useAuth.getState().refresh
    )
      throw e;
    await refreshSession();
    checkSession();
    const result = await request<T>(path, method, body, useAuth.getState().access);
    checkSession();
    return result;
  }
}
export const publicApi = <T>(path: string, body: unknown) =>
  request<T>(path, "POST", body);
