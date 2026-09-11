package com.alafia.android.views.hd

import android.content.Context
import android.print.PrintAttributes
import android.print.PrintManager
import android.webkit.WebView
import android.webkit.WebViewClient
import com.alafia.android.api.ApiClient
import com.alafia.android.util.ErrorUtil
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Print or save a treatment report as PDF.
 *
 * The document is rendered SERVER-SIDE and fetched as HTML, so the patient's
 * copy, the clinician's copy and the web copy are the same document. Three
 * templates would drift, and the one that drifted would be the one a clinician
 * was reading.
 *
 * `WebView.createPrintDocumentAdapter` hands it to Android's own print
 * pipeline, which gives the user "Save as PDF" and any configured printer for
 * free — affordances a bundled PDF library would have taken away.
 */
object TherapyReportPrinter {

    /**
     * Fetch and open the print dialog. Returns an error message, or null on
     * success.
     *
     * [patientId] is set when a CLINICIAN prints; the backend re-checks the
     * sharing grant on that route, so passing an id is a destination and never
     * an authorisation.
     */
    suspend fun print(context: Context, sessionId: Int, patientId: Int? = null): String? {
        val html = try {
            withContext(Dispatchers.IO) {
                val api = ApiClient.getApiService()
                val body = if (patientId != null) {
                    api.patientTherapySessionReport(patientId, sessionId)
                } else {
                    api.therapySessionReport(sessionId)
                }
                body.string()
            }
        } catch (e: Exception) {
            // Named, not swallowed: a print button that silently does nothing
            // is indistinguishable from one that was never wired.
            return ErrorUtil.userMessage(e)
        }

        return withContext(Dispatchers.Main) {
            try {
                // The WebView must be held until the adapter is created, and
                // printing may only start once the content has finished
                // loading — starting earlier prints a blank page.
                val webView = WebView(context)
                webView.webViewClient = object : WebViewClient() {
                    override fun onPageFinished(view: WebView, url: String) {
                        val manager = context.getSystemService(Context.PRINT_SERVICE) as PrintManager
                        manager.print(
                            "ALAFIA Treatment Report",
                            view.createPrintDocumentAdapter("ALAFIA Treatment Report"),
                            PrintAttributes.Builder().build(),
                        )
                    }
                }
                webView.loadDataWithBaseURL(null, html, "text/html", "UTF-8", null)
                null
            } catch (e: Exception) {
                ErrorUtil.userMessage(e)
            }
        }
    }
}
