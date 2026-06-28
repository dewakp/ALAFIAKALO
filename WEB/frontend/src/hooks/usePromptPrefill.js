import { useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

/**
 * Consume the prefill handed off by the Prompt Hub (Basis.md).
 *
 * When the user is routed here from a prompt (location.state.fromPrompt), this
 * runs `apply(prefill, intent)` once so the page can open its create/log form
 * pre-populated. The navigation state is then cleared so a refresh or back
 * navigation doesn't re-trigger the prefill.
 *
 * Arriving normally (e.g. clicking the nav link) is a no-op.
 */
export function usePromptPrefill(apply) {
  const { state, pathname } = useLocation();
  const navigate = useNavigate();
  const applied = useRef(false);

  useEffect(() => {
    if (applied.current) return;
    if (state?.fromPrompt && state?.prefill) {
      applied.current = true;
      apply(state.prefill, state.intent);
      navigate(pathname, { replace: true, state: null });
    }
  }, [state, pathname, navigate, apply]);
}
