@file:OptIn(ExperimentalMaterial3Api::class)

package com.alafia.android.views.hd
import com.alafia.android.util.ErrorUtil

import android.widget.Toast
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
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
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.alafia.android.api.ApiClient
import com.alafia.android.models.FlowsheetDefaults
import com.alafia.android.models.FlowsheetSignRequest
import com.alafia.android.models.FlowsheetStatus
import com.alafia.android.models.HDSummary
import com.alafia.android.models.TherapySession
import kotlinx.coroutines.launch
import java.time.LocalDate
import androidx.navigation.NavHostController
import androidx.compose.ui.res.stringResource
import com.alafia.android.R

@Composable
fun HemodialysisScreen(navController: NavHostController) {
    var sessions by remember { mutableStateOf<List<TherapySession>>(emptyList()) }
    var summary by remember { mutableStateOf<HDSummary?>(null) }
    var isLoading by remember { mutableStateOf(true) }
    var showForm by remember { mutableStateOf(false) }
    var editSession by remember { mutableStateOf<TherapySession?>(null) }
    var deleteTarget by remember { mutableStateOf<TherapySession?>(null) }
    var expandedId by remember { mutableStateOf<Int?>(null) }
    var periodDays by remember { mutableIntStateOf(90) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    fun loadData() {
        scope.launch {
            isLoading = true
            try {
                val all = ApiClient.getApiService().getTherapySessions(
                    therapyType = "HEMODIALYSIS", limit = 500
                )
                val cutoff = LocalDate.now().minusDays(periodDays.toLong())
                sessions = all.filter {
                    try { LocalDate.parse(it.scheduledDate.take(10)) >= cutoff } catch (_: Exception) { true }
                }
            } catch (e: Exception) {
                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
            }
            try { summary = ApiClient.getApiService().getHDSummary(periodDays) } catch (_: Exception) {}
            isLoading = false
        }
    }

    LaunchedEffect(periodDays) { loadData() }

    Scaffold(
        topBar = { TopAppBar(
                title = { Text(stringResource(R.string.hemodialysis)) },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = stringResource(R.string.back))
                    }
                }
            ) },
        floatingActionButton = {
            FloatingActionButton(onClick = { editSession = null; showForm = true }) {
                Icon(Icons.Default.Add, "Add")
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
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                // Summary
                summary?.let { s ->
                    if (s.totalSessions > 0) {
                        item {
                            Text(stringResource(R.string.summary), fontWeight = FontWeight.Bold, fontSize = 14.sp)
                            Spacer(Modifier.height(6.dp))
                            Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.fillMaxWidth()) {
                                StatCard(stringResource(R.string.sessions_3), "${s.totalSessions}", Color(0xFF1565C0), Modifier.weight(1f))
                                StatCard(stringResource(R.string.avg_pre), s.avgPreWeightKg?.let { "%.1f kg".format(it) } ?: "—", Color(0xFF4CAF50), Modifier.weight(1f))
                                StatCard(stringResource(R.string.avg_post), s.avgPostWeightKg?.let { "%.1f kg".format(it) } ?: "—", Color(0xFF4CAF50), Modifier.weight(1f))
                            }
                            Spacer(Modifier.height(6.dp))
                            Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.fillMaxWidth()) {
                                StatCard(stringResource(R.string.avg_uf), s.avgFluidRemovedMl?.let { "${it.toInt()} mL" } ?: "—", Color(0xFFFF9800), Modifier.weight(1f))
                                StatCard(stringResource(R.string.avg_dur), s.avgDurationMin?.let { "${it.toInt()} min" } ?: "—", Color(0xFF9C27B0), Modifier.weight(1f))
                                StatCard(stringResource(R.string.w_rdgs), s.sessionsWithReadings?.let { "$it" } ?: "—", Color(0xFF1565C0), Modifier.weight(1f))
                            }
                            Spacer(Modifier.height(12.dp))
                        }
                    }
                }

                // Period filter
                item {
                    val periods = listOf(30 to "30d", 90 to "90d", 180 to "180d", 365 to "1y", 3650 to "All")
                    SingleChoiceSegmentedButtonRow(modifier = Modifier.fillMaxWidth()) {
                        periods.forEachIndexed { idx, (days, label) ->
                            SegmentedButton(
                                selected = periodDays == days,
                                onClick = { periodDays = days },
                                shape = SegmentedButtonDefaults.itemShape(idx, periods.size)
                            ) { Text(label, fontSize = 12.sp) }
                        }
                    }
                    Spacer(Modifier.height(8.dp))
                }

                if (sessions.isEmpty()) {
                    item {
                        Box(Modifier.fillMaxWidth().padding(48.dp), contentAlignment = Alignment.Center) {
                            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                Icon(Icons.Default.MonitorHeart, null, Modifier.size(48.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
                                Spacer(Modifier.height(8.dp))
                                Text(stringResource(R.string.no_sessions_in_this_period), color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    }
                } else {
                    item {
                        Text(stringResource(R.string.sessions, sessions.size), fontWeight = FontWeight.Bold, fontSize = 14.sp,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }

                    items(sessions, key = { it.id }) { session ->
                        HDSessionCard(
                            session = session,
                            isExpanded = expandedId == session.id,
                            onToggle = { expandedId = if (expandedId == session.id) null else session.id },
                            onEdit = { editSession = session; showForm = true },
                            onDelete = { deleteTarget = session },
                            onReload = { loadData() }
                        )
                    }
                }
            }
        }
    }

    // Delete dialog
    deleteTarget?.let { session ->
        AlertDialog(
            onDismissRequest = { deleteTarget = null },
            title = { Text(stringResource(R.string.delete_session)) },
            text = { Text(stringResource(R.string.delete_this_hemodialysis_session)) },
            confirmButton = {
                TextButton(onClick = {
                    scope.launch {
                        try {
                            ApiClient.getApiService().deleteTherapySession(session.id)
                            deleteTarget = null; loadData()
                        } catch (e: Exception) {
                            Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                        }
                    }
                }) { Text(stringResource(R.string.delete), color = MaterialTheme.colorScheme.error) }
            },
            dismissButton = { TextButton(onClick = { deleteTarget = null }) { Text(stringResource(R.string.cancel)) } }
        )
    }

    // Add/Edit form
    if (showForm) {
        HDFormSheet(
            editing = editSession,
            onDismiss = { showForm = false; editSession = null },
            onSaved = { showForm = false; editSession = null; loadData() }
        )
    }
}

// MARK: - Session Card

@Composable
private fun HDSessionCard(
    session: TherapySession, isExpanded: Boolean,
    onToggle: () -> Unit, onEdit: () -> Unit, onDelete: () -> Unit,
    onReload: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val readings = session.intradialyticReadings ?: emptyList()

    Card(modifier = Modifier.fillMaxWidth(), onClick = onToggle) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text(session.scheduledDate.take(10), fontWeight = FontWeight.Bold, fontSize = 16.sp)
                        session.dayOfWeek?.takeIf { it.isNotEmpty() }?.let {
                            Text(it, fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                    session.durationMinutes?.let { Text(stringResource(R.string.min, it), fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                }
                Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    StatusChip(session.status)
                    session.flowsheetStatus?.takeIf { it.isNotEmpty() }?.let { FlowsheetStatusChip(it) }
                }
            }

            Spacer(Modifier.height(8.dp))
            HorizontalDivider()
            Spacer(Modifier.height(8.dp))

            Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                session.dialysisAccessType?.let { Pill(stringResource(R.string.access), it) }
                Pill(stringResource(R.string.pre_wt), session.preDialysisWeightKg?.let { "%.1f kg".format(it) } ?: "—")
                Pill(stringResource(R.string.post_wt), session.postDialysisWeightKg?.let { "%.1f kg".format(it) } ?: "—")
                session.fluidRemovedMl?.let { Pill("UF", "${it.toInt()} mL") }
            }

            if (session.preSystolicBp != null || session.postSystolicBp != null) {
                Spacer(Modifier.height(6.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                    fmtBP(session.preSystolicBp, session.preDiastolicBp)?.let { Pill(stringResource(R.string.pre_bp_2), it) }
                    fmtBP(session.postSystolicBp, session.postDiastolicBp)?.let { Pill(stringResource(R.string.post_bp_2), it) }
                    session.preHeartRate?.let { Pill("HR", "$it") }
                }
            }

            if (readings.isNotEmpty()) {
                Spacer(Modifier.height(4.dp))
                Text(stringResource(R.string.intradialytic_readings_2, readings.size), fontSize = 11.sp, fontWeight = FontWeight.Bold, color = Color(0xFF1565C0))
            }

            AnimatedVisibility(isExpanded) {
                Column(Modifier.padding(top = 8.dp)) {
                    // Standing BP
                    if (session.preStandingSystolicBp != null || session.postStandingSystolicBp != null) {
                        Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                            fmtBP(session.preStandingSystolicBp, session.preStandingDiastolicBp)?.let { Pill(stringResource(R.string.pre_stand), it) }
                            fmtBP(session.postStandingSystolicBp, session.postStandingDiastolicBp)?.let { Pill(stringResource(R.string.post_stand), it) }
                        }
                        Spacer(Modifier.height(6.dp))
                    }

                    // Print or save this session as PDF. The document is
                    // rendered server-side, so it is the same one the clinician
                    // prints — and a failure is shown rather than swallowed.
                    val printScope = rememberCoroutineScope()
                    val printContext = LocalContext.current
                    var printError by remember { mutableStateOf<String?>(null) }
                    TextButton(onClick = {
                        printScope.launch {
                            printError = TherapyReportPrinter.print(printContext, session.id)
                        }
                    }) { Text(stringResource(R.string.print_save_as_pdf)) }
                    printError?.let {
                        Text(it, color = MaterialTheme.colorScheme.error,
                             style = MaterialTheme.typography.bodySmall)
                    }

                    // Flow & prescription
                    Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                        session.bloodFlowRate?.let { Pill("BFR", "${it.toInt()}") }
                        session.dialysateFlowRate?.let { Pill("DFR", "${it.toInt()}") }
                        session.dialysateVolumeLiters?.let { Pill(stringResource(R.string.vol), "$it L") }
                        session.needleGauge?.let { Pill(stringResource(R.string.gauge), it) }
                    }

                    // Totals
                    if (session.totalDialysateLiters != null || session.totalUfLiters != null) {
                        Spacer(Modifier.height(6.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                            session.totalDialysateLiters?.let { Pill(stringResource(R.string.tot_dial), "$it L") }
                            session.totalUfLiters?.let { Pill(stringResource(R.string.tot_uf), "$it L") }
                            session.totalBloodVolumeProcessed?.let { Pill(stringResource(R.string.blood_vol), "$it L") }
                        }
                    }

                    // Intradialytic readings table
                    if (readings.isNotEmpty()) {
                        Spacer(Modifier.height(8.dp))
                        Text(stringResource(R.string.intradialytic_readings_3), fontWeight = FontWeight.Bold, fontSize = 12.sp, color = Color(0xFF1565C0))
                        Spacer(Modifier.height(4.dp))
                        Surface(color = Color(0xFF1565C0).copy(alpha = 0.05f), shape = MaterialTheme.shapes.small) {
                            Column(Modifier.padding(8.dp)) {
                                readings.forEachIndexed { idx, r ->
                                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                                        Text(r.readingTime?.take(5) ?: "—", fontSize = 11.sp, fontWeight = FontWeight.Bold, modifier = Modifier.width(40.dp))
                                        fmtBP(r.systolicBp, r.diastolicBp)?.let { Text("BP $it", fontSize = 11.sp, modifier = Modifier.width(64.dp)) }
                                        r.pulse?.let { Text("P $it", fontSize = 11.sp, modifier = Modifier.width(32.dp)) }
                                        r.bloodFlowRate?.let { Text("BFR ${it.toInt()}", fontSize = 11.sp) }
                                        r.ufVolumeRemoved?.let { Text("UF ${it.toInt()}", fontSize = 11.sp) }
                                    }
                                    if (idx < readings.size - 1) HorizontalDivider(Modifier.padding(vertical = 2.dp))
                                }
                            }
                        }
                    }

                    // Notes
                    session.sideEffects?.takeIf { it.isNotEmpty() }?.let {
                        Spacer(Modifier.height(6.dp))
                        Text("⚠️ $it", fontSize = 12.sp, color = Color(0xFFF44336))
                    }
                    session.clinicalNotes?.takeIf { it.isNotEmpty() }?.let {
                        Spacer(Modifier.height(4.dp))
                        Text(it, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 3)
                    }
                    session.facilityName?.takeIf { it.isNotEmpty() }?.let {
                        Text("📍 $it", fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }

                    Spacer(Modifier.height(8.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(onClick = onEdit, modifier = Modifier.height(32.dp)) {
                            Icon(Icons.Default.Edit, null, Modifier.size(14.dp))
                            Spacer(Modifier.width(4.dp))
                            Text(stringResource(R.string.edit), fontSize = 12.sp)
                        }
                        OutlinedButton(onClick = onDelete, modifier = Modifier.height(32.dp),
                            colors = ButtonDefaults.outlinedButtonColors(contentColor = MaterialTheme.colorScheme.error)) {
                            Icon(Icons.Default.Delete, null, Modifier.size(14.dp))
                            Spacer(Modifier.width(4.dp))
                            Text(stringResource(R.string.delete), fontSize = 12.sp)
                        }
                    }

                    // ── Flowsheet Lifecycle Actions ──────────────────────────
                    val fsStatus = FlowsheetStatus.fromString(session.flowsheetStatus)
                    Spacer(Modifier.height(10.dp))
                    HorizontalDivider()
                    Spacer(Modifier.height(6.dp))
                    Text(stringResource(R.string.flowsheet), fontWeight = FontWeight.Bold, fontSize = 12.sp, color = MaterialTheme.colorScheme.primary)
                    Spacer(Modifier.height(4.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.horizontalScroll(rememberScrollState())) {
                        if (fsStatus == null || fsStatus == FlowsheetStatus.DRAFT) {
                            FilledTonalButton(onClick = {
                                scope.launch {
                                    try { ApiClient.getApiService().submitFlowsheet(session.id); onReload() }
                                    catch (e: Exception) { Toast.makeText(context, "Submit failed: ${e.message}", Toast.LENGTH_SHORT).show() }
                                }
                            }, modifier = Modifier.height(30.dp)) { Text(stringResource(R.string.submit), fontSize = 11.sp) }
                        }
                        if (fsStatus == FlowsheetStatus.SUBMITTED) {
                            FilledTonalButton(onClick = {
                                scope.launch {
                                    try { ApiClient.getApiService().signFlowsheet(session.id, FlowsheetSignRequest("")); onReload() }
                                    catch (e: Exception) { Toast.makeText(context, "Sign failed: ${e.message}", Toast.LENGTH_SHORT).show() }
                                }
                            }, modifier = Modifier.height(30.dp)) { Text(stringResource(R.string.sign), fontSize = 11.sp) }
                        }
                        if (fsStatus == FlowsheetStatus.SIGNED) {
                            FilledTonalButton(onClick = {
                                scope.launch {
                                    try { ApiClient.getApiService().countersignFlowsheet(session.id, FlowsheetSignRequest("")); onReload() }
                                    catch (e: Exception) { Toast.makeText(context, "Countersign failed: ${e.message}", Toast.LENGTH_SHORT).show() }
                                }
                            }, modifier = Modifier.height(30.dp)) { Text(stringResource(R.string.countersign), fontSize = 11.sp) }
                        }
                        if (fsStatus == FlowsheetStatus.COUNTERSIGNED) {
                            FilledTonalButton(onClick = {
                                scope.launch {
                                    try { ApiClient.getApiService().reviewFlowsheet(session.id); onReload() }
                                    catch (e: Exception) { Toast.makeText(context, "Review failed: ${e.message}", Toast.LENGTH_SHORT).show() }
                                }
                            }, modifier = Modifier.height(30.dp)) { Text(stringResource(R.string.review), fontSize = 11.sp) }
                        }
                        if (fsStatus == FlowsheetStatus.REVIEWED) {
                            FilledTonalButton(onClick = {
                                scope.launch {
                                    try { ApiClient.getApiService().lockFlowsheet(session.id); onReload() }
                                    catch (e: Exception) { Toast.makeText(context, "Lock failed: ${e.message}", Toast.LENGTH_SHORT).show() }
                                }
                            }, modifier = Modifier.height(30.dp)) { Text(stringResource(R.string.lock), fontSize = 11.sp) }
                        }
                        if (fsStatus == FlowsheetStatus.LOCKED) {
                            Text(stringResource(R.string.locked), fontSize = 11.sp, fontWeight = FontWeight.Bold, color = Color(0xFF4CAF50))
                        }
                    }

                    // ── Clinical Notes ───────────────────────────────────────
                    session.clinicalNotesList?.takeIf { it.isNotEmpty() }?.let { notes ->
                        Spacer(Modifier.height(8.dp))
                        Text(stringResource(R.string.clinical_notes_3, notes.size), fontWeight = FontWeight.Bold, fontSize = 12.sp, color = Color(0xFF1565C0))
                        Spacer(Modifier.height(4.dp))
                        notes.forEach { note ->
                            Surface(color = Color(0xFF1565C0).copy(alpha = 0.05f), shape = MaterialTheme.shapes.small,
                                modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
                                Column(Modifier.padding(8.dp)) {
                                    Row {
                                        Text(note.noteType, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                                        Spacer(Modifier.weight(1f))
                                        Text(com.alafia.android.util.AppDate.dateTime(note.createdAt), fontSize = 10.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    }
                                    Text(note.noteText, fontSize = 12.sp, maxLines = 3)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

// MARK: - Add/Edit Form

@Composable
private fun HDFormSheet(editing: TherapySession?, onDismiss: () -> Unit, onSaved: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var saving by remember { mutableStateOf(false) }

    // Form fields
    var date by remember { mutableStateOf(editing?.scheduledDate?.take(10) ?: LocalDate.now().toString()) }
    var status by remember { mutableStateOf(editing?.status ?: "COMPLETED") }
    var dayOfWeek by remember { mutableStateOf(editing?.dayOfWeek ?: "") }
    var accessType by remember { mutableStateOf(editing?.dialysisAccessType ?: "AV Fistula") }
    var needleGauge by remember { mutableStateOf(editing?.needleGauge ?: "15G") }
    var needleLength by remember { mutableStateOf(editing?.needleLength?.toString() ?: "") }
    var buttonhole by remember { mutableStateOf(editing?.buttonholeTechnique ?: false) }
    // Weights
    var dryWeight by remember { mutableStateOf(editing?.dryWeightKg?.toString() ?: "") }
    var prevPostWeight by remember { mutableStateOf(editing?.previousPostWeightKg?.toString() ?: "") }
    var preWeight by remember { mutableStateOf(editing?.preDialysisWeightKg?.toString() ?: "") }
    var postWeight by remember { mutableStateOf(editing?.postDialysisWeightKg?.toString() ?: "") }
    var fluidRemoved by remember { mutableStateOf(editing?.fluidRemovedMl?.toInt()?.toString() ?: "") }
    var fluidToRemove by remember { mutableStateOf(editing?.fluidToRemoveKg?.toString() ?: "") }
    // Prescription
    var bfr by remember { mutableStateOf(editing?.bloodFlowRate?.toInt()?.toString() ?: "") }
    var dfr by remember { mutableStateOf(editing?.dialysateFlowRate?.toInt()?.toString() ?: "") }
    var duration by remember { mutableStateOf(editing?.durationMinutes?.toString() ?: "") }
    // Wall clocks in the form, datetimes on the wire. Two treatments in one day
    // are told apart by these, so they are what makes a same-day session
    // identifiable rather than a suspected duplicate.
    var startTime by remember { mutableStateOf(clockOf(editing?.actualStartTime)) }
    var endTime by remember { mutableStateOf(clockOf(editing?.actualEndTime)) }
    var dialVol by remember { mutableStateOf(editing?.dialysateVolumeLiters?.toString() ?: "") }
    var dialLact by remember { mutableStateOf(editing?.dialysateLactateMeq?.toString() ?: "") }
    var dialK by remember { mutableStateOf(editing?.dialysatePotassiumMeq?.toString() ?: "") }
    var sakNum by remember { mutableStateOf(editing?.sakNumber?.toString() ?: "") }
    var o2 by remember { mutableStateOf(editing?.oxygenSaturation?.toString() ?: "") }
    // Pre vitals
    var preSys by remember { mutableStateOf(editing?.preSystolicBp?.toString() ?: "") }
    var preDia by remember { mutableStateOf(editing?.preDiastolicBp?.toString() ?: "") }
    var preHr by remember { mutableStateOf(editing?.preHeartRate?.toString() ?: "") }
    var preTemp by remember { mutableStateOf(editing?.preTemperature?.toString() ?: "") }
    var preStSys by remember { mutableStateOf(editing?.preStandingSystolicBp?.toString() ?: "") }
    var preStDia by remember { mutableStateOf(editing?.preStandingDiastolicBp?.toString() ?: "") }
    var preStHr by remember { mutableStateOf(editing?.preStandingHeartRate?.toString() ?: "") }
    // Post vitals
    var postSys by remember { mutableStateOf(editing?.postSystolicBp?.toString() ?: "") }
    var postDia by remember { mutableStateOf(editing?.postDiastolicBp?.toString() ?: "") }
    var postHr by remember { mutableStateOf(editing?.postHeartRate?.toString() ?: "") }
    var postTemp by remember { mutableStateOf(editing?.postTemperature?.toString() ?: "") }
    var postStSys by remember { mutableStateOf(editing?.postStandingSystolicBp?.toString() ?: "") }
    var postStDia by remember { mutableStateOf(editing?.postStandingDiastolicBp?.toString() ?: "") }
    var postStHr by remember { mutableStateOf(editing?.postStandingHeartRate?.toString() ?: "") }
    // Pre-treatment symptoms
    var preSob by remember { mutableStateOf(editing?.preShortnessOfBreath ?: false) }
    var preSwell by remember { mutableStateOf(editing?.preSwelling ?: false) }
    var preMobility by remember { mutableStateOf(editing?.preChangeInMobility ?: false) }
    var preDigest by remember { mutableStateOf(editing?.preDigestionProblems ?: false) }
    var preHosp by remember { mutableStateOf(editing?.preHospErSinceLast ?: false) }
    // Nullable, and NOT defaulted to true. A toggle that starts on "present"
    // records a reassuring normal finding for every session nobody assessed —
    // and ABSENT, the urgent one, was indistinguishable from an untouched
    // switch. The column has always been a nullable boolean; the UI just never
    // offered the third state.
    var thrill by remember { mutableStateOf(editing?.accessThrillBruit) }
    var redness by remember { mutableStateOf(editing?.accessRednessDrainage ?: false) }
    // Equipment
    var cartLot by remember { mutableStateOf(editing?.cartridgeLot ?: "") }
    var sakLot by remember { mutableStateOf(editing?.sakLot ?: "") }
    var cycler by remember { mutableStateOf(editing?.cyclerNumber ?: "") }
    var warmer by remember { mutableStateOf(editing?.warmerSerial ?: "") }
    // Post-treatment totals
    var totDial by remember { mutableStateOf(editing?.totalDialysateLiters?.toString() ?: "") }
    var totUf by remember { mutableStateOf(editing?.totalUfLiters?.toString() ?: "") }
    var salineAdded by remember { mutableStateOf(editing?.salineAddedMl?.toString() ?: "") }
    var machineTime by remember { mutableStateOf(editing?.machineTotalTimeMinutes?.toString() ?: "") }
    var totBlood by remember { mutableStateOf(editing?.totalBloodVolumeProcessed?.toString() ?: "") }
    var dialAppear by remember { mutableStateOf(editing?.dialyzerAppearance ?: "") }
    var bleedStop by remember { mutableStateOf(editing?.postBleedingStopTime ?: "") }
    var postBruise by remember { mutableStateOf(editing?.postBruising ?: false) }
    var postInfilt by remember { mutableStateOf(editing?.postInfiltration ?: false) }
    var postSob by remember { mutableStateOf(editing?.postShortnessOfBreath ?: false) }
    var postSwell by remember { mutableStateOf(editing?.postSwelling ?: false) }
    var postDigest by remember { mutableStateOf(editing?.postDigestionProblems ?: false) }
    var postThrill by remember { mutableStateOf(editing?.postAccessThrillBruit) }
    // Machine maintenance
    var purPak by remember { mutableStateOf(editing?.purificationPakChange ?: false) }
    var airFilter by remember { mutableStateOf(editing?.airFilterCleaned ?: false) }
    var wasteBleach by remember { mutableStateOf(editing?.wasteLineBleachDisinfection ?: false) }
    var alarmTest by remember { mutableStateOf(editing?.alarmTestCompleted ?: false) }
    var sakUse by remember { mutableStateOf(editing?.sakUseNumber?.toString() ?: "") }
    var chloramine by remember { mutableStateOf(editing?.totalChloramineLevel?.toString() ?: "") }
    var labTubes by remember { mutableStateOf(editing?.labTubesDrawn ?: "") }
    // Staff & notes
    var facility by remember { mutableStateOf(editing?.facilityName ?: "") }
    var physician by remember { mutableStateOf(editing?.attendingPhysician ?: "") }
    var rnReviewer by remember { mutableStateOf(editing?.rnReviewer ?: "") }
    var sideEffects by remember { mutableStateOf(editing?.sideEffects ?: "") }
    var drugsAdministered by remember { mutableStateOf(editing?.drugsAdministered ?: "") }
    var clinicalNotes by remember { mutableStateOf(editing?.clinicalNotes ?: "") }
    var patientNotes by remember { mutableStateOf(editing?.patientNotes ?: "") }

    // Intradialytic readings. Kept as their own list rather than folded into the
    // session body: they are separate rows with their own ids, and it is those
    // ids that decide PUT vs POST when the grid is saved.
    val readings = remember { mutableStateListOf<EditableReading>() }
    val removedReadingIds = remember { mutableStateListOf<Int>() }
    var readingsError by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(editing?.id) {
        readings.clear(); removedReadingIds.clear(); readingsError = null
        val id = editing?.id ?: return@LaunchedEffect
        try {
            ApiClient.getApiService().getIntradialyticReadings(id)
                .sortedBy { it.readingTime ?: "" }
                .forEach { readings.add(EditableReading.from(it)) }
        } catch (e: Exception) {
            // An error is not an empty state: showing a blank grid here would
            // invite the user to re-enter readings that already exist, and the
            // save would then duplicate the whole flowsheet.
            readingsError = ErrorUtil.userMessage(e)
        }
    }

    val accessTypes = listOf("AV Fistula", "AV Graft", "Central Catheter", "Buttonhole")
    // A catheter has no needles and no bruit. A GRAFT is cannulated like a
    // fistula, so needle fields still apply to it. Mirrors classify_access in
    // app/services/flowsheet_defaults.py.
    val isCatheter = isCatheterAccess(accessType)

    // Pre-fill from the last treatment, but only for a NEW session — an edit
    // must show what was actually recorded, not last time's settings.
    var defaults by remember { mutableStateOf<FlowsheetDefaults?>(null) }
    LaunchedEffect(editing) {
        if (editing != null) return@LaunchedEffect
        // A failure here means an empty form, never a blocked one.
        val d = try { ApiClient.getApiService().getFlowsheetDefaults() } catch (_: Exception) { null }
        defaults = d ?: return@LaunchedEffect
        d.targetWeightKg?.let { if (dryWeight.isBlank()) dryWeight = it.toString() }
        d.carriedForward?.let { c ->
            c.dialysisAccessType?.takeIf { it.isNotBlank() }?.let { accessType = it }
            c.attendingPhysician?.let { if (physician.isBlank()) physician = it }
            c.dialysateVolumeLiters?.let { if (dialVol.isBlank()) dialVol = it.toString() }
            c.dialysatePotassiumMeq?.let { if (dialK.isBlank()) dialK = it.toString() }
            c.dialysateLactateMeq?.let { if (dialLact.isBlank()) dialLact = it.toString() }
            c.sakLot?.let { if (sakLot.isBlank()) sakLot = it }
            c.sakNumber?.let { if (sakNum.isBlank()) sakNum = it.toString() }

            // Decoded and then dropped on the floor until now — the patient
            // re-typed a cycler and warmer serial the record already held, and
            // a previous weight it could compute.
            c.previousPostWeightKg?.let { if (prevPostWeight.isBlank()) prevPostWeight = it.toString() }
            c.cartridgeLot?.let { if (cartLot.isBlank()) cartLot = it }
            c.cyclerNumber?.let { if (cycler.isBlank()) cycler = it }
            c.warmerSerial?.let { if (warmer.isBlank()) warmer = it }
            c.bloodFlowRate?.let { if (bfr.isBlank()) bfr = it.toInt().toString() }
        }
    }
    val statuses = listOf("SCHEDULED", "IN_PROGRESS", "COMPLETED", "CANCELLED")
    val gauges = listOf("15G", "16G", "17G")
    val days = listOf("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp, vertical = 8.dp)
        ) {
            Text(
                if (editing != null) stringResource(R.string.edit_hd_session) else stringResource(R.string.new_hd_session),
                style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold
            )
            Spacer(Modifier.height(16.dp))

            // Session Info
            SectionHeader(stringResource(R.string.session_info))
            OutlinedTextField(date, { date = it }, label = { Text(stringResource(R.string.date_yyyy_mm_dd)) }, modifier = Modifier.fillMaxWidth())
            Spacer(Modifier.height(6.dp))
            Text(stringResource(R.string.status), fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp), modifier = Modifier.fillMaxWidth()) {
                statuses.forEach { s -> FilterChip(status == s, { status = s }, label = { Text(s.replace("_", " "), fontSize = 11.sp) }) }
            }
            Spacer(Modifier.height(6.dp))
            Text(stringResource(R.string.day_of_week), fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp), modifier = Modifier.fillMaxWidth()) {
                days.take(4).forEach { d -> FilterChip(dayOfWeek == d, { dayOfWeek = d }, label = { Text(d.take(3), fontSize = 11.sp) }) }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                days.drop(4).forEach { d -> FilterChip(dayOfWeek == d, { dayOfWeek = d }, label = { Text(d.take(3), fontSize = 11.sp) }) }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Box(Modifier.weight(1f)) {
                    F(startTime, {
                        startTime = it
                        minutesBetween(it, endTime)?.let { m -> duration = m.toString() }
                    }, stringResource(R.string.start_time_hh_mm))
                }
                Box(Modifier.weight(1f)) {
                    F(endTime, {
                        endTime = it
                        minutesBetween(startTime, it)?.let { m -> duration = m.toString() }
                    }, stringResource(R.string.end_time_hh_mm))
                }
            }
            F(duration, { duration = it }, stringResource(R.string.duration_min_2))

            defaults?.carriedFromDate?.let { from ->
                Text(
                    stringResource(R.string.pre_filled_from_your_treatment_on_change, from),
                    fontSize = 11.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                defaults?.notes?.forEach { note ->
                    Text(note, fontSize = 11.sp, color = Color(0xFFB45309))
                }
            }

            // Vascular Access
            SectionHeader(stringResource(R.string.vascular_access))
            Text(stringResource(R.string.access_type), fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                accessTypes.forEach { a -> FilterChip(accessType == a, { accessType = a }, label = { Text(a, fontSize = 11.sp) }) }
            }
            if (isCatheter) {
                Text(
                    "Needle and bruit fields are switched off for a catheter. " +
                        "Change the access type above to turn them back on.",
                    fontSize = 11.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            Text(stringResource(R.string.needle_gauge), fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                gauges.forEach { g ->
                    FilterChip(
                        needleGauge == g, { needleGauge = g },
                        label = { Text(g, fontSize = 11.sp) },
                        enabled = !isCatheter
                    )
                }
            }
            F(needleLength, { needleLength = it }, stringResource(R.string.needle_length_mm), enabled = !isCatheter)
            ToggleRow(stringResource(R.string.buttonhole_technique), buttonhole, enabled = !isCatheter) { buttonhole = it }

            // Weights
            SectionHeader(stringResource(R.string.weights_kg))
            Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp)) {
                F(dryWeight, { dryWeight = it }, stringResource(R.string.dry), Modifier.weight(1f))
                F(prevPostWeight, { prevPostWeight = it }, stringResource(R.string.prev_post), Modifier.weight(1f))
            }
            Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp)) {
                F(preWeight, { preWeight = it }, stringResource(R.string.pre), Modifier.weight(1f))
                F(postWeight, { postWeight = it }, stringResource(R.string.post), Modifier.weight(1f))
            }
            Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp)) {
                F(fluidToRemove, { fluidToRemove = it }, stringResource(R.string.to_remove_kg), Modifier.weight(1f))
                F(fluidRemoved, { fluidRemoved = it }, stringResource(R.string.removed_ml), Modifier.weight(1f))
            }

            // Dialysate Prescription
            SectionHeader(stringResource(R.string.dialysate_prescription))
            Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp)) {
                F(bfr, { bfr = it }, stringResource(R.string.bfr_ml_min), Modifier.weight(1f))
                F(dfr, { dfr = it }, stringResource(R.string.dfr_ml_min), Modifier.weight(1f))
            }
            Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp)) {
                F(dialVol, { dialVol = it }, stringResource(R.string.volume_l), Modifier.weight(1f))
                F(sakNum, { sakNum = it }, "SAK #", Modifier.weight(1f))
            }
            Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp)) {
                F(dialLact, { dialLact = it }, stringResource(R.string.lactate_meq), Modifier.weight(1f))
                F(dialK, { dialK = it }, stringResource(R.string.k_meq), Modifier.weight(1f))
            }
            F(o2, { o2 = it }, stringResource(R.string.spo))

            // Pre-Treatment Vitals
            SectionHeader(stringResource(R.string.pre_treatment_vitals))
            Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp)) {
                F(preSys, { preSys = it }, stringResource(R.string.sit_sys), Modifier.weight(1f))
                F(preDia, { preDia = it }, stringResource(R.string.sit_dia), Modifier.weight(1f))
                F(preHr, { preHr = it }, "HR", Modifier.weight(1f))
                F(preTemp, { preTemp = it }, stringResource(R.string.temp), Modifier.weight(1f))
            }
            Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp)) {
                F(preStSys, { preStSys = it }, stringResource(R.string.stand_sys), Modifier.weight(1f))
                F(preStDia, { preStDia = it }, stringResource(R.string.stand_dia), Modifier.weight(1f))
                F(preStHr, { preStHr = it }, stringResource(R.string.stand_hr), Modifier.weight(1f))
            }

            // Pre-Treatment Assessment
            SectionHeader(stringResource(R.string.pre_treatment_assessment))
            ToggleRow(stringResource(R.string.shortness_of_breath), preSob) { preSob = it }
            ToggleRow(stringResource(R.string.swelling_edema), preSwell) { preSwell = it }
            ToggleRow(stringResource(R.string.change_in_mobility), preMobility) { preMobility = it }
            ToggleRow(stringResource(R.string.digestion_problems), preDigest) { preDigest = it }
            ToggleRow(stringResource(R.string.hospital_er_since_last), preHosp) { preHosp = it }
            ThrillRow(thrill) { thrill = it }
            ToggleRow(stringResource(R.string.access_redness_drainage), redness) { redness = it }

            // Post-Treatment Vitals
            SectionHeader(stringResource(R.string.post_treatment_vitals))
            Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp)) {
                F(postSys, { postSys = it }, stringResource(R.string.sit_sys), Modifier.weight(1f))
                F(postDia, { postDia = it }, stringResource(R.string.sit_dia), Modifier.weight(1f))
                F(postHr, { postHr = it }, "HR", Modifier.weight(1f))
                F(postTemp, { postTemp = it }, stringResource(R.string.temp), Modifier.weight(1f))
            }
            Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp)) {
                F(postStSys, { postStSys = it }, stringResource(R.string.stand_sys), Modifier.weight(1f))
                F(postStDia, { postStDia = it }, stringResource(R.string.stand_dia), Modifier.weight(1f))
                F(postStHr, { postStHr = it }, stringResource(R.string.stand_hr), Modifier.weight(1f))
            }

            // Post-Treatment Totals
            SectionHeader(stringResource(R.string.post_treatment_totals))
            Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp)) {
                F(totDial, { totDial = it }, stringResource(R.string.total_dial_l), Modifier.weight(1f))
                F(totUf, { totUf = it }, stringResource(R.string.total_uf_l_machine), Modifier.weight(1f))
            }
            Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp)) {
                F(totBlood, { totBlood = it }, stringResource(R.string.blood_vol_l), Modifier.weight(1f))
                F(dialAppear, { dialAppear = it }, stringResource(R.string.dialyzer), Modifier.weight(1f))
            }
            F(bleedStop, { bleedStop = it }, stringResource(R.string.bleed_stop_time))
            ToggleRow(stringResource(R.string.bruising), postBruise) { postBruise = it }
            ToggleRow(stringResource(R.string.infiltration), postInfilt) { postInfilt = it }
            ToggleRow("SOB", postSob) { postSob = it }
            ToggleRow(stringResource(R.string.swelling), postSwell) { postSwell = it }
            ToggleRow(stringResource(R.string.gi_issues), postDigest) { postDigest = it }
            ThrillRow(postThrill) { postThrill = it }

            // Equipment
            SectionHeader(stringResource(R.string.equipment))
            Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp)) {
                F(cartLot, { cartLot = it }, stringResource(R.string.cartridge_lot), Modifier.weight(1f))
                F(sakLot, { sakLot = it }, stringResource(R.string.sak_lot), Modifier.weight(1f))
            }
            Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp)) {
                F(cycler, { cycler = it }, stringResource(R.string.cycler), Modifier.weight(1f))
                F(warmer, { warmer = it }, stringResource(R.string.warmer_serial), Modifier.weight(1f))
            }

            // Machine Maintenance
            SectionHeader(stringResource(R.string.machine_maintenance))
            ToggleRow(stringResource(R.string.purification_pak_change), purPak) { purPak = it }
            ToggleRow(stringResource(R.string.air_filter_cleaned), airFilter) { airFilter = it }
            ToggleRow(stringResource(R.string.waste_line_bleach), wasteBleach) { wasteBleach = it }
            ToggleRow(stringResource(R.string.alarm_test_complete), alarmTest) { alarmTest = it }
            Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp)) {
                F(sakUse, { sakUse = it }, stringResource(R.string.sak_use), Modifier.weight(1f))
                F(chloramine, { chloramine = it }, stringResource(R.string.chloramine_ppm), Modifier.weight(1f))
            }
            F(labTubes, { labTubes = it }, stringResource(R.string.lab_tubes_drawn))

            // Saline is volume put BACK, so the machine's gross UF overstates
            // what came off until it is deducted. The scale-derived
            // fluid_removed_ml is already net — the patient was weighed after
            // the saline went in — so the deduction belongs on the UF figure.
            //
            // The machine's total time is its own reading and excludes alarms
            // and pauses; the summary's duration is end - start and is a
            // different, larger number. Kt/V follows time actually dialysing.
            Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp)) {
                F(salineAdded, { salineAdded = it }, stringResource(R.string.saline_added_ml), Modifier.weight(1f))
                MachineTimeField(machineTime) { machineTime = it }
            }

            // Facility & Staff
            SectionHeader(stringResource(R.string.facility_staff))
            F(facility, { facility = it }, stringResource(R.string.facility))
            F(physician, { physician = it }, stringResource(R.string.physician))
            F(rnReviewer, { rnReviewer = it }, stringResource(R.string.rn_reviewer))

            // Notes
            SectionHeader(stringResource(R.string.notes))
            // This screen had no drugs field at all; a decade of Epogene, Venofer
            // and Doxercalciferol arrived only by import (§3aa).
            DrugsAdministeredEditor(value = drugsAdministered, onChange = { drugsAdministered = it })
            Spacer(Modifier.height(8.dp))
            OutlinedTextField(sideEffects, { sideEffects = it }, label = { Text(stringResource(R.string.side_effects_2)) }, modifier = Modifier.fillMaxWidth(), minLines = 2)
            Spacer(Modifier.height(4.dp))
            OutlinedTextField(clinicalNotes, { clinicalNotes = it }, label = { Text(stringResource(R.string.clinical_notes)) }, modifier = Modifier.fillMaxWidth(), minLines = 2)
            Spacer(Modifier.height(4.dp))
            OutlinedTextField(patientNotes, { patientNotes = it }, label = { Text(stringResource(R.string.patient_notes)) }, modifier = Modifier.fillMaxWidth(), minLines = 2)

            // Intradialytic readings
            SectionHeader(stringResource(R.string.intradialytic_readings_3))
            val loadFailed = readingsError
            if (loadFailed != null) {
                Text(
                    "Could not load existing readings: $loadFailed. " +
                        "Editing them here is disabled so the saved ones are not duplicated.",
                    fontSize = 12.sp, color = MaterialTheme.colorScheme.error,
                )
            } else {
                IntradialyticEditor(readings, removedReadingIds)
            }

            Spacer(Modifier.height(16.dp))

            Button(
                onClick = {
                    scope.launch {
                        saving = true
                        try {
                            val body = mutableMapOf<String, Any?>(
                                // NOT a hardcoded condition id. 14 exists for no
                                // user in these databases; the web form shipped it
                                // and the API's ownership check rejected every save
                                // with "Chronic condition not found". Omitting it is
                                // valid — the endpoint only verifies an id when sent.
                                "therapy_type" to "HEMODIALYSIS",
                                "scheduled_date" to date, "status" to status,
                                "dialysis_access_type" to accessType,
                            )
                            fun s(k: String, v: String) { if (v.isNotEmpty()) body[k] = v }
                            fun d(k: String, v: String) { v.toDoubleOrNull()?.let { body[k] = it } }
                            fun i(k: String, v: String) { v.toIntOrNull()?.let { body[k] = it } }
                            fun b(k: String, v: Boolean) { body[k] = v }

                            s("day_of_week", dayOfWeek); s("needle_gauge", needleGauge)
                            d("needle_length", needleLength); b("buttonhole_technique", buttonhole)
                            d("dry_weight_kg", dryWeight); d("previous_post_weight_kg", prevPostWeight)
                            d("pre_dialysis_weight_kg", preWeight); d("post_dialysis_weight_kg", postWeight)
                            d("fluid_removed_ml", fluidRemoved); d("fluid_to_remove_kg", fluidToRemove)
                            d("blood_flow_rate", bfr); d("dialysate_flow_rate", dfr)
                            i("duration_minutes", duration)
                            isoAt(date, startTime)?.let { body["actual_start_time"] = it }
                            isoAt(date, endTime)?.let { body["actual_end_time"] = it }
                            d("dialysate_volume_liters", dialVol); d("dialysate_lactate_meq", dialLact)
                            d("dialysate_potassium_meq", dialK); i("sak_number", sakNum)
                            i("oxygen_saturation", o2)
                            i("pre_systolic_bp", preSys); i("pre_diastolic_bp", preDia)
                            i("pre_heart_rate", preHr); d("pre_temperature", preTemp)
                            i("pre_standing_systolic_bp", preStSys); i("pre_standing_diastolic_bp", preStDia)
                            i("pre_standing_heart_rate", preStHr)
                            i("post_systolic_bp", postSys); i("post_diastolic_bp", postDia)
                            i("post_heart_rate", postHr); d("post_temperature", postTemp)
                            i("post_standing_systolic_bp", postStSys); i("post_standing_diastolic_bp", postStDia)
                            i("post_standing_heart_rate", postStHr)
                            b("pre_shortness_of_breath", preSob); b("pre_swelling", preSwell)
                            b("pre_change_in_mobility", preMobility); b("pre_digestion_problems", preDigest)
                            b("pre_hosp_er_since_last", preHosp)
                            thrill?.let { b("access_thrill_bruit", it) }
                            b("access_redness_drainage", redness)
                            s("cartridge_lot", cartLot); s("sak_lot", sakLot)
                            s("cycler_number", cycler); s("warmer_serial", warmer)
                            d("total_dialysate_liters", totDial); d("total_uf_liters", totUf)
                            d("saline_added_ml", salineAdded)
                            // HR:MIN in, minutes out. Converted once, here.
                            parseMachineTime(machineTime)?.let {
                                body["machine_total_time_minutes"] = it
                            }
                            d("total_blood_volume_processed", totBlood)
                            s("dialyzer_appearance", dialAppear); s("post_bleeding_stop_time", bleedStop)
                            b("post_bruising", postBruise); b("post_infiltration", postInfilt)
                            b("post_shortness_of_breath", postSob); b("post_swelling", postSwell)
                            b("post_digestion_problems", postDigest)
                            postThrill?.let { b("post_access_thrill_bruit", it) }
                            b("purification_pak_change", purPak); b("air_filter_cleaned", airFilter)
                            b("waste_line_bleach_disinfection", wasteBleach); b("alarm_test_completed", alarmTest)
                            i("sak_use_number", sakUse); d("total_chloramine_level", chloramine)
                            s("lab_tubes_drawn", labTubes)
                            s("facility_name", facility); s("attending_physician", physician)
                            s("rn_reviewer", rnReviewer)
                            s("side_effects", sideEffects); s("clinical_notes", clinicalNotes)
                            s("drugs_administered", drugsAdministered)
                            s("patient_notes", patientNotes)

                            val saved = if (editing != null) {
                                ApiClient.getApiService().updateTherapySession(editing.id, body)
                            } else {
                                // The id comes back from the server — a new session
                                // has none until then, and the readings need it.
                                ApiClient.getApiService().createTherapySession(body)
                            }
                            // Only when the grid is trustworthy. If the existing
                            // readings failed to load, the list on screen is not
                            // the session's readings and writing it would append a
                            // second copy of the flowsheet.
                            if (readingsError == null) {
                                persistReadings(saved.id, readings.toList(),
                                                removedReadingIds.toList())
                            }
                            onSaved()
                        } catch (e: Exception) {
                            Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                        }
                        saving = false
                    }
                },
                modifier = Modifier.fillMaxWidth(), enabled = !saving
            ) { Text(if (saving) stringResource(R.string.saving) else if (editing != null) stringResource(R.string.update_session) else stringResource(R.string.save_session)) }

            Spacer(Modifier.height(32.dp))
        }
    }
}

// MARK: - Helpers

@Composable
private fun SectionHeader(title: String) {
    Spacer(Modifier.height(14.dp))
    Text(title, fontWeight = FontWeight.Bold, fontSize = 14.sp, color = MaterialTheme.colorScheme.primary)
    Spacer(Modifier.height(6.dp))
}

@Composable
private fun F(
    value: String,
    onChange: (String) -> Unit,
    label: String,
    modifier: Modifier = Modifier.fillMaxWidth(),
    enabled: Boolean = true,
) {
    OutlinedTextField(
        value, onChange,
        label = { Text(label, fontSize = 12.sp) },
        modifier = modifier, singleLine = true, enabled = enabled,
    )
    Spacer(Modifier.height(4.dp))
}



/**
 * The machine displays its total time as HR:MIN. Accept that.
 *
 * The column stores minutes and the field demanded them, so a patient reading
 * "7:27" off the machine had to work out 447 themselves every session — and a
 * conversion done in someone's head at the end of a four-hour treatment is one
 * that will sometimes be wrong.
 *
 * A bare number is minutes, because that is what every stored value is.
 * `toIntOrNull()` on "7:27" is null rather than 7, so the clock form can never
 * be mistaken for a seven-minute treatment.
 */
internal fun parseMachineTime(value: String): Int? {
    val text = value.trim()
    if (text.isEmpty()) return null
    if (text.contains(":")) {
        val parts = text.split(":")
        if (parts.size != 2) return null
        val h = parts[0].toIntOrNull() ?: return null
        val m = parts[1].toIntOrNull() ?: return null
        if (h < 0 || m !in 0..59) return null
        return h * 60 + m
    }
    return text.toIntOrNull()?.takeIf { it >= 0 }
}

internal fun formatMachineTime(minutes: Int): String = "%d:%02d".format(minutes / 60, minutes % 60)

/**
 * Machine total time, typed the way the machine shows it, with the converted
 * minutes stated underneath so the arithmetic is visible rather than trusted.
 */
@Composable
private fun MachineTimeField(value: String, onChange: (String) -> Unit) {
    val minutes = parseMachineTime(value)
    val unreadable = value.trim().isNotEmpty() && minutes == null
    Column(Modifier.fillMaxWidth()) {
        OutlinedTextField(
            value = value,
            onValueChange = onChange,
            label = { Text(stringResource(R.string.machine_total_time)) },
            placeholder = { Text(stringResource(R.string.text_7_27_or_447)) },
            isError = unreadable,
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        when {
            unreadable -> Text(
                stringResource(R.string.enter_it_as_hr_min_7_27_or_as_minutes),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.error,
            )
            minutes != null -> Text(
                if (value.contains(":")) stringResource(R.string.min_4, minutes)
                else stringResource(R.string.min_3, minutes, formatMachineTime(minutes)),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

/**
 * Access thrill / bruit — three states, matching the nullable column.
 *
 *   null   not assessed
 *   true   PRESENT — the access is patent, the normal finding
 *   false  ABSENT — possible clotted access, urgent
 *
 * It was a toggle labelled "Access Thrill/Bruit ✓" defaulting to ON, sitting
 * among problem toggles. So ticking it read as reporting a problem when it
 * meant the opposite, every unassessed session recorded a reassuring normal,
 * and the one finding that needs to shout looked like an untouched switch.
 */
@Composable
private fun ThrillRow(value: Boolean?, onChange: (Boolean?) -> Unit) {
    Column(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Text(stringResource(R.string.access_thrill_bruit), style = MaterialTheme.typography.labelMedium)
        Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp)) {
            listOf<Triple<String, Boolean?, Boolean>>(
                Triple("Not assessed", null, false),
                Triple("Present", true, false),
                Triple("ABSENT", false, true),
            ).forEach { (label, state, urgent) ->
                val selected = value == state
                FilterChip(
                    selected = selected,
                    onClick = { onChange(state) },
                    label = {
                        Text(
                            label,
                            color = if (urgent && selected) MaterialTheme.colorScheme.onError
                                    else Color.Unspecified,
                        )
                    },
                    colors = if (urgent) FilterChipDefaults.filterChipColors(
                        selectedContainerColor = MaterialTheme.colorScheme.error,
                    ) else FilterChipDefaults.filterChipColors(),
                )
            }
        }
    }
}

@Composable
private fun ToggleRow(
    label: String,
    checked: Boolean,
    enabled: Boolean = true,
    onToggle: (Boolean) -> Unit,
) {
    Row(
        Modifier.fillMaxWidth()
            .clickable(enabled = enabled) { onToggle(!checked) }
            .padding(vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            label, Modifier.weight(1f), fontSize = 14.sp,
            color = if (enabled) MaterialTheme.colorScheme.onSurface
                    else MaterialTheme.colorScheme.onSurface.copy(alpha = 0.38f)
        )
        Switch(checked, onToggle, enabled = enabled)
    }
}

@Composable
private fun StatCard(title: String, value: String, color: Color, modifier: Modifier = Modifier) {
    Card(modifier = modifier, colors = CardDefaults.cardColors(containerColor = color.copy(alpha = 0.08f))) {
        Column(Modifier.padding(8.dp).fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
            Text(value, fontWeight = FontWeight.Bold, fontSize = 18.sp, color = color)
            Text(title, fontSize = 10.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun StatusChip(status: String) {
    val color = when (status.uppercase()) {
        "COMPLETED" -> Color(0xFF4CAF50); "IN_PROGRESS" -> Color(0xFF2196F3)
        "SCHEDULED" -> Color(0xFFFF9800); "CANCELLED" -> Color(0xFFF44336)
        else -> Color.Gray
    }
    Surface(color = color.copy(alpha = 0.15f), shape = MaterialTheme.shapes.small) {
        Text(status.replace("_", " "), Modifier.padding(horizontal = 8.dp, vertical = 2.dp),
            fontSize = 11.sp, fontWeight = FontWeight.Bold, color = color)
    }
}

@Composable
private fun FlowsheetStatusChip(status: String) {
    val fs = FlowsheetStatus.fromString(status)
    val color = when (fs) {
        FlowsheetStatus.DRAFT -> Color(0xFF9E9E9E)
        FlowsheetStatus.SUBMITTED -> Color(0xFF2196F3)
        FlowsheetStatus.SIGNED -> Color(0xFF009688)
        FlowsheetStatus.COUNTERSIGNED -> Color(0xFF673AB7)
        FlowsheetStatus.REVIEWED -> Color(0xFFFF9800)
        FlowsheetStatus.LOCKED -> Color(0xFF4CAF50)
        else -> Color.Gray
    }
    Surface(color = color.copy(alpha = 0.15f), shape = MaterialTheme.shapes.small) {
        Text("FS: ${status.uppercase()}", Modifier.padding(horizontal = 8.dp, vertical = 2.dp),
            fontSize = 10.sp, fontWeight = FontWeight.Bold, color = color)
    }
}

@Composable
private fun Pill(label: String, value: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(label, fontSize = 10.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, fontSize = 12.sp, fontWeight = FontWeight.Bold)
    }
}

private fun fmtBP(sys: Int?, dia: Int?): String? =
    if (sys != null && dia != null) "$sys/$dia" else null


/** The clock part of a stored session timestamp, for the HH:MM form field. */
internal fun clockOf(value: String?): String {
    if (value.isNullOrBlank()) return ""
    val m = Regex("""T([01]\d|2[0-3]):([0-5]\d)""").find(value)
    return if (m != null) "${m.groupValues[1]}:${m.groupValues[2]}" else ""
}

/** "HH:MM" combined with the SESSION's date — editing a 2013 flowsheet must not
 *  restamp it with today. Returns null when the clock is not a valid time. */
internal fun isoAt(date: String, clock: String): String? {
    val m = Regex("""^([01]\d|2[0-3]):([0-5]\d)$""").find(clock.trim()) ?: return null
    return "${date.take(10)}T${m.groupValues[1]}:${m.groupValues[2]}:00"
}

/** Minutes between two wall clocks, crossing midnight: 21:00 → 01:00 is four
 *  hours, not minus twenty. */
internal fun minutesBetween(start: String, end: String): Int? {
    val re = Regex("""^([01]\d|2[0-3]):([0-5]\d)$""")
    val a = re.find(start.trim()) ?: return null
    val b = re.find(end.trim()) ?: return null
    val from = a.groupValues[1].toInt() * 60 + a.groupValues[2].toInt()
    val to = b.groupValues[1].toInt() * 60 + b.groupValues[2].toInt()
    var mins = to - from
    if (mins < 0) mins += 24 * 60
    return mins
}

/**
 * Mirrors `classify_access` in `app/services/flowsheet_defaults.py`.
 *
 * The stored column is free text — "Catheter. URJ", "AV Graft Left lower arm",
 * and a misspelt "Cather. URJ" all appear — so this matches on substance.
 * A graft counts as needled. Anything unrecognised disables nothing: wrongly
 * greying out a field stops the patient recording what actually happened.
 */
internal fun isCatheterAccess(accessType: String?): Boolean {
    val text = accessType?.trim()?.lowercase() ?: return false
    if (text.isEmpty()) return false
    if (Regex("fistula|graft|\\bavf\\b|\\bavg\\b|buttonhole").containsMatchIn(text)) return false
    return Regex("cath?eter|\\bcather\\b|\\bcvc\\b|perm[ -]?cath|tunn?el").containsMatchIn(text)
}
