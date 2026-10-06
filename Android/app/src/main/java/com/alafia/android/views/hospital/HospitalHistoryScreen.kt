// Copyright © 2026 Wole Akpose / 6igma Health Inc.
// All rights reserved. ALAFIA — proprietary and confidential.

package com.alafia.android.views.hospital

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.navigation.NavHostController
import com.alafia.android.R
import com.alafia.android.api.ApiClient
import com.alafia.android.models.HospitalHistoryResponse
import com.alafia.android.models.HospitalizationView
import com.alafia.android.models.ProcedureView
import kotlinx.coroutines.launch

/**
 * Hospital stays and surgical procedures.
 *
 * Lasting effects lead the screen, ahead of any list of admissions, because
 * that is the half a patient and a clinician act on: a parathyroidectomy
 * explains a calcium requirement no guideline default can express, and it
 * stays true decades after the admission is history.
 *
 * Stays and procedures are drawn as SEPARATE sections. A procedure may have no
 * admission at all — day-case surgery, or anything recorded years later — so a
 * screen that only walked stays and their nested procedures would silently
 * omit exactly those operations.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HospitalHistoryScreen(
    navController: NavHostController
) {
    var history by remember { mutableStateOf(HospitalHistoryResponse()) }
    var isLoading by remember { mutableStateOf(true) }
    // Separate from `history` on purpose: a failed load must never render as
    // "no hospital history recorded", which reads as a clinical fact when the
    // truth is that we could not fetch it (§3aa).
    var loadError by remember { mutableStateOf<String?>(null) }
    var reloadToken by remember { mutableIntStateOf(0) }
    // READ by the dialog below. A flag nothing observes is a dead control.
    var showAddProcedure by remember { mutableStateOf(false) }
    var saveError by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    // Captured HERE, in composable scope. `stringResource` cannot be called
    // from the save lambda, and hard-coding the sentence there would put
    // untranslatable English in the one place a patient reads on failure.
    val nameRequired = stringResource(R.string.hospital_name_required)
    // Write parity with web and iOS: both offer an add-stay form as well as an
    // add-operation one, so Android does too. A read-only platform beside two
    // writable ones is the parity gap §3 refuses to let a disclosure satisfy.
    var showAddStay by remember { mutableStateOf(false) }
    val admittedRequired = stringResource(R.string.hospital_admitted_required)

    LaunchedEffect(reloadToken) {
        isLoading = true
        try {
            history = ApiClient.getApiService().getHospitalHistory()
            loadError = null
        } catch (e: Exception) {
            loadError = e.message ?: "unknown error"
        }
        isLoading = false
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.hospital_history)) },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack,
                             contentDescription = stringResource(R.string.back))
                    }
                }
            )
        },
        floatingActionButton = {
            // An in-screen dialog, NOT `navigate("hospital-add")`. That route
            // does not exist, so the button would have crashed on tap — a
            // control wired to nothing, which compiles perfectly (§3ar).
            FloatingActionButton(onClick = { showAddProcedure = true }) {
                Icon(Icons.Default.Add,
                     contentDescription = stringResource(R.string.hospital_add_procedure))
            }
        }
    ) { padding ->
        when {
            isLoading && history.stays.isEmpty() && history.procedures.isEmpty() -> {
                Column(
                    modifier = Modifier.fillMaxSize().padding(padding),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center
                ) { CircularProgressIndicator() }
            }
            else -> {
                LazyColumn(
                    modifier = Modifier.fillMaxSize().padding(padding).padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    loadError?.let { message ->
                        item {
                            Card {
                                Column(Modifier.padding(16.dp)) {
                                    Text(stringResource(R.string.hospital_could_not_load),
                                         style = MaterialTheme.typography.titleSmall)
                                    Text(message, style = MaterialTheme.typography.bodySmall)
                                    Button(onClick = { reloadToken++ }) {
                                        Text(stringResource(R.string.retry))
                                    }
                                }
                            }
                        }
                    }

                    if (history.lastingEffects.isNotEmpty()) {
                        item {
                            Card(colors = CardDefaults.cardColors(
                                containerColor = MaterialTheme.colorScheme.secondaryContainer
                            )) {
                                Column(Modifier.padding(16.dp)) {
                                    Text(stringResource(R.string.hospital_lasting_effects),
                                         style = MaterialTheme.typography.titleSmall)
                                    history.lastingEffects.forEach { effect ->
                                        Text("• $effect",
                                             style = MaterialTheme.typography.bodyMedium)
                                    }
                                    Text(stringResource(R.string.hospital_lasting_effects_note),
                                         style = MaterialTheme.typography.bodySmall)
                                }
                            }
                        }
                    }

                    item {
                        Button(onClick = { showAddStay = true }) {
                            Text(stringResource(R.string.hospital_add_stay))
                        }
                    }

                    item {
                        Text(stringResource(R.string.hospital_stays),
                             style = MaterialTheme.typography.titleMedium)
                    }
                    if (history.stays.isEmpty() && loadError == null) {
                        item {
                            Text(stringResource(R.string.hospital_no_stays),
                                 style = MaterialTheme.typography.bodyMedium)
                        }
                    }
                    items(history.stays) { stay -> StayCard(stay) }

                    item {
                        Column {
                            Text(stringResource(R.string.hospital_all_procedures),
                                 style = MaterialTheme.typography.titleMedium)
                            Text(stringResource(R.string.hospital_all_procedures_note),
                                 style = MaterialTheme.typography.bodySmall)
                        }
                    }
                    if (history.procedures.isEmpty() && loadError == null) {
                        item {
                            Text(stringResource(R.string.hospital_no_procedures),
                                 style = MaterialTheme.typography.bodyMedium)
                        }
                    }
                    items(history.procedures) { procedure -> ProcedureCard(procedure) }
                }
            }
        }
    }

    // The flag the FAB sets is READ here. Without this the button would be a
    // dead control that compiles perfectly (§3ar).
    if (showAddStay) {
        AddStayDialog(
            error = saveError,
            onDismiss = { showAddStay = false; saveError = null },
            onSave = { body ->
                scope.launch {
                    if (body["admitted_at"] == null) {
                        saveError = admittedRequired
                        return@launch
                    }
                    try {
                        ApiClient.getApiService().createHospitalStay(body)
                        showAddStay = false
                        saveError = null
                        reloadToken++
                    } catch (e: Exception) {
                        saveError = e.message ?: "unknown error"
                    }
                }
            }
        )
    }

    if (showAddProcedure) {
        AddProcedureDialog(
            error = saveError,
            onDismiss = { showAddProcedure = false; saveError = null },
            onSave = { body ->
                scope.launch {
                    val name = (body["name"] as? String).orEmpty()
                    if (name.isBlank()) {
                        saveError = nameRequired
                        return@launch
                    }
                    try {
                        ApiClient.getApiService().createSurgicalProcedure(body)
                        showAddProcedure = false
                        saveError = null
                        reloadToken++
                    } catch (e: Exception) {
                        // The server's own sentence, not a generic failure: a
                        // guard that cannot explain itself gets blamed for the
                        // thing it did not do (§3aj).
                        saveError = e.message ?: "unknown error"
                    }
                }
            }
        )
    }
}

/**
 * Add an operation.
 *
 * Deliberately the operation form and not the stay form: a procedure is the
 * row this feature exists for, and it is the one that can stand alone. A stay
 * with no operation is far less often the thing a patient needs to record
 * years after the fact.
 *
 * Dates are typed as `YYYY-MM-DD` and sent as midnight local. The API column
 * is naive, so no offset is attached — an offset would make it a different
 * instant from the one the patient meant.
 */
@Composable
private fun AddProcedureDialog(
    onDismiss: () -> Unit,
    onSave: (Map<String, Any?>) -> Unit,
    error: String?
) {
    var name by remember { mutableStateOf("") }
    var performed by remember { mutableStateOf("") }
    var code by remember { mutableStateOf("") }
    var codeSystem by remember { mutableStateOf("") }
    var bodySite by remember { mutableStateOf("") }
    var ongoingEffects by remember { mutableStateOf("") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.hospital_add_procedure)) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = name, onValueChange = { name = it },
                    label = { Text(stringResource(R.string.hospital_procedure_name)) },
                    singleLine = true
                )
                OutlinedTextField(
                    value = performed, onValueChange = { performed = it },
                    label = { Text(stringResource(R.string.hospital_performed)) },
                    singleLine = true
                )
                OutlinedTextField(
                    value = code, onValueChange = { code = it },
                    label = { Text(stringResource(R.string.hospital_code)) },
                    singleLine = true
                )
                OutlinedTextField(
                    value = codeSystem, onValueChange = { codeSystem = it },
                    label = { Text(stringResource(R.string.hospital_code_system)) },
                    singleLine = true
                )
                Text(stringResource(R.string.hospital_code_system_help),
                     style = MaterialTheme.typography.bodySmall)
                OutlinedTextField(
                    value = bodySite, onValueChange = { bodySite = it },
                    label = { Text(stringResource(R.string.hospital_body_site)) },
                    singleLine = true
                )
                OutlinedTextField(
                    value = ongoingEffects, onValueChange = { ongoingEffects = it },
                    label = { Text(stringResource(R.string.hospital_ongoing_effects)) }
                )
                Text(stringResource(R.string.hospital_ongoing_effects_help),
                     style = MaterialTheme.typography.bodySmall)
                Text(stringResource(R.string.hospital_procedure_no_stay_note),
                     style = MaterialTheme.typography.bodySmall)
                error?.let {
                    Text(it, style = MaterialTheme.typography.bodySmall,
                         color = MaterialTheme.colorScheme.error)
                }
            }
        },
        confirmButton = {
            Button(onClick = {
                // Blanks are DROPPED, never sent: the enums reject "" and the
                // server would answer 422 for a field left alone.
                val body = mutableMapOf<String, Any?>("name" to name.trim())
                if (performed.isNotBlank()) body["performed_at"] = "${performed.trim()}T00:00:00"
                if (code.isNotBlank()) body["code"] = code.trim()
                if (codeSystem.isNotBlank()) body["code_system"] = codeSystem.trim()
                if (bodySite.isNotBlank()) body["body_site"] = bodySite.trim()
                if (ongoingEffects.isNotBlank()) body["ongoing_effects"] = ongoingEffects.trim()
                onSave(body)
            }) { Text(stringResource(R.string.hospital_save)) }
        },
        dismissButton = {
            Button(onClick = onDismiss) { Text(stringResource(R.string.hospital_cancel)) }
        }
    )
}

/**
 * Add a hospital stay.
 *
 * `admitted` is the only required field — a stay is meaningful before anyone
 * knows when it ended, and demanding a discharge date would refuse the current
 * admission, which is the one that matters most. The server refuses a
 * discharge that precedes the admission with a 422, and its sentence is shown
 * rather than a generic failure.
 */
@Composable
private fun AddStayDialog(
    onDismiss: () -> Unit,
    onSave: (Map<String, Any?>) -> Unit,
    error: String?
) {
    var admitted by remember { mutableStateOf("") }
    var discharged by remember { mutableStateOf("") }
    var facility by remember { mutableStateOf("") }
    var reason by remember { mutableStateOf("") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.hospital_add_stay)) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = admitted, onValueChange = { admitted = it },
                    label = { Text(stringResource(R.string.hospital_admitted)) },
                    singleLine = true
                )
                OutlinedTextField(
                    value = discharged, onValueChange = { discharged = it },
                    label = { Text(stringResource(R.string.hospital_discharged)) },
                    singleLine = true
                )
                OutlinedTextField(
                    value = facility, onValueChange = { facility = it },
                    label = { Text(stringResource(R.string.hospital_facility)) },
                    singleLine = true
                )
                OutlinedTextField(
                    value = reason, onValueChange = { reason = it },
                    label = { Text(stringResource(R.string.hospital_reason)) },
                    singleLine = true
                )
                error?.let {
                    Text(it, style = MaterialTheme.typography.bodySmall,
                         color = MaterialTheme.colorScheme.error)
                }
            }
        },
        confirmButton = {
            Button(onClick = {
                val body = mutableMapOf<String, Any?>()
                if (admitted.isNotBlank()) body["admitted_at"] = "${admitted.trim()}T00:00:00"
                if (discharged.isNotBlank()) body["discharged_at"] = "${discharged.trim()}T00:00:00"
                if (facility.isNotBlank()) body["facility_name"] = facility.trim()
                if (reason.isNotBlank()) body["reason"] = reason.trim()
                onSave(body)
            }) { Text(stringResource(R.string.hospital_save)) }
        },
        dismissButton = {
            Button(onClick = onDismiss) { Text(stringResource(R.string.hospital_cancel)) }
        }
    )
}

@Composable
private fun StayCard(stay: HospitalizationView) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(stay.admitted, style = MaterialTheme.typography.titleSmall)
                stay.discharged?.let {
                    Text("→ $it", style = MaterialTheme.typography.titleSmall)
                }
                // Null while the patient is still an inpatient — never a
                // length measured against today.
                stay.nights?.let {
                    Text(stringResource(R.string.hospital_nights_count, it),
                         style = MaterialTheme.typography.bodySmall)
                }
            }
            stay.facility?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
            stay.reason?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
            stay.diagnosis?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
            val meta = listOfNotNull(stay.admissionType, stay.status, stay.source)
            if (meta.isNotEmpty()) {
                Text(meta.joinToString(" · "),
                     style = MaterialTheme.typography.bodySmall)
            }
            stay.procedures.forEach { procedure ->
                Text("• ${procedure.name}" + (procedure.performed?.let { " · $it" } ?: ""),
                     style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

@Composable
private fun ProcedureCard(procedure: ProcedureView) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Text(procedure.name, style = MaterialTheme.typography.titleSmall)
            val detail = listOfNotNull(
                procedure.performed, procedure.bodySite, procedure.outcome)
            if (detail.isNotEmpty()) {
                Text(detail.joinToString(" · "),
                     style = MaterialTheme.typography.bodySmall)
            }
            // A code is unusable without the vocabulary that issued it.
            procedure.code?.let { code ->
                Text(code + (procedure.codeSystem?.let { " ($it)" } ?: ""),
                     style = MaterialTheme.typography.bodySmall)
            }
            Text(
                procedure.admission?.let {
                    stringResource(R.string.hospital_during, it)
                } ?: stringResource(R.string.hospital_no_stay_recorded),
                style = MaterialTheme.typography.bodySmall
            )
            procedure.ongoingEffects?.let { effect ->
                Text(effect,
                     style = MaterialTheme.typography.bodyMedium,
                     color = MaterialTheme.colorScheme.primary)
            }
        }
    }
}
