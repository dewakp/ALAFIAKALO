@file:OptIn(ExperimentalMaterial3Api::class)

package com.alafia.android.views.clinician
import com.alafia.android.util.ErrorUtil

import android.widget.Toast
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.alafia.android.api.ApiClient
import com.alafia.android.models.ClinicianDashboardResponse
import com.alafia.android.models.PatientSummary
import kotlinx.coroutines.launch
import androidx.navigation.NavHostController

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ClinicianDashboardScreen(navController: NavHostController) {
    var dashboard by remember { mutableStateOf<ClinicianDashboardResponse?>(null) }
    var isLoading by remember { mutableStateOf(true) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    fun loadDashboard() {
        scope.launch {
            isLoading = true
            errorMessage = null
            try {
                dashboard = ApiClient.getApiService().getClinicianDashboard()
            } catch (e: retrofit2.HttpException) {
                if (e.code() == 403) {
                    errorMessage = "Access denied. This feature is only available to clinicians."
                } else {
                    errorMessage = "Error: ${e.message()}"
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

    Scaffold(
        topBar = { TopAppBar(
                title = { Text("Clinician Dashboard") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                }
            ) }
    ) { padding ->
        if (isLoading) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        } else if (errorMessage != null) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(
                        Icons.Default.Lock,
                        "Access restricted",
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
                    Button(onClick = { loadDashboard() }) {
                        Text("Retry")
                    }
                }
            }
        } else if (dashboard == null || dashboard!!.patients.isEmpty()) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(
                        Icons.Default.People,
                        "No patients",
                        modifier = Modifier.size(64.dp),
                        tint = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Spacer(Modifier.height(12.dp))
                    Text(
                        "No patients have shared data with you yet",
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        "Patients can share their health data from their Data Sharing settings",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                item {
                    Text(
                        "${dashboard!!.patients.size} patient${if (dashboard!!.patients.size != 1) "s" else ""}",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(bottom = 4.dp)
                    )
                }
                items(dashboard!!.patients, key = { it.patientId }) { patient ->
                    PatientCard(patient)
                }
            }
        }
    }
}

@Composable
private fun PatientCard(patient: PatientSummary) {
    var expanded by remember { mutableStateOf(false) }

    Card(
        modifier = Modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
        onClick = { expanded = !expanded }
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        Icons.Default.Person,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.size(40.dp)
                    )
                    Spacer(Modifier.width(12.dp))
                    Column {
                        Text(
                            text = patient.displayName ?: "Patient #${patient.patientId}",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold
                        )
                        Text(
                            text = "ID: ${patient.patientId}",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
                Icon(
                    if (expanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                    contentDescription = if (expanded) "Collapse" else "Expand",
                    tint = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            // Shared data type chips
            if (!patient.sharedDataTypes.isNullOrEmpty()) {
                Spacer(Modifier.height(12.dp))
                Text(
                    "Shared Data Types",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontWeight = FontWeight.SemiBold
                )
                Spacer(Modifier.height(4.dp))
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    val typesToShow = if (expanded) patient.sharedDataTypes else patient.sharedDataTypes.take(4)
                    typesToShow.forEach { dataType ->
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
                                    modifier = Modifier.size(16.dp)
                                )
                            }
                        )
                    }
                    if (!expanded && patient.sharedDataTypes.size > 4) {
                        SuggestionChip(
                            onClick = { },
                            label = { Text("+${patient.sharedDataTypes.size - 4} more") }
                        )
                    }
                }
            }
        }
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
    "dialysis" -> Icons.Default.WaterDrop
    "lifestyle" -> Icons.Default.Spa
    "appointments" -> Icons.Default.CalendarToday
    else -> Icons.Default.Folder
}
