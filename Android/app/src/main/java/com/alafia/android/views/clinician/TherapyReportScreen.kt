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
import com.alafia.android.models.SessionSignoff
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

    if (sessions.isEmpty()) {
        Text("No therapy sessions in this period.",
             style = MaterialTheme.typography.bodySmall,
             color = MaterialTheme.colorScheme.onSurfaceVariant)
        return
    }

    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(Modifier.horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            StatTile("Sessions", sessions.size.toString(), Color(0xFF2A78D6))
            StatTile("Avg Pre Wt", fmt(avg(sessions, "pre_weight_kg"), 1, "kg"), Color(0xFF1BAF7A))
            StatTile("Avg Post Wt", fmt(avg(sessions, "post_weight_kg"), 1, "kg"), Color(0xFF1BAF7A))
            StatTile("Avg UF", fmt(avg(sessions, "fluid_removed_ml"), 0, "mL"), Color(0xFFEB6834))
            StatTile("Avg Duration", fmt(avg(sessions, "duration_minutes"), 0, "min"), Color(0xFF7C3AED))
        }
        Text("${sessions.size} sessions in the last $days days",
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
                if (r.notes.isNotEmpty()) {
                    item {
                        Card(Modifier.fillMaxWidth()) {
                            Column(Modifier.padding(12.dp)) {
                                Text("Clinical notes", style = MaterialTheme.typography.titleSmall,
                                     fontWeight = FontWeight.Bold)
                                r.notes.forEach { n ->
                                    Spacer(Modifier.height(6.dp))
                                    Text("${n.authorRole ?: "clinician"} · ${n.noteType ?: "general"}",
                                         style = MaterialTheme.typography.labelSmall,
                                         color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    Text(n.noteText, style = MaterialTheme.typography.bodyMedium)
                                }
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
    val usable = readings.filter { it.readingTime.isNotBlank() }
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
