package com.alafia.android.views.pharmacy

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.alafia.android.api.ApiClient
import com.alafia.android.models.*
import kotlinx.coroutines.launch
import java.time.Instant
import androidx.navigation.NavHostController

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PharmacyScreen(navController: NavHostController) {
    var selectedTab by remember { mutableIntStateOf(0) }
    val tabs = listOf("Rx", "Dispense", "Adherence", "Schedules", "Refills", "Impact")

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Pharmacy") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                }
            )
        }
    ) { padding ->
        Column(modifier = Modifier.padding(padding)) {
            ScrollableTabRow(selectedTabIndex = selectedTab) {
                tabs.forEachIndexed { index, title ->
                    Tab(
                        selected = selectedTab == index,
                        onClick = { selectedTab = index },
                        text = { Text(title) }
                    )
                }
            }

            when (selectedTab) {
                0 -> PrescriptionsTab()
                1 -> DispensesTab()
                2 -> AdherenceTab()
                3 -> SchedulesTab()
                4 -> RefillsTab()
                5 -> ImpactTab()
            }
        }
    }
}

// ── Prescriptions ──

@Composable
fun PrescriptionsTab() {
    val scope = rememberCoroutineScope()
    var prescriptions by remember { mutableStateOf<List<PharmacyPrescription>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var showDialog by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    fun load() {
        scope.launch {
            try { prescriptions = ApiClient.getApiService().getPrescriptions(); loading = false }
            catch (e: Exception) { error = e.message; loading = false }
        }
    }

    LaunchedEffect(Unit) { load() }

    Box(modifier = Modifier.fillMaxSize()) {
        if (loading) {
            CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
        } else if (prescriptions.isEmpty()) {
            Text("No prescriptions yet", modifier = Modifier.align(Alignment.Center), color = MaterialTheme.colorScheme.onSurfaceVariant)
        } else {
            LazyColumn(modifier = Modifier.fillMaxSize().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                item { Spacer(Modifier.height(8.dp)) }
                items(prescriptions) { rx ->
                    PrescriptionCard(rx) {
                        scope.launch {
                            try { ApiClient.getApiService().deletePrescription(rx.id); load() }
                            catch (e: Exception) { error = e.message }
                        }
                    }
                }
                item { Spacer(Modifier.height(80.dp)) }
            }
        }

        FloatingActionButton(
            onClick = { showDialog = true },
            modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp)
        ) { Icon(Icons.Default.Add, contentDescription = "Add") }
    }

    if (showDialog) {
        AddPrescriptionDialog(
            onDismiss = { showDialog = false },
            onSave = { req ->
                scope.launch {
                    try { ApiClient.getApiService().createPrescription(req); showDialog = false; load() }
                    catch (e: Exception) { error = e.message }
                }
            }
        )
    }

    error?.let { msg ->
        LaunchedEffect(msg) { error = null }
        // Could use a Snackbar
    }
}

@Composable
fun PrescriptionCard(rx: PharmacyPrescription, onDelete: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(rx.medicationName, style = MaterialTheme.typography.titleMedium)
                    Text(listOfNotNull(rx.dosage, rx.dosageUnit).joinToString(" "),
                        style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                StatusChip(rx.status)
            }
            Spacer(Modifier.height(4.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                rx.frequency?.let { Text(it, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                Spacer(Modifier.weight(1f))
                Text("Refills: ${rx.refillsRemaining}/${rx.refillsAuthorized}",
                    style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                IconButton(onClick = onDelete, modifier = Modifier.size(32.dp)) {
                    Icon(Icons.Default.Delete, contentDescription = "Delete", tint = MaterialTheme.colorScheme.error, modifier = Modifier.size(18.dp))
                }
            }
        }
    }
}

@Composable
fun AddPrescriptionDialog(onDismiss: () -> Unit, onSave: (PrescriptionCreateRequest) -> Unit) {
    var patientId by remember { mutableStateOf("") }
    var medName by remember { mutableStateOf("") }
    var dosage by remember { mutableStateOf("") }
    var unit by remember { mutableStateOf("mg") }
    var frequency by remember { mutableStateOf("once daily") }
    var quantity by remember { mutableStateOf("") }
    var refills by remember { mutableStateOf("0") }
    var diagnosis by remember { mutableStateOf("") }
    var instructions by remember { mutableStateOf("") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("New Prescription") },
        text = {
            LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                item { OutlinedTextField(value = patientId, onValueChange = { patientId = it }, label = { Text("Patient ID") }, modifier = Modifier.fillMaxWidth()) }
                item { OutlinedTextField(value = medName, onValueChange = { medName = it }, label = { Text("Medication name") }, modifier = Modifier.fillMaxWidth()) }
                item {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedTextField(value = dosage, onValueChange = { dosage = it }, label = { Text("Dosage") }, modifier = Modifier.weight(1f))
                        OutlinedTextField(value = unit, onValueChange = { unit = it }, label = { Text("Unit") }, modifier = Modifier.weight(1f))
                    }
                }
                item { OutlinedTextField(value = frequency, onValueChange = { frequency = it }, label = { Text("Frequency") }, modifier = Modifier.fillMaxWidth()) }
                item {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedTextField(value = quantity, onValueChange = { quantity = it }, label = { Text("Qty") }, modifier = Modifier.weight(1f))
                        OutlinedTextField(value = refills, onValueChange = { refills = it }, label = { Text("Refills") }, modifier = Modifier.weight(1f))
                    }
                }
                item { OutlinedTextField(value = diagnosis, onValueChange = { diagnosis = it }, label = { Text("Diagnosis") }, modifier = Modifier.fillMaxWidth()) }
                item { OutlinedTextField(value = instructions, onValueChange = { instructions = it }, label = { Text("Instructions") }, modifier = Modifier.fillMaxWidth()) }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    val pid = patientId.toIntOrNull() ?: return@Button
                    onSave(PrescriptionCreateRequest(
                        patientId = pid, medicationName = medName,
                        dosage = dosage.ifBlank { null }, dosageUnit = unit,
                        frequency = frequency, quantity = quantity.toIntOrNull(),
                        refillsAuthorized = refills.toIntOrNull() ?: 0,
                        diagnosis = diagnosis.ifBlank { null },
                        instructions = instructions.ifBlank { null }
                    ))
                },
                enabled = medName.isNotBlank() && patientId.isNotBlank()
            ) { Text("Save") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } }
    )
}

// ── Dispenses ──

@Composable
fun DispensesTab() {
    val scope = rememberCoroutineScope()
    var dispenses by remember { mutableStateOf<List<PharmacyDispense>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var showDialog by remember { mutableStateOf(false) }

    fun load() {
        scope.launch {
            try { dispenses = ApiClient.getApiService().getDispenses(); loading = false }
            catch (_: Exception) { loading = false }
        }
    }

    LaunchedEffect(Unit) { load() }

    Box(modifier = Modifier.fillMaxSize()) {
        if (loading) {
            CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
        } else if (dispenses.isEmpty()) {
            Text("No dispenses yet", modifier = Modifier.align(Alignment.Center), color = MaterialTheme.colorScheme.onSurfaceVariant)
        } else {
            LazyColumn(modifier = Modifier.fillMaxSize().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                item { Spacer(Modifier.height(8.dp)) }
                items(dispenses) { d -> DispenseCard(d) }
                item { Spacer(Modifier.height(80.dp)) }
            }
        }

        FloatingActionButton(
            onClick = { showDialog = true },
            modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp)
        ) { Icon(Icons.Default.Add, contentDescription = "Add") }
    }

    if (showDialog) {
        AddDispenseDialog(onDismiss = { showDialog = false }) { req ->
            scope.launch {
                try { ApiClient.getApiService().createDispense(req); showDialog = false; load() }
                catch (_: Exception) {}
            }
        }
    }
}

@Composable
fun DispenseCard(d: PharmacyDispense) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(d.medicationName ?: "Rx #${d.prescriptionId}", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                StatusChip(d.status)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                d.quantityDispensed?.let { Text("Qty: $it", style = MaterialTheme.typography.labelSmall) }
                if (d.interactionsChecked) Text("DUR ✓", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary)
                if (d.allergyChecked) Text("Allergy ✓", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary)
            }
            d.pharmacistName?.let { Text("By: $it", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
        }
    }
}

@Composable
fun AddDispenseDialog(onDismiss: () -> Unit, onSave: (DispenseCreateRequest) -> Unit) {
    var rxId by remember { mutableStateOf("") }
    var qty by remember { mutableStateOf("") }
    var days by remember { mutableStateOf("") }
    var ndcCode by remember { mutableStateOf("") }
    var lotNumber by remember { mutableStateOf("") }
    var manufacturer by remember { mutableStateOf("") }
    var isGeneric by remember { mutableStateOf(false) }
    var interactionsChecked by remember { mutableStateOf(false) }
    var allergyChecked by remember { mutableStateOf(false) }
    var counselingProvided by remember { mutableStateOf(false) }
    var notes by remember { mutableStateOf("") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Dispense Prescription") },
        text = {
            LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                item { OutlinedTextField(value = rxId, onValueChange = { rxId = it }, label = { Text("Prescription ID") }, modifier = Modifier.fillMaxWidth()) }
                item {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedTextField(value = qty, onValueChange = { qty = it }, label = { Text("Quantity") }, modifier = Modifier.weight(1f))
                        OutlinedTextField(value = days, onValueChange = { days = it }, label = { Text("Days supply") }, modifier = Modifier.weight(1f))
                    }
                }
                item { OutlinedTextField(value = ndcCode, onValueChange = { ndcCode = it }, label = { Text("NDC code") }, modifier = Modifier.fillMaxWidth()) }
                item { OutlinedTextField(value = lotNumber, onValueChange = { lotNumber = it }, label = { Text("Lot number") }, modifier = Modifier.fillMaxWidth()) }
                item { OutlinedTextField(value = manufacturer, onValueChange = { manufacturer = it }, label = { Text("Manufacturer") }, modifier = Modifier.fillMaxWidth()) }
                item { Row(verticalAlignment = Alignment.CenterVertically) { Checkbox(checked = isGeneric, onCheckedChange = { isGeneric = it }); Text("Generic") } }
                item { Row(verticalAlignment = Alignment.CenterVertically) { Checkbox(checked = interactionsChecked, onCheckedChange = { interactionsChecked = it }); Text("Interactions checked") } }
                item { Row(verticalAlignment = Alignment.CenterVertically) { Checkbox(checked = allergyChecked, onCheckedChange = { allergyChecked = it }); Text("Allergy checked") } }
                item { Row(verticalAlignment = Alignment.CenterVertically) { Checkbox(checked = counselingProvided, onCheckedChange = { counselingProvided = it }); Text("Counseling provided") } }
                item { OutlinedTextField(value = notes, onValueChange = { notes = it }, label = { Text("Clinical notes") }, modifier = Modifier.fillMaxWidth()) }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    val pid = rxId.toIntOrNull() ?: return@Button
                    onSave(DispenseCreateRequest(
                        prescriptionId = pid, quantityDispensed = qty.toIntOrNull(),
                        daysSupply = days.toIntOrNull(), ndcCode = ndcCode.ifBlank { null },
                        lotNumber = lotNumber.ifBlank { null }, manufacturer = manufacturer.ifBlank { null },
                        isGeneric = isGeneric, interactionsChecked = interactionsChecked,
                        allergyChecked = allergyChecked, counselingProvided = counselingProvided,
                        clinicalNotes = notes.ifBlank { null }
                    ))
                },
                enabled = rxId.isNotBlank()
            ) { Text("Dispense") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } }
    )
}

// ── Adherence ──

@Composable
fun AdherenceTab() {
    val scope = rememberCoroutineScope()
    var logs by remember { mutableStateOf<List<PharmacyAdherenceLog>>(emptyList()) }
    var report by remember { mutableStateOf<PharmacyAdherenceReport?>(null) }
    var loading by remember { mutableStateOf(true) }
    var showDialog by remember { mutableStateOf(false) }

    fun load() {
        scope.launch {
            try {
                logs = ApiClient.getApiService().getAdherenceLogs()
                report = try { ApiClient.getApiService().getAdherenceReport() } catch (_: Exception) { null }
                loading = false
            } catch (_: Exception) { loading = false }
        }
    }

    LaunchedEffect(Unit) { load() }

    Box(modifier = Modifier.fillMaxSize()) {
        if (loading) {
            CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
        } else {
            LazyColumn(modifier = Modifier.fillMaxSize().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                item { Spacer(Modifier.height(8.dp)) }
                report?.let { r ->
                    item {
                        Card(modifier = Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)) {
                            Column(modifier = Modifier.padding(16.dp)) {
                                Text("Adherence Summary", style = MaterialTheme.typography.titleSmall)
                                Spacer(Modifier.height(8.dp))
                                Row(horizontalArrangement = Arrangement.SpaceEvenly, modifier = Modifier.fillMaxWidth()) {
                                    SummaryItem("Rate", "${(r.adherenceRate * 100).toInt()}%")
                                    SummaryItem("Taken", "${r.totalTaken}")
                                    SummaryItem("Missed", "${r.totalMissed}")
                                    SummaryItem("Streak", "${r.streakCurrent}d")
                                }
                                if (r.commonSideEffects.isNotEmpty()) {
                                    Spacer(Modifier.height(4.dp))
                                    Text("Side effects: ${r.commonSideEffects.joinToString(", ")}", style = MaterialTheme.typography.labelSmall)
                                }
                            }
                        }
                    }
                }
                if (logs.isEmpty()) {
                    item { Text("No adherence logs", color = MaterialTheme.colorScheme.onSurfaceVariant) }
                }
                items(logs) { log -> AdherenceLogCard(log) }
                item { Spacer(Modifier.height(80.dp)) }
            }
        }

        FloatingActionButton(
            onClick = { showDialog = true },
            modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp)
        ) { Icon(Icons.Default.Add, contentDescription = "Log dose") }
    }

    if (showDialog) {
        LogDoseDialog(onDismiss = { showDialog = false }) { req ->
            scope.launch {
                try { ApiClient.getApiService().createAdherenceLog(req); showDialog = false; load() }
                catch (_: Exception) {}
            }
        }
    }
}

@Composable
fun AdherenceLogCard(log: PharmacyAdherenceLog) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(log.medicationName ?: "Rx #${log.prescriptionId}", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                StatusChip(log.status)
            }
            log.doseTaken?.let { Text("Dose: $it", style = MaterialTheme.typography.bodySmall) }
            log.sideEffectsReported?.let { Text("Side effects: $it", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.error) }
        }
    }
}

@Composable
fun LogDoseDialog(onDismiss: () -> Unit, onSave: (AdherenceLogCreateRequest) -> Unit) {
    var rxId by remember { mutableStateOf("") }
    var status by remember { mutableStateOf("taken") }
    var dose by remember { mutableStateOf("") }
    var sideEffects by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }
    var moodBefore by remember { mutableStateOf("") }
    var moodAfter by remember { mutableStateOf("") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Log Dose") },
        text = {
            LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                item { OutlinedTextField(value = rxId, onValueChange = { rxId = it }, label = { Text("Prescription ID") }, modifier = Modifier.fillMaxWidth()) }
                item { OutlinedTextField(value = status, onValueChange = { status = it }, label = { Text("Status (taken/missed/skipped/late)") }, modifier = Modifier.fillMaxWidth()) }
                item { OutlinedTextField(value = dose, onValueChange = { dose = it }, label = { Text("Dose taken") }, modifier = Modifier.fillMaxWidth()) }
                item {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedTextField(value = moodBefore, onValueChange = { moodBefore = it }, label = { Text("Mood before") }, modifier = Modifier.weight(1f))
                        OutlinedTextField(value = moodAfter, onValueChange = { moodAfter = it }, label = { Text("Mood after") }, modifier = Modifier.weight(1f))
                    }
                }
                item { OutlinedTextField(value = sideEffects, onValueChange = { sideEffects = it }, label = { Text("Side effects") }, modifier = Modifier.fillMaxWidth()) }
                item { OutlinedTextField(value = notes, onValueChange = { notes = it }, label = { Text("Notes") }, modifier = Modifier.fillMaxWidth()) }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    val pid = rxId.toIntOrNull() ?: return@Button
                    onSave(AdherenceLogCreateRequest(
                        prescriptionId = pid, scheduledTime = Instant.now().toString(),
                        status = status, doseTaken = dose.ifBlank { null },
                        notes = notes.ifBlank { null }, sideEffectsReported = sideEffects.ifBlank { null },
                        moodBefore = moodBefore.toIntOrNull(), moodAfter = moodAfter.toIntOrNull()
                    ))
                },
                enabled = rxId.isNotBlank()
            ) { Text("Save") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } }
    )
}

// ── Schedules ──

@Composable
fun SchedulesTab() {
    val scope = rememberCoroutineScope()
    var schedules by remember { mutableStateOf<List<PharmacySchedule>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var showDialog by remember { mutableStateOf(false) }

    fun load() {
        scope.launch {
            try { schedules = ApiClient.getApiService().getPharmacySchedules(); loading = false }
            catch (_: Exception) { loading = false }
        }
    }

    LaunchedEffect(Unit) { load() }

    Box(modifier = Modifier.fillMaxSize()) {
        if (loading) {
            CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
        } else if (schedules.isEmpty()) {
            Text("No schedules yet", modifier = Modifier.align(Alignment.Center), color = MaterialTheme.colorScheme.onSurfaceVariant)
        } else {
            LazyColumn(modifier = Modifier.fillMaxSize().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                item { Spacer(Modifier.height(8.dp)) }
                items(schedules) { s ->
                    ScheduleCard(s) {
                        scope.launch {
                            try { ApiClient.getApiService().deletePharmacySchedule(s.id); load() }
                            catch (_: Exception) {}
                        }
                    }
                }
                item { Spacer(Modifier.height(80.dp)) }
            }
        }

        FloatingActionButton(
            onClick = { showDialog = true },
            modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp)
        ) { Icon(Icons.Default.Add, contentDescription = "Add") }
    }

    if (showDialog) {
        AddScheduleDialog(onDismiss = { showDialog = false }) { req ->
            scope.launch {
                try { ApiClient.getApiService().createPharmacySchedule(req); showDialog = false; load() }
                catch (_: Exception) {}
            }
        }
    }
}

@Composable
fun ScheduleCard(s: PharmacySchedule, onDelete: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(s.medicationName ?: "Rx #${s.prescriptionId}", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                StatusChip(if (s.isActive) "active" else "inactive")
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("⏰ ${s.timeOfDay}", style = MaterialTheme.typography.bodySmall)
                s.daysOfWeek?.let { Text("📅 $it", style = MaterialTheme.typography.bodySmall) }
                Text("🔔 ${s.reminderMinutesBefore}m", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Row {
                Spacer(Modifier.weight(1f))
                IconButton(onClick = onDelete, modifier = Modifier.size(32.dp)) {
                    Icon(Icons.Default.Delete, contentDescription = "Delete", tint = MaterialTheme.colorScheme.error, modifier = Modifier.size(18.dp))
                }
            }
        }
    }
}

@Composable
fun AddScheduleDialog(onDismiss: () -> Unit, onSave: (ScheduleCreateRequest) -> Unit) {
    var rxId by remember { mutableStateOf("") }
    var timeOfDay by remember { mutableStateOf("08:00") }
    var daysOfWeek by remember { mutableStateOf("") }
    var doseLabel by remember { mutableStateOf("") }
    var reminder by remember { mutableStateOf("15") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("New Schedule") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(value = rxId, onValueChange = { rxId = it }, label = { Text("Prescription ID") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = timeOfDay, onValueChange = { timeOfDay = it }, label = { Text("Time (HH:MM)") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = daysOfWeek, onValueChange = { daysOfWeek = it }, label = { Text("Days (e.g. Mon,Wed,Fri)") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = doseLabel, onValueChange = { doseLabel = it }, label = { Text("Dose label") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = reminder, onValueChange = { reminder = it }, label = { Text("Reminder (minutes before)") }, modifier = Modifier.fillMaxWidth())
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    val pid = rxId.toIntOrNull() ?: return@Button
                    onSave(ScheduleCreateRequest(
                        prescriptionId = pid, timeOfDay = timeOfDay,
                        daysOfWeek = daysOfWeek.ifBlank { null }, doseLabel = doseLabel.ifBlank { null },
                        reminderMinutesBefore = reminder.toIntOrNull() ?: 15
                    ))
                },
                enabled = rxId.isNotBlank()
            ) { Text("Save") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } }
    )
}

// ── Refills ──

@Composable
fun RefillsTab() {
    val scope = rememberCoroutineScope()
    var refills by remember { mutableStateOf<List<PharmacyRefillRequest>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var showDialog by remember { mutableStateOf(false) }

    fun load() {
        scope.launch {
            try { refills = ApiClient.getApiService().getRefillRequests(); loading = false }
            catch (_: Exception) { loading = false }
        }
    }

    LaunchedEffect(Unit) { load() }

    Box(modifier = Modifier.fillMaxSize()) {
        if (loading) {
            CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
        } else if (refills.isEmpty()) {
            Text("No refill requests", modifier = Modifier.align(Alignment.Center), color = MaterialTheme.colorScheme.onSurfaceVariant)
        } else {
            LazyColumn(modifier = Modifier.fillMaxSize().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                item { Spacer(Modifier.height(8.dp)) }
                items(refills) { r -> RefillCard(r) }
                item { Spacer(Modifier.height(80.dp)) }
            }
        }

        FloatingActionButton(
            onClick = { showDialog = true },
            modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp)
        ) { Icon(Icons.Default.Add, contentDescription = "Request refill") }
    }

    if (showDialog) {
        AddRefillDialog(onDismiss = { showDialog = false }) { req ->
            scope.launch {
                try { ApiClient.getApiService().createRefillRequest(req); showDialog = false; load() }
                catch (_: Exception) {}
            }
        }
    }
}

@Composable
fun RefillCard(r: PharmacyRefillRequest) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(r.medicationName ?: "Rx #${r.prescriptionId}", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                StatusChip(r.status)
            }
            r.quantityRequested?.let { Text("Quantity: $it", style = MaterialTheme.typography.bodySmall) }
            r.denialReason?.let { Text("Denied: $it", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.error) }
        }
    }
}

@Composable
fun AddRefillDialog(onDismiss: () -> Unit, onSave: (RefillCreateRequest) -> Unit) {
    var rxId by remember { mutableStateOf("") }
    var qty by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Request Refill") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(value = rxId, onValueChange = { rxId = it }, label = { Text("Prescription ID") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = qty, onValueChange = { qty = it }, label = { Text("Quantity") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = notes, onValueChange = { notes = it }, label = { Text("Notes") }, modifier = Modifier.fillMaxWidth())
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    val pid = rxId.toIntOrNull() ?: return@Button
                    onSave(RefillCreateRequest(
                        prescriptionId = pid, quantityRequested = qty.toIntOrNull(),
                        notes = notes.ifBlank { null }
                    ))
                },
                enabled = rxId.isNotBlank()
            ) { Text("Submit") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } }
    )
}

// ── Impact ──

@Composable
fun ImpactTab() {
    val scope = rememberCoroutineScope()
    var rxIdText by remember { mutableStateOf("") }
    var report by remember { mutableStateOf<MedicationImpactResponse?>(null) }

    LazyColumn(modifier = Modifier.fillMaxSize().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        item { Spacer(Modifier.height(8.dp)) }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(value = rxIdText, onValueChange = { rxIdText = it }, label = { Text("Prescription ID") }, modifier = Modifier.weight(1f))
                Button(
                    onClick = {
                        val id = rxIdText.toIntOrNull() ?: return@Button
                        scope.launch {
                            try { report = ApiClient.getApiService().getMedicationImpact(id) }
                            catch (_: Exception) {}
                        }
                    },
                    enabled = rxIdText.isNotBlank()
                ) { Text("Analyze") }
            }
        }

        report?.let { r ->
            item {
                Card(modifier = Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text("${r.medicationName} Impact", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                        Spacer(Modifier.height(8.dp))
                        Row(horizontalArrangement = Arrangement.SpaceEvenly, modifier = Modifier.fillMaxWidth()) {
                            SummaryItem("Adherence", "${(r.adherenceRate * 100).toInt()}%")
                            SummaryItem("Taken", "${r.dosesTaken}")
                            SummaryItem("Missed", "${r.dosesMissed}")
                            SummaryItem("Period", "${r.analysisPeriodDays}d")
                        }
                    }
                }
            }

            item {
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text("Mood Impact", style = MaterialTheme.typography.titleSmall)
                        Spacer(Modifier.height(4.dp))
                        Row(horizontalArrangement = Arrangement.SpaceEvenly, modifier = Modifier.fillMaxWidth()) {
                            r.avgMoodBefore?.let { SummaryItem("Before", String.format("%.1f", it)) }
                            r.avgMoodAfter?.let { SummaryItem("After", String.format("%.1f", it)) }
                            r.moodTrend?.let { SummaryItem("Trend", it) }
                        }
                    }
                }
            }

            if (r.reportedSideEffects.isNotEmpty()) {
                item {
                    Card(modifier = Modifier.fillMaxWidth()) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            Text("Side Effects", style = MaterialTheme.typography.titleSmall)
                            Text(r.reportedSideEffects.joinToString(", "), style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
            }

            item {
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text("Scores", style = MaterialTheme.typography.titleSmall)
                        Row(horizontalArrangement = Arrangement.SpaceEvenly, modifier = Modifier.fillMaxWidth()) {
                            r.effectivenessScore?.let { SummaryItem("Effectiveness", "${(it * 100).toInt()}%") }
                            r.tolerabilityScore?.let { SummaryItem("Tolerability", "${(it * 100).toInt()}%") }
                        }
                    }
                }
            }

            r.aiSummary?.let { summary ->
                item {
                    Card(modifier = Modifier.fillMaxWidth()) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            Text("AI Summary", style = MaterialTheme.typography.titleSmall)
                            Spacer(Modifier.height(4.dp))
                            Text(summary, style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
            }
        }

        item { Spacer(Modifier.height(16.dp)) }
    }
}

// ── Shared ──

@Composable
fun SummaryItem(label: String, value: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
        Text(label, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
fun StatusChip(status: String) {
    val color = when (status.lowercase()) {
        "active", "taken", "approved", "dispensed", "completed" -> MaterialTheme.colorScheme.primary
        "pending", "pending_review", "in_progress", "late" -> MaterialTheme.colorScheme.tertiary
        "cancelled", "denied", "missed", "expired" -> MaterialTheme.colorScheme.error
        else -> MaterialTheme.colorScheme.outline
    }
    Surface(
        color = color.copy(alpha = 0.12f),
        shape = MaterialTheme.shapes.small
    ) {
        Text(
            text = status.replace("_", " ").replaceFirstChar { it.uppercase() },
            style = MaterialTheme.typography.labelSmall,
            color = color,
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp)
        )
    }
}
