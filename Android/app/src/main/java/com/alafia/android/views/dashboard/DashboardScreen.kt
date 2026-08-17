package com.alafia.android.views.dashboard
import com.alafia.android.util.ErrorUtil

import android.widget.Toast
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import com.alafia.android.api.ApiClient
import com.alafia.android.views.main.CLINICIAN_ROLES
import com.alafia.android.views.main.ClinicianModeState
import com.alafia.android.schemas.UserSchema
import com.alafia.android.schemas.UserUpdateRequest
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DashboardScreen(navController: NavController? = null) {
    var user by remember { mutableStateOf<UserSchema?>(null) }
    var isLoading by remember { mutableStateOf(true) }
    var showProfile by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    fun loadUser() {
        scope.launch {
            isLoading = true
            try {
                user = ApiClient.getApiService().getCurrentUser()
            } catch (e: Exception) {
                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
            }
            isLoading = false
        }
    }

    LaunchedEffect(Unit) { loadUser() }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Dashboard") },
                actions = {
                    // Clinician mode belongs where a clinician starts their day.
                    // It used to exist only as one tile among thirty in the More
                    // grid, which meant a physician had to know it was there to
                    // find it. Gated on the roles the account actually holds, so
                    // it is absent — not disabled — for everyone else.
                    val roles = (user?.active_roles ?: emptyList()) +
                        listOfNotNull(user?.primary_role)
                    if (roles.any { it in CLINICIAN_ROLES }) {
                        IconButton(onClick = { ClinicianModeState.enter(roles) }) {
                            Icon(Icons.Default.MedicalServices, "Clinician mode")
                        }
                    }
                    IconButton(onClick = { showProfile = true }) {
                        Icon(Icons.Default.Person, "Profile")
                    }
                }
            )
        }
    ) { padding ->
        if (isLoading) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        } else {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding)
                    .padding(16.dp)
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                // Welcome card
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)
                ) {
                    Column(modifier = Modifier.padding(20.dp)) {
                        Text(
                            "Welcome, ${user?.full_name ?: "User"}!",
                            style = MaterialTheme.typography.headlineSmall,
                            fontWeight = FontWeight.Bold
                        )
                        Spacer(Modifier.height(4.dp))
                        Text(
                            "Track your health and wellness journey",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.8f)
                        )
                    }
                }

                // Quick stats
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    QuickStatCard(
                        "Nutrition", Icons.Default.Restaurant, Color(0xFF4CAF50),
                        subtitle = "Track meals & macros",
                        modifier = Modifier.weight(1f),
                        onClick = { navController?.navigate("nutrition") }
                    )
                    QuickStatCard(
                        "Fitness", Icons.Default.FitnessCenter, Color(0xFF2196F3),
                        subtitle = "Log workouts",
                        modifier = Modifier.weight(1f),
                        onClick = { navController?.navigate("fitness") }
                    )
                }
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    QuickStatCard(
                        "Labs", Icons.Default.Science, Color(0xFF9C27B0),
                        subtitle = "Store results",
                        modifier = Modifier.weight(1f),
                        onClick = { navController?.navigate("labs") }
                    )
                    QuickStatCard(
                        "Medications", Icons.Default.Medication, Color(0xFFFF9800),
                        subtitle = "Manage Rx",
                        modifier = Modifier.weight(1f),
                        onClick = { navController?.navigate("medications") }
                    )
                }
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    QuickStatCard(
                        "Mood", Icons.Default.Face, Color(0xFFE91E63),
                        subtitle = "Mental health",
                        modifier = Modifier.weight(1f),
                        onClick = { navController?.navigate("mood") }
                    )
                    QuickStatCard(
                        "Lifestyle", Icons.Default.Favorite, Color(0xFFF44336),
                        subtitle = "Vitals & habits",
                        modifier = Modifier.weight(1f),
                        onClick = { navController?.navigate("lifestyle") }
                    )
                }

                // Health summary card
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text("Health Summary", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                        Spacer(Modifier.height(8.dp))
                        if (user?.blood_type != null) {
                            InfoRow("Blood Type", user!!.blood_type!!)
                        }
                        if (user?.height_cm != null) {
                            InfoRow("Height", "${user!!.height_cm} cm")
                        }
                        if (user?.current_weight_kg != null) {
                            InfoRow("Weight", "${user!!.current_weight_kg} kg")
                        }
                        if (user?.activity_level != null) {
                            InfoRow("Activity Level", user!!.activity_level!!.replaceFirstChar { it.uppercase() })
                        }
                        if (user?.allergies != null) {
                            InfoRow("Allergies", user!!.allergies!!)
                        }
                        if (user?.blood_type == null && user?.height_cm == null && user?.current_weight_kg == null) {
                            Text("Tap the profile icon to add your health info", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }
        }
    }

    if (showProfile) {
        ProfileEditDialog(
            user = user,
            onDismiss = { showProfile = false },
            onSave = { update ->
                scope.launch {
                    try {
                        user = ApiClient.getApiService().updateUser(update)
                        showProfile = false
                        Toast.makeText(context, "Profile updated", Toast.LENGTH_SHORT).show()
                    } catch (e: Exception) {
                        Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                    }
                }
            }
        )
    }
}

@Composable
private fun QuickStatCard(
    title: String,
    icon: ImageVector,
    color: Color,
    subtitle: String = "",
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null
) {
    Card(
        modifier = modifier,
        onClick = { onClick?.invoke() }
    ) {
        Column(
            modifier = Modifier.padding(16.dp).fillMaxWidth(),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Icon(icon, title, tint = color, modifier = Modifier.size(32.dp))
            Spacer(Modifier.height(8.dp))
            Text(title, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
            if (subtitle.isNotEmpty()) {
                Text(
                    subtitle,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

@Composable
private fun InfoRow(label: String, value: String) {
    Row(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Text(label, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.weight(1f))
        Text(value, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun ProfileEditDialog(user: UserSchema?, onDismiss: () -> Unit, onSave: (UserUpdateRequest) -> Unit) {
    var fullName by remember { mutableStateOf(user?.full_name ?: "") }
    var bloodType by remember { mutableStateOf(user?.blood_type ?: "") }
    var heightCm by remember { mutableStateOf(user?.height_cm?.toString() ?: "") }
    var weightKg by remember { mutableStateOf(user?.current_weight_kg?.toString() ?: "") }
    var allergies by remember { mutableStateOf(user?.allergies ?: "") }
    var activityLevel by remember { mutableStateOf(user?.activity_level ?: "") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Edit Profile") },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                OutlinedTextField(value = fullName, onValueChange = { fullName = it }, label = { Text("Full Name") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = bloodType, onValueChange = { bloodType = it }, label = { Text("Blood Type") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = heightCm, onValueChange = { heightCm = it }, label = { Text("Height (cm)") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = weightKg, onValueChange = { weightKg = it }, label = { Text("Weight (kg)") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = allergies, onValueChange = { allergies = it }, label = { Text("Allergies") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = activityLevel, onValueChange = { activityLevel = it }, label = { Text("Activity Level") }, modifier = Modifier.fillMaxWidth())
            }
        },
        confirmButton = {
            TextButton(onClick = {
                onSave(UserUpdateRequest(
                    full_name = fullName.ifBlank { null },
                    blood_type = bloodType.ifBlank { null },
                    height_cm = heightCm.toDoubleOrNull(),
                    current_weight_kg = weightKg.toDoubleOrNull(),
                    allergies = allergies.ifBlank { null },
                    activity_level = activityLevel.ifBlank { null }
                ))
            }) { Text("Save") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Cancel") }
        }
    )
}
