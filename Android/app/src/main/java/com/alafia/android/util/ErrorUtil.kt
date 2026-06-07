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
                in 500..599 -> "Server error. Please try again later."
                else -> "Something went wrong. Please try again."
            }
            else -> "Something went wrong. Please try again."
        }
    }
}
