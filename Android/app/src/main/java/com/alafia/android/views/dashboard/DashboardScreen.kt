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
import androidx.compose.ui.res.stringResource
import com.alafia.android.R

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
                title = { Text(stringResource(R.string.dashboard)) },
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
                            stringResource(R.string.welcome, user?.full_name ?: stringResource(R.string.user_2)),
                            style = MaterialTheme.typography.headlineSmall,
                            fontWeight = FontWeight.Bold
                        )
                        Spacer(Modifier.height(4.dp))
                        Text(
                            stringResource(R.string.track_your_health_and_wellness_journey),
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
                        stringResource(R.string.nutrition), Icons.Default.Restaurant, Color(0xFF4CAF50),
                        subtitle = stringResource(R.string.track_meals_macros),
                        modifier = Modifier.weight(1f),
                        onClick = { navController?.navigate("nutrition") }
                    )
                    QuickStatCard(
                        stringResource(R.string.fitness), Icons.Default.FitnessCenter, Color(0xFF2196F3),
                        subtitle = stringResource(R.string.log_workouts),
                        modifier = Modifier.weight(1f),
                        onClick = { navController?.navigate("fitness") }
                    )
                }
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    QuickStatCard(
                        stringResource(R.string.labs_3), Icons.Default.Science, Color(0xFF9C27B0),
                        subtitle = stringResource(R.string.store_results),
                        modifier = Modifier.weight(1f),
                        onClick = { navController?.navigate("labs") }
                    )
                    QuickStatCard(
                        stringResource(R.string.medications), Icons.Default.Medication, Color(0xFFFF9800),
                        subtitle = stringResource(R.string.manage_rx),
                        modifier = Modifier.weight(1f),
                        onClick = { navController?.navigate("medications") }
                    )
                }
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    QuickStatCard(
                        stringResource(R.string.mood), Icons.Default.Face, Color(0xFFE91E63),
                        subtitle = stringResource(R.string.mental_health_2),
                        modifier = Modifier.weight(1f),
                        onClick = { navController?.navigate("mood") }
                    )
                    QuickStatCard(
                        stringResource(R.string.lifestyle), Icons.Default.Favorite, Color(0xFFF44336),
                        subtitle = stringResource(R.string.vitals_habits),
                        modifier = Modifier.weight(1f),
                        onClick = { navController?.navigate("lifestyle") }
                    )
                }

                // Health summary card
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text(stringResource(R.string.health_summary), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                        Spacer(Modifier.height(8.dp))
                        if (user?.blood_type != null) {
                            InfoRow(stringResource(R.string.blood_type), user!!.blood_type!!)
                        }
                        if (user?.height_cm != null) {
                            InfoRow(stringResource(R.string.height_2), "${user!!.height_cm} cm")
                        }
                        if (user?.current_weight_kg != null) {
                            InfoRow(stringResource(R.string.weight_2), "${user!!.current_weight_kg} kg")
                        }
                        if (user?.activity_level != null) {
                            InfoRow(stringResource(R.string.activity_level), user!!.activity_level!!.replaceFirstChar { it.uppercase() })
                        }
                        if (user?.allergies != null) {
                            InfoRow(stringResource(R.string.allergies), user!!.allergies!!)
                        }
                        if (user?.blood_type == null && user?.height_cm == null && user?.current_weight_kg == null) {
                            Text(stringResource(R.string.tap_the_profile_icon_to_add_your_health), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
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
    // The patient reads their height off whatever is in front of them. Their
    // profile says which system they use (locale picks the default; they can
    // change and toggle it), so the field is LABELLED in that unit, prefilled
    // in it, and the unit is sent with the value for the backend to convert.
    // Previously this was labelled "(cm)" for everyone and sent the raw number,
    // so an imperial patient entering 70 was stored as a 70 cm adult.
    val imperial = user?.preferred_units.equals("imperial", ignoreCase = true)
    val heightUnit = if (imperial) "in" else "cm"
    val weightUnit = if (imperial) "lb" else "kg"

    fun cmToIn(v: Double) = Math.round(v / 2.54 * 10.0) / 10.0
    fun kgToLb(v: Double) = Math.round(v / 0.45359237 * 10.0) / 10.0

    var heightCm by remember {
        mutableStateOf(user?.height_cm?.let { if (imperial) cmToIn(it).toString() else it.toString() } ?: "")
    }
    var weightKg by remember {
        mutableStateOf(user?.current_weight_kg?.let { if (imperial) kgToLb(it).toString() else it.toString() } ?: "")
    }
    var allergies by remember { mutableStateOf(user?.allergies ?: "") }
    var activityLevel by remember { mutableStateOf(user?.activity_level ?: "") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.edit_profile)) },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                OutlinedTextField(value = fullName, onValueChange = { fullName = it }, label = { Text(stringResource(R.string.full_name)) }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = bloodType, onValueChange = { bloodType = it }, label = { Text(stringResource(R.string.blood_type)) }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = heightCm, onValueChange = { heightCm = it }, label = { Text(stringResource(R.string.height, heightUnit)) }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = weightKg, onValueChange = { weightKg = it }, label = { Text(stringResource(R.string.weight, weightUnit)) }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = allergies, onValueChange = { allergies = it }, label = { Text(stringResource(R.string.allergies)) }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = activityLevel, onValueChange = { activityLevel = it }, label = { Text(stringResource(R.string.activity_level)) }, modifier = Modifier.fillMaxWidth())
            }
        },
        confirmButton = {
            TextButton(onClick = {
                onSave(UserUpdateRequest(
                    full_name = fullName.ifBlank { null },
                    blood_type = bloodType.ifBlank { null },
                    height_cm = heightCm.toDoubleOrNull(),
                    current_weight_kg = weightKg.toDoubleOrNull(),
                    // Say which unit the numbers above are in; the backend converts.
                    height_unit = heightCm.toDoubleOrNull()?.let { heightUnit },
                    weight_unit = weightKg.toDoubleOrNull()?.let { weightUnit },
                    allergies = allergies.ifBlank { null },
                    activity_level = activityLevel.ifBlank { null }
                ))
            }) { Text(stringResource(R.string.save)) }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text(stringResource(R.string.cancel)) }
        }
    )
}
