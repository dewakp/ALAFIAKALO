// Copyright © 2026 Wole Akpose / 6igma Health Inc.
// All rights reserved. ALAFIA — proprietary and confidential.

package com.alafia.android

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/**
 * One signal, so the writer and the navigation cannot disagree about it.
 *
 * `MainTabView` asks `GET /users/me/surfaces` once. Anything that changes what
 * the record justifies — declaring a condition, setting a therapy switch —
 * must say so, or the patient sees the old navigation until the app restarts.
 *
 * OPEN_ITEMS 37b/38c/39b: open through three deploys, and the therapy switch
 * made it worse — a patient can now state *"I am NOT on this"* and then watch
 * the screen they just retired stay on screen, which reads as a control that
 * did nothing (§3ar).
 *
 * It carries NO payload. The surface rule is the SERVER's (§3), so the only
 * correct response to "something changed" is to ASK AGAIN; a client that
 * recomputed the set locally would be a second implementation of a clinical
 * decision, which is the drift this codebase keeps paying for.
 *
 * A counter rather than a `SharedFlow`: `MainTabView` keys a `LaunchedEffect`
 * on it, so a bump re-runs the fetch and a collector that was not listening at
 * the moment of the write still converges on the current value. A one-shot
 * event would be dropped while the Conditions screen is in front.
 */
object SurfaceRefresh {
    private val _epoch = MutableStateFlow(0)
    val epoch: StateFlow<Int> = _epoch

    /** Call after any write that could change which screens the record justifies. */
    fun announce() {
        _epoch.value = _epoch.value + 1
    }
}
