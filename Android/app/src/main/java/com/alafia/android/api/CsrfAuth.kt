package com.alafia.android.api

import com.alafia.android.schemas.LoginResponse

private val CSRF_COOKIE_REGEX = Regex("(?:^|;\\s*)csrf_token=([^;]+)")

private fun extractCsrfToken(setCookies: List<String>): String? {
    for (cookie in setCookies) {
        val token = CSRF_COOKIE_REGEX.find(cookie)?.groupValues?.getOrNull(1)
        if (!token.isNullOrBlank()) return token
    }
    return null
}

suspend fun loginWithCsrf(
    apiService: ApiService,
    username: String,
    password: String,
): LoginResponse {
    val csrfResponse = apiService.getCsrfCookie()
    val csrfToken = extractCsrfToken(csrfResponse.headers().values("set-cookie"))
        ?: throw IllegalStateException("Failed to obtain CSRF token")

    return apiService.login(
        username = username,
        password = password,
        csrfToken = csrfToken,
        csrfCookie = "csrf_token=$csrfToken",
    )
}
