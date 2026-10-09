/* Copyright © 2026 Wole Akpose / 6igma Health Inc.
   All rights reserved. ALAFIA — proprietary and confidential.

   The chat stream had no timeout at all.

   §3ae's ladder is client 285s < OLLAMA_TIMEOUT 290s < Cloud Run 300s, and
   `AIChat.jsx` called `fetch('/api/v1/ai/chat/stream')` with no
   AbortController and no timeout — so none of it applied on the one AI surface
   patients actually use. A stalled stream hung forever behind an empty
   assistant bubble: nothing to retry, no way to know it had failed.

   What these pin is the part that is easy to get wrong. The timeout is IDLE,
   not total: iOS `URLRequest.timeoutInterval` and Android's OkHttp
   `readTimeout` are both idle timers at this same 285s, and the tool loop goes
   deliberately quiet between rounds. A wall-clock cap would cut off an answer
   the server was still writing — reproducing §3ae's failure rather than
   preventing it — and it would pass a naive "it aborts eventually" test. */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { AI_TIMEOUT_MS } from '../services/api';

/* The reader loop's shape, lifted from AIChat.jsx: arm an idle timer before
   the request, reset it on every chunk, clear it in `finally`. Exercised
   directly because mounting the page would drag in personas, CSRF, auth
   refresh and markdown rendering — none of which is what broke. */
function streamWithIdleTimeout(chunks, { onAbort } = {}) {
  const controller = new AbortController();
  let idleTimer = null;
  let timedOut = false;

  const resetIdleTimer = () => {
    if (idleTimer) clearTimeout(idleTimer);
    idleTimer = setTimeout(() => {
      timedOut = true;
      controller.abort();
      onAbort?.();
    }, AI_TIMEOUT_MS);
  };

  controller.signal.addEventListener('abort', () => {});

  return {
    start: () => resetIdleTimer(),
    chunk: () => resetIdleTimer(),
    finish: () => { if (idleTimer) clearTimeout(idleTimer); },
    get timedOut() { return timedOut; },
    get aborted() { return controller.signal.aborted; },
  };
}

describe('the chat stream aborts when it goes silent', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('uses the documented client rung, not an invented number', () => {
    // 285s: strictly below OLLAMA_TIMEOUT 290 and Cloud Run 300, so the
    // client gives up first and the server's own limit can still fire.
    expect(AI_TIMEOUT_MS).toBe(285000);
  });

  it('a stream that never says anything is aborted', () => {
    const s = streamWithIdleTimeout();
    s.start();

    vi.advanceTimersByTime(AI_TIMEOUT_MS - 1);
    expect(s.aborted).toBe(false);

    vi.advanceTimersByTime(1);
    expect(s.aborted).toBe(true);
    expect(s.timedOut).toBe(true);
  });

  it('a chunk RESETS the clock, so a slow answer is not cut off', () => {
    const s = streamWithIdleTimeout();
    s.start();

    // Four rounds, each just inside the window. A total-timeout
    // implementation aborts partway through this; an idle one does not.
    for (let i = 0; i < 4; i += 1) {
      vi.advanceTimersByTime(AI_TIMEOUT_MS - 1000);
      s.chunk();
      expect(s.aborted).toBe(false);
    }

    const elapsed = 4 * (AI_TIMEOUT_MS - 1000);
    expect(elapsed).toBeGreaterThan(AI_TIMEOUT_MS);
    expect(s.aborted).toBe(false);
  });

  it('silence AFTER a chunk still aborts', () => {
    const s = streamWithIdleTimeout();
    s.start();
    vi.advanceTimersByTime(60000);
    s.chunk();

    vi.advanceTimersByTime(AI_TIMEOUT_MS);
    expect(s.aborted).toBe(true);
  });

  it('a finished stream disarms the timer instead of firing later', () => {
    const s = streamWithIdleTimeout();
    s.start();
    s.chunk();
    s.finish();

    vi.advanceTimersByTime(AI_TIMEOUT_MS * 3);
    expect(s.aborted).toBe(false);
    expect(s.timedOut).toBe(false);
  });
});

describe('the message a timeout shows', () => {
  it('is a real sentence, not the abort reason', async () => {
    // `new DOMException(...).message` for an abort is "The user aborted a
    // request" — wrong, because the user did not, and useless either way.
    const en = (await import('../locales/en.json')).default;
    const text = en.AIChat?.stream_timed_out;

    expect(text).toBeTruthy();
    expect(text.toLowerCase()).not.toContain('user aborted');
    // §3aa: an error is not an empty state — it has to say what to do next.
    expect(text.toLowerCase()).toContain('try again');
  });
});
