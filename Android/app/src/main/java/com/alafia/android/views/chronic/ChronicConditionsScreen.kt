// Copyright © 2026 Wole Akpose / 6igma Health Inc.
// All rights reserved. ALAFIA — proprietary and confidential.

package com.alafia.android.views.chronic

import android.widget.Toast
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.navigation.NavHostController
import com.alafia.android.api.ApiClient
import com.alafia.android.models.ChronicCondition
import kotlinx.coroutines.launch
import androidx.compose.ui.res.stringResource
import com.alafia.android.R

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChronicConditionsScreen(
    navController: NavHostController
) {
    var conditions by remember { mutableStateOf<List<ChronicCondition>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    // Separate from `conditions` on purpose: a Toast disappears and leaves the
    // empty-state copy on screen, which reads as "you have no conditions" when
    // the truth is "we could not load them" (CLAUDE.md §3aa).
    var loadError by remember { mutableStateOf<String?>(null) }
    var reloadToken by remember { mutableStateOf(0) }
    var showDialog by remember { mutableStateOf(false) }
    var editingCondition by remember { mutableStateOf<ChronicCondition?>(null) }
    val scope = rememberCoroutineScope()
    val context = LocalContext.current

    LaunchedEffect(reloadToken) {
        isLoading = true
        try {
            val apiService = ApiClient.getApiService()
            conditions = apiService.getChronicConditions(limit = 1000, isActive = true)
            loadError = null
        } catch (e: Exception) {
            loadError = "Could not load your conditions. This is a loading problem, " +
                "not an empty list — retry before assuming nothing is recorded."
        } finally {
            isLoading = false
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.chronic_conditions)) },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = stringResource(R.string.back))
                    }
                }
            )
        },
        floatingActionButton = {
            FloatingActionButton(
                onClick = {
                    editingCondition = null
                    showDialog = true
                }
            ) {
                Icon(Icons.Default.Add, contentDescription = stringResource(R.string.add_condition))
            }
        }
    ) { paddingValues ->
        if (isLoading) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(paddingValues),
                contentAlignment = Alignment.Center
            ) {
                CircularProgressIndicator()
            }
        } else if (loadError != null) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(paddingValues),
                contentAlignment = Alignment.Center
            ) {
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    modifier = Modifier.padding(24.dp)
                ) {
                    Text(
                        loadError!!,
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.error
                    )
                    Spacer(modifier = Modifier.height(12.dp))
                    Button(onClick = { reloadToken++ }) { Text(stringResource(R.string.retry)) }
                }
            }
        } else if (conditions.isEmpty()) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(paddingValues),
                contentAlignment = Alignment.Center
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(
                        stringResource(R.string.no_chronic_conditions),
                        style = MaterialTheme.typography.titleLarge,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        stringResource(R.string.tap_to_add_a_condition),
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        } else {
            LazyColumn(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(paddingValues),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                items(conditions) { condition ->
                    ConditionCard(
                        condition = condition,
                        onEdit = {
                            editingCondition = condition
                            showDialog = true
                        },
                        onDelete = {
                            scope.launch {
                                try {
                                    val apiService = ApiClient.getApiService()
                                    apiService.deleteChronicCondition(condition.id)
                                    // Deleting the last condition retires
                                    // screens as surely as adding one opens
                                    // them, and its therapy rows go with it
                                    // (FK ON DELETE CASCADE).
                                    com.alafia.android.SurfaceRefresh.announce()
                                    conditions = apiService.getChronicConditions(limit = 1000, isActive = true)
                                    Toast.makeText(context, "Condition deleted", Toast.LENGTH_SHORT).show()
                                } catch (e: Exception) {
                                    Toast.makeText(context, "Failed to delete: ${e.message}", Toast.LENGTH_SHORT).show()
                                }
                            }
                        }
                    )
                }
            }
        }
    }

    if (showDialog) {
        ConditionFormDialog(
            condition = editingCondition,
            onDismiss = { showDialog = false },
            onSave = { conditionData, therapies ->
                scope.launch {
                    try {
                        val apiService = ApiClient.getApiService()
                        val conditionId = if (editingCondition != null) {
                            apiService.updateChronicCondition(editingCondition!!.id, conditionData)
                            Toast.makeText(context, "Condition updated", Toast.LENGTH_SHORT).show()
                            editingCondition!!.id
                        } else {
                            val created = apiService.createChronicCondition(conditionData)
                            Toast.makeText(context, "Condition created", Toast.LENGTH_SHORT).show()
                            created.id
                        }
                        // The therapy switches, written AFTER the condition
                        // exists. Deliberately a second request and
                        // deliberately not fatal to the first: losing a
                        // therapy answer is bad, losing the condition the
                        // patient just typed because a therapy write failed is
                        // worse (§3c's argument for saving the meal before
                        // estimating it). The failure is REPORTED — silence
                        // would leave the patient believing they declared a
                        // treatment the navigation will not reflect (§3aa).
                        if (therapies.isNotEmpty()) {
                            try {
                                apiService.putConditionTherapies(
                                    conditionId,
                                    com.alafia.android.models.ConditionTherapiesUpdate(therapies),
                                )
                            } catch (e: Exception) {
                                Toast.makeText(
                                    context,
                                    context.getString(R.string.therapies_not_saved),
                                    Toast.LENGTH_LONG,
                                ).show()
                            }
                        }
                        // Declaring a condition or a therapy is what decides
                        // which clinical screens the navigation offers, so the
                        // nav must ask again rather than keep the answer it got
                        // on first composition (OPEN_ITEMS 39b).
                        com.alafia.android.SurfaceRefresh.announce()
                        conditions = apiService.getChronicConditions(limit = 1000, isActive = true)
                        showDialog = false
                    } catch (e: Exception) {
                        Toast.makeText(context, "Failed to save: ${e.message}", Toast.LENGTH_SHORT).show()
                    }
                }
            }
        )
    }
}

@Composable
fun ConditionCard(
    condition: ChronicCondition,
    onEdit: () -> Unit,
    onDelete: () -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(
            modifier = Modifier.padding(16.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Top
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            text = condition.conditionName,
                            style = MaterialTheme.typography.titleMedium
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        SeverityChip(severity = condition.severity)
                    }
                    
                    Spacer(modifier = Modifier.height(8.dp))
                    
                    Text(
                        text = condition.category.replace("_", " ").capitalize(),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    
                    condition.icd11Code?.let { icd11 ->
                        Text(
                            text = "ICD-11: $icd11" +
                                (condition.icd11Title?.let { " — $it" } ?: ""),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }

                    condition.icd10Code?.let { icd10 ->
                        Text(
                            text = "ICD-10: $icd10",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                    
                    condition.diagnosisDate?.let { date ->
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = stringResource(R.string.diagnosed, date),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                    
                    condition.primaryPhysician?.let { physician ->
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = stringResource(R.string.physician_2, physician),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
                
                Column(
                    horizontalAlignment = Alignment.End,
                    verticalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    TextButton(onClick = onEdit) {
                        Text(stringResource(R.string.edit))
                    }
                    TextButton(
                        onClick = onDelete,
                        colors = ButtonDefaults.textButtonColors(
                            contentColor = MaterialTheme.colorScheme.error
                        )
                    ) {
                        Text(stringResource(R.string.delete))
                    }
                }
            }
            
            condition.currentTreatmentPlan?.let { plan ->
                Spacer(modifier = Modifier.height(12.dp))
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surfaceVariant
                    )
                ) {
                    Column(modifier = Modifier.padding(12.dp)) {
                        Text(
                            text = stringResource(R.string.current_treatment_plan),
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = plan,
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                }
            }
        }
    }
}

@Composable
fun SeverityChip(severity: String) {
    val color = when (severity) {
        "mild" -> Color(0xFF4CAF50)
        "moderate" -> Color(0xFFFF9800)
        "severe" -> Color(0xFFF44336)
        "critical" -> Color(0xFFD32F2F)
        "remission" -> Color(0xFF2196F3)
        else -> Color.Gray
    }
    
    Surface(
        shape = MaterialTheme.shapes.small,
        color = color,
        modifier = Modifier.padding(2.dp)
    ) {
        Text(
            text = severity.uppercase(),
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
            style = MaterialTheme.typography.labelSmall,
            color = Color.White
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
/**
 * YYYY-MM-DD and nothing else.
 *
 * Deliberately NOT a locale-aware parser. §3aw records that the app's language
 * is an `attachBaseContext` choice and not `Locale.setDefault`, so a parser
 * keyed to either could disagree with what the keyboard produced — and §3bd
 * measured what that costs on a typed NUMBER. A wire date has exactly one
 * correct spelling, so this checks for that spelling rather than guessing
 * between two readings of the same keystrokes.
 *
 * It also rejects an impossible day: `2026-02-31` is shaped like a date and is
 * not one, and a server 422 on it is a refusal the patient cannot act on.
 */
internal fun isIsoDay(text: String): Boolean {
    if (!Regex("^\\d{4}-\\d{2}-\\d{2}$").matches(text)) return false
    return try {
        java.time.LocalDate.parse(text); true
    } catch (_: Exception) { false }
}

@Composable
fun ConditionFormDialog(
    condition: ChronicCondition?,
    onDismiss: () -> Unit,
    /** The condition AND its therapy statements — a switch belongs to a
     *  condition that must exist first, so the caller needs both. */
    onSave: (Map<String, Any?>, List<com.alafia.android.models.ConditionTherapyRow>) -> Unit
) {
    var conditionName by remember { mutableStateOf(condition?.conditionName ?: "") }
    var category by remember { mutableStateOf(condition?.category ?: "other") }
    var icd10Code by remember { mutableStateOf(condition?.icd10Code ?: "") }
    var icd11Code by remember { mutableStateOf(condition?.icd11Code ?: "") }
    var icd11Title by remember { mutableStateOf(condition?.icd11Title ?: "") }
    var severity by remember { mutableStateOf(condition?.severity ?: "moderate") }
    var diagnosisDate by remember { mutableStateOf(condition?.diagnosisDate ?: "") }
    var primaryPhysician by remember { mutableStateOf(condition?.primaryPhysician ?: "") }
    var treatmentPlan by remember { mutableStateOf(condition?.currentTreatmentPlan ?: "") }
    // Therapies this condition is treated with — a SWITCH over WHO's whole
    // therapy branch, not a set of ticked items.
    //
    // This was a Checkbox per therapy, and a checkbox cannot record three
    // states (§3at). Unticked meant BOTH "not on this therapy" and "nobody
    // asked"; the first retires a screen and the second must leave it alone.
    //
    //     absent from the map   nobody asked          -> nothing inferred
    //     false                 explicitly not on it  -> a measured ZERO
    //     true                  undergoing it         -> opens its screen
    var therapySwitches by remember { mutableStateOf<Map<String, Boolean>>(emptyMap()) }
    var therapyRegimens by remember { mutableStateOf<Map<String, String>>(emptyMap()) }
    // When a therapy STARTED, and when it stopped — `YYYY-MM-DD` or absent.
    // Both optional and NEVER inferred (TASKS 20b): flipping a switch to "not
    // on this" is otherwise the only way to say a therapy ended, and that
    // loses WHEN, which is what makes a history interpretable.
    //
    // ⚠️ A `receiving = false` with no end date cannot distinguish "never was
    // on it" from "stopped, date unknown". A real limit of a switch plus two
    // dates, recorded rather than papered over — an absent date means NOT
    // RECORDED, and a fourth state invented to hold it would be §3at's
    // collapse pointing the other way.
    var therapyStarted by remember { mutableStateOf<Map<String, String>>(emptyMap()) }
    var therapyEnded by remember { mutableStateOf<Map<String, String>>(emptyMap()) }
    // This dialog's OWN context. The screen's `context` (line 45) is a
    // different composable's scope and is not in scope here — the compiler
    // read the bare name as Kotlin's `context(...)` declaration and said so.
    val dialogContext = LocalContext.current
    // §3aa: an unreadable list must never render as a screen full of zeros.
    var therapyLoadFailed by remember { mutableStateOf(false) }
    var notes by remember { mutableStateOf(condition?.notes ?: "") }
    
    val categories = listOf(
        "cancer", "renal", "diabetes", "blood_disorder",
        "cardiovascular", "respiratory", "autoimmune",
        "neurological", "endocrine", "other"
    )

    // Fetched from the server, which reads it out of the bundled WHO ICD-11
    // catalog. This screen used to hold its OWN copy — one of four, alongside
    // the backend, web and iOS — while WHO already codes every entry.
    // §3ad: the catalog is the authority and a code is never typed from memory.
    //
    // Empty until it loads, and empty if the request fails: the field simply
    // does not render, which is correct — a guessed list is worse than none.
    var therapyOptions by remember {
        mutableStateOf<List<com.alafia.android.models.TherapyOption>>(emptyList())
    }
    LaunchedEffect(condition?.id) {
        val api = com.alafia.android.api.ApiClient.getApiService()
        try {
            therapyOptions = api.getTherapyOptions().options
        } catch (_: Exception) { }
        // The stored statements, read back before the form is touched. A
        // control that never loads its stored value shows its default, which
        // reads as NEVER RECORDED, and the next save overwrites what was
        // there — §3av, measured on `machine_total_time_minutes`.
        val existing = condition?.id ?: return@LaunchedEffect
        try {
            val rows = api.getConditionTherapies(existing).therapies
            therapySwitches = rows.associate { it.therapyCode to it.receiving }
            therapyRegimens = rows.mapNotNull { row ->
                row.regimen?.let { row.therapyCode to it }
            }.toMap()
            // Loaded, or the field draws blank — which reads as NOT RECORDED —
            // and the next save overwrites a stored date (§3av).
            therapyStarted = rows.mapNotNull { row ->
                row.startedOn?.take(10)?.takeIf { it.isNotBlank() }?.let { row.therapyCode to it }
            }.toMap()
            therapyEnded = rows.mapNotNull { row ->
                row.endedOn?.take(10)?.takeIf { it.isNotBlank() }?.let { row.therapyCode to it }
            }.toMap()
            therapyLoadFailed = false
        } catch (_: Exception) {
            // Never guess. Every therapy stays UNANSWERED, so the save sends
            // nothing for those codes and what is stored survives.
            therapyLoadFailed = true
        }
    }
    
    val severities = listOf("mild", "moderate", "severe", "critical", "remission")
    
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (condition == null) stringResource(R.string.add_condition) else stringResource(R.string.edit_condition)) },
        text = {
            LazyColumn(
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                item {
                    OutlinedTextField(
                        value = conditionName,
                        onValueChange = { conditionName = it },
                        label = { Text(stringResource(R.string.condition_name)) },
                        modifier = Modifier.fillMaxWidth()
                    )
                }
                
                item {
                    var categoryExpanded by remember { mutableStateOf(false) }
                    ExposedDropdownMenuBox(
                        expanded = categoryExpanded,
                        onExpandedChange = { categoryExpanded = it }
                    ) {
                        OutlinedTextField(
                            value = category.replace("_", " ").capitalize(),
                            onValueChange = {},
                            readOnly = true,
                            label = { Text(stringResource(R.string.category)) },
                            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = categoryExpanded) },
                            modifier = Modifier
                                .menuAnchor()
                                .fillMaxWidth()
                        )
                        ExposedDropdownMenu(
                            expanded = categoryExpanded,
                            onDismissRequest = { categoryExpanded = false }
                        ) {
                            categories.forEach { cat ->
                                DropdownMenuItem(
                                    text = { Text(cat.replace("_", " ").capitalize()) },
                                    onClick = {
                                        category = cat
                                        categoryExpanded = false
                                    }
                                )
                            }
                        }
                    }
                }
                
                item {
                    var severityExpanded by remember { mutableStateOf(false) }
                    ExposedDropdownMenuBox(
                        expanded = severityExpanded,
                        onExpandedChange = { severityExpanded = it }
                    ) {
                        OutlinedTextField(
                            value = severity.capitalize(),
                            onValueChange = {},
                            readOnly = true,
                            label = { Text(stringResource(R.string.severity)) },
                            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = severityExpanded) },
                            modifier = Modifier
                                .menuAnchor()
                                .fillMaxWidth()
                        )
                        ExposedDropdownMenu(
                            expanded = severityExpanded,
                            onDismissRequest = { severityExpanded = false }
                        ) {
                            severities.forEach { sev ->
                                DropdownMenuItem(
                                    text = { Text(sev.capitalize()) },
                                    onClick = {
                                        severity = sev
                                        severityExpanded = false
                                    }
                                )
                            }
                        }
                    }
                }
                
                item {
                    Icd11PickerField(
                        code = icd11Code,
                        title = icd11Title,
                        onChange = { c, t -> icd11Code = c; icd11Title = t }
                    )
                }

                item {
                    OutlinedTextField(
                        value = icd10Code,
                        onValueChange = { icd10Code = it },
                        label = { Text(stringResource(R.string.icd_10_code)) },
                        modifier = Modifier.fillMaxWidth()
                    )
                }
                
                item {
                    OutlinedTextField(
                        value = diagnosisDate,
                        onValueChange = { diagnosisDate = it },
                        label = { Text(stringResource(R.string.diagnosis_date_yyyy_mm_dd)) },
                        modifier = Modifier.fillMaxWidth()
                    )
                }
                
                item {
                    OutlinedTextField(
                        value = primaryPhysician,
                        onValueChange = { primaryPhysician = it },
                        label = { Text(stringResource(R.string.primary_physician)) },
                        modifier = Modifier.fillMaxWidth()
                    )
                }
                
                item {
                    Column(modifier = Modifier.fillMaxWidth()) {
                        Text(
                            stringResource(R.string.therapy_types),
                            style = MaterialTheme.typography.labelLarge
                        )
                        Text(
                            stringResource(R.string.therapy_switch_help),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        if (therapyLoadFailed) {
                            Text(
                                stringResource(R.string.therapies_not_loaded),
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.error
                            )
                        }
                        // Grouping is the SERVER's (`group`/`group_title`).
                        // Splitting a code on its dot here would make this
                        // screen decide what a code means (§3ad).
                        therapyOptions.groupBy { it.group ?: it.code }.forEach { (groupCode, options) ->
                            val heading = options.first().groupTitle ?: groupCode
                            val answered = options.any { it.code in therapySwitches }
                            var expanded by remember(groupCode) { mutableStateOf(answered) }
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clickable { expanded = !expanded }
                                    .padding(vertical = 6.dp)
                            ) {
                                Icon(
                                    if (expanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                                    contentDescription = null
                                )
                                Spacer(Modifier.width(4.dp))
                                // WHO's own heading, or the shared prefix of
                                // its members where the root has no title.
                                Text(heading, style = MaterialTheme.typography.labelMedium)
                                if (answered) {
                                    Text(
                                        stringResource(R.string.therapy_group_answered),
                                        style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.primary
                                    )
                                }
                            }
                            if (expanded) {
                                options.forEach { option ->
                                    val state: Boolean? = therapySwitches[option.code]
                                    Column(modifier = Modifier.padding(start = 12.dp, bottom = 8.dp)) {
                                        // WHO's own title; nothing relabelled.
                                        Text(option.title, style = MaterialTheme.typography.bodySmall)
                                        Row {
                                            listOf(
                                                true to stringResource(R.string.therapy_on),
                                                false to stringResource(R.string.therapy_off),
                                                null to stringResource(R.string.therapy_unanswered),
                                            ).forEach { (value, label) ->
                                                FilterChip(
                                                    selected = state == value,
                                                    onClick = {
                                                        therapySwitches = if (value == null) {
                                                            // Back to unanswered. REMOVING the key is
                                                            // the point: a client cannot express
                                                            // "unknown" by sending false, so it stops
                                                            // sending the entry at all.
                                                            therapySwitches - option.code
                                                        } else {
                                                            therapySwitches + (option.code to value)
                                                        }
                                                        if (value != true) {
                                                            therapyRegimens = therapyRegimens - option.code
                                                        }
                                                    },
                                                    label = { Text(label, style = MaterialTheme.typography.labelSmall) },
                                                    modifier = Modifier.padding(end = 4.dp)
                                                )
                                            }
                                        }
                                        // Compounding: therapies given as ONE
                                        // treatment share a label. It records
                                        // what is given together and claims
                                        // nothing about the effect.
                                        if (state == true) {
                                            OutlinedTextField(
                                                value = therapyRegimens[option.code] ?: "",
                                                onValueChange = {
                                                    therapyRegimens = therapyRegimens + (option.code to it)
                                                },
                                                label = { Text(stringResource(R.string.therapy_regimen_placeholder)) },
                                                textStyle = MaterialTheme.typography.bodySmall,
                                                modifier = Modifier.fillMaxWidth()
                                            )
                                            // A typed YYYY-MM-DD, the same
                                            // idiom this form already uses for
                                            // the diagnosis date — and the one
                                            // that leaves an untouched field
                                            // EMPTY rather than stamping today
                                            // onto a clinical date nobody
                                            // supplied.
                                            OutlinedTextField(
                                                value = therapyStarted[option.code] ?: "",
                                                onValueChange = {
                                                    therapyStarted = therapyStarted + (option.code to it)
                                                },
                                                label = { Text(stringResource(R.string.therapy_started_on) + " (YYYY-MM-DD)") },
                                                textStyle = MaterialTheme.typography.bodySmall,
                                                modifier = Modifier.fillMaxWidth()
                                            )
                                        }
                                        if (state == false) {
                                            OutlinedTextField(
                                                value = therapyEnded[option.code] ?: "",
                                                onValueChange = {
                                                    therapyEnded = therapyEnded + (option.code to it)
                                                },
                                                label = { Text(stringResource(R.string.therapy_ended_on) + " (YYYY-MM-DD)") },
                                                textStyle = MaterialTheme.typography.bodySmall,
                                                modifier = Modifier.fillMaxWidth()
                                            )
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                item {
                    OutlinedTextField(
                        value = treatmentPlan,
                        onValueChange = { treatmentPlan = it },
                        label = { Text(stringResource(R.string.treatment_plan)) },
                        modifier = Modifier.fillMaxWidth(),
                        minLines = 3
                    )
                }
                
                item {
                    OutlinedTextField(
                        value = notes,
                        onValueChange = { notes = it },
                        label = { Text(stringResource(R.string.notes)) },
                        modifier = Modifier.fillMaxWidth(),
                        minLines = 3
                    )
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    val data = mutableMapOf<String, Any?>(
                        "condition_name" to conditionName,
                        "category" to category,
                        "severity" to severity,
                        "is_active" to true
                    )
                    if (icd10Code.isNotBlank()) data["icd10_code"] = icd10Code
                    // Sent even when blank (as null) so clearing a code on an
                    // edit actually removes it; omitting the key would leave
                    // the old code in place. The backend derives the title.
                    data["icd11_code"] = icd11Code.ifBlank { null }
                    if (diagnosisDate.isNotBlank()) data["diagnosis_date"] = diagnosisDate
                    if (primaryPhysician.isNotBlank()) data["primary_physician"] = primaryPhysician
                    if (treatmentPlan.isNotBlank()) data["current_treatment_plan"] = treatmentPlan
                    if (notes.isNotBlank()) data["notes"] = notes

                    // Nothing writes the comma-separated `therapy_types`
                    // column any more — the switch table is the authority, and
                    // two homes for one fact is the drift this codebase keeps
                    // paying for. Not SENDING the key leaves what is stored
                    // there, which is deliberate: a declaration made before
                    // the table existed stays readable until a switch speaks
                    // for that code.
                    // §3av: a field holding data but no usable value must
                    // REFUSE the save and say which, never be discarded. A
                    // half-typed date silently dropped is how the web
                    // flowsheet ate intradialytic readings; a half-typed date
                    // SENT is a 422 the patient cannot act on.
                    val badDate = (therapyStarted + therapyEnded).entries
                        .firstOrNull { (_, v) -> v.isNotBlank() && !isIsoDay(v) }
                    if (badDate != null) {
                        Toast.makeText(
                            dialogContext,
                            dialogContext.getString(
                                R.string.therapy_date_unreadable, badDate.value),
                            Toast.LENGTH_LONG,
                        ).show()
                        return@TextButton
                    }
                    onSave(data, therapySwitches.keys.sorted().map { code ->
                        com.alafia.android.models.ConditionTherapyRow(
                            therapyCode = code,
                            receiving = therapySwitches[code] == true,
                            regimen = therapyRegimens[code]?.takeIf { it.isNotBlank() },
                            startedOn = therapyStarted[code]?.takeIf { it.isNotBlank() },
                            endedOn = therapyEnded[code]?.takeIf { it.isNotBlank() },
                        )
                    })
                },
                enabled = conditionName.isNotBlank()
            ) {
                Text(if (condition == null) stringResource(R.string.create) else stringResource(R.string.update))
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text(stringResource(R.string.cancel))
            }
        }
    )
}
