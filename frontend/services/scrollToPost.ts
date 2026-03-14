/**
 * Simple global store for "scroll to post" intent.
 * Set before navigating to the profile tab; the profile screen
 * reads and clears it on focus.
 */

type ScrollIntent = {
  postId: string;
  section: 'comments' | 'reactions';
  reactionType?: string;
} | null;

let _intent: ScrollIntent = null;

export function setScrollToPostIntent(
  postId: string,
  section: 'comments' | 'reactions',
  reactionType?: string,
) {
  _intent = { postId, section, reactionType };
}

export function consumeScrollToPostIntent(): ScrollIntent {
  const intent = _intent;
  _intent = null;
  return intent;
}
