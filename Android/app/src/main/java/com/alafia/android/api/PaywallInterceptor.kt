package com.alafia.android.api

import okhttp3.Interceptor
import okhttp3.Response

/**
 * Watches every response for the app-wide paywall's 402.
 *
 * The gate at launch is not enough on its own: a membership can lapse, be
 * refunded, or be cancelled while the app is open, and from that moment the
 * backend answers 402 to every gated path. Without this the user sits in a shell
 * of failed requests with no explanation — the mobile version of a screen that
 * says "no data" when it means "you are not allowed".
 */
class PaywallInterceptor : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val response = chain.proceed(chain.request())
        if (response.code == 402) {
            EntitlementState.markPaymentRequired()
        }
        return response
    }
}
