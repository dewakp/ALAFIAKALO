@file:OptIn(ExperimentalMaterial3Api::class)

package com.alafia.android.views.directives
import com.alafia.android.util.ErrorUtil

import android.widget.Toast
import androidx.compose.foundation.layout.*
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
import com.alafia.android.api.ApiClient
import com.alafia.android.models.AdvancedDirective
import kotlinx.coroutines.launch
import androidx.navigation.NavHostController
import androidx.compose.ui.res.stringResource
import com.alafia.android.R

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AdvancedDirectivesScreen(navController: NavHostController) {
    var directive by remember { mutableStateOf<AdvancedDirective?>(null) }
    var isLoading by remember { mutableStateOf(true) }
    var isEditing by remember { mutableStateOf(false) }
    var hasExisting by remember { mutableStateOf(false) }
    var showDeleteDialog by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    // Editable fields
    var primaryAgentName by remember { mutableStateOf("") }
    var primaryAgentRelationship by remember { mutableStateOf("") }
    var primaryAgentPhone by remember { mutableStateOf("") }
    var primaryAgentEmail by remember { mutableStateOf("") }
    var alternateAgentName by remember { mutableStateOf("") }
    var alternateAgentRelationship by remember { mutableStateOf("") }
    var alternateAgentPhone by remember { mutableStateOf("") }
    var organDonation by remember { mutableStateOf("Full Treatment") }
    var lifeSupport by remember { mutableStateOf("Full Treatment") }
    var cpr by remember { mutableStateOf("Full Treatment") }
    var ventilator by remember { mutableStateOf("Full Treatment") }
    var feedingTube by remember { mutableStateOf("Full Treatment") }
    var dialysisDirective by remember { mutableStateOf("Full Treatment") }
    var bloodTransfusion by remember { mutableStateOf("Full Treatment") }
    var documentSigned by remember { mutableStateOf(false) }
    var documentDate by remember { mutableStateOf("") }
    var additionalInstructions by remember { mutableStateOf("") }

    fun populateFields(d: AdvancedDirective) {
        primaryAgentName = d.primaryAgentName ?: ""
        primaryAgentRelationship = d.primaryAgentRelationship ?: ""
        primaryAgentPhone = d.primaryAgentPhone ?: ""
        primaryAgentEmail = d.primaryAgentEmail ?: ""
        alternateAgentName = d.alternateAgentName ?: ""
        alternateAgentRelationship = d.alternateAgentRelationship ?: ""
        alternateAgentPhone = d.alternateAgentPhone ?: ""
        organDonation = d.organDonation ?: "Full Treatment"
        lifeSupport = d.lifeSupport ?: "Full Treatment"
        cpr = d.cpr ?: "Full Treatment"
        ventilator = d.ventilator ?: "Full Treatment"
        feedingTube = d.feedingTube ?: "Full Treatment"
        dialysisDirective = d.dialysisDirective ?: "Full Treatment"
        bloodTransfusion = d.bloodTransfusion ?: "Full Treatment"
        documentSigned = d.documentSigned ?: false
        documentDate = d.documentDate ?: ""
        additionalInstructions = d.additionalInstructions ?: ""
    }

    fun buildDirective() = AdvancedDirective(
        id = directive?.id,
        primaryAgentName = primaryAgentName.ifBlank { null },
        primaryAgentRelationship = primaryAgentRelationship.ifBlank { null },
        primaryAgentPhone = primaryAgentPhone.ifBlank { null },
        primaryAgentEmail = primaryAgentEmail.ifBlank { null },
        alternateAgentName = alternateAgentName.ifBlank { null },
        alternateAgentRelationship = alternateAgentRelationship.ifBlank { null },
        alternateAgentPhone = alternateAgentPhone.ifBlank { null },
        organDonation = organDonation,
        lifeSupport = lifeSupport,
        cpr = cpr,
        ventilator = ventilator,
        feedingTube = feedingTube,
        dialysisDirective = dialysisDirective,
        bloodTransfusion = bloodTransfusion,
        documentSigned = documentSigned,
        documentDate = documentDate.ifBlank { null },
        additionalInstructions = additionalInstructions.ifBlank { null }
    )

    fun loadDirective() {
        scope.launch {
            isLoading = true
            try {
                val d = ApiClient.getApiService().getAdvancedDirective()
                directive = d
                hasExisting = true
                populateFields(d)
            } catch (e: retrofit2.HttpException) {
                if (e.code() == 404) {
                    directive = null
                    hasExisting = false
                    isEditing = true
                } else {
                    Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                }
            } catch (e: Exception) {
                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
            }
            isLoading = false
        }
    }

    LaunchedEffect(Unit) { loadDirective() }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.advanced_directives)) },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = stringResource(R.string.back))
                    }
                },
                actions = {
                    if (!isLoading) {
                        if (hasExisting && !isEditing) {
                            IconButton(onClick = { isEditing = true }) {
                                Icon(Icons.Default.Edit, "Edit")
                            }
                            IconButton(onClick = { showDeleteDialog = true }) {
                                Icon(Icons.Default.Delete, "Delete", tint = MaterialTheme.colorScheme.error)
                            }
                        } else if (isEditing && hasExisting) {
                            IconButton(onClick = {
                                isEditing = false
                                directive?.let { populateFields(it) }
                            }) {
                                Icon(Icons.Default.Close, "Cancel")
                            }
                        }
                    }
                }
            )
        }
    ) { padding ->
        if (isLoading) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        } else {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding)
                    .verticalScroll(rememberScrollState())
                    .padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                if (isEditing) {
                    EditableDirectiveContent(
                        primaryAgentName = primaryAgentName, onPrimaryAgentNameChange = { primaryAgentName = it },
                        primaryAgentRelationship = primaryAgentRelationship, onPrimaryAgentRelationshipChange = { primaryAgentRelationship = it },
                        primaryAgentPhone = primaryAgentPhone, onPrimaryAgentPhoneChange = { primaryAgentPhone = it },
                        primaryAgentEmail = primaryAgentEmail, onPrimaryAgentEmailChange = { primaryAgentEmail = it },
                        alternateAgentName = alternateAgentName, onAlternateAgentNameChange = { alternateAgentName = it },
                        alternateAgentRelationship = alternateAgentRelationship, onAlternateAgentRelationshipChange = { alternateAgentRelationship = it },
                        alternateAgentPhone = alternateAgentPhone, onAlternateAgentPhoneChange = { alternateAgentPhone = it },
                        organDonation = organDonation, onOrganDonationChange = { organDonation = it },
                        lifeSupport = lifeSupport, onLifeSupportChange = { lifeSupport = it },
                        cpr = cpr, onCprChange = { cpr = it },
                        ventilator = ventilator, onVentilatorChange = { ventilator = it },
                        feedingTube = feedingTube, onFeedingTubeChange = { feedingTube = it },
                        dialysisDirective = dialysisDirective, onDialysisDirectiveChange = { dialysisDirective = it },
                        bloodTransfusion = bloodTransfusion, onBloodTransfusionChange = { bloodTransfusion = it },
                        documentSigned = documentSigned, onDocumentSignedChange = { documentSigned = it },
                        documentDate = documentDate, onDocumentDateChange = { documentDate = it },
                        additionalInstructions = additionalInstructions, onAdditionalInstructionsChange = { additionalInstructions = it }
                    )

                    Button(
                        onClick = {
                            scope.launch {
                                try {
                                    val body = buildDirective()
                                    val saved = if (hasExisting) {
                                        ApiClient.getApiService().updateAdvancedDirective(body)
                                    } else {
                                        ApiClient.getApiService().createAdvancedDirective(body)
                                    }
                                    directive = saved
                                    hasExisting = true
                                    isEditing = false
                                    populateFields(saved)
                                    Toast.makeText(context, "Directive saved!", Toast.LENGTH_SHORT).show()
                                } catch (e: Exception) {
                                    Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                                }
                            }
                        },
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Icon(Icons.Default.Save, contentDescription = null)
                        Spacer(Modifier.width(8.dp))
                        Text(stringResource(R.string.save_directive))
                    }
                } else {
                    directive?.let { ReadOnlyDirectiveContent(it) }
                }

                Spacer(Modifier.height(32.dp))
            }
        }
    }

    // Delete confirmation
    if (showDeleteDialog) {
        AlertDialog(
            onDismissRequest = { showDeleteDialog = false },
            title = { Text(stringResource(R.string.delete_directive)) },
            text = { Text(stringResource(R.string.are_you_sure_you_want_to_delete_your)) },
            confirmButton = {
                TextButton(onClick = {
                    scope.launch {
                        try {
                            ApiClient.getApiService().deleteAdvancedDirective()
                            showDeleteDialog = false
                            directive = null
                            hasExisting = false
                            isEditing = true
                            primaryAgentName = ""; primaryAgentRelationship = ""; primaryAgentPhone = ""; primaryAgentEmail = ""
                            alternateAgentName = ""; alternateAgentRelationship = ""; alternateAgentPhone = ""
                            organDonation = "Full Treatment"; lifeSupport = "Full Treatment"; cpr = "Full Treatment"
                            ventilator = "Full Treatment"; feedingTube = "Full Treatment"; dialysisDirective = "Full Treatment"
                            bloodTransfusion = "Full Treatment"; documentSigned = false; documentDate = ""; additionalInstructions = ""
                            Toast.makeText(context, "Directive deleted", Toast.LENGTH_SHORT).show()
                        } catch (e: Exception) {
                            Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                        }
                    }
                }) { Text(stringResource(R.string.delete), color = MaterialTheme.colorScheme.error) }
            },
            dismissButton = {
                TextButton(onClick = { showDeleteDialog = false }) { Text(stringResource(R.string.cancel)) }
            }
        )
    }
}

// ── Read-Only View ──────────────────────────────────────────────────────────

@Composable
private fun ReadOnlyDirectiveContent(d: AdvancedDirective) {
    // Healthcare Agent section
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(stringResource(R.string.healthcare_agent), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)

            Text(stringResource(R.string.primary_agent), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
            d.primaryAgentName?.let { LabeledValue(stringResource(R.string.name), it) }
            d.primaryAgentRelationship?.let { LabeledValue(stringResource(R.string.relationship), it) }
            d.primaryAgentPhone?.let { LabeledValue(stringResource(R.string.phone), it) }
            d.primaryAgentEmail?.let { LabeledValue(stringResource(R.string.email), it) }

            if (d.alternateAgentName != null || d.alternateAgentRelationship != null || d.alternateAgentPhone != null) {
                HorizontalDivider()
                Text(stringResource(R.string.alternate_agent), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
                d.alternateAgentName?.let { LabeledValue(stringResource(R.string.name), it) }
                d.alternateAgentRelationship?.let { LabeledValue(stringResource(R.string.relationship), it) }
                d.alternateAgentPhone?.let { LabeledValue(stringResource(R.string.phone), it) }
            }
        }
    }

    // Treatment Preferences section
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(stringResource(R.string.treatment_preferences), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)

            d.organDonation?.let { LabeledValue(stringResource(R.string.organ_donation), it) }
            d.lifeSupport?.let { LabeledValue(stringResource(R.string.life_support), it) }
            d.cpr?.let { LabeledValue("CPR", it) }
            d.ventilator?.let { LabeledValue(stringResource(R.string.ventilator), it) }
            d.feedingTube?.let { LabeledValue(stringResource(R.string.feeding_tube), it) }
            d.dialysisDirective?.let { LabeledValue(stringResource(R.string.dialysis), it) }
            d.bloodTransfusion?.let { LabeledValue(stringResource(R.string.blood_transfusion), it) }
        }
    }

    // Document Info section
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(stringResource(R.string.document_info), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)

            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked = d.documentSigned == true, onCheckedChange = null, enabled = false)
                Spacer(Modifier.width(8.dp))
                Text(stringResource(R.string.document_signed))
            }

            d.documentDate?.let { LabeledValue(stringResource(R.string.document_date), it) }
            d.additionalInstructions?.let { LabeledValue(stringResource(R.string.additional_instructions), it) }
        }
    }
}

// ── Editable View ───────────────────────────────────────────────────────────

@Composable
private fun EditableDirectiveContent(
    primaryAgentName: String, onPrimaryAgentNameChange: (String) -> Unit,
    primaryAgentRelationship: String, onPrimaryAgentRelationshipChange: (String) -> Unit,
    primaryAgentPhone: String, onPrimaryAgentPhoneChange: (String) -> Unit,
    primaryAgentEmail: String, onPrimaryAgentEmailChange: (String) -> Unit,
    alternateAgentName: String, onAlternateAgentNameChange: (String) -> Unit,
    alternateAgentRelationship: String, onAlternateAgentRelationshipChange: (String) -> Unit,
    alternateAgentPhone: String, onAlternateAgentPhoneChange: (String) -> Unit,
    organDonation: String, onOrganDonationChange: (String) -> Unit,
    lifeSupport: String, onLifeSupportChange: (String) -> Unit,
    cpr: String, onCprChange: (String) -> Unit,
    ventilator: String, onVentilatorChange: (String) -> Unit,
    feedingTube: String, onFeedingTubeChange: (String) -> Unit,
    dialysisDirective: String, onDialysisDirectiveChange: (String) -> Unit,
    bloodTransfusion: String, onBloodTransfusionChange: (String) -> Unit,
    documentSigned: Boolean, onDocumentSignedChange: (Boolean) -> Unit,
    documentDate: String, onDocumentDateChange: (String) -> Unit,
    additionalInstructions: String, onAdditionalInstructionsChange: (String) -> Unit
) {
    val treatmentOptions = listOf("Full Treatment", "Limited Treatment", "Comfort Care Only")

    // Healthcare Agent section
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(stringResource(R.string.healthcare_agent), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)

            Text(stringResource(R.string.primary_agent), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
            OutlinedTextField(value = primaryAgentName, onValueChange = onPrimaryAgentNameChange, label = { Text(stringResource(R.string.name)) }, modifier = Modifier.fillMaxWidth(), singleLine = true)
            OutlinedTextField(value = primaryAgentRelationship, onValueChange = onPrimaryAgentRelationshipChange, label = { Text(stringResource(R.string.relationship)) }, modifier = Modifier.fillMaxWidth(), singleLine = true)
            OutlinedTextField(value = primaryAgentPhone, onValueChange = onPrimaryAgentPhoneChange, label = { Text(stringResource(R.string.phone)) }, modifier = Modifier.fillMaxWidth(), singleLine = true)
            OutlinedTextField(value = primaryAgentEmail, onValueChange = onPrimaryAgentEmailChange, label = { Text(stringResource(R.string.email)) }, modifier = Modifier.fillMaxWidth(), singleLine = true)

            HorizontalDivider()
            Text(stringResource(R.string.alternate_agent), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
            OutlinedTextField(value = alternateAgentName, onValueChange = onAlternateAgentNameChange, label = { Text(stringResource(R.string.name)) }, modifier = Modifier.fillMaxWidth(), singleLine = true)
            OutlinedTextField(value = alternateAgentRelationship, onValueChange = onAlternateAgentRelationshipChange, label = { Text(stringResource(R.string.relationship)) }, modifier = Modifier.fillMaxWidth(), singleLine = true)
            OutlinedTextField(value = alternateAgentPhone, onValueChange = onAlternateAgentPhoneChange, label = { Text(stringResource(R.string.phone)) }, modifier = Modifier.fillMaxWidth(), singleLine = true)
        }
    }

    // Treatment Preferences section
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(stringResource(R.string.treatment_preferences), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)

            TreatmentDropdown(stringResource(R.string.organ_donation), organDonation, treatmentOptions, onOrganDonationChange)
            TreatmentDropdown(stringResource(R.string.life_support), lifeSupport, treatmentOptions, onLifeSupportChange)
            TreatmentDropdown("CPR", cpr, treatmentOptions, onCprChange)
            TreatmentDropdown(stringResource(R.string.ventilator), ventilator, treatmentOptions, onVentilatorChange)
            TreatmentDropdown(stringResource(R.string.feeding_tube), feedingTube, treatmentOptions, onFeedingTubeChange)
            TreatmentDropdown(stringResource(R.string.dialysis), dialysisDirective, treatmentOptions, onDialysisDirectiveChange)
            TreatmentDropdown(stringResource(R.string.blood_transfusion), bloodTransfusion, treatmentOptions, onBloodTransfusionChange)
        }
    }

    // Document Info section
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(stringResource(R.string.document_info), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)

            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked = documentSigned, onCheckedChange = onDocumentSignedChange)
                Spacer(Modifier.width(8.dp))
                Text(stringResource(R.string.document_signed))
            }

            OutlinedTextField(value = documentDate, onValueChange = onDocumentDateChange, label = { Text(stringResource(R.string.document_date_yyyy_mm_dd)) }, modifier = Modifier.fillMaxWidth(), singleLine = true, placeholder = { Text("2026-02-16") })
            OutlinedTextField(value = additionalInstructions, onValueChange = onAdditionalInstructionsChange, label = { Text(stringResource(R.string.additional_instructions)) }, modifier = Modifier.fillMaxWidth(), minLines = 3)
        }
    }
}

// ── Treatment Dropdown ──────────────────────────────────────────────────────

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun TreatmentDropdown(
    label: String,
    value: String,
    options: List<String>,
    onValueChange: (String) -> Unit
) {
    var expanded by remember { mutableStateOf(false) }

    ExposedDropdownMenuBox(
        expanded = expanded,
        onExpandedChange = { expanded = !expanded }
    ) {
        OutlinedTextField(
            value = value,
            onValueChange = {},
            readOnly = true,
            label = { Text(label) },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) },
            modifier = Modifier.fillMaxWidth().menuAnchor()
        )
        ExposedDropdownMenu(
            expanded = expanded,
            onDismissRequest = { expanded = false }
        ) {
            options.forEach { option ->
                DropdownMenuItem(
                    text = { Text(option) },
                    onClick = {
                        onValueChange(option)
                        expanded = false
                    }
                )
            }
        }
    }
}

// ── Shared Components ───────────────────────────────────────────────────────

@Composable
private fun LabeledValue(label: String, value: String) {
    Column {
        Text(label, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, style = MaterialTheme.typography.bodyMedium)
    }
}
