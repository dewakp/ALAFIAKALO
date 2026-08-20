@file:OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)

package com.alafia.android.views.clinician
import com.alafia.android.util.ErrorUtil

import android.widget.Toast
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.alafia.android.api.ApiClient
import com.alafia.android.models.ClinicianDashboardResponse
import com.alafia.android.models.PatientSummary
import kotlinx.coroutines.launch
import androidx.navigation.NavHostController

/**
 * The clinician's home screen: every patient who shares with them, as a grid of
 * cards. Each card carries enough signal — latest vitals, how many labs are
 * abnormal — to decide who to open first, and tapping one opens the full record.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ClinicianDashboardScreen(
    navController: NavHostController,
    showBack: Boolean = true,
) {
    var dashboard by remember { mutableStateOf<ClinicianDashboardResponse?>(null) }
    var isLoading by remember { mutableStateOf(true) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    var selected by remember { mutableStateOf<PatientSummary?>(null) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    fun loadDashboard() {
        scope.launch {
            isLoading = true
            errorMessage = null
            try {
                dashboard = ApiClient.getApiService().getClinicianDashboard()
            } catch (e: retrofit2.HttpException) {
                errorMessage = if (e.code() == 403) {
                    "Access denied. This view is only available to clinician accounts."
                } else {
                    "Error: ${e.message()}"
                }
                Toast.makeText(context, errorMessage, Toast.LENGTH_SHORT).show()
            } catch (e: Exception) {
                errorMessage = ErrorUtil.userMessage(e)
                Toast.makeText(context, errorMessage, Toast.LENGTH_SHORT).show()
            }
            isLoading = false
        }
    }

    LaunchedEffect(Unit) { loadDashboard() }

    val patient = selected
    if (patient != null) {
        PatientBoardScreen(
            patientId = patient.userId,
            patientName = patient.fullName.ifEmpty { "Patient #${patient.userId}" },
            onBack = { selected = null },
        )
        return
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("My Patients") },
                navigationIcon = {
                    if (showBack) {
                        IconButton(onClick = { navController.popBackStack() }) {
                            Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                        }
                    }
                }
            )
        }
    ) { padding ->
        when {
            isLoading -> Box(
                Modifier.fillMaxSize().padding(padding),
                contentAlignment = Alignment.Center
            ) { CircularProgressIndicator() }

            errorMessage != null -> Box(
                Modifier.fillMaxSize().padding(padding),
                contentAlignment = Alignment.Center
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(
                        Icons.Default.Lock, "Access restricted",
                        modifier = Modifier.size(64.dp),
                        tint = MaterialTheme.colorScheme.error
                    )
                    Spacer(Modifier.height(12.dp))
                    Text(
                        errorMessage!!,
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.error
                    )
                    Spacer(Modifier.height(16.dp))
                    Button(onClick = { loadDashboard() }) { Text("Retry") }
                }
            }

            dashboard == null || dashboard!!.patients.isEmpty() -> Box(
                Modifier.fillMaxSize().padding(padding),
                contentAlignment = Alignment.Center
            ) {
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    modifier = Modifier.padding(24.dp)
                ) {
                    Icon(
                        Icons.Default.People, "No patients",
                        modifier = Modifier.size(64.dp),
                        tint = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Spacer(Modifier.height(12.dp))
                    Text(
                        "No patients yet",
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        "Patients appear here as soon as they share their records with you, from Share, using your account email.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            else -> LazyVerticalGrid(
                columns = GridCells.Adaptive(minSize = 168.dp),
                modifier = Modifier.fillMaxSize().padding(padding),
                contentPadding = PaddingValues(12.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                item(span = { GridItemSpan(maxLineSpan) }) {
                    Text(
                        "${dashboard!!.patients.size} patient${if (dashboard!!.patients.size != 1) "s" else ""}",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                items(dashboard!!.patients, key = { it.userId }) { p ->
                    PatientCard(p) { selected = p }
                }
            }
        }
    }
}

/** Deterministic tint per patient, so a card keeps its colour between loads. */
private val avatarTints = listOf(
    Color(0xFF0EA5E9), Color(0xFF8B5CF6), Color(0xFFF59E0B),
    Color(0xFF10B981), Color(0xFFEF4444), Color(0xFF6366F1),
)

private fun tintFor(id: Int) = avatarTints[kotlin.math.abs(id) % avatarTints.size]

private fun initialsOf(name: String): String {
    val parts = name.trim().split(Regex("\\s+")).filter { it.isNotEmpty() }.take(2)
    val s = parts.mapNotNull { it.firstOrNull()?.uppercase() }.joinToString("")
    return s.ifEmpty { "?" }
}

@Composable
private fun PatientCard(patient: PatientSummary, onOpen: () -> Unit) {
    val abnormal = patient.latestLabs.count { it.isAbnormal }

    Card(
        modifier = Modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
        onClick = onOpen
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    modifier = Modifier.size(40.dp),
                    contentAlignment = Alignment.Center
                ) {
                    Surface(
                        color = tintFor(patient.userId),
                        shape = MaterialTheme.shapes.extraLarge,
                        modifier = Modifier.size(40.dp)
                    ) {}
                    Text(
                        initialsOf(patient.fullName),
                        style = MaterialTheme.typography.labelLarge,
                        fontWeight = FontWeight.Bold,
                        color = Color.White
                    )
                }
                Spacer(Modifier.width(10.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        patient.fullName.ifEmpty { "Patient #${patient.userId}" },
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                    patient.email?.let {
                        Text(
                            it,
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                }
            }

            patient.latestVitals?.let { v ->
                Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                    v.bp?.let { Metric("BP", it) }
                    v.hr?.let { Metric("HR", "$it") }
                }
            }

            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(
                    "${patient.latestLabs.size} labs",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Text(
                    "${patient.medications.size} meds",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                if (abnormal > 0) {
                    Text(
                        "⚠ $abnormal abnormal",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.error,
                        fontWeight = FontWeight.SemiBold
                    )
                }
            }

            if (patient.permissions.isNotEmpty()) {
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                    verticalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    patient.permissions.take(3).forEach { dataType ->
                        SuggestionChip(
                            onClick = {},
                            label = {
                                Text(
                                    dataType.replaceFirstChar { it.uppercase() },
                                    style = MaterialTheme.typography.labelSmall
                                )
                            },
                            icon = {
                                Icon(
                                    imageVector = dataTypeIcon(dataType),
                                    contentDescription = null,
                                    modifier = Modifier.size(14.dp)
                                )
                            }
                        )
                    }
                    if (patient.permissions.size > 3) {
                        Text(
                            "+${patient.permissions.size - 3}",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun Metric(label: String, value: String) {
    Column {
        Text(
            label,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Text(value, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun dataTypeIcon(type: String) = when (type.lowercase()) {
    "labs" -> Icons.Default.Science
    "medications" -> Icons.Default.LocalPharmacy
    "vitals" -> Icons.Default.MonitorHeart
    "nutrition" -> Icons.Default.Restaurant
    "fitness" -> Icons.Default.FitnessCenter
    "mood" -> Icons.Default.SentimentSatisfied
    "sleep" -> Icons.Default.Bedtime
    "conditions" -> Icons.Default.MedicalServices
    "elimination" -> Icons.Default.WaterDrop
    "journal" -> Icons.Default.Book
    "connected_records" -> Icons.Default.Link
    "messages" -> Icons.Default.Forum
    "dialysis" -> Icons.Default.WaterDrop
    "lifestyle" -> Icons.Default.Spa
    "all" -> Icons.Default.SelectAll
    else -> Icons.Default.Folder
}
