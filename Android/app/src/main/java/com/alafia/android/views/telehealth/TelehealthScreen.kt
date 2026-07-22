package com.alafia.android.views.telehealth

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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.alafia.android.api.ApiClient
import com.alafia.android.models.*
import com.alafia.android.schemas.*
import kotlinx.coroutines.launch
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import androidx.navigation.NavHostController

/* ── Color constants ── */
private val StatusScheduled = Color(0xFF2196F3)
private val StatusWaiting = Color(0xFFFF9800)
private val StatusActive = Color(0xFF4CAF50)
private val StatusCompleted = Color(0xFF607D8B)
private val StatusCancelled = Color(0xFFF44336)
private val TypeVideo = Color(0xFF2196F3)
private val TypeVoice = Color(0xFF4CAF50)
private val TypeChat = Color(0xFF9C27B0)

private fun statusColor(status: String) = when (status) {
    "scheduled" -> StatusScheduled
    "waiting" -> StatusWaiting
    "in_progress" -> StatusActive
    "completed" -> StatusCompleted
    "cancelled", "no_show" -> StatusCancelled
    else -> Color.Gray
}
private fun typeColor(type: String) = when (type) {
    "video" -> TypeVideo; "voice" -> TypeVoice; "chat" -> TypeChat; else -> Color.Gray
}
private fun statusLabel(s: String) = s.replace("_", " ")
    .replaceFirstChar { it.uppercase() }
    .split(" ").joinToString(" ") { it.replaceFirstChar { c -> c.uppercase() } }

private val SPECIALTIES = listOf(
    "", "General Practice", "Cardiology", "Dermatology", "Endocrinology",
    "Gastroenterology", "Neurology", "Oncology", "Orthopedics",
    "Pediatrics", "Psychiatry", "Pulmonology", "Urology"
)
private val FILTERS = listOf("all", "upcoming", "past", "cancelled")

/* ══════════════════════════════════════════════════════════
   MAIN TELEHEALTH SCREEN
   ══════════════════════════════════════════════════════════ */

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TelehealthScreen(navController: NavHostController) {
    var sessions by remember { mutableStateOf<List<TelehealthSession>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    var filter by remember { mutableStateOf("all") }
    var showCreate by remember { mutableStateOf(false) }
    var selectedSession by remember { mutableStateOf<TelehealthSession?>(null) }
    var showCall by remember { mutableStateOf(false) }
    var callSession by remember { mutableStateOf<TelehealthSession?>(null) }
    val scope = rememberCoroutineScope()

    fun loadSessions() {
        scope.launch {
            isLoading = true
            try {
                val status = when (filter) {
                    "upcoming" -> "scheduled"
                    "past" -> "completed"
                    "cancelled" -> "cancelled"
                    else -> null
                }
                sessions = ApiClient.getApiService().getTelehealthSessions(status = status)
            } catch (_: Exception) {}
            isLoading = false
        }
    }

    LaunchedEffect(filter) { loadSessions() }

    // Create sheet
    if (showCreate) {
        CreateSessionSheet(
            onDismiss = { showCreate = false },
            onCreated = { showCreate = false; loadSessions() }
        )
    }

    // Detail sheet
    selectedSession?.let { session ->
        SessionDetailSheet(
            session = session,
            onDismiss = { selectedSession = null },
            onJoinCall = {
                callSession = session
                selectedSession = null
                showCall = true
            },
            onRefresh = { loadSessions() }
        )
    }

    // Call overlay
    if (showCall && callSession != null) {
        VideoCallScreen(
            session = callSession!!,
            onEnd = { showCall = false; callSession = null; loadSessions() }
        )
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Telehealth", fontWeight = FontWeight.Bold) },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    IconButton(onClick = { showCreate = true }) {
                        Icon(Icons.Default.Add, "New Session")
                    }
                }
            )
        }
    ) { padding ->
        Column(modifier = Modifier.fillMaxSize().padding(padding)) {
            // Filter chips
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                FILTERS.forEach { f ->
                    FilterChip(
                        selected = filter == f,
                        onClick = { filter = f },
                        label = { Text(statusLabel(f), fontSize = 12.sp) }
                    )
                }
            }

            when {
                isLoading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
                sessions.isEmpty() -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(Icons.Default.Videocam, null, Modifier.size(48.dp), tint = Color.Gray)
                        Spacer(Modifier.height(8.dp))
                        Text("No sessions found", color = Color.Gray)
                        Spacer(Modifier.height(8.dp))
                        Button(onClick = { showCreate = true }) { Text("Schedule Visit") }
                    }
                }
                else -> LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    items(sessions) { session ->
                        SessionCard(
                            session = session,
                            onTap = { selectedSession = session },
                            onJoin = {
                                callSession = session
                                showCall = true
                            }
                        )
                    }
                }
            }
        }
    }
}

/* ── Session Card ── */

@Composable
private fun SessionCard(session: TelehealthSession, onTap: () -> Unit, onJoin: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onTap),
        shape = RoundedCornerShape(12.dp)
    ) {
        Row(modifier = Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            // Icon
            Box(
                modifier = Modifier.size(40.dp).clip(CircleShape)
                    .background(typeColor(session.sessionType).copy(alpha = 0.15f)),
                contentAlignment = Alignment.Center
            ) {
                Icon(
                    when (session.sessionType) {
                        "video" -> Icons.Default.Videocam
                        "voice" -> Icons.Default.Phone
                        else -> Icons.Default.Chat
                    },
                    null,
                    tint = typeColor(session.sessionType),
                    modifier = Modifier.size(22.dp)
                )
            }

            Spacer(Modifier.width(12.dp))

            Column(modifier = Modifier.weight(1f)) {
                Text(session.displayTitle, fontWeight = FontWeight.SemiBold,
                    maxLines = 1, overflow = TextOverflow.Ellipsis)
                Spacer(Modifier.height(4.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    StatusChip(statusLabel(session.sessionType), typeColor(session.sessionType))
                    StatusChip(statusLabel(session.status), statusColor(session.status))
                    if (session.priority != null && session.priority != "routine") {
                        StatusChip(statusLabel(session.priority),
                            if (session.priority == "urgent") Color(0xFFFF9800) else Color.Red)
                    }
                }
                Spacer(Modifier.height(4.dp))
                Text(
                    formatDateTime(session.scheduledStart),
                    fontSize = 12.sp, color = Color.Gray
                )
                session.specialty?.let {
                    Text(it, fontSize = 12.sp, color = Color.Gray)
                }
            }

            if (session.isJoinable) {
                IconButton(onClick = onJoin) {
                    Box(
                        modifier = Modifier.size(36.dp).clip(CircleShape).background(StatusActive),
                        contentAlignment = Alignment.Center
                    ) {
                        Icon(Icons.Default.Videocam, null, tint = Color.White, modifier = Modifier.size(18.dp))
                    }
                }
            }
        }
    }
}

@Composable
private fun StatusChip(text: String, color: Color) {
    Text(
        text, fontSize = 10.sp, fontWeight = FontWeight.SemiBold,
        color = color,
        modifier = Modifier
            .background(color.copy(alpha = 0.12f), RoundedCornerShape(10.dp))
            .padding(horizontal = 8.dp, vertical = 2.dp)
    )
}

/* ══════════════════════════════════════════════════════════
   CREATE SESSION SHEET
   ══════════════════════════════════════════════════════════ */

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CreateSessionSheet(onDismiss: () -> Unit, onCreated: () -> Unit) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val scope = rememberCoroutineScope()

    var sessionType by remember { mutableStateOf("video") }
    var title by remember { mutableStateOf("") }
    var reasonForVisit by remember { mutableStateOf("") }
    var chiefComplaint by remember { mutableStateOf("") }
    var specialty by remember { mutableStateOf("") }
    var priority by remember { mutableStateOf("routine") }
    var transcription by remember { mutableStateOf(true) }
    var chat by remember { mutableStateOf(true) }
    var recording by remember { mutableStateOf(false) }
    var waitingRoom by remember { mutableStateOf(true) }
    var submitting by remember { mutableStateOf(false) }
    var dateStr by remember { mutableStateOf("") }

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheetState) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 24.dp, vertical = 16.dp)
        ) {
            Text("Schedule Visit", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(16.dp))

            // Type
            Text("Visit Type", fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf("video" to "Video", "voice" to "Voice", "chat" to "Chat").forEach { (k, label) ->
                    FilterChip(
                        selected = sessionType == k,
                        onClick = { sessionType = k },
                        label = { Text(label) }
                    )
                }
            }
            Spacer(Modifier.height(16.dp))

            // Date/Time
            OutlinedTextField(
                value = dateStr, onValueChange = { dateStr = it },
                label = { Text("Start (YYYY-MM-DDTHH:mm:ss)") },
                placeholder = { Text("2025-01-15T14:00:00") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true
            )
            Spacer(Modifier.height(12.dp))

            OutlinedTextField(
                value = title, onValueChange = { title = it },
                label = { Text("Title (optional)") },
                modifier = Modifier.fillMaxWidth(), singleLine = true
            )
            Spacer(Modifier.height(12.dp))

            OutlinedTextField(
                value = reasonForVisit, onValueChange = { reasonForVisit = it },
                label = { Text("Reason for Visit") },
                modifier = Modifier.fillMaxWidth(), singleLine = true
            )
            Spacer(Modifier.height(12.dp))

            OutlinedTextField(
                value = chiefComplaint, onValueChange = { chiefComplaint = it },
                label = { Text("Chief Complaint") },
                modifier = Modifier.fillMaxWidth(), maxLines = 3
            )
            Spacer(Modifier.height(12.dp))

            // Specialty dropdown
            var specExpanded by remember { mutableStateOf(false) }
            ExposedDropdownMenuBox(expanded = specExpanded, onExpandedChange = { specExpanded = it }) {
                OutlinedTextField(
                    value = if (specialty.isEmpty()) "— None —" else specialty,
                    onValueChange = {},
                    readOnly = true,
                    label = { Text("Specialty") },
                    modifier = Modifier.fillMaxWidth().menuAnchor(),
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(specExpanded) }
                )
                ExposedDropdownMenu(expanded = specExpanded, onDismissRequest = { specExpanded = false }) {
                    SPECIALTIES.forEach { s ->
                        DropdownMenuItem(
                            text = { Text(if (s.isEmpty()) "— None —" else s) },
                            onClick = { specialty = s; specExpanded = false }
                        )
                    }
                }
            }
            Spacer(Modifier.height(12.dp))

            // Priority
            var priExpanded by remember { mutableStateOf(false) }
            ExposedDropdownMenuBox(expanded = priExpanded, onExpandedChange = { priExpanded = it }) {
                OutlinedTextField(
                    value = statusLabel(priority),
                    onValueChange = {},
                    readOnly = true,
                    label = { Text("Priority") },
                    modifier = Modifier.fillMaxWidth().menuAnchor(),
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(priExpanded) }
                )
                ExposedDropdownMenu(expanded = priExpanded, onDismissRequest = { priExpanded = false }) {
                    listOf("routine", "urgent", "emergency").forEach { p ->
                        DropdownMenuItem(
                            text = { Text(statusLabel(p)) },
                            onClick = { priority = p; priExpanded = false }
                        )
                    }
                }
            }
            Spacer(Modifier.height(16.dp))

            // Feature toggles
            Text("Features", fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(8.dp))
            listOf(
                "Live Transcription" to transcription,
                "In-Session Chat" to chat,
                "Recording" to recording,
                "Waiting Room" to waitingRoom
            ).forEachIndexed { i, (label, checked) ->
                Row(
                    modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(label, modifier = Modifier.weight(1f))
                    Switch(checked = checked, onCheckedChange = { v ->
                        when (i) {
                            0 -> transcription = v; 1 -> chat = v
                            2 -> recording = v; 3 -> waitingRoom = v
                        }
                    })
                }
            }
            Spacer(Modifier.height(20.dp))

            Button(
                onClick = {
                    if (dateStr.isBlank()) return@Button
                    submitting = true
                    scope.launch {
                        try {
                            ApiClient.getApiService().createTelehealthSession(
                                TelehealthSessionRequest(
                                    sessionType = sessionType,
                                    title = title.ifBlank { null },
                                    scheduledStart = dateStr,
                                    reasonForVisit = reasonForVisit.ifBlank { null },
                                    chiefComplaint = chiefComplaint.ifBlank { null },
                                    specialty = specialty.ifBlank { null },
                                    priority = priority,
                                    transcriptionEnabled = transcription,
                                    chatEnabled = chat,
                                    recordingEnabled = recording,
                                    waitingRoomEnabled = waitingRoom
                                )
                            )
                            onCreated()
                        } catch (e: Exception) {
                            // show error
                        }
                        submitting = false
                    }
                },
                modifier = Modifier.fillMaxWidth(),
                enabled = !submitting && dateStr.isNotBlank()
            ) {
                if (submitting) CircularProgressIndicator(Modifier.size(20.dp), color = Color.White,
                    strokeWidth = 2.dp)
                else Text("Schedule Visit")
            }
            Spacer(Modifier.height(24.dp))
        }
    }
}

/* ══════════════════════════════════════════════════════════
   SESSION DETAIL SHEET
   ══════════════════════════════════════════════════════════ */

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SessionDetailSheet(
    session: TelehealthSession,
    onDismiss: () -> Unit,
    onJoinCall: () -> Unit,
    onRefresh: () -> Unit
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val scope = rememberCoroutineScope()
    var tab by remember { mutableIntStateOf(0) }
    var notes by remember { mutableStateOf<List<TelehealthNote>>(emptyList()) }
    var transcripts by remember { mutableStateOf<List<TelehealthTranscript>>(emptyList()) }
    var noteText by remember { mutableStateOf("") }

    LaunchedEffect(session.id) {
        try { notes = ApiClient.getApiService().getTelehealthNotes(session.id) } catch (_: Exception) {}
        try { transcripts = ApiClient.getApiService().getTelehealthTranscripts(session.id) } catch (_: Exception) {}
    }

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheetState) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 24.dp)
                .heightIn(min = 400.dp)
        ) {
            // Header
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(session.displayTitle, style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                if (session.isJoinable) {
                    Button(onClick = onJoinCall, contentPadding = PaddingValues(horizontal = 16.dp)) {
                        Icon(Icons.Default.Videocam, null, Modifier.size(16.dp))
                        Spacer(Modifier.width(4.dp))
                        Text("Join")
                    }
                }
            }
            Spacer(Modifier.height(8.dp))

            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                StatusChip(statusLabel(session.sessionType), typeColor(session.sessionType))
                StatusChip(statusLabel(session.status), statusColor(session.status))
                session.priority?.let { StatusChip(statusLabel(it),
                    if (it == "urgent") Color(0xFFFF9800) else if (it == "emergency") Color.Red else Color.Gray) }
            }
            Spacer(Modifier.height(12.dp))

            // Tabs
            TabRow(selectedTabIndex = tab) {
                Tab(selected = tab == 0, onClick = { tab = 0 }) { Text("Info", Modifier.padding(12.dp)) }
                Tab(selected = tab == 1, onClick = { tab = 1 }) { Text("Notes", Modifier.padding(12.dp)) }
                Tab(selected = tab == 2, onClick = { tab = 2 }) { Text("Transcripts", Modifier.padding(12.dp)) }
            }
            Spacer(Modifier.height(12.dp))

            Column(modifier = Modifier.verticalScroll(rememberScrollState()).weight(1f, fill = false)) {
                when (tab) {
                    0 -> {
                        InfoRow("Scheduled Start", formatDateTime(session.scheduledStart))
                        session.scheduledEnd?.let { InfoRow("Scheduled End", formatDateTime(it)) }
                        session.actualStart?.let { InfoRow("Actual Start", formatDateTime(it)) }
                        session.actualEnd?.let { InfoRow("Actual End", formatDateTime(it)) }
                        session.durationMinutes?.let { InfoRow("Duration", "$it min") }
                        session.specialty?.let { InfoRow("Specialty", it) }
                        session.reasonForVisit?.let { InfoRow("Reason", it) }
                        session.chiefComplaint?.let { InfoRow("Chief Complaint", it) }
                        if (session.followUpNeeded) {
                            Spacer(Modifier.height(12.dp))
                            Card(colors = CardDefaults.cardColors(
                                containerColor = MaterialTheme.colorScheme.primaryContainer)) {
                                Column(Modifier.padding(12.dp)) {
                                    Text("Follow-up Needed", fontWeight = FontWeight.SemiBold)
                                    session.followUpDate?.let { Text("Date: $it", fontSize = 13.sp) }
                                    session.followUpNotes?.let { Text(it, fontSize = 13.sp) }
                                }
                            }
                        }
                        Spacer(Modifier.height(12.dp))
                        // Participants
                        session.participants?.let { parts ->
                            Text("Participants", fontWeight = FontWeight.SemiBold)
                            Spacer(Modifier.height(8.dp))
                            parts.forEach { p ->
                                Row(Modifier.fillMaxWidth().padding(vertical = 4.dp),
                                    verticalAlignment = Alignment.CenterVertically) {
                                    Icon(if (p.role == "provider") Icons.Default.LocalHospital
                                        else Icons.Default.Person, null,
                                        tint = if (p.role == "provider") StatusScheduled else StatusActive,
                                        modifier = Modifier.size(20.dp))
                                    Spacer(Modifier.width(8.dp))
                                    Text("User #${p.userId}", fontSize = 13.sp)
                                    Spacer(Modifier.width(4.dp))
                                    Text("${statusLabel(p.role)} · ${statusLabel(p.status)}",
                                        fontSize = 11.sp, color = Color.Gray)
                                    Spacer(Modifier.weight(1f))
                                    Icon(if (p.cameraEnabled) Icons.Default.Videocam else Icons.Default.VideocamOff,
                                        null, modifier = Modifier.size(14.dp),
                                        tint = if (p.cameraEnabled) StatusActive else Color.Gray)
                                    Spacer(Modifier.width(4.dp))
                                    Icon(if (p.microphoneEnabled) Icons.Default.Mic else Icons.Default.MicOff,
                                        null, modifier = Modifier.size(14.dp),
                                        tint = if (p.microphoneEnabled) StatusActive else Color.Gray)
                                }
                            }
                        }

                        // Cancel button
                        if (session.status !in listOf("cancelled", "completed")) {
                            Spacer(Modifier.height(16.dp))
                            OutlinedButton(
                                onClick = {
                                    scope.launch {
                                        try {
                                            ApiClient.getApiService().updateTelehealthSession(
                                                session.id, TelehealthStatusRequest("cancelled"))
                                            onRefresh(); onDismiss()
                                        } catch (_: Exception) {}
                                    }
                                },
                                modifier = Modifier.fillMaxWidth(),
                                colors = ButtonDefaults.outlinedButtonColors(contentColor = Color.Red)
                            ) { Text("Cancel Session") }
                        }
                    }
                    1 -> {
                        // Add note
                        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                            OutlinedTextField(
                                value = noteText, onValueChange = { noteText = it },
                                label = { Text("Add a note…") },
                                modifier = Modifier.weight(1f), maxLines = 3
                            )
                            Spacer(Modifier.width(8.dp))
                            IconButton(onClick = {
                                if (noteText.isBlank()) return@IconButton
                                scope.launch {
                                    try {
                                        ApiClient.getApiService().createTelehealthNote(
                                            session.id, TelehealthNoteRequest(content = noteText))
                                        noteText = ""
                                        notes = ApiClient.getApiService().getTelehealthNotes(session.id)
                                    } catch (_: Exception) {}
                                }
                            }) {
                                Icon(Icons.Default.Send, null, tint = MaterialTheme.colorScheme.primary)
                            }
                        }
                        Spacer(Modifier.height(12.dp))

                        if (notes.isEmpty()) {
                            Text("No notes yet.", color = Color.Gray, modifier = Modifier.padding(vertical = 16.dp))
                        }
                        notes.forEach { note ->
                            Card(Modifier.fillMaxWidth().padding(bottom = 8.dp)) {
                                Column(Modifier.padding(12.dp)) {
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        StatusChip(statusLabel(note.noteType), StatusScheduled)
                                        Spacer(Modifier.weight(1f))
                                        Text(com.alafia.android.util.AppDate.date(note.createdAt), fontSize = 11.sp, color = Color.Gray)
                                        IconButton(
                                            onClick = {
                                                scope.launch {
                                                    try {
                                                        ApiClient.getApiService().deleteTelehealthNote(
                                                            session.id, note.id)
                                                        notes = ApiClient.getApiService()
                                                            .getTelehealthNotes(session.id)
                                                    } catch (_: Exception) {}
                                                }
                                            },
                                            modifier = Modifier.size(24.dp)
                                        ) {
                                            Icon(Icons.Default.Delete, null, Modifier.size(14.dp), tint = Color.Red)
                                        }
                                    }
                                    Spacer(Modifier.height(4.dp))
                                    Text(note.content, fontSize = 14.sp)
                                    note.diagnosisCodes?.let {
                                        Text("ICD: $it", fontSize = 11.sp, color = Color.Gray) }
                                    note.procedureCodes?.let {
                                        Text("CPT: $it", fontSize = 11.sp, color = Color.Gray) }
                                }
                            }
                        }
                    }
                    2 -> {
                        if (transcripts.isEmpty()) {
                            Text("No transcripts recorded.", color = Color.Gray,
                                modifier = Modifier.padding(vertical = 16.dp))
                        }
                        transcripts.forEach { t ->
                            Row(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                                Icon(Icons.Default.Person, null, Modifier.size(18.dp), tint = Color.Gray)
                                Spacer(Modifier.width(8.dp))
                                Column {
                                    Row {
                                        Text("Speaker #${t.speakerId ?: 0}", fontSize = 11.sp, color = Color.Gray)
                                        Spacer(Modifier.weight(1f))
                                        t.confidence?.let {
                                            Text("${(it * 100).toInt()}%", fontSize = 11.sp, color = Color.Gray) }
                                    }
                                    Text(t.content, fontSize = 13.sp)
                                }
                            }
                            HorizontalDivider(Modifier.padding(vertical = 4.dp))
                        }
                    }
                }
            }
            Spacer(Modifier.height(16.dp))
        }
    }
}

@Composable
private fun InfoRow(label: String, value: String) {
    Column(Modifier.padding(vertical = 4.dp)) {
        Text(label, fontSize = 11.sp, color = Color.Gray)
        Text(value, fontSize = 14.sp, fontWeight = FontWeight.Medium)
    }
}

/* ══════════════════════════════════════════════════════════
   VIDEO CALL SCREEN (OVERLAY)
   ══════════════════════════════════════════════════════════ */

@Composable
private fun VideoCallScreen(session: TelehealthSession, onEnd: () -> Unit) {
    var callState by remember { mutableStateOf("connecting") } // connecting, waiting, active, ended
    var elapsed by remember { mutableIntStateOf(0) }
    var cameraOn by remember { mutableStateOf(true) }
    var micOn by remember { mutableStateOf(true) }
    var chatOpen by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val isVideo = session.sessionType == "video"

    // Timer
    LaunchedEffect(callState) {
        if (callState == "active") {
            while (true) {
                kotlinx.coroutines.delay(1000)
                elapsed++
            }
        }
    }

    // Init call
    LaunchedEffect(Unit) {
        try {
            ApiClient.getApiService().joinTelehealthSession(session.id)
        } catch (_: Exception) {}
        if (session.status == "scheduled") {
            try { ApiClient.getApiService().startTelehealthSession(session.id) } catch (_: Exception) {}
        }
        callState = if (session.waitingRoomEnabled) "waiting" else "active"
        // Simulate connecting
        kotlinx.coroutines.delay(2000)
        if (callState == "waiting") callState = "active"
    }

    val elapsedStr = "%02d:%02d".format(elapsed / 60, elapsed % 60)

    Box(modifier = Modifier.fillMaxSize().background(Color(0xFF1A1A2E))) {
        Column(Modifier.fillMaxSize()) {
            // Top bar
            Row(
                modifier = Modifier.fillMaxWidth().background(Color.Black.copy(alpha = 0.4f))
                    .padding(horizontal = 16.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(Modifier.weight(1f)) {
                    Text(session.displayTitle, color = Color.White, fontWeight = FontWeight.Bold,
                        maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(8.dp).clip(CircleShape).background(
                            when (callState) { "active" -> StatusActive; "waiting" -> StatusWaiting; else -> Color.Gray }
                        ))
                        Spacer(Modifier.width(6.dp))
                        Text(
                            when (callState) { "active" -> "Live"; "waiting" -> "Waiting"; else -> "Connecting" },
                            color = Color.White.copy(alpha = 0.7f), fontSize = 12.sp
                        )
                    }
                }
                Icon(Icons.Default.Schedule, null, tint = Color.White.copy(alpha = 0.7f), modifier = Modifier.size(14.dp))
                Spacer(Modifier.width(4.dp))
                Text(elapsedStr, color = Color.White, fontWeight = FontWeight.Bold)
            }

            // Main area
            Box(modifier = Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
                when {
                    callState == "waiting" -> Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        CircularProgressIndicator(color = Color.White)
                        Spacer(Modifier.height(16.dp))
                        Text("Waiting Room", color = Color.White, fontSize = 20.sp, fontWeight = FontWeight.SemiBold)
                        Spacer(Modifier.height(8.dp))
                        Text("Please wait while the provider admits you",
                            color = Color.White.copy(alpha = 0.7f), fontSize = 14.sp)
                    }
                    callState == "connecting" -> Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        CircularProgressIndicator(color = Color.White)
                        Spacer(Modifier.height(16.dp))
                        Text("Connecting…", color = Color.White, fontSize = 18.sp)
                    }
                    isVideo -> {
                        // Placeholder for remote video
                        Icon(Icons.Default.Person, null, modifier = Modifier.size(80.dp),
                            tint = Color.White.copy(alpha = 0.3f))
                    }
                    else -> Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(Icons.Default.Phone, null, modifier = Modifier.size(60.dp),
                            tint = Color.White.copy(alpha = 0.3f))
                        Spacer(Modifier.height(12.dp))
                        Text("Voice Call", color = Color.White.copy(alpha = 0.7f), fontSize = 18.sp)
                        Text(elapsedStr, color = Color.White, fontSize = 28.sp, fontWeight = FontWeight.Bold)
                    }
                }

                // Local video PIP
                if (isVideo && callState == "active") {
                    Box(
                        modifier = Modifier.align(Alignment.BottomEnd)
                            .padding(12.dp)
                            .size(width = 120.dp, height = 90.dp)
                            .clip(RoundedCornerShape(12.dp))
                            .background(Color.DarkGray.copy(alpha = 0.5f)),
                        contentAlignment = Alignment.Center
                    ) {
                        Icon(
                            if (cameraOn) Icons.Default.Person else Icons.Default.VideocamOff,
                            null, tint = Color.White.copy(alpha = 0.5f), modifier = Modifier.size(28.dp)
                        )
                    }
                }
            }

            // Controls
            Row(
                modifier = Modifier.fillMaxWidth().background(Color.Black.copy(alpha = 0.5f))
                    .padding(vertical = 16.dp),
                horizontalArrangement = Arrangement.Center,
                verticalAlignment = Alignment.CenterVertically
            ) {
                if (isVideo) {
                    CallControlBtn(
                        icon = if (cameraOn) Icons.Default.Videocam else Icons.Default.VideocamOff,
                        active = cameraOn,
                        onClick = { cameraOn = !cameraOn }
                    )
                    Spacer(Modifier.width(16.dp))
                }

                CallControlBtn(
                    icon = if (micOn) Icons.Default.Mic else Icons.Default.MicOff,
                    active = micOn,
                    onClick = { micOn = !micOn }
                )

                if (session.chatEnabled) {
                    Spacer(Modifier.width(16.dp))
                    CallControlBtn(
                        icon = Icons.Default.Chat,
                        active = chatOpen,
                        onClick = { chatOpen = !chatOpen },
                        tint = if (chatOpen) StatusScheduled else null
                    )
                }

                Spacer(Modifier.width(20.dp))

                // End call
                IconButton(
                    onClick = {
                        scope.launch {
                            try { ApiClient.getApiService().endTelehealthSession(session.id) } catch (_: Exception) {}
                            try { ApiClient.getApiService().leaveTelehealthSession(session.id) } catch (_: Exception) {}
                            onEnd()
                        }
                    },
                    modifier = Modifier.size(56.dp).clip(CircleShape).background(Color.Red)
                ) {
                    Icon(Icons.Default.CallEnd, null, tint = Color.White, modifier = Modifier.size(24.dp))
                }
            }
        }
    }
}

@Composable
private fun CallControlBtn(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    active: Boolean,
    onClick: () -> Unit,
    tint: Color? = null
) {
    IconButton(
        onClick = onClick,
        modifier = Modifier.size(48.dp)
            .clip(CircleShape)
            .background(tint ?: if (active) Color.White.copy(alpha = 0.15f) else Color.White.copy(alpha = 0.08f))
    ) {
        Icon(icon, null, tint = Color.White, modifier = Modifier.size(20.dp))
    }
}

/* ── Helpers ── */

// Local timezone (server timestamps are UTC).
private fun formatDateTime(iso: String): String = com.alafia.android.util.AppDate.dateTime(iso)
