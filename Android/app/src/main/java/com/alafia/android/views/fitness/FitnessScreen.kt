@file:OptIn(ExperimentalMaterial3Api::class)

package com.alafia.android.views.fitness
import com.alafia.android.util.ErrorUtil

import android.widget.Toast
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
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
import com.alafia.android.schemas.FitnessLogRequest
import com.alafia.android.schemas.FitnessLogResponse
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import androidx.navigation.NavHostController

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FitnessScreen(navController: NavHostController) {
    var logs by remember { mutableStateOf<List<FitnessLogResponse>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    var showForm by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    fun loadLogs() {
        scope.launch {
            isLoading = true
            try {
                logs = ApiClient.getApiService().getFitnessLogs()
            } catch (e: Exception) {
                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
            }
            isLoading = false
        }
    }

    LaunchedEffect(Unit) { loadLogs() }

    Scaffold(
        topBar = { TopAppBar(
                title = { Text("Fitness") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                }
            ) },
        floatingActionButton = {
            FloatingActionButton(onClick = { showForm = true }) {
                Icon(Icons.Default.Add, "Add Workout")
            }
        }
    ) { padding ->
        if (isLoading) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        } else if (logs.isEmpty()) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(Icons.Default.FitnessCenter, "No workouts", modifier = Modifier.size(64.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
                    Spacer(Modifier.height(12.dp))
                    Text("No workouts logged", style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text("Tap + to log a workout", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(logs, key = { it.id }) { log ->
                    FitnessLogCard(
                        log = log,
                        onDelete = {
                            scope.launch {
                                try {
                                    ApiClient.getApiService().deleteFitnessLog(log.id)
                                    loadLogs()
                                } catch (e: Exception) {
                                    Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                                }
                            }
                        }
                    )
                }
            }
        }
    }

    if (showForm) {
        AddFitnessDialog(
            onDismiss = { showForm = false },
            onSave = { request ->
                scope.launch {
                    try {
                        ApiClient.getApiService().createFitnessLog(request)
                        showForm = false
                        loadLogs()
                        Toast.makeText(context, "Workout logged!", Toast.LENGTH_SHORT).show()
                    } catch (e: Exception) {
                        Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                    }
                }
            }
        )
    }
}

@Composable
private fun FitnessLogCard(log: FitnessLogResponse, onDelete: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        log.activity_type.replaceFirstChar { it.uppercase() },
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold
                    )
                    Text(log.log_date, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                if (log.intensity != null) {
                    AssistChip(
                        onClick = {},
                        label = { Text(log.intensity.replaceFirstChar { it.uppercase() }) }
                    )
                }
                IconButton(onClick = onDelete) {
                    Icon(Icons.Default.Delete, "Delete", tint = MaterialTheme.colorScheme.error)
                }
            }
            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                if (log.duration_minutes != null) {
                    MetricChip("${log.duration_minutes} min")
                }
                if (log.distance_km != null) {
                    MetricChip("${log.distance_km} km")
                }
                if (log.calories_burned != null) {
                    MetricChip("${log.calories_burned.toInt()} cal")
                }
                if (log.steps != null) {
                    MetricChip("${log.steps} steps")
                }
            }
            if (log.notes != null && log.notes.isNotEmpty()) {
                Spacer(Modifier.height(8.dp))
                Text(log.notes, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

@Composable
private fun MetricChip(text: String) {
    Surface(
        color = MaterialTheme.colorScheme.secondaryContainer,
        shape = MaterialTheme.shapes.small
    ) {
        Text(text, modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp), style = MaterialTheme.typography.labelSmall)
    }
}

@Composable
private fun AddFitnessDialog(onDismiss: () -> Unit, onSave: (FitnessLogRequest) -> Unit) {
    val activityTypes = listOf("running", "walking", "cycling", "swimming", "weight_training", "yoga", "hiit", "stretching", "other")
    val intensities = listOf("low", "moderate", "high", "very_high")

    var activityType by remember { mutableStateOf("running") }
    var duration by remember { mutableStateOf("") }
    var distance by remember { mutableStateOf("") }
    var calories by remember { mutableStateOf("") }
    var steps by remember { mutableStateOf("") }
    var heartRate by remember { mutableStateOf("") }
    var intensity by remember { mutableStateOf("moderate") }
    var notes by remember { mutableStateOf("") }
    var expandedActivity by remember { mutableStateOf(false) }
    var expandedIntensity by remember { mutableStateOf(false) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Log Workout") },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                // Activity type dropdown
                ExposedDropdownMenuBox(expanded = expandedActivity, onExpandedChange = { expandedActivity = it }) {
                    OutlinedTextField(
                        value = activityType.replaceFirstChar { it.uppercase() },
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Activity") },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expandedActivity) },
                        modifier = Modifier.menuAnchor().fillMaxWidth()
                    )
                    ExposedDropdownMenu(expanded = expandedActivity, onDismissRequest = { expandedActivity = false }) {
                        activityTypes.forEach {
                            DropdownMenuItem(
                                text = { Text(it.replace("_", " ").replaceFirstChar { c -> c.uppercase() }) },
                                onClick = { activityType = it; expandedActivity = false }
                            )
                        }
                    }
                }

                OutlinedTextField(value = duration, onValueChange = { duration = it }, label = { Text("Duration (min)") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = distance, onValueChange = { distance = it }, label = { Text("Distance (km)") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = calories, onValueChange = { calories = it }, label = { Text("Calories Burned") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = steps, onValueChange = { steps = it }, label = { Text("Steps") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = heartRate, onValueChange = { heartRate = it }, label = { Text("Avg Heart Rate") }, modifier = Modifier.fillMaxWidth())

                // Intensity dropdown
                ExposedDropdownMenuBox(expanded = expandedIntensity, onExpandedChange = { expandedIntensity = it }) {
                    OutlinedTextField(
                        value = intensity.replaceFirstChar { it.uppercase() },
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Intensity") },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expandedIntensity) },
                        modifier = Modifier.menuAnchor().fillMaxWidth()
                    )
                    ExposedDropdownMenu(expanded = expandedIntensity, onDismissRequest = { expandedIntensity = false }) {
                        intensities.forEach {
                            DropdownMenuItem(
                                text = { Text(it.replace("_", " ").replaceFirstChar { c -> c.uppercase() }) },
                                onClick = { intensity = it; expandedIntensity = false }
                            )
                        }
                    }
                }

                OutlinedTextField(value = notes, onValueChange = { notes = it }, label = { Text("Notes") }, modifier = Modifier.fillMaxWidth(), minLines = 2)
            }
        },
        confirmButton = {
            TextButton(onClick = {
                onSave(FitnessLogRequest(
                    log_date = LocalDate.now().format(DateTimeFormatter.ISO_DATE),
                    activity_type = activityType,
                    duration_minutes = duration.toIntOrNull(),
                    distance_km = distance.toFloatOrNull(),
                    calories_burned = calories.toFloatOrNull(),
                    heart_rate_avg = heartRate.toIntOrNull(),
                    heart_rate_max = null,
                    steps = steps.toIntOrNull(),
                    sets = null,
                    reps = null,
                    weight_kg = null,
                    intensity = intensity,
                    notes = notes.ifBlank { null }
                ))
            }) { Text("Save") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Cancel") }
        }
    )
}
