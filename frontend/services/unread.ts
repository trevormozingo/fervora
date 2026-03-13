import { useState, useEffect } from 'react';
import { getUid } from '@/services/auth';
import { subscribeToConversations, type Conversation } from '@/services/messaging';

let _unreadCount = 0;
let _listeners: Set<(count: number) => void> = new Set();

function notify(count: number) {
  _unreadCount = count;
  _listeners.forEach((fn) => fn(count));
}

/** Subscribe to the global unread message count. Returns unsubscribe. */
export function useUnreadCount(): number {
  const [count, setCount] = useState(_unreadCount);
  useEffect(() => {
    _listeners.add(setCount);
    setCount(_unreadCount);
    return () => { _listeners.delete(setCount); };
  }, []);
  return count;
}

let _unsub: (() => void) | null = null;

/** Start listening for unread conversations. Call once after auth. */
export function startUnreadListener() {
  stopUnreadListener();
  const uid = getUid();
  if (!uid) return;
  _unsub = subscribeToConversations(uid, (convos: Conversation[]) => {
    const unread = convos.filter((c) => c.unread).length;
    notify(unread);
  });
}

export function stopUnreadListener() {
  _unsub?.();
  _unsub = null;
  notify(0);
}
