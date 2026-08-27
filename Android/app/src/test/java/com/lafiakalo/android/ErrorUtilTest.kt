package com.alafia.android

import com.alafia.android.util.ErrorUtil
import org.junit.Assert.*
import org.junit.Test
import retrofit2.HttpException
import okhttp3.ResponseBody.Companion.toResponseBody
import okhttp3.MediaType.Companion.toMediaType
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

/**
 * A user who mistypes their email must be told which field is wrong.
 *
 * FastAPI validation errors are 422 with `detail` as a LIST. They used to fall
 * through to "Something went wrong. Please try again." — a message that tells
 * someone to retry the exact thing that just failed.
 */
class ValidationMessageTest {

    private fun http422(body: String) = retrofit2.HttpException(
        retrofit2.Response.error<Any>(
            422,
            body.toResponseBody("application/json".toMediaType()),
        )
    )

    @Test
    fun `a field validation error names the field`() {
        val msg = ErrorUtil.userMessage(
            http422("""{"detail":[{"loc":["body","email"],"msg":"value is not a valid email address"}]}""")
        )
        assertTrue(msg, msg.contains("Email"))
        assertTrue(msg, msg.contains("not a valid email address"))
    }

    @Test
    fun `several problems are all reported`() {
        val msg = ErrorUtil.userMessage(
            http422("""{"detail":[
                {"loc":["body","email"],"msg":"field required"},
                {"loc":["body","password"],"msg":"too short"}]}""")
        )
        assertTrue(msg, msg.contains("Email"))
        assertTrue(msg, msg.contains("Password"))
    }

    /** The dose guard also answers 422, with an OBJECT. Not a toast. */
    @Test
    fun `an object detail is not treated as a field error`() {
        val msg = ErrorUtil.userMessage(
            http422("""{"detail":{"message":"This dose looks wrong","findings":[]}}""")
        )
        assertEquals("Please check the details you entered.", msg)
    }
}
