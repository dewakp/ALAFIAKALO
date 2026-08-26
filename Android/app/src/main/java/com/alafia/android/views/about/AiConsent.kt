package com.alafia.android.views.about

import android.content.Context
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

/**
 * Whether this user has agreed to AI features being answered by third-party
 * model providers.
 *
 * Requests are de-identified before they leave ALAFIA — the user is represented
 * by a token we issue and direct identifiers are stripped from the text — but
 * consent is still asked for, because "we removed your name" is our assurance,
 * not the user's decision. iOS parity: AIConsentManager.
 */
object AiConsent {
    private const val PREFS = "alafia_prefs"
    private const val KEY = "alafia.aiConsentAccepted.v1"

    fun isAccepted(context: Context): Boolean =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getBoolean(KEY, false)

    fun accept(context: Context) = set(context, true)

    /** Withdrawal is a real option, not a formality — it turns the features off. */
    fun withdraw(context: Context) = set(context, false)

    private fun set(context: Context, value: Boolean) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit().putBoolean(KEY, value).apply()
    }
}

/** Shown in place of an AI feature until the user accepts. */
@Composable
fun AiConsentScreen(onAccept: () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Text("Before you use ALAFIA's AI", style = MaterialTheme.typography.titleLarge)
        Text(
            "ALAFIA's AI features are answered by established model providers we " +
                "work with. Here is exactly what that means for your information.",
            style = MaterialTheme.typography.bodyMedium
        )

        Group("What is sent", listOf(
            "The health details needed to answer — for example a lab value, a " +
                "medication name and its dose."
        ))
        Group("What is never sent", listOf(
            "Your name, email address or phone number.",
            "Your date of birth or any record number.",
            "The names of clinicians you mention."
        ))
        Group("How you are identified", listOf(
            "By a token ALAFIA issues, such as \"alafia-ba9e8bb2f9077c6e\". It means " +
                "nothing outside ALAFIA and cannot be linked back to you by the provider."
        ))
        Group("Your choices", listOf(
            "You can withdraw at any time in Profile → AI & Your Data, which turns " +
                "these features off.",
            "Your data is never used to train a provider's models."
        ))

        Text(
            "ALAFIA is not a medical device. It does not diagnose, treat or prescribe, " +
                "and it is not a substitute for your care team.",
            style = MaterialTheme.typography.bodySmall
        )

        Button(onClick = onAccept, modifier = Modifier.fillMaxWidth()) {
            Text("Accept & Enable AI Features")
        }
    }
}

@Composable
private fun Group(title: String, items: List<String>) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
        items.forEach { item ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.Top) {
                Text("•", style = MaterialTheme.typography.bodySmall)
                Text(item, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

/** Wraps an AI feature so it cannot run before consent is given. */
@Composable
fun AiConsentGate(context: Context, content: @Composable () -> Unit) {
    var accepted by remember { mutableStateOf(AiConsent.isAccepted(context)) }
    if (accepted) content() else AiConsentScreen(onAccept = {
        AiConsent.accept(context); accepted = true
    })
}
