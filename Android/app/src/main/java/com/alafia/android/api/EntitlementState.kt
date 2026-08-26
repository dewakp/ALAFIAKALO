package com.alafia.android.api

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/**
 * Whether the signed-in user may use the app.
 *
 * The backend owns entitlement; this only mirrors `GET /subscription/status`
 * plus any 402 the app-wide paywall returns mid-session.
 *
 * The states are four, not two, and that is the point: [Unavailable] means we
 * could not find out, and it must never render as [Locked]. Telling a paying
 * member to subscribe because their connection dropped is a worse failure than
 * showing them a retry button — the same "an error is not an empty state" rule
 * the clinician board learned the hard way.
 */
object EntitlementState {

    sealed interface State {
        data object Unknown : State                       // not asked yet
        data object Checking : State                      // asking now
        data object Entitled : State                      // paid — the app opens
        data object Locked : State                        // definitively not paid
        data class Unavailable(val message: String) : State  // could not ask; retry
    }

    private val _state = MutableStateFlow<State>(State.Unknown)
    val state: StateFlow<State> = _state

    /**
     * Set when the status check comes back 401 — the session is dead, not merely
     * stale (OkHttp's TokenAuthenticator has already tried a silent refresh).
     *
     * Without this, a 401 parked the gate in [State.Unknown], which MainActivity
     * renders as the splash spinner — leaving the app loading forever with no
     * retry and no way out. The comment said "signed out; not our question", but
     * nothing was listening, so nobody ever asked it. App Review rejected the iOS
     * build for exactly that (guideline 2.1(a)); the Android path was identical.
     */
    private val _sessionExpired = MutableStateFlow(false)
    val sessionExpired: StateFlow<Boolean> = _sessionExpired

    /** Cleared once the app has acted on it, so a later sign-in starts clean. */
    fun acknowledgeSessionExpired() { _sessionExpired.value = false }

    /** Ask the backend. Never downgrades a failure into a lock. */
    suspend fun refresh() {
        if (_state.value is State.Unknown) _state.value = State.Checking
        try {
            val status = ApiClient.getApiService().getSubscriptionStatus()
            _state.value = if (status.entitled) State.Entitled else State.Locked
        } catch (e: retrofit2.HttpException) {
            _state.value = when (e.code()) {
                402 -> State.Locked                       // the server's own verdict
                401 -> {                                  // dead session: hand it to the UI
                    _sessionExpired.value = true
                    State.Unknown
                }
                else -> State.Unavailable(e.message())
            }
        } catch (e: Exception) {
            _state.value = State.Unavailable(e.message ?: "Network unavailable")
        }
    }

    /** A 402 on ANY request — the membership lapsed mid-session. */
    fun markPaymentRequired() { _state.value = State.Locked }

    /** A verified purchase: open the app without another round-trip. */
    fun markEntitled() { _state.value = State.Entitled }

    /** Sign-out: the next user must be checked from scratch. */
    fun reset() {
        _state.value = State.Unknown
        _sessionExpired.value = false
    }
}
