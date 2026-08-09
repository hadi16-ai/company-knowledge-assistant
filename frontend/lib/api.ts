import type { UserRole } from "@/lib/roles";

export type { UserRole };

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const API_PREFIX = "/api/v1";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export interface AuthUser {
  id: string;
  org_id: string;
  org_name: string;
  email: string;
  full_name: string;
  role: UserRole;
  expires_at: string | null;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export type DocumentStatus = "pending" | "processing" | "ready" | "failed";

export interface DocumentRecord {
  id: string;
  filename: string;
  status: DocumentStatus;
  chunk_count: number;
  page_count: number;
  size_bytes: number;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentViewUrl {
  url: string;
  filename: string;
  page_count: number;
  expires_in_seconds: number;
}

export interface DocumentUploadAccepted {
  document_id: string;
  filename: string;
  status: DocumentStatus;
  message: string;
}

export interface SourceCitation {
  filename: string;
  page_number: number | null;
  excerpt: string;
  score: number;
  document_id: string | null;
}

export interface Conversation {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationMessage {
  id: string;
  query: string;
  answer: string;
  created_at: string;
}

export interface OrgMember {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  expires_at: string | null;
  created_at: string;
}

export interface UpdateMemberRequest {
  role?: UserRole;
  is_active?: boolean;
  expires_at?: string | null;
}

export interface Invitation {
  id: string;
  role: UserRole;
  email_hint: string | null;
  created_at: string;
  expires_at: string;
  used_at: string | null;
}

export interface CreateInvitationRequest {
  role: UserRole;
  email_hint?: string;
  expires_in_hours?: number;
}

export interface InvitationCreated {
  id: string;
  role: UserRole;
  email_hint: string | null;
  expires_at: string;
  token: string;
}

const ACCESS_TOKEN_KEY = "cka_access_token";
const REFRESH_TOKEN_KEY = "cka_refresh_token";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function storeTokens(tokens: TokenResponse): void {
  window.localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
  window.localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
}

export function clearTokens(): void {
  window.localStorage.removeItem(ACCESS_TOKEN_KEY);
  window.localStorage.removeItem(REFRESH_TOKEN_KEY);
}

async function parseErrorDetail(response: Response): Promise<string> {
  try {
    const body = await response.json();
    return body.detail ?? response.statusText;
  } catch {
    return response.statusText;
  }
}

async function refreshAccessToken(): Promise<boolean> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;

  const response = await fetch(`${API_BASE_URL}${API_PREFIX}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });

  if (!response.ok) {
    clearTokens();
    return false;
  }

  const tokens: TokenResponse = await response.json();
  storeTokens(tokens);
  return true;
}

interface RequestOptions extends RequestInit {
  authenticated?: boolean;
}

async function apiFetch(path: string, options: RequestOptions = {}): Promise<Response> {
  const { authenticated = true, headers, ...rest } = options;

  const buildHeaders = (): HeadersInit => {
    const merged: Record<string, string> = { ...(headers as Record<string, string>) };
    if (authenticated) {
      const token = getAccessToken();
      if (token) merged["Authorization"] = `Bearer ${token}`;
    }
    return merged;
  };

  let response = await fetch(`${API_BASE_URL}${API_PREFIX}${path}`, {
    ...rest,
    headers: buildHeaders(),
  });

  if (response.status === 401 && authenticated) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      response = await fetch(`${API_BASE_URL}${API_PREFIX}${path}`, {
        ...rest,
        headers: buildHeaders(),
      });
    }
  }

  return response;
}

export async function apiJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await apiFetch(path, options);
  if (!response.ok) {
    throw new ApiError(await parseErrorDetail(response), response.status);
  }
  return response.json() as Promise<T>;
}

export interface RegisterParams {
  email: string;
  password: string;
  fullName: string;
  // Exactly one of these two must be set: create a new organization
  // (becomes its Company Admin), or join an existing one via invite.
  organizationName?: string;
  inviteToken?: string;
}

export const authApi = {
  register: ({ email, password, fullName, organizationName, inviteToken }: RegisterParams) =>
    apiJson<TokenResponse>("/auth/register", {
      method: "POST",
      authenticated: false,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email,
        password,
        full_name: fullName,
        organization_name: organizationName,
        invite_token: inviteToken,
      }),
    }),
  login: (email: string, password: string) =>
    apiJson<TokenResponse>("/auth/login", {
      method: "POST",
      authenticated: false,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }),
  me: () => apiJson<AuthUser>("/auth/me"),
  createWorkspace: (organizationName: string) =>
    apiJson<TokenResponse>("/auth/create-workspace", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ organization_name: organizationName }),
    }),
};

async function uploadFile<T>(path: string, method: "POST" | "PUT", file: File): Promise<T> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await apiFetch(path, { method, body: formData });
  if (!response.ok) {
    throw new ApiError(await parseErrorDetail(response), response.status);
  }
  return response.json();
}

export const documentsApi = {
  list: () => apiJson<DocumentRecord[]>("/documents"),
  get: (id: string) => apiJson<DocumentRecord>(`/documents/${id}`),
  upload: (file: File) => uploadFile<DocumentUploadAccepted>("/documents", "POST", file),
  replace: (id: string, file: File) => uploadFile<DocumentUploadAccepted>(`/documents/${id}`, "PUT", file),
  reindex: (id: string) =>
    apiJson<DocumentUploadAccepted>(`/documents/${id}/reindex`, { method: "POST" }),
  delete: async (id: string): Promise<void> => {
    const response = await apiFetch(`/documents/${id}`, { method: "DELETE" });
    if (!response.ok) {
      throw new ApiError(await parseErrorDetail(response), response.status);
    }
  },
  getViewUrl: (id: string) => apiJson<DocumentViewUrl>(`/documents/${id}/view-url`),
};

export const conversationsApi = {
  list: () => apiJson<Conversation[]>("/conversations"),
  create: () => apiJson<Conversation>("/conversations", { method: "POST" }),
  messages: (id: string) => apiJson<ConversationMessage[]>(`/conversations/${id}/messages`),
  remove: async (id: string): Promise<void> => {
    const response = await apiFetch(`/conversations/${id}`, { method: "DELETE" });
    if (!response.ok) {
      throw new ApiError(await parseErrorDetail(response), response.status);
    }
  },
};

export const usersApi = {
  list: () => apiJson<OrgMember[]>("/users"),
  update: (id: string, payload: UpdateMemberRequest) =>
    apiJson<OrgMember>(`/users/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
};

export const invitationsApi = {
  list: () => apiJson<Invitation[]>("/invitations"),
  create: (payload: CreateInvitationRequest) =>
    apiJson<InvitationCreated>("/invitations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  revoke: async (id: string): Promise<void> => {
    const response = await apiFetch(`/invitations/${id}`, { method: "DELETE" });
    if (!response.ok) {
      throw new ApiError(await parseErrorDetail(response), response.status);
    }
  },
};

export interface StreamedAnswerHandlers {
  onSources?: (sources: SourceCitation[]) => void;
  onToken?: (text: string) => void;
  onDone?: (answer: string) => void;
  onError?: (message: string) => void;
}

/** Streams a chat answer via Server-Sent Events, invoking the given handlers as events arrive. */
export async function streamAsk(
  question: string,
  conversationId: string,
  handlers: StreamedAnswerHandlers
): Promise<void> {
  const response = await apiFetch("/chat/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, conversation_id: conversationId }),
  });

  if (!response.ok || !response.body) {
    handlers.onError?.(await parseErrorDetail(response));
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";

    for (const rawEvent of events) {
      const eventLine = rawEvent.split("\n").find((line) => line.startsWith("event: "));
      const dataLine = rawEvent.split("\n").find((line) => line.startsWith("data: "));
      if (!eventLine || !dataLine) continue;

      const eventName = eventLine.replace("event: ", "").trim();
      const data = JSON.parse(dataLine.replace("data: ", ""));

      if (eventName === "sources") handlers.onSources?.(data.sources);
      else if (eventName === "token") handlers.onToken?.(data.text);
      else if (eventName === "done") handlers.onDone?.(data.answer);
      else if (eventName === "error") handlers.onError?.(data.message);
    }
  }
}
