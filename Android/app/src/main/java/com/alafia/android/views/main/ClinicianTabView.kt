@file:OptIn(ExperimentalMaterial3Api::class)

package com.alafia.android.views.main

import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.alafia.android.MainActivity
import com.alafia.android.views.calendar.CalendarScreen
import com.alafia.android.views.clinician.ClinicianDashboardScreen
import com.alafia.android.views.messaging.MessagingScreen
import com.alafia.android.views.profile.ProfileScreen
import com.alafia.android.views.roles.RolesScreen
import com.alafia.android.views.sharing.DataSharingScreen
import com.alafia.android.views.subscription.SubscriptionScreen
import com.alafia.android.views.telehealth.TelehealthScreen

/**
 * The clinician persona's tab bar.
 *
 * Clinician mode swaps the whole shell rather than adding a screen to the
 * patient one: a physician reviewing patients should not be navigating past
 * their own meal diary to do it, and the patient grid is the home screen.
 */
@Composable
fun ClinicianTabView(
    navController: NavHostController,
    activity: MainActivity
) {
    val innerNavController = rememberNavController()
    var selectedTab by remember { mutableStateOf(0) }

    data class ClinicianTab(
        val label: String,
        val icon: androidx.compose.ui.graphics.vector.ImageVector,
        val route: String,
    )

    val tabs = listOf(
        ClinicianTab("Patients", Icons.Default.People, "patients"),
        ClinicianTab("Messages", Icons.Default.Chat, "messaging"),
        ClinicianTab("Telehealth", Icons.Default.VideoCall, "telehealth"),
        ClinicianTab("Calendar", Icons.Default.CalendarMonth, "calendar"),
        ClinicianTab("Account", Icons.Default.Person, "account"),
    )

    Scaffold(
        bottomBar = {
            NavigationBar {
                tabs.forEachIndexed { index, tab ->
                    NavigationBarItem(
                        icon = { Icon(tab.icon, contentDescription = tab.label) },
                        label = { Text(tab.label) },
                        selected = selectedTab == index,
                        onClick = {
                            selectedTab = index
                            innerNavController.navigate(tab.route) {
                                popUpTo(tab.route) { inclusive = true }
                            }
                        }
                    )
                }
            }
        }
    ) { paddingValues ->
        NavHost(
            navController = innerNavController,
            startDestination = "patients",
            modifier = Modifier.padding(paddingValues)
        ) {
            composable("patients") {
                // No back arrow: this is the clinician's home screen, and there
                // is nothing behind it to pop to.
                ClinicianDashboardScreen(navController = innerNavController, showBack = false)
            }
            composable("messaging") { MessagingScreen(navController = innerNavController) }
            composable("telehealth") { TelehealthScreen(navController = innerNavController) }
            composable("calendar") { CalendarScreen(navController = innerNavController) }
            composable("account") { ClinicianAccountScreen(innerNavController) }
            composable("profile") { ProfileScreen(navController = innerNavController) }
            composable("roles") { RolesScreen(navController = innerNavController) }
            composable("subscription") { SubscriptionScreen(navController = innerNavController) }
            composable("data-sharing") { DataSharingScreen(navController = innerNavController) }
        }
    }
}

/** Account tab for clinician mode — and the way back to the patient view. */
@Composable
private fun ClinicianAccountScreen(navController: NavHostController) {
    Scaffold(
        topBar = { TopAppBar(title = { Text("Account") }) }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(
                            Icons.Default.MedicalServices,
                            contentDescription = null,
                            tint = MaterialTheme.colorScheme.primary
                        )
                        Spacer(Modifier.width(10.dp))
                        Text(
                            "Clinician view",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold
                        )
                    }
                    Text(
                        "Your own health record, meals and tracking live in the patient view.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Button(
                        onClick = { ClinicianModeState.exit() },
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Icon(Icons.Default.SwapHoriz, contentDescription = null)
                        Spacer(Modifier.width(8.dp))
                        Text("Switch to Patient View")
                    }
                }
            }

            listOf(
                Triple("My Profile", Icons.Default.Person, "profile"),
                Triple("Role", Icons.Default.Badge, "roles"),
                Triple("ALAFIA Membership", Icons.Default.AutoAwesome, "subscription"),
                Triple("Share Records", Icons.Default.Share, "data-sharing"),
            ).forEach { (label, icon, route) ->
                Card(
                    onClick = { navController.navigate(route) },
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        Modifier.padding(16.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(icon, contentDescription = null)
                        Spacer(Modifier.width(12.dp))
                        Text(label, style = MaterialTheme.typography.bodyLarge)
                    }
                }
            }
        }
    }
}
