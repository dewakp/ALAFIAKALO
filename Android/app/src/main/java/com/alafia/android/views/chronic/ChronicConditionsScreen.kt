package com.alafia.android.views.chronic

import android.widget.Toast
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ArrowBack
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
                title = { Text("Chronic Conditions") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
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
                Icon(Icons.Default.Add, contentDescription = "Add Condition")
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
                    Button(onClick = { reloadToken++ }) { Text("Retry") }
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
                        "No Chronic Conditions",
                        style = MaterialTheme.typography.titleLarge,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        "Tap + to add a condition",
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
            onSave = { conditionData ->
                scope.launch {
                    try {
                        val apiService = ApiClient.getApiService()
                        if (editingCondition != null) {
                            apiService.updateChronicCondition(editingCondition!!.id, conditionData)
                            Toast.makeText(context, "Condition updated", Toast.LENGTH_SHORT).show()
                        } else {
                            apiService.createChronicCondition(conditionData)
                            Toast.makeText(context, "Condition created", Toast.LENGTH_SHORT).show()
                        }
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
                            text = "Diagnosed: $date",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                    
                    condition.primaryPhysician?.let { physician ->
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = "Physician: $physician",
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
                        Text("Edit")
                    }
                    TextButton(
                        onClick = onDelete,
                        colors = ButtonDefaults.textButtonColors(
                            contentColor = MaterialTheme.colorScheme.error
                        )
                    ) {
                        Text("Delete")
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
                            text = "Current Treatment Plan:",
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
@Composable
fun ConditionFormDialog(
    condition: ChronicCondition?,
    onDismiss: () -> Unit,
    onSave: (Map<String, Any?>) -> Unit
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
    var notes by remember { mutableStateOf(condition?.notes ?: "") }
    
    val categories = listOf(
        "cancer", "renal", "diabetes", "blood_disorder",
        "cardiovascular", "respiratory", "autoimmune",
        "neurological", "endocrine", "other"
    )
    
    val severities = listOf("mild", "moderate", "severe", "critical", "remission")
    
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (condition == null) "Add Condition" else "Edit Condition") },
        text = {
            LazyColumn(
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                item {
                    OutlinedTextField(
                        value = conditionName,
                        onValueChange = { conditionName = it },
                        label = { Text("Condition Name *") },
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
                            label = { Text("Category") },
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
                            label = { Text("Severity") },
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
                        label = { Text("ICD-10 Code") },
                        modifier = Modifier.fillMaxWidth()
                    )
                }
                
                item {
                    OutlinedTextField(
                        value = diagnosisDate,
                        onValueChange = { diagnosisDate = it },
                        label = { Text("Diagnosis Date (YYYY-MM-DD)") },
                        modifier = Modifier.fillMaxWidth()
                    )
                }
                
                item {
                    OutlinedTextField(
                        value = primaryPhysician,
                        onValueChange = { primaryPhysician = it },
                        label = { Text("Primary Physician") },
                        modifier = Modifier.fillMaxWidth()
                    )
                }
                
                item {
                    OutlinedTextField(
                        value = treatmentPlan,
                        onValueChange = { treatmentPlan = it },
                        label = { Text("Treatment Plan") },
                        modifier = Modifier.fillMaxWidth(),
                        minLines = 3
                    )
                }
                
                item {
                    OutlinedTextField(
                        value = notes,
                        onValueChange = { notes = it },
                        label = { Text("Notes") },
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
                    
                    onSave(data)
                },
                enabled = conditionName.isNotBlank()
            ) {
                Text(if (condition == null) "Create" else "Update")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel")
            }
        }
    )
}
