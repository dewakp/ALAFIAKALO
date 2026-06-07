@file:OptIn(ExperimentalMaterial3Api::class)

package com.alafia.android.views.pd
import com.alafia.android.util.ErrorUtil

import android.widget.Toast
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.combinedClickable
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
import androidx.compose.ui.unit.sp
import com.alafia.android.api.ApiClient
import com.alafia.android.models.*
import kotlinx.coroutines.launch
import androidx.navigation.NavHostController

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PeritonealDialysisScreen(navController: NavHostController) {
    var sessions by remember { mutableStateOf<List<PDSession>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    var showForm by remember { mutableStateOf(false) }
    var deleteTarget by remember { mutableStateOf<PDSession?>(null) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    fun loadSessions() {
        scope.launch {
            isLoading = true
            try {
                sessions = ApiClient.getApiService().getPDSessions()
            } catch (e: Exception) {
                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
            }
            isLoading = false
        }
    }

    LaunchedEffect(Unit) { loadSessions() }

    Scaffold(
        topBar = { TopAppBar(
                title = { Text("Peritoneal Dialysis") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                }
            ) },
        floatingActionButton = {
            FloatingActionButton(onClick = { showForm = true }) {
                Icon(Icons.Default.Add, "Add Session")
            }
        }
    ) { padding ->
        if (isLoading) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        } else if (sessions.isEmpty()) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(Icons.Default.WaterDrop, "No sessions", modifier = Modifier.size(64.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
                    Spacer(Modifier.height(12.dp))
                    Text("No PD sessions", style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text("Tap + to add a session", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(sessions, key = { it.id }) { session ->
                    PDSessionCard(
                        session = session,
                        onDelete = { deleteTarget = session }
                    )
                }
            }
        }
    }

    // Delete confirmation dialog
    deleteTarget?.let { session ->
        AlertDialog(
            onDismissRequest = { deleteTarget = null },
            title = { Text("Delete Session") },
            text = { Text("Delete PD session from ${session.sessionDate}?") },
            confirmButton = {
                TextButton(onClick = {
                    scope.launch {
                        try {
                            ApiClient.getApiService().deletePDSession(session.id)
                            deleteTarget = null
                            loadSessions()
                            Toast.makeText(context, "Session deleted", Toast.LENGTH_SHORT).show()
                        } catch (e: Exception) {
                            Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                        }
                    }
                }) { Text("Delete", color = MaterialTheme.colorScheme.error) }
            },
            dismissButton = {
                TextButton(onClick = { deleteTarget = null }) { Text("Cancel") }
            }
        )
    }

    // Add session bottom sheet
    if (showForm) {
        AddPDSessionSheet(
            onDismiss = { showForm = false },
            onSave = { request ->
                scope.launch {
                    try {
                        ApiClient.getApiService().createPDSession(request)
                        showForm = false
                        loadSessions()
                        Toast.makeText(context, "Session added!", Toast.LENGTH_SHORT).show()
                    } catch (e: Exception) {
                        Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                    }
                }
            }
        )
    }
}

// ── Session Card ────────────────────────────────────────────────────────────

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun PDSessionCard(session: PDSession, onDelete: () -> Unit) {
    var expanded by remember { mutableStateOf(false) }

    val modalityColor = when (session.modality.uppercase()) {
        "CAPD" -> Color(0xFF2196F3)
        "APD" -> Color(0xFF9C27B0)
        "CCPD" -> Color(0xFF009688)
        else -> MaterialTheme.colorScheme.primary
    }

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .combinedClickable(
                onClick = { expanded = !expanded },
                onLongClick = onDelete
            )
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(session.sessionDate, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        session.preWeightKg?.let { Text("Pre: ${it}kg", style = MaterialTheme.typography.bodySmall) }
                        session.postWeightKg?.let { Text("Post: ${it}kg", style = MaterialTheme.typography.bodySmall) }
                    }
                }

                Column(horizontalAlignment = Alignment.End) {
                    SuggestionChip(
                        onClick = {},
                        label = { Text(session.modality.uppercase(), fontSize = 11.sp, fontWeight = FontWeight.Bold) },
                        colors = SuggestionChipDefaults.suggestionChipColors(containerColor = modalityColor.copy(alpha = 0.15f))
                    )
                }
            }

            Row(
                modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                session.preBpSystolic?.let { sys ->
                    session.preBpDiastolic?.let { dia ->
                        Text("Pre BP: $sys/$dia", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
                session.postBpSystolic?.let { sys ->
                    session.postBpDiastolic?.let { dia ->
                        Text("Post BP: $sys/$dia", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
                session.totalUfMl?.let {
                    Text("Total UF: ${it}ml", style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
                }
            }

            // Expandable exchanges section
            AnimatedVisibility(visible = expanded) {
                Column(modifier = Modifier.padding(top = 12.dp)) {
                    session.exitSiteStatus?.let {
                        Text("Exit Site: $it", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    session.temperatureC?.let {
                        Text("Temperature: ${it}°C", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    session.notes?.let {
                        Text("Notes: $it", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }

                    session.exchanges?.takeIf { it.isNotEmpty() }?.let { exchanges ->
                        Spacer(Modifier.height(8.dp))
                        Text("Exchanges", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                        HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))

                        exchanges.forEach { exchange ->
                            Row(
                                modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp),
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text("#${exchange.exchangeNumber}", fontWeight = FontWeight.Bold, fontSize = 12.sp, modifier = Modifier.weight(0.4f))
                                Text(exchange.solutionType ?: "-", fontSize = 12.sp, modifier = Modifier.weight(1f))
                                Text("In: ${exchange.inflowVolumeMl ?: "-"}ml", fontSize = 11.sp, modifier = Modifier.weight(0.9f))
                                Text("Out: ${exchange.outflowVolumeMl ?: "-"}ml", fontSize = 11.sp, modifier = Modifier.weight(0.9f))
                                Text("UF: ${exchange.ufMl ?: "-"}", fontSize = 11.sp, modifier = Modifier.weight(0.7f))
                            }
                            exchange.effluentClarity?.let {
                                Text("  Clarity: $it", fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    }

                    Spacer(Modifier.height(8.dp))
                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                        TextButton(onClick = onDelete) {
                            Icon(Icons.Default.Delete, "Delete", tint = MaterialTheme.colorScheme.error, modifier = Modifier.size(16.dp))
                            Spacer(Modifier.width(4.dp))
                            Text("Delete", color = MaterialTheme.colorScheme.error)
                        }
                    }
                }
            }

            Icon(
                if (expanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                "Toggle details",
                modifier = Modifier.align(Alignment.CenterHorizontally).size(20.dp),
                tint = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

// ── Add PD Session Sheet ────────────────────────────────────────────────────

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AddPDSessionSheet(onDismiss: () -> Unit, onSave: (PDSessionCreate) -> Unit) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    var sessionDate by remember { mutableStateOf("") }
    var modality by remember { mutableStateOf("capd") }
    var modalityExpanded by remember { mutableStateOf(false) }
    var preWeight by remember { mutableStateOf("") }
    var postWeight by remember { mutableStateOf("") }
    var preBpSys by remember { mutableStateOf("") }
    var preBpDia by remember { mutableStateOf("") }
    var postBpSys by remember { mutableStateOf("") }
    var postBpDia by remember { mutableStateOf("") }
    var temperature by remember { mutableStateOf("") }
    var exitSiteStatus by remember { mutableStateOf("healthy") }
    var exitSiteExpanded by remember { mutableStateOf(false) }
    var notes by remember { mutableStateOf("") }
    var exchanges by remember { mutableStateOf<List<ExchangeFormData>>(emptyList()) }

    val modalityOptions = listOf("capd", "apd", "ccpd")
    val exitSiteOptions = listOf("healthy", "red", "swollen", "drainage")

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 16.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            Text("Add PD Session", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)

            OutlinedTextField(
                value = sessionDate,
                onValueChange = { sessionDate = it },
                label = { Text("Session Date (YYYY-MM-DD)") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                placeholder = { Text("2026-02-16") }
            )

            // Modality dropdown
            ExposedDropdownMenuBox(
                expanded = modalityExpanded,
                onExpandedChange = { modalityExpanded = !modalityExpanded }
            ) {
                OutlinedTextField(
                    value = modality.uppercase(),
                    onValueChange = {},
                    readOnly = true,
                    label = { Text("Modality") },
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = modalityExpanded) },
                    modifier = Modifier.fillMaxWidth().menuAnchor()
                )
                ExposedDropdownMenu(
                    expanded = modalityExpanded,
                    onDismissRequest = { modalityExpanded = false }
                ) {
                    modalityOptions.forEach { option ->
                        DropdownMenuItem(
                            text = { Text(option.uppercase()) },
                            onClick = {
                                modality = option
                                modalityExpanded = false
                            }
                        )
                    }
                }
            }

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = preWeight,
                    onValueChange = { preWeight = it },
                    label = { Text("Pre Weight (kg)") },
                    modifier = Modifier.weight(1f),
                    singleLine = true
                )
                OutlinedTextField(
                    value = postWeight,
                    onValueChange = { postWeight = it },
                    label = { Text("Post Weight (kg)") },
                    modifier = Modifier.weight(1f),
                    singleLine = true
                )
            }

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = preBpSys,
                    onValueChange = { preBpSys = it },
                    label = { Text("Pre BP Sys") },
                    modifier = Modifier.weight(1f),
                    singleLine = true
                )
                OutlinedTextField(
                    value = preBpDia,
                    onValueChange = { preBpDia = it },
                    label = { Text("Pre BP Dia") },
                    modifier = Modifier.weight(1f),
                    singleLine = true
                )
            }

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = postBpSys,
                    onValueChange = { postBpSys = it },
                    label = { Text("Post BP Sys") },
                    modifier = Modifier.weight(1f),
                    singleLine = true
                )
                OutlinedTextField(
                    value = postBpDia,
                    onValueChange = { postBpDia = it },
                    label = { Text("Post BP Dia") },
                    modifier = Modifier.weight(1f),
                    singleLine = true
                )
            }

            OutlinedTextField(
                value = temperature,
                onValueChange = { temperature = it },
                label = { Text("Temperature (°C)") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true
            )

            // Exit site status dropdown
            ExposedDropdownMenuBox(
                expanded = exitSiteExpanded,
                onExpandedChange = { exitSiteExpanded = !exitSiteExpanded }
            ) {
                OutlinedTextField(
                    value = exitSiteStatus.replaceFirstChar { it.uppercase() },
                    onValueChange = {},
                    readOnly = true,
                    label = { Text("Exit Site Status") },
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = exitSiteExpanded) },
                    modifier = Modifier.fillMaxWidth().menuAnchor()
                )
                ExposedDropdownMenu(
                    expanded = exitSiteExpanded,
                    onDismissRequest = { exitSiteExpanded = false }
                ) {
                    exitSiteOptions.forEach { option ->
                        DropdownMenuItem(
                            text = { Text(option.replaceFirstChar { it.uppercase() }) },
                            onClick = {
                                exitSiteStatus = option
                                exitSiteExpanded = false
                            }
                        )
                    }
                }
            }

            OutlinedTextField(
                value = notes,
                onValueChange = { notes = it },
                label = { Text("Notes") },
                modifier = Modifier.fillMaxWidth(),
                minLines = 2
            )

            // Exchanges section
            Text("Exchanges", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)

            exchanges.forEachIndexed { index, exchange ->
                ExchangeFormRow(
                    exchange = exchange,
                    onUpdate = { updated -> exchanges = exchanges.toMutableList().also { it[index] = updated } },
                    onRemove = { exchanges = exchanges.toMutableList().also { it.removeAt(index) } }
                )
            }

            OutlinedButton(
                onClick = {
                    exchanges = exchanges + ExchangeFormData(exchangeNumber = exchanges.size + 1)
                },
                modifier = Modifier.fillMaxWidth()
            ) {
                Icon(Icons.Default.Add, contentDescription = null)
                Spacer(Modifier.width(4.dp))
                Text("Add Exchange")
            }

            Spacer(Modifier.height(8.dp))

            Button(
                onClick = {
                    val request = PDSessionCreate(
                        sessionDate = sessionDate.ifBlank { "2026-02-16" },
                        modality = modality,
                        preWeightKg = preWeight.toDoubleOrNull(),
                        postWeightKg = postWeight.toDoubleOrNull(),
                        preBpSystolic = preBpSys.toIntOrNull(),
                        preBpDiastolic = preBpDia.toIntOrNull(),
                        postBpSystolic = postBpSys.toIntOrNull(),
                        postBpDiastolic = postBpDia.toIntOrNull(),
                        temperatureC = temperature.toDoubleOrNull(),
                        exitSiteStatus = exitSiteStatus,
                        notes = notes.ifBlank { null },
                        exchanges = exchanges.map { it.toPDExchange() }.ifEmpty { null }
                    )
                    onSave(request)
                },
                modifier = Modifier.fillMaxWidth()
            ) {
                Text("Save Session")
            }

            Spacer(Modifier.height(32.dp))
        }
    }
}

// ── Exchange Form Data ──────────────────────────────────────────────────────

private data class ExchangeFormData(
    val exchangeNumber: Int = 1,
    val solutionType: String = "",
    val inflowVolume: String = "",
    val outflowVolume: String = "",
    val effluentClarity: String = "clear"
)

private fun ExchangeFormData.toPDExchange() = PDExchange(
    exchangeNumber = exchangeNumber,
    solutionType = solutionType.ifBlank { null },
    inflowVolumeMl = inflowVolume.toIntOrNull(),
    outflowVolumeMl = outflowVolume.toIntOrNull(),
    effluentClarity = effluentClarity
)

@Composable
private fun ExchangeFormRow(
    exchange: ExchangeFormData,
    onUpdate: (ExchangeFormData) -> Unit,
    onRemove: () -> Unit
) {
    var clarityExpanded by remember { mutableStateOf(false) }
    val clarityOptions = listOf("clear", "slightly cloudy", "cloudy", "bloody")

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text("Exchange #${exchange.exchangeNumber}", fontWeight = FontWeight.Bold)
                IconButton(onClick = onRemove, modifier = Modifier.size(24.dp)) {
                    Icon(Icons.Default.Close, "Remove", tint = MaterialTheme.colorScheme.error, modifier = Modifier.size(18.dp))
                }
            }

            OutlinedTextField(
                value = exchange.solutionType,
                onValueChange = { onUpdate(exchange.copy(solutionType = it)) },
                label = { Text("Solution Type") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                placeholder = { Text("e.g., 1.5% Dextrose") }
            )

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = exchange.inflowVolume,
                    onValueChange = { onUpdate(exchange.copy(inflowVolume = it)) },
                    label = { Text("Inflow (ml)") },
                    modifier = Modifier.weight(1f),
                    singleLine = true
                )
                OutlinedTextField(
                    value = exchange.outflowVolume,
                    onValueChange = { onUpdate(exchange.copy(outflowVolume = it)) },
                    label = { Text("Outflow (ml)") },
                    modifier = Modifier.weight(1f),
                    singleLine = true
                )
            }

            ExposedDropdownMenuBox(
                expanded = clarityExpanded,
                onExpandedChange = { clarityExpanded = !clarityExpanded }
            ) {
                OutlinedTextField(
                    value = exchange.effluentClarity.replaceFirstChar { it.uppercase() },
                    onValueChange = {},
                    readOnly = true,
                    label = { Text("Effluent Clarity") },
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = clarityExpanded) },
                    modifier = Modifier.fillMaxWidth().menuAnchor()
                )
                ExposedDropdownMenu(
                    expanded = clarityExpanded,
                    onDismissRequest = { clarityExpanded = false }
                ) {
                    clarityOptions.forEach { option ->
                        DropdownMenuItem(
                            text = { Text(option.replaceFirstChar { it.uppercase() }) },
                            onClick = {
                                onUpdate(exchange.copy(effluentClarity = option))
                                clarityExpanded = false
                            }
                        )
                    }
                }
            }
        }
    }
}
