/**
 * Events service — CRUD + RSVP for workout events / meeting invites.
 */

import { apiFetch } from './api';
import type { EventItem, EventListResponse, CreateEventPayload } from '@/models/event';

/** Create a new event. */
export async function createEvent(data: CreateEventPayload): Promise<EventItem> {
  return apiFetch<EventItem>('/events', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
}

/** List events created by the current user. */
export async function getMyEvents(): Promise<EventListResponse> {
  return apiFetch<EventListResponse>('/events');
}

/** List events the current user is invited to. */
export async function getInvitedEvents(): Promise<EventListResponse> {
  return apiFetch<EventListResponse>('/events/invited');
}

/** Get a single event by ID. */
export async function getEvent(eventId: string): Promise<EventItem> {
  return apiFetch<EventItem>(`/events/${encodeURIComponent(eventId)}`);
}

/** Delete an event (only the creator can delete). */
export async function deleteEvent(eventId: string): Promise<void> {
  return apiFetch<void>(`/events/${encodeURIComponent(eventId)}`, { method: 'DELETE' });
}

/** RSVP to an event (accept or decline). */
export async function rsvpEvent(
  eventId: string,
  status: 'accepted' | 'declined',
): Promise<EventItem> {
  return apiFetch<EventItem>(`/events/${encodeURIComponent(eventId)}/rsvp`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  });
}
