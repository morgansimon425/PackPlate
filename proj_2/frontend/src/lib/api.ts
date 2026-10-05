// Base URL of the FastAPI backend. Set NEXT_PUBLIC_API_URL in .env.local
// to override; defaults to the local dev server.
export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
