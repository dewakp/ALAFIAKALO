package com.alafia.android.api

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

object KeychainHelper {
    private const val PREFS_NAME = "alafia_secure"
    private const val TOKEN_KEY = "auth_token"
    private const val REFRESH_TOKEN_KEY = "refresh_token"
    private const val USER_ID_KEY = "user_id"
    private const val USERNAME_KEY = "username"

    private fun getEncryptedPreferences(context: Context): EncryptedSharedPreferences {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()

        return EncryptedSharedPreferences.create(
            context,
            PREFS_NAME,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        ) as EncryptedSharedPreferences
    }

    fun saveToken(context: Context, token: String) {
        getEncryptedPreferences(context).edit().putString(TOKEN_KEY, token).apply()
    }

    fun getToken(context: Context): String? {
        return getEncryptedPreferences(context).getString(TOKEN_KEY, null)
    }

    fun saveRefreshToken(context: Context, token: String) {
        getEncryptedPreferences(context).edit().putString(REFRESH_TOKEN_KEY, token).apply()
    }

    fun getRefreshToken(context: Context): String? {
        return getEncryptedPreferences(context).getString(REFRESH_TOKEN_KEY, null)
    }

    fun saveUserId(context: Context, userId: String) {
        getEncryptedPreferences(context).edit().putString(USER_ID_KEY, userId).apply()
    }

    fun getUserId(context: Context): String? {
        return getEncryptedPreferences(context).getString(USER_ID_KEY, null)
    }

    fun saveUsername(context: Context, username: String) {
        getEncryptedPreferences(context).edit().putString(USERNAME_KEY, username).apply()
    }

    fun getUsername(context: Context): String? {
        return getEncryptedPreferences(context).getString(USERNAME_KEY, null)
    }

    fun clearAll(context: Context) {
        getEncryptedPreferences(context).edit().clear().apply()
    }

    fun isLoggedIn(context: Context): Boolean {
        return getToken(context) != null
    }
}
