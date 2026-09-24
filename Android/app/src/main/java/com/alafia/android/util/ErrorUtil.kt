package com.alafia.android.util

import android.util.Log
import retrofit2.HttpException
import java.net.SocketTimeoutException
import java.net.UnknownHostException

/**
 * Converts exceptions into user-friendly messages.
 * Internal details are logged but never shown to the user.
 */
object ErrorUtil {
    private const val TAG = "ALAFIA"

    /**
     * Reads pydantic's `{"detail":[{"loc":["body","email"],"msg":"..."}]}` into
     * one line a user can act on. Returns null for any other 422 shape — the
     * medication dose guard also answers 422, with an object, and that one is
     * rendered in the form by [DoseGuard], not as a toast.
     */
    private fun validationMessage(e: HttpException): String? {
        val body = try {
            e.response()?.errorBody()?.string()
        } catch (_: Exception) {
            null
        } ?: return null
        return try {
            val detail = com.google.gson.JsonParser.parseString(body)
                .asJsonObject.get("detail")
            if (detail == null || !detail.isJsonArray) return null
            val parts = detail.asJsonArray.mapNotNull { item ->
                val obj = item.asJsonObject
                val msg = obj.get("msg")?.asString?.takeIf { it.isNotBlank() }
                    ?: return@mapNotNull null
                val field = obj.getAsJsonArray("loc")
                    ?.mapNotNull { it.asString.takeIf { s -> s != "body" } }
                    ?.lastOrNull()
                    ?.replace('_', ' ')
                    ?.replaceFirstChar { c -> c.uppercase() }
                if (field != null) "$field: $msg" else msg
            }
            parts.takeIf { it.isNotEmpty() }?.joinToString("\n")
        } catch (_: Exception) {
            null
        }
    }

    /**
     * Reads FastAPI's OTHER shape — `{"detail":"a whole sentence"}` — which is
     * what a deliberate refusal uses, as opposed to pydantic's list of field
     * problems above.
     *
     * /auth/signup/start answers 409 with the reason AND the way forward
     * ("An account already exists… try signing in, or reset your password").
     * Collapsing that into "Something went wrong. Please try again." sends the
     * one person who demonstrably already has an account back to the same form
     * to try again — §3aj, where a guard that cannot explain itself gets blamed
     * for the thing it did not do.
     *
     * NOTE: `errorBody().string()` is consumable ONCE. Call this or
     * [validationMessage] for a given exception, never both.
     */
    fun detailMessage(e: HttpException): String? {
        val body = try {
            e.response()?.errorBody()?.string()
        } catch (_: Exception) {
            null
        } ?: return null
        return try {
            val detail = com.google.gson.JsonParser.parseString(body)
                .asJsonObject.get("detail")
            detail?.takeIf { it.isJsonPrimitive }?.asString?.takeIf { it.isNotBlank() }
        } catch (_: Exception) {
            null
        }
    }

    fun userMessage(e: Exception): String {
        Log.e(TAG, "Error: ${e.javaClass.simpleName}", e)
        return when (e) {
            is UnknownHostException -> "No internet connection. Please check your network."
            is SocketTimeoutException -> "Request timed out. Please try again."
            is HttpException -> when (e.code()) {
                401 -> "Session expired. Please log in again."
                403 -> "You don't have permission to perform this action."
                404 -> "The requested data was not found."
                429 -> "Too many requests. Please wait a moment."
                // A deliberate refusal that already names the way forward —
                // signing up with an address that already has an account.
                409 -> detailMessage(e)
                    ?: "An account already exists for this email address. Try signing in."
                // FastAPI validation errors name the field that is wrong.
                // Collapsing them into "Something went wrong" told a user with a
                // mistyped email to try again, without saying what to change.
                422 -> validationMessage(e) ?: "Please check the details you entered."
                in 500..599 -> "Server error. Please try again later."
                else -> "Something went wrong. Please try again."
            }
            else -> "Something went wrong. Please try again."
        }
    }
}
