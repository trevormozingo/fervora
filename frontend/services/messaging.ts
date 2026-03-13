/**
 * Messaging service — Firestore-backed direct & group messages.
 *
 * Data model:
 *   conversations/{conversationId}
 *     - participants: string[]          (sorted UIDs — 2 for DM, 2+ for group)
 *     - hiddenFor: string[]             (UIDs who have "deleted" the conversation)
 *     - lastMessage: string
 *     - lastMessageAt: Timestamp
 *     - createdAt: Timestamp
 *
 *   conversations/{conversationId}/messages/{messageId}
 *     - senderUid: string
 *     - text: string
 *     - createdAt: Timestamp
 */

import {
  collection,
  doc,
  addDoc,
  getDoc,
  getDocs,
  query,
  where,
  orderBy,
  limit,
  onSnapshot,
  updateDoc,
  arrayUnion,
  arrayRemove,
  serverTimestamp,
  type Unsubscribe,
  type QuerySnapshot,
  type DocumentData,
  Timestamp,
} from 'firebase/firestore';
import { db } from './firebase';

// ── Types ────────────────────────────────────────────────────────────

export interface Conversation {
  id: string;
  participants: string[];
  lastMessage: string;
  lastMessageAt: Date | null;
  createdAt: Date | null;
  unread: boolean;
}

export interface Message {
  id: string;
  senderUid: string;
  text: string;
  createdAt: Date | null;
}

// ── Helpers ──────────────────────────────────────────────────────────

function toDate(ts: any): Date | null {
  if (ts instanceof Timestamp) return ts.toDate();
  if (ts instanceof Date) return ts;
  return null;
}

// ── Conversation CRUD ────────────────────────────────────────────────

/**
 * Find or create a 1:1 conversation between two users.
 * Returns the conversation ID.
 */
export async function getOrCreateConversation(
  myUid: string,
  otherUid: string,
): Promise<string> {
  const sorted = [myUid, otherUid].sort();

  // Check if conversation already exists
  const q = query(
    collection(db, 'conversations'),
    where('participants', '==', sorted),
    limit(1),
  );
  const snap = await getDocs(q);
  if (!snap.empty) {
    const existing = snap.docs[0];
    // Un-hide if previously deleted
    const hidden: string[] = existing.data().hiddenFor ?? [];
    if (hidden.includes(myUid)) {
      await updateDoc(existing.ref, { hiddenFor: arrayRemove(myUid) });
    }
    return existing.id;
  }

  // Create new conversation
  const ref = await addDoc(collection(db, 'conversations'), {
    participants: sorted,
    hiddenFor: [],
    lastMessage: '',
    lastMessageAt: serverTimestamp(),
    createdAt: serverTimestamp(),
  });
  return ref.id;
}

/**
 * Create a group conversation with multiple participants.
 * Returns the conversation ID.
 */
export async function createGroupConversation(
  participantUids: string[],
): Promise<string> {
  const sorted = [...participantUids].sort();
  const ref = await addDoc(collection(db, 'conversations'), {
    participants: sorted,
    hiddenFor: [],
    lastMessage: '',
    lastMessageAt: serverTimestamp(),
    createdAt: serverTimestamp(),
  });
  return ref.id;
}

/**
 * Listen to the current user's conversations, ordered by most recent message.
 * Filters out conversations the user has hidden (deleted).
 */
export function subscribeToConversations(
  uid: string,
  onData: (conversations: Conversation[]) => void,
): Unsubscribe {
  const q = query(
    collection(db, 'conversations'),
    where('participants', 'array-contains', uid),
    orderBy('lastMessageAt', 'desc'),
  );

  return onSnapshot(q, (snap: QuerySnapshot<DocumentData>) => {
    const conversations: Conversation[] = snap.docs
      .filter((d) => {
        const hidden: string[] = d.data().hiddenFor ?? [];
        return !hidden.includes(uid);
      })
      .map((d) => {
        const lastReadAt = toDate(d.data().lastReadAt?.[uid]);
        const lastMessageAt = toDate(d.data().lastMessageAt);
        const unread = lastMessageAt != null && (lastReadAt == null || lastReadAt < lastMessageAt);
        return {
          id: d.id,
          participants: d.data().participants,
          lastMessage: d.data().lastMessage ?? '',
          lastMessageAt,
          createdAt: toDate(d.data().createdAt),
          unread,
        };
      });
    onData(conversations);
  }, () => {
    // Silently ignore permission-denied (e.g. after sign-out)
  });
}

// ── Messages ─────────────────────────────────────────────────────────

/**
 * Send a message in a conversation.
 * Also updates the conversation's lastMessage/lastMessageAt and
 * un-hides the conversation for all participants.
 */
export async function sendMessage(
  conversationId: string,
  senderUid: string,
  text: string,
): Promise<void> {
  const trimmed = text.trim();
  if (!trimmed) return;

  // Add the message
  await addDoc(
    collection(db, 'conversations', conversationId, 'messages'),
    {
      senderUid,
      text: trimmed,
      createdAt: serverTimestamp(),
    },
  );

  // Update conversation metadata + un-hide for everyone
  await updateDoc(doc(db, 'conversations', conversationId), {
    lastMessage: trimmed,
    lastMessageAt: serverTimestamp(),
    hiddenFor: [],
  });
}

/**
 * Subscribe to messages in a conversation (newest last for chat UI).
 */
export function subscribeToMessages(
  conversationId: string,
  onData: (messages: Message[]) => void,
  messageLimit = 50,
): Unsubscribe {
  const q = query(
    collection(db, 'conversations', conversationId, 'messages'),
    orderBy('createdAt', 'asc'),
    limit(messageLimit),
  );

  return onSnapshot(q, (snap: QuerySnapshot<DocumentData>) => {
    const messages: Message[] = snap.docs.map((d) => ({
      id: d.id,
      senderUid: d.data().senderUid,
      text: d.data().text,
      createdAt: toDate(d.data().createdAt),
    }));
    onData(messages);
  });
}

/**
 * Hide a conversation for the current user (soft-delete).
 * The conversation and messages remain for other participants.
 * If someone sends a new message, it will re-appear.
 */
export async function hideConversation(
  conversationId: string,
  uid: string,
): Promise<void> {
  await updateDoc(doc(db, 'conversations', conversationId), {
    hiddenFor: arrayUnion(uid),
  });
}

/**
 * Mark a conversation as read by the current user.
 */
export async function markConversationRead(
  conversationId: string,
  uid: string,
): Promise<void> {
  await updateDoc(doc(db, 'conversations', conversationId), {
    [`lastReadAt.${uid}`]: serverTimestamp(),
  });
}

/**
 * Get display participants (everyone except the current user).
 */
export function getOtherParticipants(
  conversation: Conversation,
  myUid: string,
): string[] {
  return conversation.participants.filter((p) => p !== myUid);
}

/**
 * Get the other participant's UID from a conversation (1:1 shortcut).
 */
export function getOtherParticipant(
  conversation: Conversation,
  myUid: string,
): string {
  return conversation.participants.find((p) => p !== myUid) ?? '';
}
