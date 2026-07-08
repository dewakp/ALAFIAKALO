package com.alafia.android.views.elimination
import com.alafia.android.util.ErrorUtil

import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.alafia.android.api.ApiClient
import com.alafia.android.models.BowelMovement
import com.alafia.android.models.VomitingLog
import com.alafia.android.models.UrinationLog
import com.alafia.android.models.EliminationFromImageResponse
import com.alafia.android.models.EliminationImageRequest
import com.alafia.android.schemas.BowelMovementRequest
import com.alafia.android.schemas.VomitingLogRequest
import com.alafia.android.schemas.UrinationLogRequest
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.format.DateTimeFormatter

@Composable
fun EliminationScreen() {
    var selectedTab by remember { mutableStateOf(0) }
    val tabs = listOf("💩 Bowel", "🤮 Vomiting", "💧 Urination")

    Column(modifier = Modifier.fillMaxSize()) {
        // Header
        Text(
            text = "Elimination",
            style = MaterialTheme.typography.headlineLarge,
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp)
        )

        // Tabs
        TabRow(selectedTabIndex = selectedTab) {
            tabs.forEachIndexed { index, title ->
                Tab(
                    selected = selectedTab == index,
                    onClick = { selectedTab = index },
                    text = { Text(title, fontSize = 13.sp) }
                )
            }
        }

        when (selectedTab) {
            0 -> BowelMovementTab()
            1 -> VomitingTab()
            2 -> UrinationTab()
        }
    }
}

// ── Analyze-photo control (shared by the three log dialogs) ─────────────────────

/**
 * "Analyze photo" button: picks an image, runs it through the vision model
 * (`elimination-from-image`) for the given [eventType], hands the suggested
 * fields back via [onResult], and renders any attention flags + disclaimer.
 * AI visual estimate — not a diagnosis.
 */
@Composable
private fun AnalyzeEliminationPhoto(
    eventType: String,
    onResult: (EliminationFromImageResponse) -> Unit,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var analyzing by remember { mutableStateOf(false) }
    var flags by remember { mutableStateOf<List<String>>(emptyList()) }

    val picker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            analyzing = true
            try {
                val bytes = context.contentResolver.openInputStream(uri)?.use { it.readBytes() } ?: byteArrayOf()
                val b64 = "data:image/jpeg;base64," +
                    android.util.Base64.encodeToString(bytes, android.util.Base64.NO_WRAP)
                val res = ApiClient.getApiService().eliminationFromImage(
                    EliminationImageRequest(eventType = eventType, imageBase64 = b64)
                )
                onResult(res)
                flags = res.flags + listOfNotNull(res.disclaimer)
            } catch (e: Exception) {
                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
            }
            analyzing = false
        }
    }

    Column {
        OutlinedButton(onClick = { picker.launch("image/*") }, enabled = !analyzing,
            modifier = Modifier.fillMaxWidth()) {
            if (analyzing) {
                CircularProgressIndicator(Modifier.size(16.dp))
                Spacer(Modifier.width(8.dp)); Text("Analyzing photo…")
            } else {
                Icon(Icons.Default.PhotoCamera, contentDescription = null, modifier = Modifier.size(16.dp))
                Spacer(Modifier.width(8.dp)); Text("Analyze photo")
            }
        }
        flags.forEach { f ->
            Row(Modifier.padding(top = 4.dp), verticalAlignment = Alignment.Top) {
                Text("⚠ ", color = Color(0xFFE65100), fontSize = 12.sp)
                Text(f, style = MaterialTheme.typography.bodySmall, color = Color(0xFFE65100))
            }
        }
    }
}

// ── Bowel Movement Tab ─────────────────────────────────────────────────────────

@Composable
fun BowelMovementTab() {
    var entries by remember { mutableStateOf<List<BowelMovement>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    var showForm by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    fun load() {
        scope.launch {
            isLoading = true
            try {
                entries = ApiClient.getApiService().getBowelMovements()
            } catch (e: Exception) {
                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
            }
            isLoading = false
        }
    }

    LaunchedEffect(Unit) { load() }

    Box(modifier = Modifier.fillMaxSize()) {
        when {
            isLoading -> CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
            entries.isEmpty() -> Column(
                modifier = Modifier.align(Alignment.Center),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text("💩", fontSize = 48.sp)
                Spacer(Modifier.height(8.dp))
                Text("No bowel records yet", style = MaterialTheme.typography.titleMedium)
                Text("Tap + to log one", color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            else -> LazyColumn(modifier = Modifier.fillMaxSize()) {
                items(entries) { entry ->
                    BowelMovementCard(entry = entry, onDelete = {
                        scope.launch {
                            try {
                                ApiClient.getApiService().deleteBowelMovement(entry.id)
                                entries = entries.filter { it.id != entry.id }
                            } catch (e: Exception) {
                                Toast.makeText(context, "Delete failed", Toast.LENGTH_SHORT).show()
                            }
                        }
                    })
                }
            }
        }

        FloatingActionButton(
            onClick = { showForm = true },
            modifier = Modifier
                .align(Alignment.BottomEnd)
                .padding(16.dp)
        ) {
            Icon(Icons.Default.Add, contentDescription = "Add")
        }
    }

    if (showForm) {
        AddBowelDialog(
            onDismiss = { showForm = false },
            onSave = { request ->
                scope.launch {
                    try {
                        ApiClient.getApiService().createBowelMovement(request)
                        load()
                        showForm = false
                    } catch (e: Exception) {
                        Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                    }
                }
            }
        )
    }
}

@Composable
fun BowelMovementCard(entry: BowelMovement, onDelete: () -> Unit) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 4.dp)
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            verticalAlignment = Alignment.Top
        ) {
            Text("💩", fontSize = 28.sp, modifier = Modifier.padding(end = 12.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(entry.logDate, fontWeight = FontWeight.Bold)
                entry.logTime?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                entry.bristolScale?.let {
                    AssistChip(
                        onClick = {},
                        label = { Text("Bristol $it", fontSize = 11.sp) },
                        modifier = Modifier.height(24.dp)
                    )
                }
                if (entry.bloodPresent == true) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Default.Warning, contentDescription = null, tint = Color.Red, modifier = Modifier.size(14.dp))
                        Spacer(Modifier.width(4.dp))
                        Text("Blood present", color = Color.Red, fontSize = 12.sp)
                    }
                }
                entry.notes?.let { Text(it, style = MaterialTheme.typography.bodySmall, maxLines = 2) }
            }
            IconButton(onClick = onDelete, modifier = Modifier.size(32.dp)) {
                Icon(Icons.Default.Delete, contentDescription = "Delete", tint = MaterialTheme.colorScheme.error)
            }
        }
    }
}

@Composable
fun AddBowelDialog(onDismiss: () -> Unit, onSave: (BowelMovementRequest) -> Unit) {
    var bristolScale by remember { mutableStateOf(4f) }
    var bloodPresent by remember { mutableStateOf(false) }
    var mucusPresent by remember { mutableStateOf(false) }
    var straining by remember { mutableStateOf(false) }
    var urgency by remember { mutableStateOf(false) }
    var notes by remember { mutableStateOf("") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Log Bowel Movement") },
        text = {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(max = 500.dp)
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                AnalyzeEliminationPhoto(eventType = "bowel") { res ->
                    val s = res.suggested
                    s.bristolScale?.let { bristolScale = it.toFloat() }
                    if (s.bloodPresent == true) bloodPresent = true
                    if (s.mucusPresent == true) mucusPresent = true
                    val bits = buildList {
                        s.bristolScale?.let { add("Bristol type $it") }
                        s.consistency?.let { add(it) }
                        s.color?.let { add("$it color") }
                        if (s.bloodPresent == true) add("possible blood")
                        if (s.mucusPresent == true) add("possible mucus")
                    }
                    notes = if (bits.isNotEmpty()) "${bits.joinToString(", ")} — ${res.description}" else res.description
                }
                HorizontalDivider()
                Text("Bristol Scale: ${bristolScale.toInt()}", fontWeight = FontWeight.Medium)
                Slider(value = bristolScale, onValueChange = { bristolScale = it }, valueRange = 1f..7f, steps = 5)
                Text(bristolDescription(bristolScale.toInt()), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                HorizontalDivider()
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = bloodPresent, onCheckedChange = { bloodPresent = it })
                    Text("Blood present", color = if (bloodPresent) Color.Red else MaterialTheme.colorScheme.onSurface)
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = mucusPresent, onCheckedChange = { mucusPresent = it })
                    Text("Mucus present")
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = straining, onCheckedChange = { straining = it })
                    Text("Straining")
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = urgency, onCheckedChange = { urgency = it })
                    Text("Urgency")
                }
                OutlinedTextField(
                    value = notes,
                    onValueChange = { notes = it },
                    label = { Text("Notes") },
                    modifier = Modifier.fillMaxWidth(),
                    minLines = 2
                )
            }
        },
        confirmButton = {
            Button(onClick = {
                val today = LocalDate.now().format(DateTimeFormatter.ISO_DATE)
                onSave(BowelMovementRequest(
                    logDate = today,
                    bristolScale = bristolScale.toInt(),
                    bloodPresent = bloodPresent,
                    mucusPresent = mucusPresent,
                    straining = straining,
                    urgency = urgency,
                    notes = notes.ifBlank { null }
                ))
            }) { Text("Save") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } }
    )
}

private fun bristolDescription(type: Int) = when (type) {
    1 -> "Separate hard lumps"
    2 -> "Lumpy sausage shape"
    3 -> "Sausage with cracks"
    4 -> "Smooth, soft sausage ✓"
    5 -> "Soft blobs, clear edges"
    6 -> "Fluffy pieces, mushy"
    7 -> "Entirely liquid"
    else -> ""
}

// ── Vomiting Tab ───────────────────────────────────────────────────────────────

@Composable
fun VomitingTab() {
    var entries by remember { mutableStateOf<List<VomitingLog>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    var showForm by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    fun load() {
        scope.launch {
            isLoading = true
            try {
                entries = ApiClient.getApiService().getVomitingLogs()
            } catch (e: Exception) {
                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
            }
            isLoading = false
        }
    }

    LaunchedEffect(Unit) { load() }

    Box(modifier = Modifier.fillMaxSize()) {
        when {
            isLoading -> CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
            entries.isEmpty() -> Column(
                modifier = Modifier.align(Alignment.Center),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text("🤮", fontSize = 48.sp)
                Spacer(Modifier.height(8.dp))
                Text("No vomiting records", style = MaterialTheme.typography.titleMedium)
            }
            else -> LazyColumn(modifier = Modifier.fillMaxSize()) {
                items(entries) { entry ->
                    VomitingCard(entry = entry, onDelete = {
                        scope.launch {
                            try {
                                ApiClient.getApiService().deleteVomitingLog(entry.id)
                                entries = entries.filter { it.id != entry.id }
                            } catch (e: Exception) {
                                Toast.makeText(context, "Delete failed", Toast.LENGTH_SHORT).show()
                            }
                        }
                    })
                }
            }
        }

        FloatingActionButton(
            onClick = { showForm = true },
            modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp)
        ) { Icon(Icons.Default.Add, contentDescription = "Add") }
    }

    if (showForm) {
        AddVomitingDialog(
            onDismiss = { showForm = false },
            onSave = { request ->
                scope.launch {
                    try {
                        ApiClient.getApiService().createVomitingLog(request)
                        load()
                        showForm = false
                    } catch (e: Exception) {
                        Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                    }
                }
            }
        )
    }
}

@Composable
fun VomitingCard(entry: VomitingLog, onDelete: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 4.dp)) {
        Row(modifier = Modifier.padding(12.dp), verticalAlignment = Alignment.Top) {
            Text("🤮", fontSize = 28.sp, modifier = Modifier.padding(end = 12.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(entry.logDate, fontWeight = FontWeight.Bold)
                entry.logTime?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                if (entry.containsBlood == true) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Default.Warning, contentDescription = null, tint = Color.Red, modifier = Modifier.size(14.dp))
                        Spacer(Modifier.width(4.dp))
                        Text("Contains blood", color = Color.Red, fontSize = 12.sp)
                    }
                }
                entry.trigger?.let { Text("Trigger: $it", style = MaterialTheme.typography.bodySmall) }
                entry.notes?.let { Text(it, style = MaterialTheme.typography.bodySmall, maxLines = 2) }
            }
            IconButton(onClick = onDelete, modifier = Modifier.size(32.dp)) {
                Icon(Icons.Default.Delete, contentDescription = "Delete", tint = MaterialTheme.colorScheme.error)
            }
        }
    }
}

@Composable
fun AddVomitingDialog(onDismiss: () -> Unit, onSave: (VomitingLogRequest) -> Unit) {
    var containsFood by remember { mutableStateOf(false) }
    var containsBile by remember { mutableStateOf(false) }
    var containsBlood by remember { mutableStateOf(false) }
    var nauseaBefore by remember { mutableStateOf(false) }
    var nauseaAfter by remember { mutableStateOf(false) }
    var projectile by remember { mutableStateOf(false) }
    var reliefAfter by remember { mutableStateOf(false) }
    var fever by remember { mutableStateOf(false) }
    var trigger by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Log Vomiting Episode") },
        text = {
            Column(
                modifier = Modifier.fillMaxWidth().heightIn(max = 520.dp)
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(4.dp)
            ) {
                AnalyzeEliminationPhoto(eventType = "vomiting") { res ->
                    if (res.suggested.bloodPresent == true) containsBlood = true
                    notes = res.description
                }
                HorizontalDivider()
                Text("Contents", fontWeight = FontWeight.SemiBold)
                Row(verticalAlignment = Alignment.CenterVertically) { Checkbox(checked = containsFood, onCheckedChange = { containsFood = it }); Text("Contains food") }
                Row(verticalAlignment = Alignment.CenterVertically) { Checkbox(checked = containsBile, onCheckedChange = { containsBile = it }); Text("Contains bile") }
                Row(verticalAlignment = Alignment.CenterVertically) { Checkbox(checked = containsBlood, onCheckedChange = { containsBlood = it }); Text("Contains blood", color = if (containsBlood) Color.Red else MaterialTheme.colorScheme.onSurface) }
                Row(verticalAlignment = Alignment.CenterVertically) { Checkbox(checked = projectile, onCheckedChange = { projectile = it }); Text("Projectile") }
                HorizontalDivider()
                Text("Symptoms", fontWeight = FontWeight.SemiBold)
                Row(verticalAlignment = Alignment.CenterVertically) { Checkbox(checked = nauseaBefore, onCheckedChange = { nauseaBefore = it }); Text("Nausea before") }
                Row(verticalAlignment = Alignment.CenterVertically) { Checkbox(checked = nauseaAfter, onCheckedChange = { nauseaAfter = it }); Text("Nausea after") }
                Row(verticalAlignment = Alignment.CenterVertically) { Checkbox(checked = reliefAfter, onCheckedChange = { reliefAfter = it }); Text("Relief after") }
                Row(verticalAlignment = Alignment.CenterVertically) { Checkbox(checked = fever, onCheckedChange = { fever = it }); Text("Fever") }
                HorizontalDivider()
                OutlinedTextField(value = trigger, onValueChange = { trigger = it }, label = { Text("Trigger") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = notes, onValueChange = { notes = it }, label = { Text("Notes") }, modifier = Modifier.fillMaxWidth(), minLines = 2)
            }
        },
        confirmButton = {
            Button(onClick = {
                val today = LocalDate.now().format(DateTimeFormatter.ISO_DATE)
                onSave(VomitingLogRequest(
                    logDate = today,
                    containsFood = containsFood,
                    containsBile = containsBile,
                    containsBlood = containsBlood,
                    nauseaBefore = nauseaBefore,
                    nauseaAfter = nauseaAfter,
                    projectile = projectile,
                    reliefAfter = reliefAfter,
                    fever = fever,
                    trigger = trigger.ifBlank { null },
                    notes = notes.ifBlank { null }
                ))
            }) { Text("Save") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } }
    )
}

// ── Urination Tab ──────────────────────────────────────────────────────────────

@Composable
fun UrinationTab() {
    var entries by remember { mutableStateOf<List<UrinationLog>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    var showForm by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    fun load() {
        scope.launch {
            isLoading = true
            try {
                entries = ApiClient.getApiService().getUrinationLogs()
            } catch (e: Exception) {
                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
            }
            isLoading = false
        }
    }

    LaunchedEffect(Unit) { load() }

    Box(modifier = Modifier.fillMaxSize()) {
        when {
            isLoading -> CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
            entries.isEmpty() -> Column(
                modifier = Modifier.align(Alignment.Center),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text("💧", fontSize = 48.sp)
                Spacer(Modifier.height(8.dp))
                Text("No urination records", style = MaterialTheme.typography.titleMedium)
            }
            else -> LazyColumn(modifier = Modifier.fillMaxSize()) {
                items(entries) { entry ->
                    UrinationCard(entry = entry, onDelete = {
                        scope.launch {
                            try {
                                ApiClient.getApiService().deleteUrinationLog(entry.id)
                                entries = entries.filter { it.id != entry.id }
                            } catch (e: Exception) {
                                Toast.makeText(context, "Delete failed", Toast.LENGTH_SHORT).show()
                            }
                        }
                    })
                }
            }
        }

        FloatingActionButton(
            onClick = { showForm = true },
            modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp)
        ) { Icon(Icons.Default.Add, contentDescription = "Add") }
    }

    if (showForm) {
        AddUrinationDialog(
            onDismiss = { showForm = false },
            onSave = { request ->
                scope.launch {
                    try {
                        ApiClient.getApiService().createUrinationLog(request)
                        load()
                        showForm = false
                    } catch (e: Exception) {
                        Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                    }
                }
            }
        )
    }
}

@Composable
fun UrinationCard(entry: UrinationLog, onDelete: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 4.dp)) {
        Row(modifier = Modifier.padding(12.dp), verticalAlignment = Alignment.Top) {
            Text("💧", fontSize = 28.sp, modifier = Modifier.padding(end = 12.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(entry.logDate, fontWeight = FontWeight.Bold)
                entry.logTime?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    entry.color?.let { Text("Color: $it", style = MaterialTheme.typography.bodySmall) }
                    entry.volumeMl?.let { Text("$it mL", style = MaterialTheme.typography.bodySmall) }
                }
                if (entry.bloodPresent == true) {
                    Text("⚠ Blood present", color = Color.Red, fontSize = 12.sp)
                }
                if (entry.burningSensation == true) {
                    Text("Burning sensation", color = Color(0xFFE65100), fontSize = 12.sp)
                }
                entry.notes?.let { Text(it, style = MaterialTheme.typography.bodySmall, maxLines = 2) }
            }
            IconButton(onClick = onDelete, modifier = Modifier.size(32.dp)) {
                Icon(Icons.Default.Delete, contentDescription = "Delete", tint = MaterialTheme.colorScheme.error)
            }
        }
    }
}

@Composable
fun AddUrinationDialog(onDismiss: () -> Unit, onSave: (UrinationLogRequest) -> Unit) {
    var volumeStr by remember { mutableStateOf("") }
    var color by remember { mutableStateOf("") }
    var clarity by remember { mutableStateOf("") }
    var bloodPresent by remember { mutableStateOf(false) }
    var burningSensation by remember { mutableStateOf(false) }
    var urgency by remember { mutableStateOf(false) }
    var nighttime by remember { mutableStateOf(false) }
    var notes by remember { mutableStateOf("") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Log Urination") },
        text = {
            Column(
                modifier = Modifier.fillMaxWidth().heightIn(max = 500.dp)
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                AnalyzeEliminationPhoto(eventType = "urination") { res ->
                    val s = res.suggested
                    s.color?.let { color = it }
                    if (s.bloodPresent == true) bloodPresent = true
                    val bits = buildList {
                        s.color?.let { add("$it color") }
                        if (s.bloodPresent == true) add("possible blood")
                    }
                    notes = if (bits.isNotEmpty()) "${bits.joinToString(", ")} — ${res.description}" else res.description
                }
                HorizontalDivider()
                OutlinedTextField(value = volumeStr, onValueChange = { volumeStr = it }, label = { Text("Volume (mL)") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = color, onValueChange = { color = it }, label = { Text("Color") }, modifier = Modifier.fillMaxWidth(), placeholder = { Text("pale, yellow, amber, dark…") })
                OutlinedTextField(value = clarity, onValueChange = { clarity = it }, label = { Text("Clarity") }, modifier = Modifier.fillMaxWidth(), placeholder = { Text("clear, cloudy, foamy…") })
                HorizontalDivider()
                Row(verticalAlignment = Alignment.CenterVertically) { Checkbox(checked = bloodPresent, onCheckedChange = { bloodPresent = it }); Text("Blood present", color = if (bloodPresent) Color.Red else MaterialTheme.colorScheme.onSurface) }
                Row(verticalAlignment = Alignment.CenterVertically) { Checkbox(checked = burningSensation, onCheckedChange = { burningSensation = it }); Text("Burning sensation") }
                Row(verticalAlignment = Alignment.CenterVertically) { Checkbox(checked = urgency, onCheckedChange = { urgency = it }); Text("Urgency") }
                Row(verticalAlignment = Alignment.CenterVertically) { Checkbox(checked = nighttime, onCheckedChange = { nighttime = it }); Text("Nighttime (nocturia)") }
                OutlinedTextField(value = notes, onValueChange = { notes = it }, label = { Text("Notes") }, modifier = Modifier.fillMaxWidth(), minLines = 2)
            }
        },
        confirmButton = {
            Button(onClick = {
                val today = LocalDate.now().format(DateTimeFormatter.ISO_DATE)
                onSave(UrinationLogRequest(
                    logDate = today,
                    volumeMl = volumeStr.toIntOrNull(),
                    color = color.ifBlank { null },
                    clarity = clarity.ifBlank { null },
                    bloodPresent = bloodPresent,
                    burningSensation = burningSensation,
                    urgency = urgency,
                    nighttime = nighttime,
                    notes = notes.ifBlank { null }
                ))
            }) { Text("Save") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } }
    )
}
