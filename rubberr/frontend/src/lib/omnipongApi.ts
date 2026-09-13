// Client for the omnipong REST API — the tournament calendar data
// (events synced from USATT & the Stadium League), events only.
//
// NOTE: rubberr is a Next.js app (not Vite), so the base URL is read the
// Next.js way — from a NEXT_PUBLIC_ build-time env var, matching the existing
// NEXT_PUBLIC_API_URL convention used across this codebase. Set
// NEXT_PUBLIC_OMNIPONG_API to the deployed API host (see .env.local.example).
// The default below is an obvious placeholder, NOT a real host.

export const OMNIPONG_API_BASE =
  process.env.NEXT_PUBLIC_OMNIPONG_API || "https://REPLACE-WITH-DEPLOY-HOST";

export type OmnipongEventType =
  | "tournaments"
  | "leagues"
  | "camps"
  | "international";

// Raw event object exactly as GET /events returns it.
export interface OmnipongEvent {
  tournament_id: string;
  status: "Enter" | "Closed" | "Results" | "Info" | "Draws" | string;
  name: string;
  city: string;
  date: string; // "MM/DD/YY" or "MM/DD/YY - MM/DD/YY"
  contact: string;
  ball: string;
  usatt_level: string;
  state_section: string;
  entry_form_pdf: string;
}

// Shape the rubberr calendar/cards already consume.
export interface CalendarTournament {
  tournament_id: string;
  title: string;
  location: string;
  date_range: string;
  status: string;
  flyer_url: string;
  ball?: string;
  usatt_level?: string;
}

export interface FetchEventsParams {
  eventType?: OmnipongEventType;
  state?: string;
  keyword?: string;
  year?: string | number;
}

// Normalize one API event into the field names the UI already expects.
// CalendarView keys its calendar dots off `date_range` and its MM/DD/YY regex,
// which the API's `date` field already satisfies.
function toCalendarTournament(e: OmnipongEvent): CalendarTournament {
  const location = [e.city, e.state_section].filter(Boolean).join(", ");
  return {
    tournament_id: e.tournament_id,
    title: e.name,
    location,
    date_range: e.date,
    status: e.status,
    flyer_url: e.entry_form_pdf,
    ball: e.ball,
    usatt_level: e.usatt_level,
  };
}

// Fetch calendar events from the omnipong REST API. One method, no fallbacks:
// on any API error ({ error } with a 4xx/5xx) it throws cleanly for the caller.
export async function fetchOmnipongEvents(
  params: FetchEventsParams = {},
): Promise<CalendarTournament[]> {
  const { eventType = "tournaments", state, keyword, year } = params;

  const qs = new URLSearchParams({ event_type: eventType });
  if (state) qs.set("state", state);
  if (keyword) qs.set("keyword", keyword);
  if (year !== undefined && year !== "") qs.set("year", String(year));

  const res = await fetch(`${OMNIPONG_API_BASE}/events?${qs.toString()}`);
  const data = await res.json();

  // Errors come back as { error: "..." } with HTTP 400/429/502/503.
  if (!res.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error(
      (data && data.error) || `omnipong API error (HTTP ${res.status})`,
    );
  }
  if (!Array.isArray(data)) {
    throw new Error("omnipong API: expected an array of events");
  }

  return data.map(toCalendarTournament);
}
