// Copyright © 2026 Wole Akpose / 6igma Health Inc.
// All rights reserved. ALAFIA — proprietary and confidential.

package com.alafia.android.models

/**
 * Body for `POST /notifications/fcm-token`.
 *
 * `platform` is sent explicitly rather than inferred server-side, because the
 * two platforms are delivered by DIFFERENT transports and the column decides
 * which: `android` goes to FCM, `ios` to APNs directly. A token filed under the
 * wrong platform is handed to a service that cannot address it.
 */
data class DeviceTokenRequest(
    val token: String,
    val platform: String = "android",
)

/** What the backend returns once the token is on file. */
data class DeviceTokenOut(
    val id: Int,
    val platform: String,
)
