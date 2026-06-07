package com.alafia.android.views.mood
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.alafia.android.api.ApiClient
import com.alafia.android.models.MoodEntry
import com.alafia.android.schemas.MoodEntryRequest
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.format.DateTimeFormatter

@Composable
fun MoodScreen() {
    var entries by remember { mutableStateOf<List<MoodEntry>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    var showForm by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    fun loadEntries() {
        scope.launch {
            isLoading = true
            try {
                entries = ApiClient.getApiService().getMoodEntries()
            } catch (e: Exception) {
                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
            }
            isLoading = false
        }
    }

    LaunchedEffect(Unit) { loadEntries() }

    Column(modifier = Modifier.fillMaxSize()) {
        // Header
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("Mood", style = MaterialTheme.typography.headlineLarge)
            Button(onClick = { showForm = true }) {
                Icon(Icons.Default.Add, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(4.dp))
                Text("Check In")
            }
        }

        if (isLoading) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        } else if (entries.isEmpty()) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("😐", fontSize = 48.sp)
                    Spacer(Modifier.height(8.dp))
                    Text("No mood entries yet", style = MaterialTheme.typography.titleMedium)
                    Text("Tap Check In to log how you feel", color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        } else {
            LazyColumn(
                contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(entries) { entry ->
                    MoodEntryCard(entry = entry, onDelete = {
                        scope.launch {
                            try {
                                ApiClient.getApiService().deleteMoodEntry(entry.id)
                                loadEntries()
                            } catch (e: Exception) {
                                Toast.makeText(context, "Delete failed: ${e.message}", Toast.LENGTH_SHORT).show()
                            }
                        }
                    })
                }
            }
        }
    }

    if (showForm) {
        AddMoodDialog(
            onDismiss = { showForm = false },
            onSave = { showForm = false; loadEntries() }
        )
    }
}

@Composable
fun MoodEntryCard(entry: MoodEntry, onDelete: () -> Unit) {
    val emoji = when (entry.moodScore) {
        in 8..10 -> "😄"
        in 6..7 -> "🙂"
        in 4..5 -> "😐"
        in 2..3 -> "😔"
        else -> "😢"
    }

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(emoji, fontSize = 32.sp)
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text("Mood: ${entry.moodScore}/10", fontWeight = FontWeight.Bold)
                    Text(entry.entryDate, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                IconButton(onClick = onDelete, modifier = Modifier.size(32.dp)) {
                    Icon(Icons.Default.Delete, contentDescription = "Delete", tint = MaterialTheme.colorScheme.error, modifier = Modifier.size(18.dp))
                }
            }

            Spacer(Modifier.height(8.dp))

            // Metric chips row
            Row(
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                entry.energyLevel?.let { MetricChip("⚡ $it", Color(0xFFFFF3E0)) }
                entry.stressLevel?.let { MetricChip("😤 $it", Color(0xFFFFEBEE)) }
                entry.anxietyLevel?.let { MetricChip("😰 $it", Color(0xFFFCE4EC)) }
                entry.sleepQuality?.let { MetricChip("😴 $it", Color(0xFFE8EAF6)) }
                entry.sleepHours?.let { MetricChip("🛏 ${"%.1f".format(it)}h", Color(0xFFE3F2FD)) }
            }

            // Emotions
            entry.emotions?.let {
                if (it.isNotBlank()) {
                    Spacer(Modifier.height(6.dp))
                    Text("Emotions: $it", fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }

            // Triggers
            entry.triggers?.let {
                if (it.isNotBlank()) {
                    Spacer(Modifier.height(4.dp))
                    Text("Triggers: $it", fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }

            // Coping
            entry.copingStrategies?.let {
                if (it.isNotBlank()) {
                    Spacer(Modifier.height(4.dp))
                    Text("Coping: $it", fontSize = 13.sp, color = Color(0xFF2E7D32))
                }
            }

            // Journal
            entry.journalEntry?.let {
                if (it.isNotBlank()) {
                    Spacer(Modifier.height(6.dp))
                    Text(it, fontSize = 13.sp, maxLines = 3, overflow = TextOverflow.Ellipsis)
                }
            }
        }
    }
}

@Composable
fun MetricChip(text: String, bgColor: Color) {
    Surface(
        shape = MaterialTheme.shapes.small,
        color = bgColor
    ) {
        Text(text, fontSize = 11.sp, modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp))
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AddMoodDialog(onDismiss: () -> Unit, onSave: () -> Unit) {
    var moodScore by remember { mutableIntStateOf(5) }
    var energyLevel by remember { mutableIntStateOf(5) }
    var stressLevel by remember { mutableIntStateOf(5) }
    var anxietyLevel by remember { mutableIntStateOf(5) }
    var sleepQuality by remember { mutableIntStateOf(5) }
    var sleepHours by remember { mutableStateOf("") }
    var emotions by remember { mutableStateOf("") }
    var triggers by remember { mutableStateOf("") }
    var copingStrategies by remember { mutableStateOf("") }
    var gratitude by remember { mutableStateOf("") }
    var journalEntry by remember { mutableStateOf("") }
    var saving by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    val emoji = when (moodScore) {
        in 8..10 -> "😄"
        in 6..7 -> "🙂"
        in 4..5 -> "😐"
        in 2..3 -> "😔"
        else -> "😢"
    }

    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 24.dp, vertical = 16.dp)
        ) {
            // Header
            Text(emoji, fontSize = 48.sp, modifier = Modifier.align(Alignment.CenterHorizontally))
            Text("How are you feeling?", style = MaterialTheme.typography.headlineSmall, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
            Spacer(Modifier.height(20.dp))

            // Mood slider
            Text("Mood: $moodScore/10", fontWeight = FontWeight.SemiBold)
            Slider(value = moodScore.toFloat(), onValueChange = { moodScore = it.toInt() }, valueRange = 1f..10f, steps = 8)

            // Energy slider
            Text("Energy: $energyLevel/10", fontWeight = FontWeight.SemiBold)
            Slider(value = energyLevel.toFloat(), onValueChange = { energyLevel = it.toInt() }, valueRange = 1f..10f, steps = 8)

            // Stress slider
            Text("Stress: $stressLevel/10", fontWeight = FontWeight.SemiBold)
            Slider(value = stressLevel.toFloat(), onValueChange = { stressLevel = it.toInt() }, valueRange = 1f..10f, steps = 8,
                colors = SliderDefaults.colors(thumbColor = Color(0xFFF44336), activeTrackColor = Color(0xFFF44336)))

            // Anxiety slider
            Text("Anxiety: $anxietyLevel/10", fontWeight = FontWeight.SemiBold)
            Slider(value = anxietyLevel.toFloat(), onValueChange = { anxietyLevel = it.toInt() }, valueRange = 1f..10f, steps = 8,
                colors = SliderDefaults.colors(thumbColor = Color(0xFFFF9800), activeTrackColor = Color(0xFFFF9800)))

            // Sleep
            Text("Sleep Quality: $sleepQuality/10", fontWeight = FontWeight.SemiBold)
            Slider(value = sleepQuality.toFloat(), onValueChange = { sleepQuality = it.toInt() }, valueRange = 1f..10f, steps = 8,
                colors = SliderDefaults.colors(thumbColor = Color(0xFF3F51B5), activeTrackColor = Color(0xFF3F51B5)))

            OutlinedTextField(
                value = sleepHours, onValueChange = { sleepHours = it },
                label = { Text("Sleep Hours") }, modifier = Modifier.fillMaxWidth(),
                singleLine = true
            )
            Spacer(Modifier.height(12.dp))

            // Emotions & Coping
            Text("Emotions & Coping", fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.titleSmall)
            Spacer(Modifier.height(4.dp))
            OutlinedTextField(
                value = emotions, onValueChange = { emotions = it },
                label = { Text("Emotions (e.g. happy, anxious)") }, modifier = Modifier.fillMaxWidth()
            )
            OutlinedTextField(
                value = triggers, onValueChange = { triggers = it },
                label = { Text("Triggers") }, modifier = Modifier.fillMaxWidth()
            )
            OutlinedTextField(
                value = copingStrategies, onValueChange = { copingStrategies = it },
                label = { Text("Coping strategies used") }, modifier = Modifier.fillMaxWidth()
            )
            Spacer(Modifier.height(12.dp))

            // Gratitude & Journal
            OutlinedTextField(
                value = gratitude, onValueChange = { gratitude = it },
                label = { Text("Gratitude") }, modifier = Modifier.fillMaxWidth()
            )
            OutlinedTextField(
                value = journalEntry, onValueChange = { journalEntry = it },
                label = { Text("Journal entry") }, modifier = Modifier.fillMaxWidth(),
                minLines = 3
            )
            Spacer(Modifier.height(16.dp))

            Button(
                onClick = {
                    saving = true
                    scope.launch {
                        try {
                            ApiClient.getApiService().createMoodEntry(
                                MoodEntryRequest(
                                    entryDate = LocalDate.now().format(DateTimeFormatter.ISO_LOCAL_DATE),
                                    moodScore = moodScore,
                                    energyLevel = energyLevel,
                                    stressLevel = stressLevel,
                                    anxietyLevel = anxietyLevel,
                                    sleepQuality = sleepQuality,
                                    sleepHours = sleepHours.toDoubleOrNull(),
                                    emotions = emotions.ifBlank { null },
                                    triggers = triggers.ifBlank { null },
                                    copingStrategies = copingStrategies.ifBlank { null },
                                    gratitude = gratitude.ifBlank { null },
                                    journalEntry = journalEntry.ifBlank { null }
                                )
                            )
                            onSave()
                        } catch (e: Exception) {
                            Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                        }
                        saving = false
                    }
                },
                modifier = Modifier.fillMaxWidth(),
                enabled = !saving
            ) {
                Text(if (saving) "Saving..." else "Save Check-In")
            }
            Spacer(Modifier.height(32.dp))
        }
    }
}
