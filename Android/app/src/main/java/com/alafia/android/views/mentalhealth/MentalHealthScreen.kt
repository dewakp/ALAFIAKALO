package com.alafia.android.views.mentalhealth
import com.alafia.android.util.ErrorUtil

import android.widget.Toast
import androidx.compose.animation.animateColorAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.alafia.android.api.ApiClient
import com.alafia.android.models.*
import com.alafia.android.schemas.*
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import androidx.navigation.NavHostController

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MentalHealthScreen(navController: NavHostController) {
    var selectedTab by remember { mutableIntStateOf(0) }
    val tabs = listOf("Dashboard", "Breathing", "Gratitude", "Assessments")

    var stats by remember { mutableStateOf<MentalHealthStats?>(null) }
    var exercises by remember { mutableStateOf<List<BreathingExerciseInfo>>(emptyList()) }
    var gratitudes by remember { mutableStateOf<List<GratitudeEntryResponse>>(emptyList()) }
    var assessments by remember { mutableStateOf<List<MentalHealthAssessment>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    fun loadAll() {
        scope.launch {
            isLoading = true
            try {
                val api = ApiClient.getApiService()
                stats = api.getMentalHealthStats()
                exercises = api.getBreathingExercises()
                gratitudes = api.getGratitudeEntries()
                assessments = api.getAssessments()
            } catch (e: Exception) {
                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
            }
            isLoading = false
        }
    }

    LaunchedEffect(Unit) { loadAll() }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Mental Health") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                }
            )
        }
    ) { padding ->
    Column(modifier = Modifier.fillMaxSize().padding(padding)) {
        ScrollableTabRow(selectedTabIndex = selectedTab, edgePadding = 8.dp) {
            tabs.forEachIndexed { i, title ->
                Tab(selected = selectedTab == i, onClick = { selectedTab = i }, text = { Text(title) })
            }
        }

        if (isLoading) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        } else {
            when (selectedTab) {
                0 -> DashboardTab(stats)
                1 -> BreathingTab(exercises) { loadAll() }
                2 -> GratitudeTab(gratitudes) { loadAll() }
                3 -> AssessmentsTab(assessments) { loadAll() }
            }
        }
    }
}
}

// ──────────── Dashboard Tab ────────────

@Composable
fun DashboardTab(stats: MentalHealthStats?) {
    if (stats == null) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Text("No data yet. Start by logging your mood!", textAlign = TextAlign.Center)
        }
        return
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        // Wellness Score
        val score = stats.wellnessScore ?: 0
        val color = when { score >= 70 -> Color(0xFF4CAF50); score >= 40 -> Color(0xFFFF9800); else -> Color(0xFFF44336) }

        Text(
            text = "$score",
            fontSize = 56.sp,
            fontWeight = FontWeight.Black,
            color = color
        )
        Text("Wellness Score (0–100)", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)

        Spacer(Modifier.height(20.dp))

        // Stats Grid
        val trendEmoji = when (stats.moodTrend) { "improving" -> "📈"; "declining" -> "📉"; else -> "➡️" }

        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp)) {
                StatTile("Mood (7d)", stats.avgMood7d?.let { "%.1f/10".format(it) } ?: "—", Modifier.weight(1f))
                StatTile("Trend", "$trendEmoji ${stats.moodTrend ?: "—"}", Modifier.weight(1f))
                StatTile("Streak", "${stats.streakDays}d 🔥", Modifier.weight(1f))
            }
            Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp)) {
                StatTile("Stress", stats.avgStress7d?.let { "%.1f/10".format(it) } ?: "—", Modifier.weight(1f))
                StatTile("Anxiety", stats.avgAnxiety7d?.let { "%.1f/10".format(it) } ?: "—", Modifier.weight(1f))
                StatTile("Sleep", stats.avgSleepHours7d?.let { "%.1fh".format(it) } ?: "—", Modifier.weight(1f))
            }
            Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp)) {
                StatTile("Entries (30d)", "${stats.totalEntries30d}", Modifier.weight(1f))
                StatTile("Breathing", "${stats.totalBreathingMinutes30d}m", Modifier.weight(1f))
                StatTile("Sleep Q.", stats.avgSleepQuality7d?.let { "%.1f".format(it) } ?: "—", Modifier.weight(1f))
            }
        }

        Spacer(Modifier.height(20.dp))

        // Clinical Summary
        if (stats.latestPhq9Score != null || stats.latestGad7Score != null || stats.latestWho5Score != null) {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp)) {
                    Text("📋 Clinical Assessments", style = MaterialTheme.typography.titleMedium)
                    Spacer(Modifier.height(8.dp))
                    stats.latestPhq9Score?.let {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text("PHQ-9: $it/27", Modifier.weight(1f))
                            SeverityChip(stats.latestPhq9Severity)
                        }
                    }
                    stats.latestGad7Score?.let {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text("GAD-7: $it/21", Modifier.weight(1f))
                            SeverityChip(stats.latestGad7Severity)
                        }
                    }
                    stats.latestWho5Score?.let {
                        Text("WHO-5: $it%")
                    }
                }
            }
        }
    }
}

@Composable
fun StatTile(label: String, value: String, modifier: Modifier = Modifier) {
    Card(modifier = modifier) {
        Column(
            Modifier.padding(10.dp).fillMaxWidth(),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(value, fontWeight = FontWeight.Bold, fontSize = 16.sp, textAlign = TextAlign.Center, maxLines = 1)
            Text(label, fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, textAlign = TextAlign.Center, maxLines = 1)
        }
    }
}

@Composable
fun SeverityChip(severity: String?) {
    if (severity == null) return
    val color = when (severity) {
        "minimal" -> Color(0xFF4CAF50); "mild" -> Color(0xFF8BC34A)
        "moderate" -> Color(0xFFFF9800); "moderately_severe", "severe" -> Color(0xFFF44336)
        "good" -> Color(0xFF4CAF50); "low", "very_low" -> Color(0xFFF44336)
        else -> Color.Gray
    }
    Text(
        severity.replace("_", " ").replaceFirstChar { it.uppercase() },
        fontSize = 11.sp,
        color = Color.White,
        modifier = Modifier
            .clip(RoundedCornerShape(12.dp))
            .background(color)
            .padding(horizontal = 10.dp, vertical = 2.dp)
    )
}

// ──────────── Breathing Tab ────────────

@Composable
fun BreathingTab(exercises: List<BreathingExerciseInfo>, onComplete: () -> Unit) {
    var activeExercise by remember { mutableStateOf<BreathingExerciseInfo?>(null) }
    var moodBefore by remember { mutableIntStateOf(5) }

    if (activeExercise != null) {
        BreathingTimer(activeExercise!!, moodBefore, onComplete = {
            activeExercise = null
            onComplete()
        }, onCancel = { activeExercise = null })
        return
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item {
            Text("Mood before: $moodBefore/10", style = MaterialTheme.typography.bodyMedium)
            Slider(
                value = moodBefore.toFloat(),
                onValueChange = { moodBefore = it.toInt() },
                valueRange = 1f..10f,
                steps = 8
            )
        }

        items(exercises) { ex ->
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp)) {
                    Text(ex.name, style = MaterialTheme.typography.titleMedium)
                    Text(ex.description, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Spacer(Modifier.height(4.dp))
                    Text(
                        "${ex.inhaleSeconds}s in → ${ex.holdSeconds}s hold → ${ex.exhaleSeconds}s out" +
                                if (ex.holdAfterExhaleSeconds > 0) " → ${ex.holdAfterExhaleSeconds}s hold" else "",
                        fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Spacer(Modifier.height(8.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        ex.benefits.forEach { b ->
                            Text(
                                b, fontSize = 10.sp, color = Color(0xFF2E7D32),
                                modifier = Modifier
                                    .clip(RoundedCornerShape(12.dp))
                                    .background(Color(0xFFE8F5E9))
                                    .padding(horizontal = 8.dp, vertical = 2.dp)
                            )
                        }
                    }
                    Spacer(Modifier.height(12.dp))
                    Button(onClick = { activeExercise = ex }, Modifier.fillMaxWidth()) {
                        Text("Start Exercise")
                    }
                }
            }
        }
    }
}

@Composable
fun BreathingTimer(
    exercise: BreathingExerciseInfo,
    moodBefore: Int,
    onComplete: () -> Unit,
    onCancel: () -> Unit
) {
    var phase by remember { mutableStateOf("inhale") }
    var timer by remember { mutableIntStateOf(exercise.inhaleSeconds) }
    var cycle by remember { mutableIntStateOf(1) }
    var done by remember { mutableStateOf(false) }
    var moodAfter by remember { mutableIntStateOf(5) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val startTime = remember { System.currentTimeMillis() }

    val phaseColor by animateColorAsState(
        when (phase) {
            "inhale" -> Color(0xFF4CAF50)
            "hold" -> Color(0xFF2196F3)
            "exhale" -> Color(0xFFFF9800)
            "hold2" -> Color(0xFF9C27B0)
            else -> Color.Gray
        }, label = "phase"
    )

    val phaseLabel = when (phase) {
        "inhale" -> "Breathe In"; "hold" -> "Hold"; "exhale" -> "Breathe Out"; "hold2" -> "Hold"; else -> ""
    }

    // Timer effect
    LaunchedEffect(done) {
        if (done) return@LaunchedEffect
        while (!done) {
            kotlinx.coroutines.delay(1000)
            timer--
            if (timer <= 0) {
                when (phase) {
                    "inhale" -> {
                        if (exercise.holdSeconds > 0) { phase = "hold"; timer = exercise.holdSeconds }
                        else { phase = "exhale"; timer = exercise.exhaleSeconds }
                    }
                    "hold" -> { phase = "exhale"; timer = exercise.exhaleSeconds }
                    "exhale" -> {
                        if (exercise.holdAfterExhaleSeconds > 0) { phase = "hold2"; timer = exercise.holdAfterExhaleSeconds }
                        else {
                            if (cycle >= exercise.recommendedCycles) { done = true }
                            else { cycle++; phase = "inhale"; timer = exercise.inhaleSeconds }
                        }
                    }
                    "hold2" -> {
                        if (cycle >= exercise.recommendedCycles) { done = true }
                        else { cycle++; phase = "inhale"; timer = exercise.inhaleSeconds }
                    }
                }
            }
        }
    }

    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        if (done) {
            Text("✅ Session Complete!", style = MaterialTheme.typography.headlineMedium)
            Spacer(Modifier.height(24.dp))
            Text("How do you feel now?")
            Text("$moodAfter/10", fontSize = 24.sp, fontWeight = FontWeight.Bold)
            Slider(
                value = moodAfter.toFloat(),
                onValueChange = { moodAfter = it.toInt() },
                valueRange = 1f..10f,
                steps = 8
            )
            Spacer(Modifier.height(16.dp))
            Button(onClick = {
                scope.launch {
                    try {
                        val duration = ((System.currentTimeMillis() - startTime) / 1000).toInt()
                        ApiClient.getApiService().createBreathingSession(
                            BreathingSessionRequest(
                                sessionDate = LocalDate.now().format(DateTimeFormatter.ISO_LOCAL_DATE),
                                exerciseType = exercise.id,
                                durationSeconds = duration,
                                moodBefore = moodBefore,
                                moodAfter = moodAfter
                            )
                        )
                        onComplete()
                    } catch (e: Exception) {
                        Toast.makeText(context, "Save failed: ${e.message}", Toast.LENGTH_SHORT).show()
                    }
                }
            }) { Text("Save Session") }
        } else {
            Text(exercise.name, style = MaterialTheme.typography.headlineSmall)
            Spacer(Modifier.height(32.dp))
            Text(phaseLabel, fontSize = 24.sp, fontWeight = FontWeight.SemiBold)
            Text("$timer", fontSize = 80.sp, fontWeight = FontWeight.Black, color = phaseColor)
            Text("Cycle $cycle of ${exercise.recommendedCycles}", color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(32.dp))
            OutlinedButton(onClick = onCancel) { Text("Stop") }
        }
    }
}

// ──────────── Gratitude Tab ────────────

@Composable
fun GratitudeTab(entries: List<GratitudeEntryResponse>, onSave: () -> Unit) {
    var showDialog by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    Column(Modifier.fillMaxSize()) {
        // Add button
        Button(
            onClick = { showDialog = true },
            modifier = Modifier.padding(16.dp).fillMaxWidth()
        ) { Text("+ New Gratitude Entry") }

        if (entries.isEmpty()) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text("No gratitude entries yet.\nWhat are you grateful for today?", textAlign = TextAlign.Center)
            }
        } else {
            LazyColumn(
                contentPadding = PaddingValues(horizontal = 16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(entries) { e ->
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(containerColor = Color(0xFFFFFDE7))
                    ) {
                        Column(Modifier.padding(16.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(e.entryDate, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.weight(1f))
                                IconButton(onClick = {
                                    scope.launch {
                                        try {
                                            ApiClient.getApiService().deleteGratitude(e.id)
                                            onSave()
                                        } catch (ex: Exception) {
                                            Toast.makeText(context, "Delete failed: ${ex.message}", Toast.LENGTH_SHORT).show()
                                        }
                                    }
                                }, modifier = Modifier.size(32.dp)) {
                                    Icon(Icons.Default.Delete, contentDescription = "Delete", tint = MaterialTheme.colorScheme.error, modifier = Modifier.size(18.dp))
                                }
                            }
                            Spacer(Modifier.height(4.dp))
                            Text("1. ${e.item1}")
                            e.item2?.let { if (it.isNotBlank()) Text("2. $it") }
                            e.item3?.let { if (it.isNotBlank()) Text("3. $it") }
                            e.reflection?.let {
                                if (it.isNotBlank()) {
                                    Spacer(Modifier.height(4.dp))
                                    Text(it, fontStyle = FontStyle.Italic, fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    if (showDialog) {
        AddGratitudeDialog(
            onDismiss = { showDialog = false },
            onSave = { showDialog = false; onSave() }
        )
    }
}

@Composable
fun AddGratitudeDialog(onDismiss: () -> Unit, onSave: () -> Unit) {
    var item1 by remember { mutableStateOf("") }
    var item2 by remember { mutableStateOf("") }
    var item3 by remember { mutableStateOf("") }
    var reflection by remember { mutableStateOf("") }
    var saving by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = {
            TextButton(
                onClick = {
                    saving = true
                    scope.launch {
                        try {
                            ApiClient.getApiService().createGratitude(
                                GratitudeRequest(
                                    entryDate = LocalDate.now().format(DateTimeFormatter.ISO_LOCAL_DATE),
                                    item1 = item1,
                                    item2 = item2.ifBlank { null },
                                    item3 = item3.ifBlank { null },
                                    reflection = reflection.ifBlank { null }
                                )
                            )
                            onSave()
                        } catch (e: Exception) {
                            Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                        }
                        saving = false
                    }
                },
                enabled = item1.isNotBlank() && !saving
            ) { Text(if (saving) "Saving..." else "Save") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
        title = { Text("🙏 Gratitude Entry") },
        text = {
            Column {
                OutlinedTextField(value = item1, onValueChange = { item1 = it }, label = { Text("1. I'm grateful for...") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = item2, onValueChange = { item2 = it }, label = { Text("2. I'm grateful for...") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = item3, onValueChange = { item3 = it }, label = { Text("3. I'm grateful for...") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = reflection, onValueChange = { reflection = it }, label = { Text("Reflection...") }, modifier = Modifier.fillMaxWidth(), minLines = 2)
            }
        }
    )
}

// ──────────── Assessments Tab ────────────

@Composable
fun AssessmentsTab(assessments: List<MentalHealthAssessment>, onSave: () -> Unit) {
    var showDialog by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    Column(Modifier.fillMaxSize()) {
        Button(
            onClick = { showDialog = true },
            modifier = Modifier.padding(16.dp).fillMaxWidth()
        ) { Text("+ Take Assessment") }

        if (assessments.isEmpty()) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text("No assessments yet.\nTake a PHQ-9, GAD-7, or WHO-5.", textAlign = TextAlign.Center)
            }
        } else {
            LazyColumn(
                contentPadding = PaddingValues(horizontal = 16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(assessments) { a ->
                    Card(Modifier.fillMaxWidth()) {
                        Row(
                            Modifier.padding(16.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Column(Modifier.weight(1f)) {
                                Text(a.assessmentType.uppercase(), fontWeight = FontWeight.Bold)
                                Text(a.assessmentDate, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                            a.totalScore?.let {
                                Text("$it", fontSize = 24.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(end = 8.dp))
                            }
                            SeverityChip(a.severity)
                            IconButton(onClick = {
                                scope.launch {
                                    try {
                                        ApiClient.getApiService().deleteAssessment(a.id)
                                        onSave()
                                    } catch (e: Exception) {
                                        Toast.makeText(context, "Delete failed: ${e.message}", Toast.LENGTH_SHORT).show()
                                    }
                                }
                            }, modifier = Modifier.size(32.dp)) {
                                Icon(Icons.Default.Delete, contentDescription = "Delete", tint = MaterialTheme.colorScheme.error, modifier = Modifier.size(18.dp))
                            }
                        }
                    }
                }
            }
        }
    }

    if (showDialog) {
        AddAssessmentDialog(
            onDismiss = { showDialog = false },
            onSave = { showDialog = false; onSave() }
        )
    }
}

data class AssessmentQuestion(val key: String, val text: String)

@Composable
fun AddAssessmentDialog(onDismiss: () -> Unit, onSave: () -> Unit) {
    var type by remember { mutableStateOf("phq9") }
    var answers by remember { mutableStateOf(mapOf<String, Int>()) }
    var saving by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    val phq9 = listOf(
        AssessmentQuestion("phq_interest", "Little interest or pleasure in doing things"),
        AssessmentQuestion("phq_feeling_down", "Feeling down, depressed, or hopeless"),
        AssessmentQuestion("phq_sleep", "Trouble falling/staying asleep, or sleeping too much"),
        AssessmentQuestion("phq_energy", "Feeling tired or having little energy"),
        AssessmentQuestion("phq_appetite", "Poor appetite or overeating"),
        AssessmentQuestion("phq_self_esteem", "Feeling bad about yourself"),
        AssessmentQuestion("phq_concentration", "Trouble concentrating"),
        AssessmentQuestion("phq_psychomotor", "Moving/speaking slowly or being fidgety"),
        AssessmentQuestion("phq_suicidal_ideation", "Thoughts of self-harm"),
    )
    val gad7 = listOf(
        AssessmentQuestion("gad_nervous", "Feeling nervous, anxious, or on edge"),
        AssessmentQuestion("gad_uncontrollable_worry", "Not being able to stop worrying"),
        AssessmentQuestion("gad_excessive_worry", "Worrying too much about different things"),
        AssessmentQuestion("gad_trouble_relaxing", "Trouble relaxing"),
        AssessmentQuestion("gad_restless", "Being so restless it's hard to sit still"),
        AssessmentQuestion("gad_irritable", "Becoming easily annoyed or irritable"),
        AssessmentQuestion("gad_afraid", "Feeling afraid something awful might happen"),
    )
    val who5 = listOf(
        AssessmentQuestion("who5_cheerful", "I have felt cheerful and in good spirits"),
        AssessmentQuestion("who5_calm", "I have felt calm and relaxed"),
        AssessmentQuestion("who5_active", "I have felt active and vigorous"),
        AssessmentQuestion("who5_rested", "I woke up feeling fresh and rested"),
        AssessmentQuestion("who5_interesting", "My daily life has been filled with things that interest me"),
    )

    val questions = when (type) { "phq9" -> phq9; "gad7" -> gad7; else -> who5 }
    val maxVal = if (type == "who5") 5 else 3
    val labels03 = listOf("Not at all (0)", "Several days (1)", "More than half (2)", "Nearly every day (3)")
    val labels05 = listOf("At no time (0)", "Some (1)", "Less than half (2)", "More than half (3)", "Most (4)", "All (5)")
    val labels = if (type == "who5") labels05 else labels03

    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = {
            TextButton(
                onClick = {
                    saving = true
                    scope.launch {
                        try {
                            ApiClient.getApiService().createAssessment(
                                AssessmentRequest(
                                    assessmentDate = LocalDate.now().format(DateTimeFormatter.ISO_LOCAL_DATE),
                                    assessmentType = type,
                                    phqInterest = answers["phq_interest"],
                                    phqFeelingDown = answers["phq_feeling_down"],
                                    phqSleep = answers["phq_sleep"],
                                    phqEnergy = answers["phq_energy"],
                                    phqAppetite = answers["phq_appetite"],
                                    phqSelfEsteem = answers["phq_self_esteem"],
                                    phqConcentration = answers["phq_concentration"],
                                    phqPsychomotor = answers["phq_psychomotor"],
                                    phqSuicidalIdeation = answers["phq_suicidal_ideation"],
                                    gadNervous = answers["gad_nervous"],
                                    gadUncontrollableWorry = answers["gad_uncontrollable_worry"],
                                    gadExcessiveWorry = answers["gad_excessive_worry"],
                                    gadTroubleRelaxing = answers["gad_trouble_relaxing"],
                                    gadRestless = answers["gad_restless"],
                                    gadIrritable = answers["gad_irritable"],
                                    gadAfraid = answers["gad_afraid"],
                                    who5Cheerful = answers["who5_cheerful"],
                                    who5Calm = answers["who5_calm"],
                                    who5Active = answers["who5_active"],
                                    who5Rested = answers["who5_rested"],
                                    who5Interesting = answers["who5_interesting"]
                                )
                            )
                            onSave()
                        } catch (e: Exception) {
                            Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                        }
                        saving = false
                    }
                },
                enabled = answers.size >= questions.size && !saving
            ) { Text(if (saving) "Submitting..." else "Submit") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
        title = { Text("📋 Clinical Assessment") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                // Type selector
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    listOf("phq9" to "PHQ-9", "gad7" to "GAD-7", "who5" to "WHO-5").forEach { (k, label) ->
                        FilterChip(
                            selected = type == k,
                            onClick = { type = k; answers = emptyMap() },
                            label = { Text(label, fontSize = 12.sp) }
                        )
                    }
                }
                Spacer(Modifier.height(12.dp))
                Text("Over the last 2 weeks…", fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                Spacer(Modifier.height(8.dp))

                questions.forEachIndexed { i, q ->
                    Text("${i + 1}. ${q.text}", fontSize = 13.sp, fontWeight = FontWeight.Medium)
                    Spacer(Modifier.height(4.dp))
                    (0..maxVal).forEach { v ->
                        Row(
                            Modifier
                                .fillMaxWidth()
                                .clickable { answers = answers + (q.key to v) }
                                .padding(vertical = 2.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            RadioButton(selected = answers[q.key] == v, onClick = { answers = answers + (q.key to v) })
                            Text(labels[v], fontSize = 12.sp)
                        }
                    }
                    if (i < questions.size - 1) HorizontalDivider(Modifier.padding(vertical = 4.dp))
                }
            }
        }
    )
}
