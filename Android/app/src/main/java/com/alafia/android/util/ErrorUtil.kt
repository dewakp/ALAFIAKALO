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
