package com.alafia.android

import android.app.Application
import android.util.Log
import java.io.File
import java.io.PrintWriter
import java.io.StringWriter
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Application subclass that installs a crash reporter on startup.
 * Uncaught exceptions are written to a crash log file in the app's files
 * directory and uploaded on the next launch, mirroring the iOS CrashReporter.
 */
class AlafiaApplication : Application() {

    override fun onCreate() {
        super.onCreate()
        CrashReporter.install(this)
        CrashReporter.uploadPendingReports(this)
    }
}

/**
 * Lightweight crash reporter — no third-party SDK required.
 * Persists stack traces to disk and uploads them to the backend on next launch.
 */
object CrashReporter {

    private const val TAG = "CrashReporter"
    private const val CRASH_DIR = "crash_logs"
    private const val MAX_REPORTS = 20

    /** Install the uncaught-exception handler. Call once in Application.onCreate(). */
    fun install(app: Application) {
        val defaultHandler = Thread.getDefaultUncaughtExceptionHandler()

        Thread.setDefaultUncaughtExceptionHandler { thread, throwable ->
            try {
                persist(app, throwable)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to write crash report", e)
            }
            // Delegate to the system handler (shows the crash dialog / kills the process)
            defaultHandler?.uncaughtException(thread, throwable)
        }

        Log.d(TAG, "Crash reporter installed")
    }

    /** Upload any persisted reports to the backend and delete them afterwards. */
    fun uploadPendingReports(app: Application) {
        val dir = crashDir(app)
        if (!dir.exists()) return

        val files = dir.listFiles() ?: return
        for (file in files) {
            try {
                val payload = file.readText()
                // Fire-and-forget: best-effort POST to the diagnostics endpoint.
                // Uses a background thread to avoid blocking the main thread on startup.
                Thread {
                    try {
                        val url = java.net.URL("${getBaseUrl(app)}/api/v1/diagnostics/crash-reports")
                        val conn = url.openConnection() as java.net.HttpURLConnection
                        conn.requestMethod = "POST"
                        conn.setRequestProperty("Content-Type", "text/plain")
                        conn.doOutput = true
                        conn.connectTimeout = 5_000
                        conn.readTimeout = 5_000
                        conn.outputStream.use { it.write(payload.toByteArray()) }
                        val code = conn.responseCode
                        if (code in 200..299) {
                            file.delete()
                            Log.d(TAG, "Crash report uploaded and deleted: ${file.name}")
                        }
                        conn.disconnect()
                    } catch (e: Exception) {
                        Log.w(TAG, "Could not upload crash report ${file.name}: ${e.message}")
                    }
                }.start()
            } catch (e: Exception) {
                Log.w(TAG, "Could not read crash report ${file.name}: ${e.message}")
            }
        }
    }

    // -------------------------------------------------------------------------

    private fun persist(app: Application, throwable: Throwable) {
        val dir = crashDir(app)
        dir.mkdirs()

        // Keep at most MAX_REPORTS files to avoid unbounded disk growth
        val existing = dir.listFiles() ?: emptyArray()
        if (existing.size >= MAX_REPORTS) {
            existing.minByOrNull { it.lastModified() }?.delete()
        }

        val timestamp = SimpleDateFormat("yyyyMMdd_HHmmss_SSS", Locale.US).format(Date())
        val file = File(dir, "crash_$timestamp.txt")

        val sw = StringWriter()
        throwable.printStackTrace(PrintWriter(sw))

        file.writeText(
            buildString {
                appendLine("=== ALAFIA Android Crash Report ===")
                appendLine("Timestamp : $timestamp")
                appendLine("Thread    : ${Thread.currentThread().name}")
                appendLine("Version   : ${app.packageManager.getPackageInfo(app.packageName, 0).versionName}")
                appendLine("SDK       : ${android.os.Build.VERSION.SDK_INT}")
                appendLine("Device    : ${android.os.Build.MANUFACTURER} ${android.os.Build.MODEL}")
                appendLine("---")
                appendLine(sw.toString())
            }
        )
    }

    private fun crashDir(app: Application) = File(app.filesDir, CRASH_DIR)

    private fun getBaseUrl(app: Application): String {
        return try {
            val ai = app.packageManager.getApplicationInfo(app.packageName, android.content.pm.PackageManager.GET_META_DATA)
            ai.metaData?.getString("alafia_api_base_url") ?: "https://api.alafia.app"
        } catch (e: Exception) {
            "https://api.alafia.app"
        }
    }
}
