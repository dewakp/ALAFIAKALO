// Copyright © 2026 Wole Akpose / 6igma Health Inc.
// All rights reserved. ALAFIA — proprietary and confidential.

package com.alafia.android.services

import android.content.Context
import android.util.Log
import com.alafia.android.api.ApiClient
import com.alafia.android.api.KeychainHelper
import com.alafia.android.models.DeviceTokenRequest
import com.google.firebase.messaging.FirebaseMessaging
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/**
 * Puts this device's FCM token on the patient's record.
 *
 * `ALAFIAFirebaseMessagingService.onNewToken` held a `// TODO: Send this token
 * to backend` and nothing else, which is why production holds **zero** Android
 * device tokens — all 21 registered tokens are iOS. The service was in the
 * manifest, `firebase-messaging-ktx` was a dependency, and the one line that
 * would have made any of it reachable was never written.
 *
 * Two call sites, deliberately, mirroring iOS's `PushNotificationManager`:
 *
 *  - `onNewToken`, which fires only when the token ROTATES. On its own this
 *    never registers an existing install.
 *  - after a successful login / session restore, which is what actually gets
 *    the first token on file — and is also when a user id exists to attach it
 *    to. A token fetched before sign-in has nobody to belong to.
 *
 * Best-effort throughout: a failed registration costs a push, and is retried
 * at the next launch. It must never surface to the patient or block a login.
 */
object PushRegistration {

    private const val TAG = "PushRegistration"

    /**
     * Register, fetching the current token when one was not handed to us.
     *
     * Uses `addOnCompleteListener` rather than `Task.await()` so this needs no
     * `kotlinx-coroutines-play-services` dependency.
     */
    fun register(context: Context, knownToken: String? = null) {
        val app = context.applicationContext
        // Not signed in yet: there is no account to attach the token to, and
        // the POST would 401. Login calls this again.
        if (KeychainHelper.getToken(app) == null) return

        if (knownToken != null) {
            post(app, knownToken)
            return
        }
        try {
            FirebaseMessaging.getInstance().token
                .addOnCompleteListener { task ->
                    val token = task.result
                    if (task.isSuccessful && !token.isNullOrBlank()) {
                        post(app, token)
                    } else {
                        Log.w(TAG, "FCM token unavailable", task.exception)
                    }
                }
        } catch (e: Exception) {
            // Firebase not configured on this build (no google-services.json).
            // Push is simply unavailable; nothing else should break.
            Log.w(TAG, "FCM unavailable: ${e.message}")
        }
    }

    private fun post(context: Context, token: String) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val api = ApiClient.initialize(context)
                api.registerFcmToken(DeviceTokenRequest(token = token))
                Log.i(TAG, "FCM token registered")
            } catch (e: Exception) {
                Log.w(TAG, "FCM token registration failed: ${e.message}")
            }
        }
    }
}
