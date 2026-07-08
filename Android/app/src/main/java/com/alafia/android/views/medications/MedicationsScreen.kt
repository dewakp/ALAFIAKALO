package com.alafia.android.views.medications
import com.alafia.android.util.ErrorUtil

import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.alafia.android.api.ApiClient
import com.alafia.android.models.Medication
import com.alafia.android.models.MedicationFromImageResponse
import com.alafia.android.schemas.MedicationRequest
import com.alafia.android.schemas.MedicationDoseLogRequest
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import androidx.navigation.NavHostController

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MedicationsScreen(navController: NavHostController) {
    var medications by remember { mutableStateOf<List<Medication>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    var showForm by remember { mutableStateOf(false) }
    var doseTarget by remember { mutableStateOf<Medication?>(null) }
    var scanPrefill by remember { mutableStateOf<MedicationFromImageResponse?>(null) }
    var scanning by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    // Scan Label: read a bottle/label photo → AI extracts the name/dosage/instructions
    // → open the Add-Medication form prefilled (parity with the web "Scan Label").
    val scanPicker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        if (uri != null) {
            scope.launch {
                scanning = true
                try {
                    val bytes = context.contentResolver.openInputStream(uri)?.use { it.readBytes() } ?: byteArrayOf()
                    val part = MultipartBody.Part.createFormData(
                        "file", "label.jpg", bytes.toRequestBody("image/*".toMediaTypeOrNull())
                    )
                    val res = ApiClient.getApiService().medicationFromImage(part)
                    val name = res.medicationName?.takeIf { it.isNotBlank() && !it.equals("Unknown Medication", true) }
                    if (name == null) {
                        Toast.makeText(context, res.notes ?: "Couldn't read the label — try a clearer, well-lit photo.", Toast.LENGTH_LONG).show()
                    } else {
                        scanPrefill = res
                        showForm = true
                    }
                } catch (e: Exception) {
                    Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                }
                scanning = false
            }
        }
    }

    fun loadMedications() {
        scope.launch {
            isLoading = true
            try {
                medications = ApiClient.getApiService().getMedications()
            } catch (e: Exception) {
                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
            }
            isLoading = false
        }
    }

    LaunchedEffect(Unit) { loadMedications() }

    Scaffold(
        topBar = { TopAppBar(
                title = { Text("Medications") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    IconButton(onClick = { if (!scanning) scanPicker.launch("image/*") }, enabled = !scanning) {
                        if (scanning) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                        else Icon(Icons.Default.CameraAlt, contentDescription = "Scan Label")
                    }
                }
            ) },
        floatingActionButton = {
            FloatingActionButton(onClick = { showForm = true }) {
                Icon(Icons.Default.Add, "Add Medication")
            }
        }
    ) { padding ->
        if (isLoading) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        } else if (medications.isEmpty()) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(Icons.Default.LocalPharmacy, "No medications", modifier = Modifier.size(64.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
                    Spacer(Modifier.height(12.dp))
                    Text("No medications", style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text("Tap + to add a medication", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(medications, key = { it.id }) { med ->
                    MedicationCard(
                        medication = med,
                        onLogDose = { doseTarget = med },
                        onDelete = {
                            scope.launch {
                                try {
                                    ApiClient.getApiService().deleteMedication(med.id)
                                    loadMedications()
                                } catch (e: Exception) {
                                    Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                                }
                            }
                        }
                    )
                }
            }
        }
    }

    if (showForm) {
        AddMedicationDialog(
            initialName = scanPrefill?.medicationName.orEmpty(),
            initialDosage = scanPrefill?.dosage?.takeIf { !it.equals("See label", true) }.orEmpty(),
            initialNotes = listOfNotNull(
                scanPrefill?.instructions?.takeIf { it.isNotBlank() },
                scanPrefill?.notes?.takeIf { it.isNotBlank() }
            ).joinToString("\n"),
            onDismiss = { showForm = false; scanPrefill = null },
            onSave = { request ->
                scope.launch {
                    try {
                        ApiClient.getApiService().createMedication(request)
                        showForm = false
                        scanPrefill = null
                        loadMedications()
                        Toast.makeText(context, "Medication added!", Toast.LENGTH_SHORT).show()
                    } catch (e: Exception) {
                        Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                    }
                }
            }
        )
    }

    doseTarget?.let { med ->
        LogDoseDialog(
            medication = med,
            onDismiss = { doseTarget = null },
            onSave = { request ->
                scope.launch {
                    try {
                        ApiClient.getApiService().logMedicationDose(request)
                        doseTarget = null
                        Toast.makeText(context, "Dose logged!", Toast.LENGTH_SHORT).show()
                    } catch (e: Exception) {
                        Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                    }
                }
            }
        )
    }
}

@Composable
private fun MedicationCard(medication: Medication, onLogDose: () -> Unit, onDelete: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Default.Medication, "Med", tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(24.dp))
                Spacer(Modifier.width(12.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text(medication.name, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                    Text(medication.dosage, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                IconButton(onClick = onDelete) {
                    Icon(Icons.Default.Delete, "Delete", tint = MaterialTheme.colorScheme.error)
                }
            }
            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Surface(color = MaterialTheme.colorScheme.secondaryContainer, shape = MaterialTheme.shapes.small) {
                    Text(medication.frequency, modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp), style = MaterialTheme.typography.labelSmall)
                }
                Surface(color = MaterialTheme.colorScheme.tertiaryContainer, shape = MaterialTheme.shapes.small) {
                    Text(medication.reason, modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp), style = MaterialTheme.typography.labelSmall)
                }
            }
            Spacer(Modifier.height(4.dp))
            Text("Since: ${medication.start_date}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            if (medication.end_date != null) {
                Text("Until: ${medication.end_date}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            if (medication.notes != null && medication.notes.isNotEmpty()) {
                Spacer(Modifier.height(4.dp))
                Text(medication.notes, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Spacer(Modifier.height(8.dp))
            FilledTonalButton(onClick = onLogDose) {
                Icon(Icons.Default.CheckCircle, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(8.dp))
                Text("Log Dose")
            }
        }
    }
}

@Composable
private fun AddMedicationDialog(
    initialName: String = "",
    initialDosage: String = "",
    initialNotes: String = "",
    onDismiss: () -> Unit,
    onSave: (MedicationRequest) -> Unit
) {
    var name by remember { mutableStateOf(initialName) }
    var dosage by remember { mutableStateOf(initialDosage) }
    var frequency by remember { mutableStateOf("") }
    var reason by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf(initialNotes) }
    val scanned = initialName.isNotBlank()

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (scanned) "Add Scanned Medication" else "Add Medication") },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                OutlinedTextField(value = name, onValueChange = { name = it }, label = { Text("Medication Name") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = dosage, onValueChange = { dosage = it }, label = { Text("Dosage (e.g. 500mg)") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = frequency, onValueChange = { frequency = it }, label = { Text("Frequency (e.g. twice daily)") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = reason, onValueChange = { reason = it }, label = { Text("Reason / Condition") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = notes, onValueChange = { notes = it }, label = { Text("Notes") }, modifier = Modifier.fillMaxWidth(), minLines = 2)
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    onSave(MedicationRequest(
                        name = name,
                        dosage = dosage,
                        frequency = frequency,
                        reason = reason,
                        start_date = LocalDate.now().format(DateTimeFormatter.ISO_DATE),
                        end_date = null,
                        notes = notes.ifBlank { null }
                    ))
                },
                enabled = name.isNotBlank() && dosage.isNotBlank() && frequency.isNotBlank() && reason.isNotBlank()
            ) { Text("Save") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Cancel") }
        }
    )
}

@Composable
private fun LogDoseDialog(
    medication: Medication,
    onDismiss: () -> Unit,
    onSave: (MedicationDoseLogRequest) -> Unit
) {
    // Prefill amount / unit from the prescription's dosage string (e.g. "500mg").
    var amount by remember(medication.id) {
        mutableStateOf(medication.dosage.filter { it.isDigit() || it == '.' })
    }
    var unit by remember(medication.id) {
        mutableStateOf(medication.dosage.filter { it.isLetter() }.ifBlank { "mg" })
    }
    var notes by remember(medication.id) { mutableStateOf("") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Log Dose") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(medication.name, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        value = amount,
                        onValueChange = { amount = it },
                        label = { Text("Amount") },
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                        modifier = Modifier.weight(1f)
                    )
                    OutlinedTextField(
                        value = unit,
                        onValueChange = { unit = it },
                        label = { Text("Unit") },
                        modifier = Modifier.weight(1f)
                    )
                }
                OutlinedTextField(
                    value = notes,
                    onValueChange = { notes = it },
                    label = { Text("Notes (optional)") },
                    modifier = Modifier.fillMaxWidth(),
                    minLines = 2
                )
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    val value = amount.toDoubleOrNull() ?: return@TextButton
                    onSave(
                        MedicationDoseLogRequest(
                            medication_name = medication.name,
                            log_date = LocalDate.now().format(DateTimeFormatter.ISO_DATE),
                            dose_amount = value,
                            dose_unit = unit.ifBlank { "unit" },
                            medication_id = medication.id,
                            notes = notes.ifBlank { null }
                        )
                    )
                },
                enabled = amount.toDoubleOrNull() != null && unit.isNotBlank()
            ) { Text("Log") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Cancel") }
        }
    )
}
