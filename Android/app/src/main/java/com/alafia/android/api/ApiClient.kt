package com.alafia.android.api

import android.content.Context
import com.google.gson.GsonBuilder
import okhttp3.Cache
import okhttp3.CacheControl
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.io.File
import java.security.MessageDigest
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManagerFactory
import javax.net.ssl.X509TrustManager

object ApiClient {
    // Base URL from BuildConfig — set per build type (debug/release) in build.gradle
    private var baseUrl: String = com.alafia.android.BuildConfig.API_BASE_URL

    /** Public accessor used by screens that construct URLs directly (e.g. SSE streaming). */
    val BASE_URL: String get() = baseUrl

    private var retrofit: Retrofit? = null
    private var apiService: ApiService? = null
    private var _okHttpClient: OkHttpClient? = null

    /** Returns the shared OkHttpClient (needed for SSE streaming). */
    fun getOkHttpClient(): OkHttpClient =
        _okHttpClient ?: throw IllegalStateException("ApiClient not initialized")

    fun initialize(context: Context): ApiService {
        if (apiService == null) {
            // 10 MB HTTP response cache for offline support
            val cacheDir = File(context.cacheDir, "http_cache")
            val cache = Cache(cacheDir, 10L * 1024 * 1024)

            // SHA-512 certificate pinning for production API domain
            val pinnedSha512Hashes = listOf(
                "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", // Replace with real SHA-512 pin
                "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB", // Backup pin
            )

            val clientBuilder = OkHttpClient.Builder()
                .cache(cache)
                .connectTimeout(30, TimeUnit.SECONDS)
                .writeTimeout(30, TimeUnit.SECONDS)
                .readTimeout(120, TimeUnit.SECONDS)  // extended for SSE streaming
                .addInterceptor(AuthInterceptor(context))
                .authenticator(TokenAuthenticator(context))  // silent refresh-and-retry on 401 (iOS parity)
                .addInterceptor(RetryInterceptor(maxRetries = 3))
                .addNetworkInterceptor(CacheControlInterceptor())
                .addInterceptor(HttpLoggingInterceptor().apply {
                    level = HttpLoggingInterceptor.Level.BASIC
                })

            // Only pin certificates in release builds
            if (!com.alafia.android.BuildConfig.DEBUG) {
                val defaultTmf = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm())
                defaultTmf.init(null as java.security.KeyStore?)
                val defaultTm = defaultTmf.trustManagers.first() as X509TrustManager

                val pinningTrustManager = object : X509TrustManager {
                    override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) {
                        defaultTm.checkClientTrusted(chain, authType)
                    }

                    override fun checkServerTrusted(chain: Array<out X509Certificate>?, authType: String?) {
                        defaultTm.checkServerTrusted(chain, authType)
                        // After default validation passes, enforce SHA-512 pin
                        if (chain.isNullOrEmpty()) throw CertificateException("Empty certificate chain")
                        val matched = chain.any { cert ->
                            val digest = MessageDigest.getInstance("SHA-512")
                            val hash = digest.digest(cert.publicKey.encoded)
                            val base64Hash = android.util.Base64.encodeToString(hash, android.util.Base64.NO_WRAP)
                            pinnedSha512Hashes.contains(base64Hash)
                        }
                        if (!matched) throw CertificateException("Certificate pin mismatch (SHA-512)")
                    }

                    override fun getAcceptedIssuers(): Array<X509Certificate> = defaultTm.acceptedIssuers
                }

                val sslContext = SSLContext.getInstance("TLS")
                sslContext.init(null, arrayOf(pinningTrustManager), null)
                clientBuilder.sslSocketFactory(sslContext.socketFactory, pinningTrustManager)
            }

            val httpClient = clientBuilder.build()
            _okHttpClient = httpClient

            val gson = GsonBuilder()
                .setLenient()
                .create()

            retrofit = Retrofit.Builder()
                .baseUrl(baseUrl)
                .client(httpClient)
                .addConverterFactory(GsonConverterFactory.create(gson))
                .build()

            apiService = retrofit!!.create(ApiService::class.java)
        }

        return apiService!!
    }

    fun getApiService(): ApiService =
        apiService ?: throw IllegalStateException("ApiClient not initialized")

    fun setBaseUrl(url: String) {
        baseUrl = url
        apiService = null
        retrofit = null
        _okHttpClient = null
    }
}

/**
 * Retry interceptor — retries failed requests up to [maxRetries] times
 * with exponential back-off for network errors and 5xx responses.
 */
private class RetryInterceptor(private val maxRetries: Int = 3) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): okhttp3.Response {
        var lastException: Exception? = null
        for (attempt in 0..maxRetries) {
            try {
                val response = chain.proceed(chain.request())
                // Don't retry client errors or successes
                if (response.code < 500 || attempt == maxRetries) return response
                response.close()
            } catch (e: Exception) {
                lastException = e
                if (attempt == maxRetries) break
            }
            // Exponential back-off: 500ms, 1s, 2s
            Thread.sleep((500L * (1 shl attempt)).coerceAtMost(4000L))
        }
        throw lastException ?: java.io.IOException("Request failed after $maxRetries retries")
    }
}

/**
 * Cache-Control interceptor — adds caching headers for GET responses to
 * enable offline reading for up to 24 hours.
 */
private class CacheControlInterceptor : Interceptor {
    override fun intercept(chain: Interceptor.Chain): okhttp3.Response {
        val response = chain.proceed(chain.request())
        if (chain.request().method == "GET") {
            val cacheControl = CacheControl.Builder()
                .maxAge(5, TimeUnit.MINUTES)        // Fresh for 5 min
                .maxStale(24, TimeUnit.HOURS)        // Serve stale for 24 h offline
                .build()
            return response.newBuilder()
                .header("Cache-Control", cacheControl.toString())
                .removeHeader("Pragma")
                .build()
        }
        return response
    }
}
