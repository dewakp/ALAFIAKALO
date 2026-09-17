@file:OptIn(ExperimentalMaterial3Api::class)

package com.alafia.android.views.labs
import com.alafia.android.util.ErrorUtil

import android.widget.Toast
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
import com.alafia.android.api.ApiClient
import com.alafia.android.models.LabResult
import com.alafia.android.schemas.LabResultRequest
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import androidx.navigation.NavHostController
import androidx.compose.ui.res.stringResource
import com.alafia.android.R

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LabsScreen(navController: NavHostController) {
    var results by remember { mutableStateOf<List<LabResult>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    var showForm by remember { mutableStateOf(false) }
    var showAddMenu by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    fun loadResults() {
        scope.launch {
            isLoading = true
            try {
                results = ApiClient.getApiService().getLabResults()
            } catch (e: Exception) {
                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
            }
            isLoading = false
        }
    }

    LaunchedEffect(Unit) { loadResults() }

    Scaffold(
        topBar = { TopAppBar(
                title = { Text(stringResource(R.string.labs)) },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = stringResource(R.string.back))
                    }
                }
            ) },
        floatingActionButton = {
            Box {
                FloatingActionButton(onClick = { showAddMenu = true }) {
                    Icon(Icons.Default.Add, contentDescription = stringResource(R.string.add_result))
                }
                DropdownMenu(expanded = showAddMenu, onDismissRequest = { showAddMenu = false }) {
                    DropdownMenuItem(
                        text = { Text(stringResource(R.string.enter_a_result)) },
                        leadingIcon = { Icon(Icons.Default.Edit, contentDescription = null) },
                        onClick = { showAddMenu = false; showForm = true },
                    )
                    // Document import, on its Import tab: the report is parsed and
                    // staged for review; nothing is saved until the patient confirms.
                    DropdownMenuItem(
                        text = { Text(stringResource(R.string.upload_lab_report_pdf)) },
                        leadingIcon = { Icon(Icons.Default.UploadFile, contentDescription = null) },
                        onClick = { showAddMenu = false; navController.navigate("pdf-tools") },
                    )
                }
            }
        }
    ) { padding ->
        if (isLoading) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        } else if (results.isEmpty()) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(Icons.Default.Science, contentDescription = stringResource(R.string.no_results), modifier = Modifier.size(64.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
                    Spacer(Modifier.height(12.dp))
                    Text(stringResource(R.string.no_lab_results), style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(stringResource(R.string.tap_to_add_a_result), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(results, key = { it.id }) { result ->
                    LabResultCard(
                        result = result,
                        onDelete = {
                            scope.launch {
                                try {
                                    ApiClient.getApiService().deleteLabResult(result.id)
                                    loadResults()
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
        AddLabResultDialog(
            onDismiss = { showForm = false },
            onSave = { request ->
                scope.launch {
                    try {
                        ApiClient.getApiService().createLabResult(request)
                        showForm = false
                        loadResults()
                        Toast.makeText(context, "Result added!", Toast.LENGTH_SHORT).show()
                    } catch (e: Exception) {
                        Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                    }
                }
            }
        )
    }
}

@Composable
private fun LabResultCard(result: LabResult, onDelete: () -> Unit) {
    val statusColor = when (result.status.lowercase()) {
        "normal", "final" -> Color(0xFF4CAF50)
        "abnormal" -> Color(0xFFFF9800)
        "critical" -> Color(0xFFF44336)
        else -> MaterialTheme.colorScheme.onSurfaceVariant
    }

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(result.shownName, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                    // The report's own wording under the analyte's name ("ALP" under
                    // Alkaline Phosphatase), so the row can still be found on the document.
                    result.reportedAs?.let {
                        Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    Text(result.test_date, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Surface(color = statusColor.copy(alpha = 0.15f), shape = MaterialTheme.shapes.small) {
                    Text(
                        result.status.replaceFirstChar { it.uppercase() },
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
                        color = statusColor,
                        fontWeight = FontWeight.SemiBold,
                        style = MaterialTheme.typography.labelSmall
                    )
                }
                IconButton(onClick = onDelete) {
                    Icon(Icons.Default.Delete, "Delete", tint = MaterialTheme.colorScheme.error)
                }
            }
            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                val valueStr = result.value?.toString() ?: result.value_string ?: "-"
                val unitStr = result.unit ?: ""
                Text(stringResource(R.string.value, valueStr, unitStr), style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
                if (result.reference_range_low != null || result.reference_range_high != null) {
                    Text(stringResource(R.string.ref, result.reference_range_low ?: "-", result.reference_range_high ?: "-"), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            if (!result.notes.isNullOrEmpty()) {
                Spacer(Modifier.height(4.dp))
                Text(result.notes, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

@Composable
private fun AddLabResultDialog(onDismiss: () -> Unit, onSave: (LabResultRequest) -> Unit) {
    val statuses = listOf("normal", "abnormal", "critical", "pending")

    var testName by remember { mutableStateOf("") }
    var value by remember { mutableStateOf("") }
    var unit by remember { mutableStateOf("") }
    var refRange by remember { mutableStateOf("") }
    var status by remember { mutableStateOf("normal") }
    var notes by remember { mutableStateOf("") }
    var expandedStatus by remember { mutableStateOf(false) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.add_lab_result)) },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                OutlinedTextField(value = testName, onValueChange = { testName = it }, label = { Text(stringResource(R.string.test_name)) }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = value, onValueChange = { value = it }, label = { Text(stringResource(R.string.value_2)) }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = unit, onValueChange = { unit = it }, label = { Text(stringResource(R.string.unit)) }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = refRange, onValueChange = { refRange = it }, label = { Text(stringResource(R.string.reference_range)) }, modifier = Modifier.fillMaxWidth())

                ExposedDropdownMenuBox(expanded = expandedStatus, onExpandedChange = { expandedStatus = it }) {
                    OutlinedTextField(
                        value = status.replaceFirstChar { it.uppercase() },
                        onValueChange = {},
                        readOnly = true,
                        label = { Text(stringResource(R.string.status)) },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expandedStatus) },
                        modifier = Modifier.menuAnchor().fillMaxWidth()
                    )
                    ExposedDropdownMenu(expanded = expandedStatus, onDismissRequest = { expandedStatus = false }) {
                        statuses.forEach {
                            DropdownMenuItem(
                                text = { Text(it.replaceFirstChar { c -> c.uppercase() }) },
                                onClick = { status = it; expandedStatus = false }
                            )
                        }
                    }
                }

                OutlinedTextField(value = notes, onValueChange = { notes = it }, label = { Text(stringResource(R.string.notes)) }, modifier = Modifier.fillMaxWidth(), minLines = 2)
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    if (testName.isNotBlank() && value.isNotBlank() && unit.isNotBlank()) {
                        onSave(LabResultRequest(
                            test_date = LocalDate.now().format(DateTimeFormatter.ISO_DATE),
                            test_name = testName,
                            value = value.toFloatOrNull() ?: 0f,
                            unit = unit,
                            reference_range_low = null,
                            reference_range_high = null,
                            status = status,
                            notes = notes.ifBlank { null }
                        ))
                    }
                },
                enabled = testName.isNotBlank() && value.isNotBlank() && unit.isNotBlank()
            ) { Text(stringResource(R.string.save)) }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text(stringResource(R.string.cancel)) }
        }
    )
}
