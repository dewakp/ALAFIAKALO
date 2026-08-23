package com.alafia.android

import com.alafia.android.api.EntitlementState
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.*
import org.junit.Test

/**
 * The membership gate's one dangerous edge: **an error is not a verdict.**
 *
 * The gate blocks the whole app, so if a failed status call collapsed into
 * "Locked" then every paying member on a flaky connection would be shown a
 * paywall and told to buy a subscription they already have. That is a worse
 * failure than briefly letting someone through, and it is exactly the shape of
 * the bug this codebase keeps re-learning — a failed fetch rendered as an empty
 * state instead of as an error.
 */
class EntitlementStateTest {

    @After
    fun tearDown() = EntitlementState.reset()

    @Test
    fun `a failed check is Unavailable, never Locked`() = runBlocking {
        // ApiClient is deliberately uninitialised here, so the call throws —
        // standing in for any network/server failure.
        EntitlementState.refresh()

        val state = EntitlementState.state.value
        assertTrue("expected Unavailable but was $state",
            state is EntitlementState.State.Unavailable)
        assertNotEquals(EntitlementState.State.Locked, state)
    }

    @Test
    fun `a 402 anywhere in the app locks the gate`() {
        EntitlementState.markPaymentRequired()
        assertEquals(EntitlementState.State.Locked, EntitlementState.state.value)
    }

    @Test
    fun `a verified purchase opens the gate without a round-trip`() {
        EntitlementState.markPaymentRequired()
        EntitlementState.markEntitled()
        assertEquals(EntitlementState.State.Entitled, EntitlementState.state.value)
    }

    @Test
    fun `sign-out clears the previous user's verdict`() {
        EntitlementState.markEntitled()
        EntitlementState.reset()
        assertEquals(EntitlementState.State.Unknown, EntitlementState.state.value)
    }
}
