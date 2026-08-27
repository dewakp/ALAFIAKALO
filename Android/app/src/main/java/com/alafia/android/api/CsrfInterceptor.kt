package com.alafia.android.api

import okhttp3.Interceptor
import okhttp3.Response
import java.util.UUID

/**
 * Attaches a double-submit CSRF pair to any mutating request that carries no
 * Bearer token.
 *
 * This mirrors the SERVER's rule rather than a list of paths. `main.py` exempts
 * a request whose credential is explicit and non-ambient — anything with
 * `Authorization: Bearer` — and enforces CSRF on everything else. The requests
 * with no Bearer token are exactly the ones a user makes when they cannot log
 * in: **register, and password reset**.
 *
 * Those were plain `@POST` calls with no CSRF pair, so the server answered 403
 * and the Reset Password screen showed "CSRF token missing or invalid" to
 * someone who had merely forgotten their password. Only `login` was wired, via
 * `loginWithCsrf` passing the token as explicit Retrofit parameters — which is
 * precisely why the other two were missed: a per-method opt-in is a thing to
 * remember, and what gets forgotten is the endpoint a locked-out user needs.
 *
 * Deriving the condition from the Authorization header is what stops the next
 * unauthenticated endpoint from shipping broken the same way.
 */
class CsrfInterceptor : Interceptor {

    private companion object {
        val SAFE_METHODS = setOf("GET", "HEAD", "OPTIONS")
    }

    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()

        if (request.method in SAFE_METHODS) return chain.proceed(request)
        // An explicit Bearer credential is not CSRF-vulnerable; the server
        // exempts it, so adding a pair here would be noise.
        if (request.header("Authorization")?.startsWith("Bearer ") == true) {
            return chain.proceed(request)
        }
        // Already handled explicitly (loginWithCsrf) — do not overwrite it.
        if (request.header("X-CSRF-Token") != null) return chain.proceed(request)

        // Double-submit only requires that header and cookie MATCH, so a locally
        // generated value is sufficient and needs no extra round-trip.
        val token = UUID.randomUUID().toString()
        val existingCookie = request.header("Cookie")
        val cookie = if (existingCookie.isNullOrBlank()) {
            "csrf_token=$token"
        } else {
            "$existingCookie; csrf_token=$token"
        }

        return chain.proceed(
            request.newBuilder()
                .header("X-CSRF-Token", token)
                .header("Cookie", cookie)
                .build()
        )
    }
}
