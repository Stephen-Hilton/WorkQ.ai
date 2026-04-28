import { CognitoAuth } from "../auth/cognito";
import type { Record } from "../types";

const BASE = __WORKQ_API_URL__.replace(/\/+$/, "");

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, body: unknown) {
    super(`API ${status}`);
    this.status = status;
    this.body = body;
  }
}

export class ConflictError extends ApiError {
  current: Record;
  constructor(body: Record) {
    super(409, body);
    this.current = body;
  }
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await CognitoAuth.instance.getJwt();
  const resp = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(init.headers ?? {}),
    },
  });
  let body: unknown = null;
  try {
    body = await resp.json();
  } catch {
    body = null;
  }
  if (resp.status === 409) {
    throw new ConflictError(body as Record);
  }
  if (!resp.ok) {
    throw new ApiError(resp.status, body);
  }
  return body as T;
}

export const api = {
  getId: (reqid: string) => call<Record>(`/id/${encodeURIComponent(reqid)}`),
  listAll: () => call<{ items: Record[]; count: number }>("/status/all"),
  listStatus: (status: string) =>
    call<{ items: Record[]; count: number }>(`/status/${encodeURIComponent(status)}`),
  create: (body: Partial<Record>) =>
    call<Record>("/id", { method: "POST", body: JSON.stringify(body) }),
  update: (
    reqid: string,
    body: Partial<Record> & { expected_timelog_len?: number },
  ) =>
    call<Record>(`/id/${encodeURIComponent(reqid)}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  remove: (reqid: string) =>
    call<{ deleted: boolean }>(`/id/${encodeURIComponent(reqid)}`, { method: "DELETE" }),
};
