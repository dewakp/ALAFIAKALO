@file:OptIn(ExperimentalMaterial3Api::class)

package com.alafia.android.views.chemo
import com.alafia.android.util.ErrorUtil

import android.widget.Toast
import androidx.compose.animation.AnimatedVisibility
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
import com.alafia.android.models.TherapySession
import kotlinx.coroutines.launch
import androidx.navigation.NavHostController
import androidx.compose.ui.res.stringResource
import com.alafia.android.R

private val COMMON_SIDE_EFFECTS = listOf(
    "Nausea", "Vomiting", "Fatigue", "Hair Loss", "Mouth Sores", "Neuropathy",
    "Low WBC", "Low Platelets", "Anemia", "Diarrhea", "Constipation",
    "Loss of Appetite", "Skin Changes", "Fever", "Chills"
)
private val ROUTES = listOf("IV Push", "IV Drip", "IV Infusion", "Oral", "Subcutaneous", "Intramuscular", "Intrathecal")
private val TOLERANCE_OPTIONS = listOf("Well Tolerated", "Moderate", "Poor", "Severe Reaction")

@Composable
fun ChemotherapyScreen(navController: NavHostController) {
    var sessions by remember { mutableStateOf<List<TherapySession>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    var showForm by remember { mutableStateOf(false) }
    var deleteTarget by remember { mutableStateOf<TherapySession?>(null) }
    var expandedId by remember { mutableStateOf<Int?>(null) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    fun loadSessions() {
        scope.launch {
            isLoading = true
            try {
                sessions = ApiClient.getApiService().getTherapySessions(therapyType = "chemotherapy")
            } catch (e: Exception) {
                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
            }
            isLoading = false
        }
    }

    LaunchedEffect(Unit) { loadSessions() }

    Scaffold(
        topBar = { TopAppBar(
                title = { Text(stringResource(R.string.chemotherapy)) },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = stringResource(R.string.back))
                    }
                }
            ) },
        floatingActionButton = {
            FloatingActionButton(onClick = { showForm = true }, containerColor = Color(0xFF7B1FA2)) {
                Icon(Icons.Default.Add, "Add Session", tint = Color.White)
            }
        }
    ) { padding ->
        if (isLoading) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        } else if (sessions.isEmpty()) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(Icons.Default.Medication, "No sessions", modifier = Modifier.size(64.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
                    Spacer(Modifier.height(12.dp))
                    Text(stringResource(R.string.no_chemo_sessions), style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(stringResource(R.string.tap_to_log_a_session), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                item {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                        ChemoSummaryCard(stringResource(R.string.total), "${sessions.size}", Color(0xFF7B1FA2), Modifier.weight(1f))
                        ChemoSummaryCard(stringResource(R.string.done), "${sessions.count { it.status == "completed" }}", Color(0xFF4CAF50), Modifier.weight(1f))
                        ChemoSummaryCard(stringResource(R.string.scheduled), "${sessions.count { it.status == "scheduled" }}", Color(0xFFFF9800), Modifier.weight(1f))
                    }
                    Spacer(Modifier.height(8.dp))
                }

                items(sessions, key = { it.id }) { session ->
                    ChemoSessionCard(
                        session = session,
                        isExpanded = expandedId == session.id,
                        onToggle = { expandedId = if (expandedId == session.id) null else session.id },
                        onDelete = { deleteTarget = session }
                    )
                }
            }
        }
    }

    // Delete dialog
    deleteTarget?.let { session ->
        AlertDialog(
            onDismissRequest = { deleteTarget = null },
            title = { Text(stringResource(R.string.delete_session)) },
            text = { Text(stringResource(R.string.delete_this_chemotherapy_session)) },
            confirmButton = {
                TextButton(onClick = {
                    scope.launch {
                        try {
                            ApiClient.getApiService().deleteTherapySession(session.id)
                            deleteTarget = null
                            loadSessions()
                        } catch (e: Exception) {
                            Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                        }
                    }
                }) { Text(stringResource(R.string.delete), color = MaterialTheme.colorScheme.error) }
            },
            dismissButton = { TextButton(onClick = { deleteTarget = null }) { Text(stringResource(R.string.cancel)) } }
        )
    }

    if (showForm) {
        ChemoAddSessionSheet(
            onDismiss = { showForm = false },
            onSaved = { showForm = false; loadSessions() }
        )
    }
}

@Composable
private fun ChemoSessionCard(session: TherapySession, isExpanded: Boolean, onToggle: () -> Unit, onDelete: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth(), onClick = onToggle) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(session.therapyName ?: stringResource(R.string.chemotherapy), fontWeight = FontWeight.Bold, fontSize = 16.sp)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        if (session.sessionNumber != null) {
                            Text(stringResource(R.string.session, session.sessionNumber), fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            if (session.totalSessionsPlanned != null) Text(" / ${session.totalSessionsPlanned}", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            Text(" · ", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        Text(session.scheduledDate.take(10), fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
                ChemoStatusChip(session.status)
                IconButton(onClick = onDelete) {
                    Icon(Icons.Default.Delete, "Delete", tint = MaterialTheme.colorScheme.error, modifier = Modifier.size(20.dp))
                }
            }

            Spacer(Modifier.height(8.dp))

            // Drug info
            Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                session.drugsAdministered?.takeIf { it.isNotEmpty() }?.let { ChemoMetricPill(stringResource(R.string.drugs), it) }
                session.dosage?.takeIf { it.isNotEmpty() }?.let { ChemoMetricPill(stringResource(R.string.dosage), it) }
                session.routeOfAdministration?.takeIf { it.isNotEmpty() }?.let { ChemoMetricPill(stringResource(R.string.route), it) }
            }

            AnimatedVisibility(isExpanded) {
                Column(modifier = Modifier.padding(top = 12.dp)) {
                    HorizontalDivider()
                    Spacer(Modifier.height(8.dp))

                    if (session.durationMinutes != null) {
                        Text(stringResource(R.string.duration_min, session.durationMinutes), fontSize = 13.sp)
                    }

                    // Vitals
                    if (session.preSystolicBp != null || session.postSystolicBp != null) {
                        Spacer(Modifier.height(4.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                            if (session.preSystolicBp != null && session.preDiastolicBp != null)
                                ChemoMetricPill(stringResource(R.string.pre_bp_2), "${session.preSystolicBp}/${session.preDiastolicBp}")
                            if (session.postSystolicBp != null && session.postDiastolicBp != null)
                                ChemoMetricPill(stringResource(R.string.post_bp_2), "${session.postSystolicBp}/${session.postDiastolicBp}")
                            session.oxygenSaturation?.let { ChemoMetricPill(stringResource(R.string.spo_2), "$it%") }
                        }
                    }

                    // Tolerance
                    session.patientTolerance?.takeIf { it.isNotEmpty() }?.let {
                        Spacer(Modifier.height(4.dp))
                        val color = when {
                            it.contains("Severe") -> Color(0xFFF44336)
                            it.contains("Poor") -> Color(0xFFFF9800)
                            else -> Color(0xFF4CAF50)
                        }
                        Text(stringResource(R.string.tolerance, it), fontSize = 13.sp, fontWeight = FontWeight.Bold, color = color)
                    }

                    // Side effects
                    session.sideEffects?.takeIf { it.isNotEmpty() }?.let {
                        Spacer(Modifier.height(4.dp))
                        Text(stringResource(R.string.side_effects, it), fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    session.adverseReactions?.takeIf { it.isNotEmpty() }?.let {
                        Text("⚠️ $it", fontSize = 12.sp, color = Color(0xFFF44336))
                    }

                    // Notes
                    session.clinicalNotes?.takeIf { it.isNotEmpty() }?.let {
                        Spacer(Modifier.height(4.dp))
                        Text(it, fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    session.facilityName?.takeIf { it.isNotEmpty() }?.let {
                        Text("📍 $it", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
    }
}

@Composable
private fun ChemoAddSessionSheet(onDismiss: () -> Unit, onSaved: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var saving by remember { mutableStateOf(false) }

    var date by remember { mutableStateOf(java.time.LocalDate.now().toString()) }
    var status by remember { mutableStateOf("completed") }
    var therapyName by remember { mutableStateOf("") }
    var sessionNum by remember { mutableStateOf("") }
    var totalPlanned by remember { mutableStateOf("") }
    var duration by remember { mutableStateOf("") }
    var drugs by remember { mutableStateOf("") }
    var dosage by remember { mutableStateOf("") }
    var route by remember { mutableStateOf("IV Infusion") }
    var preSys by remember { mutableStateOf("") }
    var preDia by remember { mutableStateOf("") }
    var preHr by remember { mutableStateOf("") }
    var postSys by remember { mutableStateOf("") }
    var postDia by remember { mutableStateOf("") }
    var postHr by remember { mutableStateOf("") }
    var o2 by remember { mutableStateOf("") }
    var selectedEffects by remember { mutableStateOf(setOf<String>()) }
    var tolerance by remember { mutableStateOf("") }
    var adverseReactions by remember { mutableStateOf("") }
    var facility by remember { mutableStateOf("") }
    var physician by remember { mutableStateOf("") }
    var clinicalNotes by remember { mutableStateOf("") }
    var patientNotes by remember { mutableStateOf("") }

    val statuses = listOf("scheduled", "in_progress", "completed", "cancelled", "missed")

    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp, vertical = 8.dp)
        ) {
            Text(stringResource(R.string.new_chemo_session), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, color = Color(0xFF7B1FA2))
            Spacer(Modifier.height(16.dp))

            // Protocol
            OutlinedTextField(value = therapyName, onValueChange = { therapyName = it }, label = { Text(stringResource(R.string.protocol_folfox_r_chop)) }, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(value = date, onValueChange = { date = it }, label = { Text(stringResource(R.string.date_yyyy_mm_dd)) }, modifier = Modifier.fillMaxWidth())
            Spacer(Modifier.height(8.dp))

            Text(stringResource(R.string.status), fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.fillMaxWidth()) {
                statuses.take(3).forEach { s ->
                    FilterChip(selected = status == s, onClick = { status = s }, label = { Text(s.replace("_", " "), fontSize = 11.sp) })
                }
            }
            Spacer(Modifier.height(8.dp))

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(value = sessionNum, onValueChange = { sessionNum = it }, label = { Text(stringResource(R.string.session_2)) }, modifier = Modifier.weight(1f))
                OutlinedTextField(value = totalPlanned, onValueChange = { totalPlanned = it }, label = { Text(stringResource(R.string.total_planned)) }, modifier = Modifier.weight(1f))
                OutlinedTextField(value = duration, onValueChange = { duration = it }, label = { Text(stringResource(R.string.duration_min_2)) }, modifier = Modifier.weight(1f))
            }
            Spacer(Modifier.height(12.dp))

            // Drugs
            Text(stringResource(R.string.drugs_administration), fontWeight = FontWeight.Bold, fontSize = 14.sp, color = Color(0xFF7B1FA2))
            OutlinedTextField(value = drugs, onValueChange = { drugs = it }, label = { Text(stringResource(R.string.drugs_administered)) }, modifier = Modifier.fillMaxWidth())
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(value = dosage, onValueChange = { dosage = it }, label = { Text(stringResource(R.string.dosage)) }, modifier = Modifier.weight(1f))
            }
            Spacer(Modifier.height(4.dp))
            Text(stringResource(R.string.route), fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp), modifier = Modifier.fillMaxWidth()) {
                ROUTES.take(4).forEach { r ->
                    FilterChip(selected = route == r, onClick = { route = r }, label = { Text(r, fontSize = 10.sp) })
                }
            }
            Spacer(Modifier.height(12.dp))

            // Vitals
            Text(stringResource(R.string.vitals), fontWeight = FontWeight.Bold, fontSize = 14.sp, color = Color(0xFF7B1FA2))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(value = preSys, onValueChange = { preSys = it }, label = { Text(stringResource(R.string.pre_sys)) }, modifier = Modifier.weight(1f))
                OutlinedTextField(value = preDia, onValueChange = { preDia = it }, label = { Text(stringResource(R.string.pre_dia)) }, modifier = Modifier.weight(1f))
                OutlinedTextField(value = preHr, onValueChange = { preHr = it }, label = { Text(stringResource(R.string.pre_hr)) }, modifier = Modifier.weight(1f))
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(value = postSys, onValueChange = { postSys = it }, label = { Text(stringResource(R.string.post_sys)) }, modifier = Modifier.weight(1f))
                OutlinedTextField(value = postDia, onValueChange = { postDia = it }, label = { Text(stringResource(R.string.post_dia)) }, modifier = Modifier.weight(1f))
                OutlinedTextField(value = postHr, onValueChange = { postHr = it }, label = { Text(stringResource(R.string.post_hr)) }, modifier = Modifier.weight(1f))
            }
            OutlinedTextField(value = o2, onValueChange = { o2 = it }, label = { Text(stringResource(R.string.spo)) }, modifier = Modifier.fillMaxWidth())
            Spacer(Modifier.height(12.dp))

            // Side Effects
            Text(stringResource(R.string.side_effects_2), fontWeight = FontWeight.Bold, fontSize = 14.sp, color = Color(0xFF7B1FA2))
            @OptIn(ExperimentalLayoutApi::class)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                COMMON_SIDE_EFFECTS.forEach { effect ->
                    FilterChip(
                        selected = effect in selectedEffects,
                        onClick = { selectedEffects = if (effect in selectedEffects) selectedEffects - effect else selectedEffects + effect },
                        label = { Text(effect, fontSize = 11.sp) }
                    )
                }
            }
            Spacer(Modifier.height(8.dp))

            Text(stringResource(R.string.tolerance_2), fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                TOLERANCE_OPTIONS.forEach { t ->
                    FilterChip(selected = tolerance == t, onClick = { tolerance = t }, label = { Text(t, fontSize = 10.sp) })
                }
            }
            OutlinedTextField(value = adverseReactions, onValueChange = { adverseReactions = it }, label = { Text(stringResource(R.string.adverse_reactions)) }, modifier = Modifier.fillMaxWidth())
            Spacer(Modifier.height(12.dp))

            // Facility
            OutlinedTextField(value = facility, onValueChange = { facility = it }, label = { Text(stringResource(R.string.facility)) }, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(value = physician, onValueChange = { physician = it }, label = { Text(stringResource(R.string.physician)) }, modifier = Modifier.fillMaxWidth())
            Spacer(Modifier.height(8.dp))
            OutlinedTextField(value = clinicalNotes, onValueChange = { clinicalNotes = it }, label = { Text(stringResource(R.string.clinical_notes)) }, modifier = Modifier.fillMaxWidth(), minLines = 2)
            OutlinedTextField(value = patientNotes, onValueChange = { patientNotes = it }, label = { Text(stringResource(R.string.patient_notes)) }, modifier = Modifier.fillMaxWidth(), minLines = 2)
            Spacer(Modifier.height(16.dp))

            Button(
                onClick = {
                    scope.launch {
                        saving = true
                        try {
                            val body = mutableMapOf<String, Any?>(
                                "therapy_type" to "CHEMOTHERAPY",
                                "scheduled_date" to date,
                                "status" to status,
                                "route_of_administration" to route,
                            )
                            if (therapyName.isNotEmpty()) body["therapy_name"] = therapyName
                            if (sessionNum.isNotEmpty()) body["session_number"] = sessionNum.toIntOrNull()
                            if (totalPlanned.isNotEmpty()) body["total_sessions_planned"] = totalPlanned.toIntOrNull()
                            if (duration.isNotEmpty()) body["duration_minutes"] = duration.toIntOrNull()
                            if (drugs.isNotEmpty()) body["drugs_administered"] = drugs
                            if (dosage.isNotEmpty()) body["dosage"] = dosage
                            if (preSys.isNotEmpty()) body["pre_systolic_bp"] = preSys.toIntOrNull()
                            if (preDia.isNotEmpty()) body["pre_diastolic_bp"] = preDia.toIntOrNull()
                            if (preHr.isNotEmpty()) body["pre_heart_rate"] = preHr.toIntOrNull()
                            if (postSys.isNotEmpty()) body["post_systolic_bp"] = postSys.toIntOrNull()
                            if (postDia.isNotEmpty()) body["post_diastolic_bp"] = postDia.toIntOrNull()
                            if (postHr.isNotEmpty()) body["post_heart_rate"] = postHr.toIntOrNull()
                            if (o2.isNotEmpty()) body["oxygen_saturation"] = o2.toIntOrNull()
                            if (selectedEffects.isNotEmpty()) body["side_effects"] = selectedEffects.sorted().joinToString(", ")
                            if (tolerance.isNotEmpty()) body["patient_tolerance"] = tolerance
                            if (adverseReactions.isNotEmpty()) body["adverse_reactions"] = adverseReactions
                            if (facility.isNotEmpty()) body["facility_name"] = facility
                            if (physician.isNotEmpty()) body["attending_physician"] = physician
                            if (clinicalNotes.isNotEmpty()) body["clinical_notes"] = clinicalNotes
                            if (patientNotes.isNotEmpty()) body["patient_notes"] = patientNotes

                            ApiClient.getApiService().createTherapySession(body)
                            onSaved()
                        } catch (e: Exception) {
                            Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                        }
                        saving = false
                    }
                },
                modifier = Modifier.fillMaxWidth(),
                enabled = !saving,
                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF7B1FA2))
            ) {
                Text(if (saving) stringResource(R.string.saving) else stringResource(R.string.save_session))
            }
            Spacer(Modifier.height(32.dp))
        }
    }
}

@Composable
private fun ChemoSummaryCard(title: String, value: String, color: Color, modifier: Modifier = Modifier) {
    Card(modifier = modifier, colors = CardDefaults.cardColors(containerColor = color.copy(alpha = 0.1f))) {
        Column(modifier = Modifier.padding(12.dp).fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
            Text(value, fontWeight = FontWeight.Bold, fontSize = 22.sp, color = color)
            Text(title, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun ChemoStatusChip(status: String) {
    val color = when (status) {
        "completed" -> Color(0xFF4CAF50)
        "in_progress" -> Color(0xFF2196F3)
        "scheduled" -> Color(0xFFFF9800)
        "cancelled" -> Color(0xFFF44336)
        else -> Color.Gray
    }
    Surface(color = color.copy(alpha = 0.15f), shape = MaterialTheme.shapes.small) {
        Text(
            status.replace("_", " "),
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp),
            fontSize = 11.sp, fontWeight = FontWeight.Bold, color = color
        )
    }
}

@Composable
private fun ChemoMetricPill(label: String, value: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(label, fontSize = 10.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, fontSize = 12.sp, fontWeight = FontWeight.Bold)
    }
}
