package com.alafia.android.views.clinician

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.alafia.android.api.ApiClient
import com.alafia.android.models.IntradialyticReading
import com.alafia.android.models.SessionIntegrity
import com.alafia.android.models.SessionSignoff
import com.alafia.android.models.TherapySessionNote
import com.alafia.android.models.TherapySummary
import com.alafia.android.models.TherapySessionReport
import com.alafia.android.util.ErrorUtil
import kotlinx.coroutines.launch

/**
 * The physician's dialysis view: session reports, the intradialytic curve, and
 * sign-off.
 *
 * Therapies used to fall through to the generic records list, whose Detail and
 * Session columns rendered as em-dashes on a patient with 2005 sessions. This
 * mirrors the patient's own Session Reports screen so both sides read the same
 * artifact, and adds the two things only a clinician does.
 */
@Composable
fun TherapyReportSection(
    patientId: Int,
    rows: List<Map<String, Any?>>,
    days: Int,
    onOpenSession: (Int) -> Unit,
) {
    // Only haemodialysis rows carry a session_id; peritoneal has its own screen.
    val sessions = remember(rows) { rows.filter { num(it["session_id"]) != null } }
    var summary by remember(patientId, days) { mutableStateOf<TherapySummary?>(null) }

    // Count in SQL, not over "whatever rows arrived" — a tile computed from the
    // page is a function of the page size.
    LaunchedEffect(patientId, days) {
        summary = try {
            ApiClient.getApiService().getPatientTherapySummary(patientId, days)
        } catch (e: Exception) { null }
    }

    if (sessions.isEmpty()) {
        Text("No therapy sessions in this period.",
             style = MaterialTheme.typography.bodySmall,
             color = MaterialTheme.colorScheme.onSurfaceVariant)
        return
    }

    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(Modifier.horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            StatTile("Sessions", (summary?.totalSessions ?: sessions.size).toString(), Color(0xFF2A78D6))
            StatTile("Avg Pre Wt", fmt(summary?.avgPreWeightKg ?: avg(sessions, "pre_weight_kg"), 1, "kg"), Color(0xFF1BAF7A))
            StatTile("Avg Post Wt", fmt(summary?.avgPostWeightKg ?: avg(sessions, "post_weight_kg"), 1, "kg"), Color(0xFF1BAF7A))
            StatTile("Avg UF", fmt(summary?.avgFluidRemovedMl ?: avg(sessions, "fluid_removed_ml"), 0, "mL"), Color(0xFFEB6834))
            StatTile("Avg Duration", fmt(summary?.avgDurationMin ?: avg(sessions, "duration_minutes"), 0, "min"), Color(0xFF7C3AED))
        }
        val allTime = summary?.totalSessionsAllTime ?: 0
        Text(
            if (allTime > (summary?.totalSessions ?: sessions.size))
                "${sessions.size} sessions in this period — $allTime on record since ${summary?.earliestSession}"
            else "${sessions.size} sessions in this period",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
        sessions.forEach { row -> SessionCard(row) { onOpenSession(num(row["session_id"])!!.toInt()) } }
    }
}

/** A missing value is excluded from the mean, never counted as zero. */
private fun avg(rows: List<Map<String, Any?>>, key: String): Double? {
    val values = rows.mapNotNull { num(it[key]) }
    return if (values.isEmpty()) null else values.average()
}

private fun num(v: Any?): Double? = when (v) {
    is Number -> v.toDouble()
    is String -> v.toDoubleOrNull()
    else -> null
}

private fun str(v: Any?): String? = when (v) {
    null -> null
    is String -> v.ifBlank { null }
    is Number -> if (v.toDouble() % 1.0 == 0.0) v.toLong().toString() else v.toString()
    else -> v.toString()
}

private fun fmt(value: Double?, digits: Int, unit: String): String =
    if (value == null) "—" else "${String.format("%.${digits}f", value)} $unit"

@Composable
private fun StatTile(label: String, value: String, tone: Color) {
    Card(Modifier.widthIn(min = 108.dp)) {
        Column(Modifier.padding(10.dp)) {
            Box(Modifier.fillMaxWidth().height(3.dp).background(tone))
            Spacer(Modifier.height(6.dp))
            Text(value, style = MaterialTheme.typography.titleMedium,
                 fontWeight = FontWeight.Bold, color = tone)
            Text(label, style = MaterialTheme.typography.labelSmall,
                 color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun SessionCard(row: Map<String, Any?>, onClick: () -> Unit) {
    val reviewed = str(row["flowsheet_status"]) == "reviewed" || str(row["reviewed_at"]) != null
    Card(Modifier.fillMaxWidth().clickable { onClick() }) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(str(row["date"]) ?: "—", style = MaterialTheme.typography.titleSmall,
                     fontWeight = FontWeight.Bold)
                str(row["status"])?.let { Chip(it, MaterialTheme.colorScheme.primary) }
                if (reviewed) Chip("reviewed", Color(0xFF1BAF7A))
                Spacer(Modifier.weight(1f))
                val pre = num(row["pre_weight_kg"]); val post = num(row["post_weight_kg"])
                if (pre != null && post != null) {
                    Text("${String.format("%.1f", pre)} → ${String.format("%.1f", post)} kg",
                         style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold)
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                num(row["fluid_removed_ml"])?.let {
                    Text("${String.format("%.0f", it)} mL",
                         style = MaterialTheme.typography.labelSmall, color = Color(0xFFEB6834))
                }
                num(row["duration_minutes"])?.let {
                    Text("${String.format("%.0f", it)} min",
                         style = MaterialTheme.typography.labelSmall, color = Color(0xFF7C3AED))
                }
                num(row["readings"])?.takeIf { it > 0 }?.let {
                    Text("${it.toInt()} readings", style = MaterialTheme.typography.labelSmall,
                         color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            if (str(row["pre_bp"]) != null || str(row["post_bp"]) != null) {
                Text("BP: Pre ${str(row["pre_bp"]) ?: "—"} → Post ${str(row["post_bp"]) ?: "—"}",
                     style = MaterialTheme.typography.labelSmall,
                     color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

@Composable
private fun Chip(text: String, tone: Color) {
    Box(Modifier.background(tone.copy(alpha = 0.15f), RoundedCornerShape(10.dp))
                .padding(horizontal = 8.dp, vertical = 2.dp)) {
        Text(text, style = MaterialTheme.typography.labelSmall,
             fontWeight = FontWeight.Bold, color = tone)
    }
}

/* ───────── one session ───────── */

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TherapySessionScreen(patientId: Int, sessionId: Int, onBack: () -> Unit) {
    var report by remember(sessionId) { mutableStateOf<TherapySessionReport?>(null) }
    var error by remember(sessionId) { mutableStateOf<String?>(null) }
    var actionError by remember(sessionId) { mutableStateOf<String?>(null) }
    var signoff by remember(sessionId) { mutableStateOf<SessionSignoff?>(null) }
    var busy by remember(sessionId) { mutableStateOf(false) }
    var addedNotes by remember(sessionId) { mutableStateOf<List<TherapySessionNote>>(emptyList()) }
    var noteText by remember(sessionId) { mutableStateOf("") }
    var noteBusy by remember(sessionId) { mutableStateOf(false) }
    var integrity by remember(sessionId) { mutableStateOf<SessionIntegrity?>(null) }
    var integrityError by remember(sessionId) { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(sessionId) {
        error = null
        try {
            report = ApiClient.getApiService().getPatientTherapySession(patientId, sessionId)
        } catch (e: retrofit2.HttpException) {
            // A failed load is an error, never an empty state.
            error = if (e.code() == 403) "This patient has not shared therapies."
                    else "Could not load this session."
        } catch (e: Exception) {
            error = ErrorUtil.userMessage(e)
        }
    }

    Scaffold(topBar = {
        TopAppBar(title = { Text(report?.session?.date ?: "Session") })
    }) { padding ->
        val r = report
        when {
            error != null -> Box(Modifier.fillMaxSize().padding(padding), Alignment.Center) {
                Text(error!!, color = MaterialTheme.colorScheme.error)
            }
            r == null -> Box(Modifier.fillMaxSize().padding(padding), Alignment.Center) {
                CircularProgressIndicator()
            }
            else -> LazyColumn(
                Modifier.fillMaxSize().padding(padding),
                contentPadding = PaddingValues(12.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                item { FactsCard(r) }
                item { ReadingCharts(r.readings) }
                item { ReadingsTable(r.readings) }
                item {
                    NotesCard(r.notes + addedNotes, noteText, { noteText = it }, noteBusy) {
                        scope.launch {
                            noteBusy = true
                            try {
                                val n = ApiClient.getApiService().addPatientTherapyNote(
                                    patientId, sessionId,
                                    mapOf("note_text" to noteText.trim(), "note_type" to "clinical"))
                                addedNotes = addedNotes + n
                                noteText = ""
                            } catch (e: Exception) {
                                actionError = "Could not save the note."
                            } finally { noteBusy = false }
                        }
                    }
                }
                item {
                    IntegrityCard(integrity, integrityError) {
                        scope.launch {
                            try {
                                integrity = ApiClient.getApiService()
                                    .getPatientTherapyIntegrity(patientId, sessionId)
                            } catch (e: Exception) {
                                integrityError = "Could not verify this record."
                            }
                        }
                    }
                }
                item {
                    SignOffCard(signoff ?: r.signoff, busy, actionError) {
                        scope.launch {
                            busy = true; actionError = null
                            try {
                                signoff = ApiClient.getApiService()
                                    .reviewPatientTherapySession(patientId, sessionId).signoff
                            } catch (e: Exception) {
                                actionError = "Sign-off failed."
                            } finally { busy = false }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun FactsCard(r: TherapySessionReport) {
    val s = r.session
    val items = listOfNotNull(
        s.name?.let { "Therapy" to it } ?: s.therapy?.let { "Therapy" to it.replace('_', ' ') },
        s.facilityName?.let { "Facility" to it },
        s.dialysisAccessType?.let { "Access" to it },
        s.attendingPhysician?.let { "Attending" to it },
        s.attendingNurse?.let { "Nurse" to it },
        s.durationMinutes?.let { "Duration" to "$it min" },
        s.preDialysisWeightKg?.let { "Pre weight" to String.format("%.1f kg", it) },
        s.postDialysisWeightKg?.let { "Post weight" to String.format("%.1f kg", it) },
        s.dryWeightKg?.let { "Dry weight" to String.format("%.1f kg", it) },
        s.fluidRemovedMl?.let { "Fluid removed" to String.format("%.0f mL", it) },
        s.bloodFlowRate?.let { "Blood flow" to String.format("%.0f mL/min", it) },
        s.preSystolicBp?.let { sys -> s.preDiastolicBp?.let { "Pre BP" to "$sys/$it" } },
        s.postSystolicBp?.let { sys -> s.postDiastolicBp?.let { "Post BP" to "$sys/$it" } },
        s.preHeartRate?.let { "Pre HR" to it.toString() },
        s.postHeartRate?.let { "Post HR" to it.toString() },
        s.patientTolerance?.let { "Tolerance" to it },
    )
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            items.chunked(2).forEach { pair ->
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    pair.forEach { (k, v) ->
                        Column(Modifier.weight(1f)) {
                            Text(k.uppercase(), style = MaterialTheme.typography.labelSmall,
                                 color = MaterialTheme.colorScheme.onSurfaceVariant)
                            Text(v, style = MaterialTheme.typography.bodyMedium,
                                 fontWeight = FontWeight.SemiBold)
                        }
                    }
                    if (pair.size == 1) Spacer(Modifier.weight(1f))
                }
            }
            s.complications?.takeIf { it.isNotBlank() }?.let {
                Text("Complications: $it", style = MaterialTheme.typography.labelMedium,
                     color = MaterialTheme.colorScheme.error)
            }
            s.adverseReactions?.takeIf { it.isNotBlank() }?.let {
                Text("Adverse reactions: $it", style = MaterialTheme.typography.labelMedium,
                     color = MaterialTheme.colorScheme.error)
            }
            s.patientNotes?.takeIf { it.isNotBlank() }?.let {
                Text("Patient notes: $it", style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

/**
 * The intradialytic curve, grouped by unit — BP, pulse and UF never share an
 * axis, and there is never a second y-axis.
 */
@Composable
private fun ReadingCharts(readings: List<IntradialyticReading>) {
    val usable = readings.filter { !it.readingTime.isNullOrBlank() }
    if (usable.size < 2) {
        Card(Modifier.fillMaxWidth()) {
            Text(
                if (usable.isEmpty()) "No intradialytic readings were recorded for this session."
                else "Only one intradialytic reading — not enough to plot a curve.",
                Modifier.padding(12.dp),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
        return
    }
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        ReadingChart("Blood pressure (mmHg)", listOf(
            "Systolic" to usable.map { it.systolicBp?.toDouble() },
            "Diastolic" to usable.map { it.diastolicBp?.toDouble() },
        ))
        ReadingChart("Pulse (bpm)", listOf("Pulse" to usable.map { it.pulse?.toDouble() }))
        ReadingChart("UF removed (mL)",
                     listOf("UF removed" to usable.map { it.ufVolumeRemoved?.toDouble() }))
    }
}

private val READING_PALETTE = listOf(Color(0xFF2A78D6), Color(0xFFEB6834), Color(0xFF1BAF7A))

@Composable
private fun ReadingChart(title: String, series: List<Pair<String, List<Double?>>>) {
    val present = series.filter { s -> s.second.any { it != null } }
    if (present.isEmpty()) return
    val gridColor = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.12f)
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Text(title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(8.dp))
            Canvas(Modifier.fillMaxWidth().height(170.dp)) {
                val all = present.flatMap { it.second.filterNotNull() }
                if (all.isEmpty()) return@Canvas
                val yMin = all.min(); val yMax = all.max()
                val range = if (yMax - yMin > 0.0001) yMax - yMin else 1.0
                for (i in 0..4) {
                    val y = size.height * i / 4f
                    drawLine(gridColor, Offset(0f, y), Offset(size.width, y), strokeWidth = 1f)
                }
                present.forEachIndexed { idx, (_, values) ->
                    val pts = values.filterNotNull()
                    if (pts.size < 2) return@forEachIndexed
                    val color = READING_PALETTE[idx % READING_PALETTE.size]
                    val stepX = size.width / (pts.size - 1).toFloat()
                    val path = Path()
                    pts.forEachIndexed { i, v ->
                        val x = stepX * i
                        val y = size.height - ((v - yMin) / range * size.height).toFloat()
                        if (i == 0) path.moveTo(x, y) else path.lineTo(x, y)
                        drawCircle(color, radius = 4f, center = Offset(x, y))
                    }
                    drawPath(path, color, style = Stroke(width = 2f))
                }
            }
            if (present.size > 1) {
                Spacer(Modifier.height(6.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    present.forEachIndexed { idx, (label, _) ->
                        Row(verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                            Box(Modifier.size(8.dp).background(
                                READING_PALETTE[idx % READING_PALETTE.size], RoundedCornerShape(4.dp)))
                            Text(label, style = MaterialTheme.typography.labelSmall)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun SignOffCard(
    so: SessionSignoff, busy: Boolean, actionError: String?, onSignOff: () -> Unit
) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("Sign-off", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
            // State what the PATIENT did, not just what the physician is about to
            // do: attesting to an unsigned record is a different act.
            Text("Patient signature: ${so.signedAt ?: "not signed"}",
                 style = MaterialTheme.typography.labelSmall,
                 color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text("Nurse countersignature: ${so.countersignedAt ?: "none"}",
                 style = MaterialTheme.typography.labelSmall,
                 color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text("Physician review: ${so.reviewedAt ?: "not reviewed"}",
                 style = MaterialTheme.typography.labelSmall,
                 color = MaterialTheme.colorScheme.onSurfaceVariant)
            so.payloadHash?.let {
                Text("Integrity hash: ${it.take(32)}…",
                     style = MaterialTheme.typography.labelSmall,
                     color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            actionError?.let {
                Text(it, style = MaterialTheme.typography.labelMedium,
                     color = MaterialTheme.colorScheme.error)
            }
            Spacer(Modifier.height(4.dp))
            if (so.isReviewed) {
                Chip("Reviewed and anchored", Color(0xFF1BAF7A))
            } else {
                Button(onClick = onSignOff, enabled = !busy) {
                    Text(if (busy) "Signing…" else "Sign off on this session")
                }
            }
        }
    }
}


/**
 * The intradialytic readings as a TABLE — the columns the patient's own expanded
 * card shows. Charts without the numbers underneath are a summary, not a record.
 */
@Composable
private fun ReadingsTable(readings: List<IntradialyticReading>) {
    val usable = readings.filter { !it.readingTime.isNullOrBlank() }
    if (usable.isEmpty()) return
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Text("Intradialytic Readings (${usable.size})",
                 style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(6.dp))
            // Wide content scrolls inside its own container, never the page.
            Column(Modifier.horizontalScroll(rememberScrollState())) {
                Row {
                    listOf("Time", "BP", "Pulse", "BFR", "UFR", "UF Vol", "Art P", "Ven P")
                        .forEach { h ->
                            Text(h, style = MaterialTheme.typography.labelSmall,
                                 fontWeight = FontWeight.Bold, modifier = Modifier.width(58.dp))
                        }
                }
                HorizontalDivider()
                usable.forEach { r ->
                    Row {
                        Cell(r.readingTime ?: "—")
                        Cell(if (r.systolicBp != null && r.diastolicBp != null)
                                 "${r.systolicBp}/${r.diastolicBp}" else "—")
                        Cell(r.pulse?.toString() ?: "—")
                        Cell(r.bloodFlowRate?.let { String.format("%.0f", it) } ?: "—")
                        Cell(r.ufRate?.let { String.format("%.0f", it) } ?: "—")
                        Cell(r.ufVolumeRemoved?.let { String.format("%.0f", it) } ?: "—")
                        Cell(r.arterialPressure?.let { String.format("%.0f", it) } ?: "—")
                        Cell(r.venousPressure?.let { String.format("%.0f", it) } ?: "—")
                    }
                }
            }
        }
    }
}

@Composable
private fun Cell(text: String) {
    Text(text, style = MaterialTheme.typography.labelSmall, modifier = Modifier.width(58.dp))
}

/** Comment. Signing a record you cannot annotate attests that you read it and
 *  nothing about what you concluded — so the note sits above the signature. */
@Composable
private fun NotesCard(
    notes: List<TherapySessionNote>, text: String, onText: (String) -> Unit,
    busy: Boolean, onAdd: () -> Unit,
) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("Clinical notes", style = MaterialTheme.typography.titleSmall,
                 fontWeight = FontWeight.Bold)
            if (notes.isEmpty()) {
                Text("No notes on this session yet.",
                     style = MaterialTheme.typography.bodySmall,
                     color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            notes.forEach { n ->
                Column {
                    Text("${n.authorRole ?: "clinician"} · ${n.noteType ?: "general"}",
                         style = MaterialTheme.typography.labelSmall,
                         color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(n.noteText, style = MaterialTheme.typography.bodyMedium)
                }
            }
            OutlinedTextField(
                value = text, onValueChange = onText,
                label = { Text("Add a clinical note…") },
                modifier = Modifier.fillMaxWidth(), minLines = 2,
            )
            Button(onClick = onAdd, enabled = !busy && text.isNotBlank()) {
                Text(if (busy) "Saving…" else "Add note")
            }
        }
    }
}

/** Tamper-evidence, recomputed rather than displayed. */
@Composable
private fun IntegrityCard(i: SessionIntegrity?, error: String?, onVerify: () -> Unit) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("Record integrity", style = MaterialTheme.typography.titleSmall,
                 fontWeight = FontWeight.Bold)
            error?.let {
                Text(it, style = MaterialTheme.typography.labelMedium,
                     color = MaterialTheme.colorScheme.error)
            }
            if (i == null) {
                Button(onClick = onVerify) { Text("Verify this record") }
            } else {
                Text(
                    when (i.payloadMatches) {
                        null -> "Signed content: never signed — nothing to check"
                        true -> "Signed content: unchanged since sign-off"
                        false -> "Signed content: DOES NOT MATCH the signed hash"
                    },
                    style = MaterialTheme.typography.labelSmall,
                    color = if (i.payloadMatches == false) MaterialTheme.colorScheme.error
                            else MaterialTheme.colorScheme.onSurfaceVariant)
                Text("Ledger: ${when (i.chainIntact) {
                        true -> "intact"; false -> "BROKEN"; null -> "no entries" }} · " +
                     "${i.anchoredCount} of ${i.trail.size} anchored",
                     style = MaterialTheme.typography.labelSmall,
                     color = if (i.chainIntact == false) MaterialTheme.colorScheme.error
                             else MaterialTheme.colorScheme.onSurfaceVariant)
                i.trail.forEach { t ->
                    Text("#${t.index} ${t.event ?: t.action} · " +
                         (if (t.anchored) "block ${t.blockNumber}" else "not anchored"),
                         style = MaterialTheme.typography.labelSmall,
                         color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }
}
