/** Mirrors the Pydantic models in backend/app/models.py. */

export type Transport = "foot" | "bike" | "car";

export interface City {
  name: string;
  display_name: string;
  lat: number;
  lon: number;
  country: string | null;
}

export interface Point {
  lat: number;
  lon: number;
}

export interface RankedPlace {
  id: string;
  name: string;
  lat: number;
  lon: number;
  category: string;
  tags: string[];
  base_score: number;
  address: string | null;
  website: string | null;
  wikidata: string | null;
  opening_hours: string | null;
  score: number;
  reason: string;
  suggested_minutes: number;
  ranked_by: "ai" | "heuristic";
}

export interface MemberPosition {
  lat: number;
  lon: number;
  accuracy_m: number | null;
  updated_at: number;
}

export interface Member {
  id: string;
  display_name: string;
  joined_at: number;
  online: boolean;
  position: MemberPosition | null;
  distance_to_meeting_m: number | null;
  distance_to_next_stop_m: number | null;
  budget?: number | null;
  currency?: string;
  preferences?: string[];
  constraints?: string[];
}

export interface MediaItem { id: string; filename: string; category: string; note: string; location: string | null; day: number | null; }
export interface Expense { id: string; title: string; amount: number; currency: string; paid_by: string; participant_ids: string[]; shares: Record<string, number>; status: "proposed" | "approved" | "declined"; }
export interface PollOption { id: string; label: string; voter_ids: string[]; }
export interface TripPoll { id: string; question: string; options: PollOption[]; status: "open" | "closed"; winner_option_id: string | null; }
export interface MemoryEntry { id: string; title: string; description: string; occurred_at: number; media_ids: string[]; }
export interface PackingList { personal: string[]; shared: string[]; assumptions: string[]; }

export interface Stop {
  order: number;
  place: RankedPlace;
  distance_from_previous_m: number;
  travel_seconds_from_previous: number;
  distance_from_meeting_m: number;
}

export interface Leg {
  from_index: number;
  to_index: number;
  distance_m: number;
  duration_s: number;
}

export interface Plan {
  generated_at: number;
  transport: Transport;
  meeting_point: Point;
  stops: Stop[];
  legs: Leg[];
  total_distance_m: number;
  total_travel_seconds: number;
  total_visit_seconds: number;
  routing_provider: "openrouteservice" | "osrm" | "straight-line";
  ranked_by: "ai" | "heuristic";
  summary: string;
}

export interface Group {
  id: string;
  name: string;
  join_code: string;
  city: City;
  created_at: number;
  interests: string[];
  transport: Transport;
  members: Member[];
  meeting_point: Point | null;
  plan: Plan | null;
  media: MediaItem[];
  expenses: Expense[];
  polls: TripPoll[];
  memories: MemoryEntry[];
}

/** Everything the server can push down the group socket. */
export type SocketEvent =
  | { type: "snapshot"; group: Group }
  | {
      type: "position";
      member_id: string;
      position: MemberPosition | null;
      distance_to_meeting_m: number | null;
      distance_to_next_stop_m: number | null;
    }
  | { type: "presence"; member_id: string; online: boolean }
  | { type: "member_joined"; member: Member }
  | { type: "member_left"; member_id: string }
  | { type: "plan"; plan: Plan; members?: Member[] }
  | { type: "pong" }
  | { type: "error"; detail: string };

export type ConnectionState = "idle" | "connecting" | "live" | "reconnecting";
