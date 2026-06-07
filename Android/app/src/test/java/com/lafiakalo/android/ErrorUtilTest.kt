package com.alafia.android

import com.alafia.android.util.ErrorUtil
import org.junit.Assert.*
import org.junit.Test
import retrofit2.HttpException
import retrofit2.Response
import java.net.SocketTimeoutException
import java.net.UnknownHostException

/**
 * Unit tests for ErrorUtil — verifies user-friendly error messages.
 */
class ErrorUtilTest {

    @Test
    fun `network error returns friendly message`() {
        val msg = ErrorUtil.userMessage(UnknownHostException("Unable to resolve host"))
        assertEquals("No internet connection. Please check your network.", msg)
    }

    @Test
    fun `timeout returns friendly message`() {
        val msg = ErrorUtil.userMessage(SocketTimeoutException("timeout"))
        assertEquals("Request timed out. Please try again.", msg)
    }

    @Test
    fun `401 HTTP error returns session expired message`() {
        val response = Response.error<String>(401, okhttp3.ResponseBody.create(null, ""))
        val msg = ErrorUtil.userMessage(HttpException(response))
        assertEquals("Session expired. Please log in again.", msg)
    }

    @Test
    fun `404 HTTP error returns not found message`() {
        val response = Response.error<String>(404, okhttp3.ResponseBody.create(null, ""))
        val msg = ErrorUtil.userMessage(HttpException(response))
        assertEquals("The requested data was not found.", msg)
    }

    @Test
    fun `500 HTTP error returns server error message`() {
        val response = Response.error<String>(500, okhttp3.ResponseBody.create(null, ""))
        val msg = ErrorUtil.userMessage(HttpException(response))
        assertEquals("Server error. Please try again later.", msg)
    }

    @Test
    fun `unknown exception returns generic safe message`() {
        val msg = ErrorUtil.userMessage(RuntimeException("NPE in some internal code"))
        assertEquals("Something went wrong. Please try again.", msg)
    }

    @Test
    fun `error message never exposes internal details`() {
        val internalMessage = "java.sql.SQLException: column user_password not found"
        val msg = ErrorUtil.userMessage(RuntimeException(internalMessage))
        assertFalse(msg.contains("sql"))
        assertFalse(msg.contains("column"))
        assertFalse(msg.contains("password"))
    }
}
