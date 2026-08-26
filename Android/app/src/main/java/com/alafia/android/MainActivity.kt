package com.alafia.android

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.size
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.alafia.android.api.ApiClient
import com.alafia.android.api.EntitlementState
import com.alafia.android.api.KeychainHelper
import com.alafia.android.ui.theme.ALAFIATheme
import kotlinx.coroutines.launch
import com.alafia.android.views.auth.LoginScreen
import com.alafia.android.views.auth.RegisterScreen
import com.alafia.android.views.auth.ForgotPasswordScreen
import com.alafia.android.views.main.MainTabView
import com.alafia.android.views.subscription.SubscriptionScreen

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        ApiClient.initialize(this)

        setContent {
            ALAFIATheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    AppNavigation(this@MainActivity, intent)
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
    }
}

@Composable
fun AppNavigation(activity: MainActivity, intent: Intent?) {
    val navController = rememberNavController()
    val scope = rememberCoroutineScope()

    // Start on a splash screen; validate the token before deciding where to go
    val authChecked = remember { mutableStateOf(false) }
    val tokenValid = remember { mutableStateOf(false) }

    // Deep link route to navigate to after auth check
    val deepLinkRoute = remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        // Parse deep link if present
        intent?.data?.let { uri ->
            deepLinkRoute.value = parseDeepLink(uri)
        }

        if (KeychainHelper.isLoggedIn(activity)) {
            // Token exists – verify it's still valid with the backend
            try {
                ApiClient.getApiService().getCurrentUser()
                tokenValid.value = true
                // Signed in is not the same as allowed in. The backend answers
                // 402 to every gated path without an active membership, so ask
                // once here rather than opening a shell of failed requests.
                EntitlementState.refresh()
            } catch (_: Exception) {
                // Token expired / invalid – clear stored credentials
                KeychainHelper.clearAll(activity)
                tokenValid.value = false
            }
        } else {
            tokenValid.value = false
        }
        authChecked.value = true
    }

    if (!authChecked.value) {
        SplashIndicator()
        return
    }

    NavHost(
        navController = navController,
        startDestination = if (tokenValid.value) "main" else "login"
    ) {
        composable("login") {
            LoginScreen(
                navController = navController,
                activity = activity,
                onLoginSuccess = { tokenValid.value = true }
            )
        }

        composable("register") {
            RegisterScreen(
                navController = navController,
                activity = activity,
                onRegisterSuccess = { tokenValid.value = true }
            )
        }

        composable("forgot-password") {
            ForgotPasswordScreen(navController = navController)
        }

        composable("main") {
            // The membership gate. Four states, not two: Unavailable means we
            // could not ask, and it must never render as "you haven't paid" —
            // locking out a paying member on a dropped connection is the worse
            // of the two mistakes.
            val entitlement by EntitlementState.state.collectAsState()
            val signOut = {
                KeychainHelper.clearAll(activity)
                EntitlementState.reset()
                tokenValid.value = false
                navController.navigate("login") { popUpTo("main") { inclusive = true } }
            }

            // A dead session must reach the login screen. Before this, a 401 left
            // the gate in Unknown and the app sat on the splash spinner forever.
            val expired by EntitlementState.sessionExpired.collectAsState()
            LaunchedEffect(expired) {
                if (expired) {
                    EntitlementState.acknowledgeSessionExpired()
                    signOut()
                }
            }

            when (val state = entitlement) {
                is EntitlementState.State.Entitled ->
                    MainTabView(navController = navController, activity = activity)

                is EntitlementState.State.Locked ->
                    SubscriptionScreen(
                        navController = navController,
                        blocking = true,
                        onSignOut = signOut,
                    )

                is EntitlementState.State.Unavailable ->
                    MembershipCheckFailed(
                        message = state.message,
                        onRetry = { scope.launch { EntitlementState.refresh() } },
                        onSignOut = signOut,
                    )

                else -> {
                    LaunchedEffect(Unit) { EntitlementState.refresh() }
                    SplashIndicator()
                }
            }
        }
    }

    // Navigate to deep link destination after auth is confirmed
    LaunchedEffect(authChecked.value, tokenValid.value) {
        if (authChecked.value && tokenValid.value) {
            deepLinkRoute.value?.let { route ->
                navController.navigate(route) {
                    launchSingleTop = true
                }
                deepLinkRoute.value = null
            }
        }
    }
}

/** Parse a deep link URI into a Compose navigation route. */
private fun parseDeepLink(uri: Uri): String? {
    // Supports:  alafia://labs   or   https://alafia.app/app/labs
    val path = when (uri.scheme) {
        "alafia" -> uri.host ?: uri.path?.trimStart('/')
        else -> uri.path?.removePrefix("/app/")?.removePrefix("/app")?.trimStart('/')
    }?.lowercase() ?: return null

    return when (path) {
        "", "dashboard", "home" -> "main"
        "login" -> "login"
        "register" -> "register"
        "forgot-password", "password-reset" -> "forgot-password"
        else -> "main" // Fall back to main tab; MainTabView handles sub-navigation
    }
}


@Composable
private fun SplashIndicator() {
    Column(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        CircularProgressIndicator(modifier = Modifier.size(48.dp))
        Text(
            text = "ALAFIA",
            style = MaterialTheme.typography.headlineMedium,
            modifier = Modifier
        )
    }
}

/**
 * We could not reach the membership check. Deliberately NOT the paywall: an
 * error is not a verdict, and a paying member must not be asked to pay again
 * because the network dropped.
 */
@Composable
private fun MembershipCheckFailed(message: String, onRetry: () -> Unit, onSignOut: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().padding(32.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text("Couldn't check your membership",
            style = MaterialTheme.typography.titleMedium)
        Spacer(Modifier.size(8.dp))
        Text(message, style = MaterialTheme.typography.bodySmall)
        Spacer(Modifier.size(20.dp))
        Button(onClick = onRetry) { Text("Try again") }
        TextButton(onClick = onSignOut) { Text("Sign out") }
    }
}
