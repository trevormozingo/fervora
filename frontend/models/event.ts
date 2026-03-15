// ──────────────────────────────────────────────────────────────────────────────
// Event models — based on models/event/*.schema.json
// ──────────────────────────────────────────────────────────────────────────────

export type RSVPStatus = 'pending' | 'accepted' | 'declined';

export interface Invitee {
  uid: string;
  status: RSVPStatus;
}

export interface EventItem {
  id: string;
  authorUid: string;
  title: string;
  description: string | null;
  location: string | null;
  startTime: string;
  endTime: string | null;
  rrule: string | null;
  invitees: Invitee[];
}

export interface CreateEventPayload {
  title: string;
  description?: string | null;
  location?: string | null;
  startTime: string;
  endTime?: string | null;
  inviteeUids?: string[];
}

export interface EventListResponse {
  items: EventItem[];
  count: number;
}
