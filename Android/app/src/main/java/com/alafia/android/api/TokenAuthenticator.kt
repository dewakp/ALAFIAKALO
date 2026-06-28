package com.alafia.android.api

import android.content.Context
import com.google.gson.Gson
import com.google.gson.JsonObject
import okhttp3.Authenticator
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.Route

/**
 * Silently refreshes the access token on a 401 using the stored refresh token, then
 * retries the original request — parity with iOS so short-lived (30-min) hybrid
 * EdDSA+ML-DSA access tokens don't bounce the user to the login screen.
 *
 * Refresh is body-based (refresh token in the JSON body), which the backend accepts
 * without CSRF for non-cookie clients. Uses a bare OkHttpClient (no authenticator)
 * to avoid recursion.
 */
class TokenAuthenticator(private val context: Context) : Authenticator {

    private val lock = Any()
    private val bareClient = OkHttpClient()
    private val gson = Gson()

    override fun authenticate(route: Route?, response: Response): Request? {
        // Give up after one retry, and never try to refresh the refresh call itself.
        if (responseCount(response) >= 2) return null
        if (response.request.url.encodedPath.endsWith("/auth/refresh")) return null

        synchronized(lock) {
            val requestToken = response.request.header("Authorization")
                ?.removePrefix("Bearer ")?.trim()
            val currentToken = KeychainHelper.getToken(context)

            // Another thread may have refreshed already → just retry with the new token.
            if (currentToken != null && currentToken != requestToken) {
                return response.request.newBuilder()
                    .header("Authorization", "Bearer $currentToken")
                    .build()
            }

            val refresh = KeychainHelper.getRefreshToken(context) ?: return null
            val newAccess = refresh(refresh) ?: return null
            return response.request.newBuilder()
                .header("Authorization", "Bearer $newAccess")
                .build()
        }
    }

    /** Calls POST /auth/refresh; persists and returns the new access token, or null. */
    private fun refresh(refreshToken: String): String? = try {
        val body = gson.toJson(mapOf("refresh_token" to refreshToken))
            .toRequestBody("application/json".toMediaType())
        val req = Request.Builder()
            .url(ApiClient.BASE_URL.trimEnd('/') + "/auth/refresh")
            .post(body)
            .build()
        bareClient.newCall(req).execute().use { resp ->
            if (!resp.isSuccessful) {
                null
            } else {
                val json = gson.fromJson(resp.body?.string(), JsonObject::class.java)
                val access = json?.get("access_token")?.takeIf { !it.isJsonNull }?.asString
                if (access != null) {
                    KeychainHelper.saveToken(context, access)
                    json.get("refresh_token")?.takeIf { !it.isJsonNull }?.asString?.let {
                        KeychainHelper.saveRefreshToken(context, it)
                    }
                }
                access
            }
        }
    } catch (e: Exception) {
        null
    }

    private fun responseCount(response: Response): Int {
        var prior = response.priorResponse
        var count = 1
        while (prior != null) {
            count++
            prior = prior.priorResponse
        }
        return count
    }
}
