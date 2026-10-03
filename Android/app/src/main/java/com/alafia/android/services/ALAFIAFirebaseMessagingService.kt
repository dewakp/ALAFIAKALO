// Copyright © 2026 Wole Akpose / 6igma Health Inc.
// All rights reserved. ALAFIA — proprietary and confidential.

package com.alafia.android.services

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import com.alafia.android.MainActivity
import com.alafia.android.R

class ALAFIAFirebaseMessagingService : FirebaseMessagingService() {

    override fun onNewToken(token: String) {
        super.onNewToken(token)
        // This single missing line is why production holds ZERO Android device
        // tokens: the service was registered in the manifest, the dependency
        // was declared, and the token was simply dropped on the floor.
        //
        // `onNewToken` fires only when the token ROTATES, so this alone would
        // never register an existing install — `PushRegistration` is also
        // called after login, which is what gets the first token on file.
        PushRegistration.register(applicationContext, knownToken = token)
    }

    override fun onMessageReceived(message: RemoteMessage) {
        super.onMessageReceived(message)

        val title = message.notification?.title ?: message.data["title"] ?: "ALAFIA"
        val body = message.notification?.body ?: message.data["body"] ?: ""
        val category = message.data["category"] ?: "general"

        showNotification(title, body, category)
    }

    private fun showNotification(title: String, body: String, category: String) {
        val channelId = "alafia_$category"
        val notificationManager = getSystemService(NotificationManager::class.java)

        // Create channel (required for Android 8+)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                channelId,
                category.replaceFirstChar { it.uppercase() },
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "ALAFIA $category notifications"
            }
            notificationManager.createNotificationChannel(channel)
        }

        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
        }
        val pendingIntent = PendingIntent.getActivity(
            this, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val notification = NotificationCompat.Builder(this, channelId)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle(title)
            .setContentText(body)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(pendingIntent)
            .build()

        notificationManager.notify(System.currentTimeMillis().toInt(), notification)
    }
}
