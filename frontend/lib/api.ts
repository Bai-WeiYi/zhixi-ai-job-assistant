import type {
  AnalysisListItem,
  AnalysisResponse,
  AuthResponse,
  InterviewAttempt,
  KnowledgeDocument,
  ParsedResume,
  UsageSummary,
  User,
} from "@/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const ACCESS_TOKEN_KEY = "zhixi_access_token_v1";
const REQUEST_TIMEOUT_MS = 90_000;

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly retryAfter?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function getAccessToken() {
  return typeof window === "undefined" ? null : window.localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function setAccessToken(token: string) {
  window.localStorage.setItem(ACCESS_TOKEN_KEY, token);
}

export function clearAccessToken() {
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(ACCESS_TOKEN_KEY);
  }
}

async function request<T>(
  path: string,
  options?: RequestInit,
  timeoutMs = REQUEST_TIMEOUT_MS,
): Promise<T> {
  const token = getAccessToken();
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      signal: options?.signal ?? controller.signal,
      headers: {
        ...(options?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options?.headers,
      },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("请求超时，免费服务可能仍在唤醒，请稍后重试");
    }
    throw new ApiError("无法连接后端；免费服务首次访问可能需要约一分钟唤醒");
  } finally {
    window.clearTimeout(timeout);
  }

  if (!response.ok) {
    if (
      response.status === 401 &&
      path !== "/api/auth/login" &&
      path !== "/api/auth/register"
    ) {
      clearAccessToken();
      window.dispatchEvent(new Event("auth:unauthorized"));
    }
    const payload = await response.json().catch(() => null);
    const retryAfter = Number(response.headers.get("Retry-After")) || undefined;
    const detail = payload?.detail;
    throw new ApiError(
      (typeof detail === "object" && detail?.message) ||
        (typeof detail === "string" ? detail : "请求失败，请稍后重试"),
      response.status,
      retryAfter,
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export function registerUser(email: string, password: string) {
  return request<AuthResponse>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function loginUser(email: string, password: string) {
  return request<AuthResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function getCurrentUser() {
  // 登录状态检查应快速失败，避免后端未启动时长时间停留在加载页。
  return request<User>("/api/auth/me", undefined, 10_000);
}

export function getUsage() {
  return request<UsageSummary>("/api/usage");
}

export function createAnalysis(resumeText: string, jobDescription: string) {
  return request<AnalysisResponse>("/api/analyses", {
    method: "POST",
    body: JSON.stringify({
      resume_text: resumeText,
      job_description: jobDescription,
    }),
  });
}

export function parseResume(file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return request<ParsedResume>("/api/resumes/parse", {
    method: "POST",
    body: formData,
  });
}

export function listAnalyses() {
  return request<AnalysisListItem[]>("/api/analyses");
}

export function getAnalysis(id: string) {
  return request<AnalysisResponse>(`/api/analyses/${id}`);
}

export function listInterviewAttempts(analysisId: number) {
  return request<InterviewAttempt[]>(`/api/analyses/${analysisId}/interview-attempts`);
}

export function createInterviewAttempt(
  analysisId: number,
  questionNumber: number,
  answerText: string,
) {
  return request<InterviewAttempt>(
    `/api/analyses/${analysisId}/questions/${questionNumber}/attempts`,
    {
      method: "POST",
      body: JSON.stringify({ answer_text: answerText }),
    },
  );
}

export function deleteAnalysis(id: number) {
  return request<void>(`/api/analyses/${id}`, { method: "DELETE" });
}

export function createKnowledgeDocument(
  title: string,
  text: string,
  file: File | null,
) {
  const formData = new FormData();
  formData.append("title", title);
  if (file) {
    formData.append("file", file);
  } else {
    formData.append("text", text);
  }
  return request<KnowledgeDocument>("/api/knowledge/documents", {
    method: "POST",
    body: formData,
  });
}

export function listKnowledgeDocuments() {
  return request<KnowledgeDocument[]>("/api/knowledge/documents");
}

export function deleteKnowledgeDocument(id: number) {
  return request<void>(`/api/knowledge/documents/${id}`, { method: "DELETE" });
}
