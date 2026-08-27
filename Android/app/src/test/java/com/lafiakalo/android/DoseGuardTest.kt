package com.alafia.android

import com.alafia.android.util.DoseGuard
import com.alafia.android.util.ErrorUtil
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.*
import org.junit.Test
import retrofit2.HttpException
import retrofit2.Response
import java.net.SocketTimeoutException

/**
 * The dose guard's refusal must survive the trip to the UI.
 *
 * The body below is the real response captured from
 * `POST /medications/dose-logs` for "Calcium Carbonated" 1000 mg — the 422 that
 * blocked a production dose. It went through [ErrorUtil.userMessage] and came
 * out as "Something went wrong. Please try again.", which does not even say the
 * dose was questioned: the findings naming the cause and the `override_with`
 * offering the way past were both discarded by the client, on a guard that had
 * already computed the correction.
 */
class DoseGuardTest {

    private val refusalBody = """
        {"detail": {
           "message": "This dose looks wrong — please check it.",
           "findings": [{
             "level": "error",
             "code": "unknown_medication",
             "message": "“Calcium Carbonated” isn’t a medication in RxNorm. The closest match is “Calcium Carbonate” — please confirm what was taken.",
             "suggestion": "Calcium Carbonate"
           }],
           "override_with": "acknowledge_unusual"
        }}
    """.trimIndent()

    private fun http(code: Int, body: String) = HttpException(
        Response.error<Any>(code, body.toResponseBody("application/json".toMediaType()))
    )

    @Test
    fun `a 422 refusal is decoded, not flattened into a generic message`() {
        val refusal = DoseGuard.refusalFrom(http(422, refusalBody))
        assertNotNull("the refusal must reach the UI", refusal)
        assertEquals(1, refusal!!.findings.size)
        assertEquals("unknown_medication", refusal.findings[0].code)
        assertEquals("error", refusal.findings[0].level)
    }

    /** The correction is the whole point: the guard already knows the answer. */
    @Test
    fun `the suggested spelling survives`() {
        val refusal = DoseGuard.refusalFrom(http(422, refusalBody))!!
        assertEquals("Calcium Carbonate", refusal.findings[0].suggestion)
    }

    /** Without this the user is blocked with no route forward on a true record. */
    @Test
    fun `the override field survives`() {
        val refusal = DoseGuard.refusalFrom(http(422, refusalBody))!!
        assertEquals("acknowledge_unusual", refusal.overrideWith)
    }

    /**
     * An ordinary failure must still take the ordinary path. A refusal has a
     * reason and a way through; a dead network has neither, and rendering one as
     * the other is the same mistake in the opposite direction.
     */
    @Test
    fun `a non-refusal is not mistaken for one`() {
        assertNull(DoseGuard.refusalFrom(SocketTimeoutException("timeout")))
        assertNull(DoseGuard.refusalFrom(http(500, "{}")))
        assertNull(DoseGuard.refusalFrom(http(409, """{"detail":"already logged"}""")))
    }

    /**
     * FastAPI's own validation errors are also 422, with `detail` as a LIST.
     * Those carry nothing a patient can act on, so they must fall through to the
     * generic handler rather than rendering as an empty guard panel.
     */
    @Test
    fun `a pydantic 422 is not a dose refusal`() {
        val pydantic = """{"detail":[{"loc":["body","dose_amount"],"msg":"field required","type":"value_error.missing"}]}"""
        assertNull(DoseGuard.refusalFrom(http(422, pydantic)))
    }

    /** A refusal with nothing to say is no better than the generic message. */
    @Test
    fun `an empty findings list is not a refusal`() {
        val empty = """{"detail":{"message":"nope","findings":[],"override_with":"acknowledge_unusual"}}"""
        assertNull(DoseGuard.refusalFrom(http(422, empty)))
    }
}
