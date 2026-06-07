@file:OptIn(ExperimentalMaterial3Api::class)

package com.alafia.android.views.planners
import com.alafia.android.util.ErrorUtil

import android.widget.Toast
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.alafia.android.api.ApiClient
import com.alafia.android.models.*
import kotlinx.coroutines.launch
import androidx.navigation.NavHostController

private val FITNESS_LEVELS = listOf("Beginner", "Intermediate", "Advanced")

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ExercisePlannerScreen(navController: NavHostController) {
    var plans by remember { mutableStateOf<List<ExercisePlanResponse>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    var isGenerating by remember { mutableStateOf(false) }
    var showForm by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    // Form fields
    var selectedLevel by remember { mutableStateOf(FITNESS_LEVELS[0]) }
    var weeklyMinutes by remember { mutableStateOf("") }
    var limitations by remember { mutableStateOf("") }

    fun loadPlans() {
        scope.launch {
            isLoading = true
            try {
                plans = ApiClient.getApiService().getExercisePlans()
            } catch (e: Exception) {
                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
            }
            isLoading = false
        }
    }

    LaunchedEffect(Unit) { loadPlans() }

    Scaffold(
        topBar = { TopAppBar(
                title = { Text("Exercise Planner") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                }
            ) },
        floatingActionButton = {
            FloatingActionButton(onClick = { showForm = !showForm }) {
                Icon(
                    if (showForm) Icons.Default.Close else Icons.Default.Add,
                    contentDescription = if (showForm) "Close" else "New Plan"
                )
            }
        }
    ) { padding ->
        if (isLoading) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                // ── Generate Form ───────────────────────────────────────
                if (showForm) {
                    item {
                        Card(
                            modifier = Modifier.fillMaxWidth(),
                            elevation = CardDefaults.cardElevation(defaultElevation = 4.dp)
                        ) {
                            Column(modifier = Modifier.padding(16.dp)) {
                                Text("Generate Exercise Plan", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                                Spacer(Modifier.height(12.dp))

                                // Fitness level dropdown
                                var levelExpanded by remember { mutableStateOf(false) }
                                ExposedDropdownMenuBox(
                                    expanded = levelExpanded,
                                    onExpandedChange = { levelExpanded = it }
                                ) {
                                    OutlinedTextField(
                                        value = selectedLevel,
                                        onValueChange = {},
                                        readOnly = true,
                                        label = { Text("Fitness Level") },
                                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = levelExpanded) },
                                        modifier = Modifier.fillMaxWidth().menuAnchor()
                                    )
                                    ExposedDropdownMenu(
                                        expanded = levelExpanded,
                                        onDismissRequest = { levelExpanded = false }
                                    ) {
                                        FITNESS_LEVELS.forEach { level ->
                                            DropdownMenuItem(
                                                text = { Text(level) },
                                                onClick = {
                                                    selectedLevel = level
                                                    levelExpanded = false
                                                }
                                            )
                                        }
                                    }
                                }

                                Spacer(Modifier.height(8.dp))

                                OutlinedTextField(
                                    value = weeklyMinutes,
                                    onValueChange = { weeklyMinutes = it.filter { ch -> ch.isDigit() } },
                                    label = { Text("Weekly Minutes Target") },
                                    placeholder = { Text("e.g. 150") },
                                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                                    modifier = Modifier.fillMaxWidth()
                                )

                                Spacer(Modifier.height(8.dp))

                                OutlinedTextField(
                                    value = limitations,
                                    onValueChange = { limitations = it },
                                    label = { Text("Limitations") },
                                    placeholder = { Text("e.g. knee injury, no jumping") },
                                    modifier = Modifier.fillMaxWidth()
                                )

                                Spacer(Modifier.height(12.dp))

                                Button(
                                    onClick = {
                                        scope.launch {
                                            isGenerating = true
                                            try {
                                                val request = ExercisePlanRequest(
                                                    fitnessLevel = selectedLevel,
                                                    weeklyMinutesTarget = weeklyMinutes.toIntOrNull(),
                                                    limitations = limitations.ifBlank { null }
                                                )
                                                ApiClient.getApiService().createExercisePlan(request)
                                                showForm = false
                                                weeklyMinutes = ""
                                                limitations = ""
                                                loadPlans()
                                                Toast.makeText(context, "Exercise plan created!", Toast.LENGTH_SHORT).show()
                                            } catch (e: Exception) {
                                                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                                            }
                                            isGenerating = false
                                        }
                                    },
                                    modifier = Modifier.fillMaxWidth(),
                                    enabled = !isGenerating
                                ) {
                                    if (isGenerating) {
                                        CircularProgressIndicator(modifier = Modifier.size(20.dp), strokeWidth = 2.dp)
                                        Spacer(Modifier.width(8.dp))
                                    }
                                    Text("Generate Plan")
                                }
                            }
                        }
                    }
                }

                // ── Existing Plans ──────────────────────────────────────
                if (plans.isEmpty()) {
                    item {
                        Box(modifier = Modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) {
                            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                Icon(Icons.Default.FitnessCenter, "No plans", modifier = Modifier.size(64.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
                                Spacer(Modifier.height(12.dp))
                                Text("No exercise plans yet", style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                Text("Tap + to generate a plan", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    }
                } else {
                    item {
                        Text("Your Exercise Plans", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    }
                    items(plans, key = { it.id }) { plan ->
                        ExercisePlanCard(plan = plan)
                    }
                }
            }
        }
    }
}

@Composable
private fun ExercisePlanCard(plan: ExercisePlanResponse) {
    var expanded by remember { mutableStateOf(false) }

    Card(
        modifier = Modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(plan.planName, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                    if (plan.fitnessLevel != null) {
                        Text(plan.fitnessLevel, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.primary)
                    }
                    if (plan.weeklyMinutesTarget != null) {
                        Text("${plan.weeklyMinutesTarget} min/week", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
                IconButton(onClick = { expanded = !expanded }) {
                    Icon(
                        if (expanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                        contentDescription = if (expanded) "Collapse" else "Expand"
                    )
                }
            }

            AnimatedVisibility(visible = expanded) {
                Column(modifier = Modifier.padding(top = 8.dp)) {
                    if (plan.advice != null) {
                        Text(plan.advice, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Spacer(Modifier.height(8.dp))
                    }

                    plan.planData?.entries?.sortedBy { it.key }?.forEach { (dayKey, exercises) ->
                        DayExercisesSection(dayLabel = dayKey, exercises = exercises)
                        Spacer(Modifier.height(8.dp))
                    }
                }
            }
        }
    }
}

@Composable
private fun DayExercisesSection(dayLabel: String, exercises: List<ExerciseItem>) {
    val displayLabel = dayLabel.replaceFirstChar { it.uppercase() }.replace("_", " ")

    Surface(
        shape = RoundedCornerShape(8.dp),
        color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(displayLabel, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(4.dp))

            exercises.forEach { exercise ->
                ExerciseItemRow(exercise = exercise)
                Spacer(Modifier.height(4.dp))
            }
        }
    }
}

@Composable
private fun ExerciseItemRow(exercise: ExerciseItem) {
    Surface(
        shape = RoundedCornerShape(6.dp),
        color = MaterialTheme.colorScheme.surface,
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(8.dp)) {
            Text(exercise.name, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)

            Row(
                modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                if (exercise.durationMinutes != null) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Default.Timer, contentDescription = null, modifier = Modifier.size(14.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
                        Spacer(Modifier.width(2.dp))
                        Text("${exercise.durationMinutes} min", style = MaterialTheme.typography.bodySmall)
                    }
                }
                if (exercise.sets != null && exercise.reps != null) {
                    Text("${exercise.sets}×${exercise.reps}", style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.Medium)
                } else if (exercise.sets != null) {
                    Text("${exercise.sets} sets", style = MaterialTheme.typography.bodySmall)
                } else if (exercise.reps != null) {
                    Text("${exercise.reps} reps", style = MaterialTheme.typography.bodySmall)
                }
            }

            if (!exercise.muscleGroups.isNullOrEmpty()) {
                Spacer(Modifier.height(4.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    exercise.muscleGroups.forEach { muscle ->
                        Surface(
                            shape = RoundedCornerShape(12.dp),
                            color = MaterialTheme.colorScheme.primaryContainer
                        ) {
                            Text(
                                muscle,
                                modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp),
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onPrimaryContainer
                            )
                        }
                    }
                }
            }

            if (exercise.description != null) {
                Spacer(Modifier.height(4.dp))
                Text(exercise.description, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}
