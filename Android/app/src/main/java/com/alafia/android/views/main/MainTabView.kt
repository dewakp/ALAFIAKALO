package com.alafia.android.views.main

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.alafia.android.MainActivity
import com.alafia.android.views.components.SharedComponents
import com.alafia.android.views.mentalhealth.MentalHealthScreen
import com.alafia.android.views.community.CommunityHealthScreen
import com.alafia.android.views.roles.RolesScreen
import com.alafia.android.views.mood.MoodScreen
import com.alafia.android.views.profile.ProfileScreen
import com.alafia.android.views.calendar.CalendarScreen
import com.alafia.android.views.telehealth.TelehealthScreen
import com.alafia.android.views.messaging.MessagingScreen
import com.alafia.android.views.nutrition.NutritionScreen
import com.alafia.android.views.dashboard.DashboardScreen
import com.alafia.android.views.fitness.FitnessScreen
import com.alafia.android.views.labs.LabsScreen
import com.alafia.android.views.medications.MedicationsScreen
import com.alafia.android.views.lifestyle.LifestyleScreen
import com.alafia.android.views.ai.AIChatScreen
import com.alafia.android.views.chronic.ChronicConditionsScreen
import com.alafia.android.views.privacy.PrivacySettingsScreen
import com.alafia.android.views.insurance.InsuranceScreen
import com.alafia.android.views.physicians.PhysiciansScreen
import com.alafia.android.views.labcharts.LabChartsScreen
import com.alafia.android.views.wellness.WellnessScreen
import com.alafia.android.views.planners.MealPlannerScreen
import com.alafia.android.views.planners.ExercisePlannerScreen
import com.alafia.android.views.imageai.ImageAIScreen
import com.alafia.android.views.pdftools.PdfToolsScreen
import com.alafia.android.views.pd.PeritonealDialysisScreen
import com.alafia.android.views.hd.HemodialysisScreen
import com.alafia.android.views.chemo.ChemotherapyScreen
import com.alafia.android.views.directives.AdvancedDirectivesScreen
import com.alafia.android.views.fda.FDARecallsScreen
import com.alafia.android.views.clinician.ClinicianDashboardScreen
import com.alafia.android.views.sharing.DataSharingScreen
import com.alafia.android.views.chartdashboard.ChartDashboardScreen
import com.alafia.android.views.pharmacy.PharmacyScreen
import com.alafia.android.views.elimination.EliminationScreen
import com.alafia.android.views.pantry.PantryScreen
import com.alafia.android.views.prompt.PromptScreen

@Composable
fun MainTabView(
    navController: NavHostController,
    activity: MainActivity
) {
    val innerNavController = rememberNavController()
    var selectedTab by remember { mutableStateOf(0) }

    Scaffold(
        bottomBar = {
            NavigationBar {
                NavigationBarItem(
                    icon = { Icon(Icons.Default.AutoAwesome, contentDescription = "Ask ALAFIA") },
                    label = { Text("Ask") },
                    selected = selectedTab == 0,
                    onClick = {
                        selectedTab = 0
                        innerNavController.navigate("prompt") {
                            popUpTo("prompt") { inclusive = true }
                        }
                    }
                )

                NavigationBarItem(
                    icon = { Icon(Icons.Default.FitnessCenter, contentDescription = "Fitness") },
                    label = { Text("Fitness") },
                    selected = selectedTab == 1,
                    onClick = {
                        selectedTab = 1
                        innerNavController.navigate("fitness") {
                            popUpTo("fitness") { inclusive = true }
                        }
                    }
                )

                NavigationBarItem(
                    icon = { Icon(Icons.Default.Face, contentDescription = "Mood") },
                    label = { Text("Mood") },
                    selected = selectedTab == 2,
                    onClick = {
                        selectedTab = 2
                        innerNavController.navigate("mood") {
                            popUpTo("mood") { inclusive = true }
                        }
                    }
                )

                NavigationBarItem(
                    icon = { Icon(Icons.Default.Restaurant, contentDescription = "Nutrition") },
                    label = { Text("Nutrition") },
                    selected = selectedTab == 3,
                    onClick = {
                        selectedTab = 3
                        innerNavController.navigate("nutrition") {
                            popUpTo("nutrition") { inclusive = true }
                        }
                    }
                )

                NavigationBarItem(
                    icon = { Icon(Icons.Default.LocalPharmacy, contentDescription = "More") },
                    label = { Text("More") },
                    selected = selectedTab == 4,
                    onClick = {
                        selectedTab = 4
                        innerNavController.navigate("more") {
                            popUpTo("more") { inclusive = true }
                        }
                    }
                )
            }
        }
    ) { paddingValues ->
        NavHost(
            navController = innerNavController,
            startDestination = "prompt",
            modifier = Modifier.padding(paddingValues)
        ) {
            composable("prompt") {
                PromptScreen(navController = innerNavController)
            }

            composable("dashboard") {
                DashboardScreen(navController = innerNavController)
            }

            composable("fitness") {
                FitnessScreen(navController = innerNavController)
            }

            composable("mood") {
                MoodScreen()
            }

            composable("nutrition") {
                NutritionScreen()
            }

            composable("more") {
                MoreScreen(innerNavController, navController, activity)
            }

            composable("labs") {
                LabsScreen(navController = innerNavController)
            }

            composable("medications") {
                MedicationsScreen(navController = innerNavController)
            }

            composable("lifestyle") {
                LifestyleScreen(navController = innerNavController)
            }

            composable("ai-chat") {
                AIChatScreen(navController = innerNavController)
            }

            composable("mental-health") {
                MentalHealthScreen(navController = innerNavController)
            }

            composable("community-health") {
                CommunityHealthScreen(navController = innerNavController)
            }

            composable("roles") {
                RolesScreen(navController = innerNavController)
            }

            composable("health-sync") {
                com.alafia.android.views.sync.HealthSyncScreen(navController = innerNavController)
            }

            composable("calendar") {
                CalendarScreen(navController = innerNavController)
            }

            composable("telehealth") {
                TelehealthScreen(navController = innerNavController)
            }

            composable("messaging") {
                MessagingScreen(navController = innerNavController)
            }

            composable("chronic-conditions") {
                ChronicConditionsScreen(navController = innerNavController)
            }

            composable("privacy-settings") {
                PrivacySettingsScreen(navController = innerNavController)
            }

            composable("insurance") {
                InsuranceScreen(navController = innerNavController)
            }

            composable("physicians") {
                PhysiciansScreen(navController = innerNavController)
            }

            composable("lab-charts") {
                LabChartsScreen(navController = innerNavController)
            }

            composable("wellness") {
                WellnessScreen(navController = innerNavController)
            }

            composable("meal-planner") {
                MealPlannerScreen(navController = innerNavController)
            }

            composable("exercise-planner") {
                ExercisePlannerScreen(navController = innerNavController)
            }

            composable("image-ai") {
                ImageAIScreen(navController = innerNavController)
            }

            composable("pdf-tools") {
                PdfToolsScreen(navController = innerNavController)
            }

            composable("hemodialysis") {
                HemodialysisScreen(navController = innerNavController)
            }

            composable("peritoneal-dialysis") {
                PeritonealDialysisScreen(navController = innerNavController)
            }

            composable("chemotherapy") {
                ChemotherapyScreen(navController = innerNavController)
            }

            composable("advanced-directives") {
                AdvancedDirectivesScreen(navController = innerNavController)
            }

            composable("fda-recalls") {
                FDARecallsScreen(navController = innerNavController)
            }

            composable("clinician-dashboard") {
                ClinicianDashboardScreen(navController = innerNavController)
            }

            composable("data-sharing") {
                DataSharingScreen(navController = innerNavController)
            }

            composable("chart-dashboard") {
                ChartDashboardScreen(navController = innerNavController)
            }

            composable("pharmacy") {
                PharmacyScreen(navController = innerNavController)
            }

            composable("pantry") {
                PantryScreen(navController = innerNavController)
            }
            composable("elimination") {
                EliminationScreen()
            }

            composable("profile") {
                ProfileScreen(navController = innerNavController)
            }
        }
    }
}

data class MoreGridItem(
    val label: String,
    val icon: ImageVector,
    val route: String,
    val clinicianOnly: Boolean = false
)

data class MoreGridSection(
    val title: String,
    val items: List<MoreGridItem>
)

@Composable
fun MoreScreen(
    innerNavController: NavHostController,
    outerNavController: NavHostController,
    activity: MainActivity
) {
    val clinicianRoles = setOf(
        "physician", "surgeon", "nurse_practitioner",
        "physician_assistant", "resident", "fellow", "attending_physician",
        "cardiologist", "dermatologist", "endocrinologist", "gastroenterologist",
        "neurologist", "oncologist", "pediatrician", "radiologist",
        "general_surgeon", "orthopedic_surgeon", "neurosurgeon",
        "cardiothoracic_surgeon", "plastic_surgeon", "vascular_surgeon",
        "oral_surgeon", "clinical_nurse_specialist", "nurse_anesthetist",
        "nurse_midwife", "charge_nurse", "nurse_administrator",
        "medical_director", "chief_medical_officer"
    )
    var isClinician by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) {
        try {
            val user = com.alafia.android.api.ApiClient.getApiService().getCurrentUser()
            val roles = (user.active_roles ?: emptyList()) + listOfNotNull(user.primary_role)
            isClinician = roles.any { it in clinicianRoles }
        } catch (_: Exception) { }
    }

    val sections = listOf(
        MoreGridSection("Health Tracking", listOf(
            MoreGridItem("Dashboard", Icons.Default.Home, "dashboard"),
            MoreGridItem("Lab Results", Icons.Default.Science, "labs"),
            MoreGridItem("Lab Charts", Icons.Default.BarChart, "lab-charts"),
            MoreGridItem("Medications", Icons.Default.Medication, "medications"),
            MoreGridItem("Lifestyle", Icons.Default.Favorite, "lifestyle"),
            MoreGridItem("Wellness", Icons.Default.Speed, "wellness"),
            MoreGridItem("Charts", Icons.Default.BarChart, "chart-dashboard"),
            MoreGridItem("Elimination", Icons.Default.WaterDrop, "elimination"),
        )),
        MoreGridSection("Mental Health", listOf(
            MoreGridItem("Mental Health", Icons.Default.Psychology, "mental-health"),
        )),
        MoreGridSection("Community", listOf(
            MoreGridItem("Community", Icons.Default.Public, "community-health"),
        )),
        MoreGridSection("Planning", listOf(
            MoreGridItem("Meal Planner", Icons.Default.Restaurant, "meal-planner"),
            MoreGridItem("Exercise", Icons.Default.DirectionsRun, "exercise-planner"),
            MoreGridItem("Pantry", Icons.Default.Kitchen, "pantry"),
            MoreGridItem("Calendar", Icons.Default.CalendarMonth, "calendar"),
        )),
        MoreGridSection("Care", listOf(
            MoreGridItem("Telehealth", Icons.Default.VideoCall, "telehealth"),
            MoreGridItem("Messages", Icons.Default.Chat, "messaging"),
            MoreGridItem("Physicians", Icons.Default.LocalHospital, "physicians"),
            MoreGridItem("Pharmacy", Icons.Default.LocalPharmacy, "pharmacy"),
            MoreGridItem("Clinician", Icons.Default.Dashboard, "clinician-dashboard", clinicianOnly = true),
        )),
        MoreGridSection("Therapies", listOf(
            MoreGridItem("Hemodialysis", Icons.Default.MonitorHeart, "hemodialysis"),
            MoreGridItem("PD", Icons.Default.WaterDrop, "peritoneal-dialysis"),
            MoreGridItem("Chemo", Icons.Default.Medication, "chemotherapy"),
        )),
        MoreGridSection("Tools", listOf(
            MoreGridItem("AI Chat", Icons.Default.SmartToy, "ai-chat"),
            MoreGridItem("Image AI", Icons.Default.CameraAlt, "image-ai"),
            MoreGridItem("PDF Tools", Icons.Default.PictureAsPdf, "pdf-tools"),
            MoreGridItem("Data Share", Icons.Default.Share, "data-sharing"),
        )),
        MoreGridSection("Profile", listOf(
            MoreGridItem("My Profile", Icons.Default.Person, "profile"),
            MoreGridItem("Role", Icons.Default.Badge, "roles"),
            MoreGridItem("Conditions", Icons.Default.MonitorHeart, "chronic-conditions"),
            MoreGridItem("Directives", Icons.Default.Description, "advanced-directives"),
            MoreGridItem("Insurance", Icons.Default.Shield, "insurance"),
            MoreGridItem("Health Sync", Icons.Default.Sync, "health-sync"),
            MoreGridItem("Privacy", Icons.Default.Lock, "privacy-settings"),
        )),
    )

    LazyVerticalGrid(
        columns = GridCells.Fixed(4),
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 12.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        item(span = { GridItemSpan(4) }) {
            Text(
                text = "More",
                style = MaterialTheme.typography.headlineLarge,
                modifier = Modifier.padding(top = 16.dp, bottom = 8.dp)
            )
        }

        sections.forEach { section ->
            val visibleItems = section.items.filter { !it.clinicianOnly || isClinician }
            if (visibleItems.isNotEmpty()) {
                item(span = { GridItemSpan(4) }) {
                    Text(
                        text = section.title,
                        style = MaterialTheme.typography.titleSmall,
                        color = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.padding(top = 12.dp, bottom = 4.dp)
                    )
                }
                items(visibleItems) { gridItem ->
                    MoreGridTile(
                        label = gridItem.label,
                        icon = gridItem.icon,
                        onClick = { innerNavController.navigate(gridItem.route) }
                    )
                }
            }
        }

        item(span = { GridItemSpan(4) }) {
            Spacer(modifier = Modifier.height(16.dp))
        }

        item(span = { GridItemSpan(4) }) {
            Button(
                onClick = {
                    com.alafia.android.api.KeychainHelper.clearAll(activity)
                    outerNavController.navigate("login") {
                        popUpTo("main") { inclusive = true }
                    }
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 24.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = MaterialTheme.colorScheme.error
                )
            ) {
                Text("Logout")
            }
        }
    }
}

@Composable
fun MoreGridTile(label: String, icon: ImageVector, onClick: () -> Unit) {
    Card(
        modifier = Modifier
            .aspectRatio(1f)
            .clickable(onClick = onClick),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant
        ),
        shape = MaterialTheme.shapes.medium
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(8.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            Icon(
                imageVector = icon,
                contentDescription = label,
                modifier = Modifier.size(28.dp),
                tint = MaterialTheme.colorScheme.primary
            )
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = label,
                style = MaterialTheme.typography.labelSmall,
                textAlign = TextAlign.Center,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
                fontSize = 11.sp
            )
        }
    }
}
