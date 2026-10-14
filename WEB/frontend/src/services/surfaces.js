// Copyright © 2026 Wole Akpose / 6igma Health Inc.
// All rights reserved. ALAFIA — proprietary and confidential.

/**
 * One name, so the writer and the navigation cannot disagree about it.
 *
 * `Layout` asks `GET /users/me/surfaces` once per user. Anything that changes
 * what the record justifies — declaring a condition, setting a therapy switch
 * — must say so, or the patient sees the old navigation until they reload.
 *
 * OPEN_ITEMS 37b/38c/39b: this was open through three deploys and got worse
 * with the switch, because a patient can now state "I am NOT on this" and then
 * watch the screen they just retired stay on screen. A control whose effect is
 * invisible reads as a control that did nothing (§3ar).
 *
 * The event carries NO payload on purpose. The surface rule is the server's
 * (§3) — recomputing it client-side would be a second implementation of a
 * clinical decision, which is the drift this codebase keeps paying for.
 */
export const SURFACES_CHANGED = 'alafia:surfaces-changed';

/** Call after any write that could change which screens the record justifies. */
export function announceSurfacesChanged() {
  window.dispatchEvent(new CustomEvent(SURFACES_CHANGED));
}
