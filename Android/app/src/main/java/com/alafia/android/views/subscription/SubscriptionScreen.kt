@file:OptIn(ExperimentalMaterial3Api::class)

package com.alafia.android.views.subscription

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import android.widget.Toast
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavHostController
import com.alafia.android.api.ApiClient
import com.alafia.android.api.EntitlementState
import com.alafia.android.billing.BillingManager
import com.alafia.android.models.GoogleVerifyRequest
import com.alafia.android.models.SubscriptionPlans
import com.alafia.android.models.SubscriptionStatus
import kotlinx.coroutines.launch

private const val PLUS_PRODUCT_ID = "alafia_plus_monthly"

private val PLUS_FEATURES = listOf(
    "Unlimited AI health-guide conversations",
    "Advanced labs & vitals trend forecasting",
    "Meal & exercise planners with AI photo analysis",
    "Priority sync across web, iOS & Android",
)

private fun Context.findActivity(): Activity? {
    var ctx: Context? = this
    while (ctx is ContextWrapper) {
        if (ctx is Activity) return ctx
        ctx = ctx.baseContext
    }
    return null
}

@Composable
fun SubscriptionScreen(
    navController: NavHostController,
    /**
     * `true` when this is the membership WALL rather than a settings screen: the
     * user has no way past it except paying, restoring, or signing out. The
     * backend already answers 402 to every gated path, so letting them into the
     * tabs only produces a shell of failed requests.
     */
    blocking: Boolean = false,
    onSignOut: () -> Unit = {},
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var status by remember { mutableStateOf<SubscriptionStatus?>(null) }
    var plans by remember { mutableStateOf<SubscriptionPlans?>(null) }
    var loading by remember { mutableStateOf(true) }
    var purchasing by remember { mutableStateOf(false) }
    var billingReady by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf<String?>(null) }

    suspend fun refreshStatus() {
        try { status = ApiClient.getApiService().getSubscriptionStatus() } catch (_: Exception) {}
    }

    // Billing lifecycle — created once, torn down on leave.
    val billingManager = remember {
        BillingManager(
            context = context,
            productId = PLUS_PRODUCT_ID,
            onReady = { billingReady = true },
            onPurchase = { token, orderId ->
                scope.launch {
                    try {
                        status = ApiClient.getApiService().verifyGooglePurchase(
                            GoogleVerifyRequest(purchaseToken = token,
                                productId = PLUS_PRODUCT_ID, orderId = orderId)
                        )
                        message = "You're now on ALAFIA Membership. Welcome aboard!"
                    } catch (e: Exception) {
                        message = "Purchase made but verification failed — it may update shortly."
                    } finally {
                        purchasing = false
                    }
                }
            },
            onError = { err ->
                purchasing = false
                message = err
            },
        )
    }

    LaunchedEffect(Unit) {
        try {
            plans = ApiClient.getApiService().getSubscriptionPlans()
            refreshStatus()
        } catch (_: Exception) {} finally { loading = false }
        billingManager.start()
    }

    // A purchase — new, restored, or already active on another device — is
    // verified server-side before it counts. When the backend agrees, open the
    // app without waiting for another round-trip.
    LaunchedEffect(status?.entitled) {
        if (status?.entitled == true) EntitlementState.markEntitled()
    }

    DisposableEffect(Unit) {
        onDispose { billingManager.end() }
    }

    message?.let {
        LaunchedEffect(it) {
            Toast.makeText(context, it, Toast.LENGTH_LONG).show()
            message = null
        }
    }

    val androidPrice = plans?.rails?.firstOrNull { it.provider == "google_play" }?.priceUsd
    val entitled = status?.entitled == true

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("ALAFIA Membership") },
                navigationIcon = {
                    if (!blocking) {
                        IconButton(onClick = { navController.popBackStack() }) {
                            Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                        }
                    }
                }
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 20.dp)
                .verticalScroll(rememberScrollState()),
        ) {
            Spacer(Modifier.height(12.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Default.AutoAwesome, contentDescription = null, tint = Color(0xFF7C4DFF))
                Spacer(Modifier.width(8.dp))
                Text(plans?.productName ?: "ALAFIA Membership",
                    fontSize = 24.sp, fontWeight = FontWeight.Bold)
            }
            Text(
                if (blocking)
                    "ALAFIA needs an active membership. Subscribe to continue — if you already pay on another device, restore it below."
                else
                    "Unlock the full ALAFIA experience across every device.",
                color = Color.Gray, modifier = Modifier.padding(top = 4.dp, bottom = 16.dp))

            when {
                loading -> Box(Modifier.fillMaxWidth().padding(40.dp), Alignment.Center) {
                    CircularProgressIndicator()
                }

                entitled -> SubscribedCard(status!!)

                else -> Card(
                    shape = RoundedCornerShape(16.dp),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Column(Modifier.padding(20.dp)) {
                        Row(verticalAlignment = Alignment.Bottom) {
                            Text(androidPrice?.let { "$%.2f".format(it) } ?: "—",
                                fontSize = 36.sp, fontWeight = FontWeight.ExtraBold)
                            Text(" / month", color = Color.Gray,
                                modifier = Modifier.padding(bottom = 6.dp))
                        }
                        Spacer(Modifier.height(14.dp))
                        PLUS_FEATURES.forEach { f ->
                            Row(Modifier.padding(vertical = 5.dp)) {
                                Icon(Icons.Default.CheckCircle, contentDescription = null,
                                    tint = Color(0xFF2E7D32), modifier = Modifier.size(20.dp))
                                Spacer(Modifier.width(10.dp))
                                Text(f, fontSize = 15.sp)
                            }
                        }
                        Spacer(Modifier.height(18.dp))
                        Button(
                            onClick = {
                                val activity = context.findActivity()
                                if (activity == null) {
                                    message = "Unable to start checkout."
                                } else {
                                    purchasing = true
                                    billingManager.launch(activity)
                                }
                            },
                            enabled = billingReady && !purchasing,
                            modifier = Modifier.fillMaxWidth().height(50.dp),
                        ) {
                            if (purchasing) {
                                CircularProgressIndicator(
                                    modifier = Modifier.size(20.dp), strokeWidth = 2.dp,
                                    color = MaterialTheme.colorScheme.onPrimary)
                            } else {
                                Text(if (billingReady) "Subscribe" else "Loading…",
                                    fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                            }
                        }
                        Text("Billed monthly through Google Play. Cancel anytime in Play Store settings.",
                            fontSize = 12.sp, color = Color.Gray,
                            modifier = Modifier.padding(top = 12.dp))
                    }
                }
            }

            // The only two ways off the wall that are not "pay again": a purchase
            // this install has not seen yet, and signing out. Without them a user
            // who already paid on iOS — or who signed in as the wrong account —
            // is simply stuck with no route forward.
            if (blocking && !entitled) {
                Spacer(Modifier.height(20.dp))
                TextButton(
                    onClick = {
                        scope.launch {
                            message = "Checking for an existing subscription…"
                            billingManager.start()      // re-queries owned purchases
                            refreshStatus()
                            EntitlementState.refresh()
                        }
                    },
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("Restore purchase") }

                TextButton(
                    onClick = {
                        EntitlementState.reset()
                        onSignOut()
                    },
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("Sign out", color = MaterialTheme.colorScheme.error) }
                Spacer(Modifier.height(24.dp))
            }
        }
    }
}

@Composable
private fun SubscribedCard(status: SubscriptionStatus) {
    Card(
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = Color(0xFFF1F8F4)),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(20.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Default.Verified, contentDescription = null, tint = Color(0xFF2E7D32))
                Spacer(Modifier.width(8.dp))
                Text("You're subscribed", fontSize = 18.sp, fontWeight = FontWeight.Bold)
            }
            Spacer(Modifier.height(10.dp))
            Text("Plan: ${status.productName}", fontSize = 14.sp)
            status.priceUsd?.let { Text("Price: $%.2f / month".format(it), fontSize = 14.sp) }
            Text("Billing via: ${prettyProvider(status.provider)}", fontSize = 14.sp)
            status.currentPeriodEnd?.let {
                val label = if (status.cancelAtPeriodEnd) "Access ends" else "Renews"
                Text("$label on ${it.take(10)}", fontSize = 14.sp)
            }
            if (status.provider == "google_play") {
                Spacer(Modifier.height(10.dp))
                Text("Manage or cancel in Google Play → Subscriptions.",
                    fontSize = 13.sp, color = Color.Gray)
            }
        }
    }
}

private fun prettyProvider(p: String): String = when (p) {
    "stripe" -> "Card (Stripe)"
    "google_play" -> "Google Play"
    "apple" -> "App Store"
    else -> p
}
