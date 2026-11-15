// Typed client for the FastAPI backend. Every call the pages make goes through
// here, so a renamed endpoint or field is a type error in one place.
//
// Set NEXT_PUBLIC_API_URL in .env.local to override the local dev server.
import type {
  ChatInvitation,
  ChatMessage,
  ChatPerson,
  ChatRoom,
  Crowd,
  CrowdLevel,
  Freshness,
  FilteredMenu,
  GroupLocation,
  LocationDetail,
  LocationSummary,
  Menu,
  Profile,
  User,
  RecommendationRequest,
  RecommendationResponse
} from "./types";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number; // 0 = the server could not be reached
  retryAfterSeconds: number | null;

  constructor(
    message: string,
    status: number,
    retryAfterSeconds: number | null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

// Every call sends the session cookie (credentials: "include"), so routes that
// need a logged-in user just work. The cookie is HttpOnly: page code never sees it.
async function request<T>(
  path: string,
  body?: unknown,
  method: "GET" | "POST" | "PATCH" | "DELETE" = body === undefined
    ? "GET"
    : "POST",
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method,
      credentials: "include",
      headers:
        body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(
      "Can’t reach the PackPlate server. Check your connection and try again.",
      0,
      null,
    );
  }

  if (!response.ok) {
    let message = `Something went wrong (${response.status}).`;
    try {
      const payload: unknown = await response.json();
      if (
        typeof payload === "object" &&
        payload !== null &&
        "detail" in payload &&
        typeof payload.detail === "string"
      ) {
        message = payload.detail;
      }
    } catch {
      // keep the generic message
    }
    const retryAfter = Number(response.headers.get("Retry-After"));
    throw new ApiError(
      message,
      response.status,
      Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : null,
    );
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function query(params: Record<string, string | undefined>): string {
  const entries = Object.entries(params).filter(
    (entry): entry is [string, string] => entry[1] !== undefined,
  );
  if (entries.length === 0) return "";
  return `?${new URLSearchParams(entries).toString()}`;
}

export const api = {
  recommendations: (options: RecommendationRequest) =>
    request<RecommendationResponse>("/recommendations", options),

  freshness: () => request<Freshness>("/freshness"),

  locations: () => request<LocationSummary[]>("/locations"),

  location: (id: number) => request<LocationDetail>(`/locations/${id}`),

  menus: (id: number, date?: string) =>
    request<Menu[]>(`/locations/${id}/menus${query({ date })}`),

  // Profiles are sent in the body and are never stored by the server.
  filterMenus: (id: number, profiles: Profile[], date?: string) =>
    request<FilteredMenu[]>(
      `/filters/locations/${id}/menus${query({ date })}`,
      {
        profiles,
      },
    ),

  filterGroup: (profiles: Profile[]) =>
    request<GroupLocation[]>("/filters/group", { profiles }),

  reportCrowd: (id: number, level: CrowdLevel) =>
    request<Crowd>(`/crowd/${id}`, { level }),

  // Accounts. Use lib/session.ts in components: it keeps the header in sync.
  register: (username: string, password: string) =>
    request<User>("/auth/register", { username, password }),

  login: (username: string, password: string) =>
    request<User>("/auth/login", { username, password }),

  logout: () => request<void>("/auth/logout", {}),

  me: () => request<User>("/auth/me"),

  setOpenToChat: (open_to_chat: boolean) =>
    request<User>("/auth/me", { open_to_chat }, "PATCH"),

  deleteAccount: (password: string) =>
    request<void>("/auth/me", { password }, "DELETE"),

  chatRooms: () => request<ChatRoom[]>("/chat/rooms"),

  chatInvitations: () => request<ChatInvitation[]>("/chat/invitations"),

  openToChatPeople: () => request<ChatPerson[]>("/chat/open-to-chat"),

  chatPerson: (username: string) =>
    request<ChatPerson>(`/chat/users/${encodeURIComponent(username)}`),

  createChatRoom: (invitee_ids: number[]) =>
    request<ChatRoom>("/chat/rooms", { invitee_ids }),

  acceptChatInvitation: (id: number) =>
    request<ChatRoom>(`/chat/invitations/${id}/accept`, undefined, "POST"),

  declineChatInvitation: (id: number) =>
    request<void>(`/chat/invitations/${id}/decline`, undefined, "POST"),

  chatMessages: (roomId: number) =>
    request<ChatMessage[]>(`/chat/rooms/${roomId}/messages`),

  sendChatMessage: (roomId: number, text: string) =>
    request<ChatMessage>(`/chat/rooms/${roomId}/messages`, { text }),

  leaveChatRoom: (roomId: number) =>
    request<void>(`/chat/rooms/${roomId}/leave`, undefined, "POST"),
};

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong.";
}
