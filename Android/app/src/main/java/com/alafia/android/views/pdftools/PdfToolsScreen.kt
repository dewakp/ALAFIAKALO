@file:OptIn(ExperimentalMaterial3Api::class)

package com.alafia.android.views.pdftools
import com.alafia.android.util.ErrorUtil

import android.net.Uri
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.ui.unit.sp
import com.alafia.android.api.ApiClient
import com.alafia.android.models.*
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody
import androidx.navigation.NavHostController

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PdfToolsScreen(navController: NavHostController) {
    var selectedTab by remember { mutableIntStateOf(0) }
    val tabs = listOf("Import Document", "Generate Flowsheet")

    Scaffold(
        topBar = { TopAppBar(
                title = { Text("PDF Tools") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                }
            ) }
    ) { padding ->
        Column(modifier = Modifier.fillMaxSize().padding(padding)) {
            TabRow(selectedTabIndex = selectedTab) {
                tabs.forEachIndexed { index, title ->
                    Tab(
                        selected = selectedTab == index,
                        onClick = { selectedTab = index },
                        text = { Text(title, maxLines = 1, fontSize = 12.sp) }
                    )
                }
            }

            when (selectedTab) {
                0 -> ParseLabReportTab()
                1 -> GenerateFlowsheetTab()
            }
        }
    }
}

// ── Parse Lab Report Tab ────────────────────────────────────────────────────

@Composable
private fun ParseLabReportTab() {
    var result by remember { mutableStateOf<LabReportParseResponse?>(null) }
    var isLoading by remember { mutableStateOf(false) }
    var isImporting by remember { mutableStateOf(false) }
    var importMessage by remember { mutableStateOf<String?>(null) }
    var selectedUri by remember { mutableStateOf<Uri?>(null) }
    // Item ids the patient has chosen to import.
    val selectedIds = remember { mutableStateListOf<Int>() }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    val pdfPicker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        if (uri != null) {
            selectedUri = uri
            scope.launch {
                isLoading = true
                importMessage = null
                try {
                    val inputStream = context.contentResolver.openInputStream(uri)
                    val bytes = inputStream?.readBytes() ?: byteArrayOf()
                    inputStream?.close()
                    val requestBody = bytes.toRequestBody("application/pdf".toMediaTypeOrNull())
                    val part = MultipartBody.Part.createFormData("file", "report.pdf", requestBody)
                    val parsed = ApiClient.getApiService().parseDocument(part)
                    result = parsed
                    // Pre-tick what the server judged safe; duplicates stay off
                    // so confirming never writes a second copy of a reading.
                    selectedIds.clear()
                    selectedIds.addAll(
                        parsed.items.orEmpty().filter { it.accepted == true }.mapNotNull { it.itemId }
                    )
                } catch (e: Exception) {
                    Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                }
                isLoading = false
            }
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Text(
            "Upload a lab report, medication list or flowsheet. Nothing is added to your " +
                "records until you review it and choose Import.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )

        Button(
            onClick = { pdfPicker.launch("application/pdf") },
            modifier = Modifier.fillMaxWidth(),
            enabled = !isLoading
        ) {
            Icon(Icons.Default.PictureAsPdf, contentDescription = null)
            Spacer(Modifier.width(8.dp))
            Text("Select Document")
        }

        if (selectedUri != null) {
            Text("Document selected", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.primary)
        }

        if (isLoading) {
            Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        }

        importMessage?.let { NoticeCard(it, MaterialTheme.colorScheme.primary) }

        result?.let { res ->
            // A document that could not be read must say so. An empty table
            // here would read as "the document contained no results".
            res.error?.let { NoticeCard(it, Color(0xFFB45309)) }
            if (res.alreadyImported) {
                NoticeCard("You have uploaded this file before — showing what was read then.",
                    MaterialTheme.colorScheme.primary)
            }

            Card(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(docTypeLabel(res.docType), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    res.patientName?.let { LabeledValue("Patient Name", it) }
                    res.reportDate?.let { LabeledValue("Report Date", it) }
                    res.labName?.let { LabeledValue("Lab Name", it) }
                    res.orderingPhysician?.let { LabeledValue("Ordering Physician", it) }
                    res.confidence?.let { LabeledValue("Confidence", "${(it * 100).toInt()}%") }
                    res.parsingNotes?.forEach {
                        Text("• $it", style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }

            res.items?.takeIf { it.isNotEmpty() }?.let { items ->
                val selectable = res.canImport && importMessage == null

                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.padding(12.dp)) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text(
                                "${items.size} reading${if (items.size == 1) "" else "s"} found",
                                style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold
                            )
                            if (selectable) {
                                Text("${selectedIds.size} selected", fontSize = 11.sp,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                        Spacer(Modifier.height(8.dp))

                        Row(modifier = Modifier.fillMaxWidth()) {
                            if (selectable) Spacer(Modifier.width(40.dp))
                            Text("Test", fontWeight = FontWeight.Bold, modifier = Modifier.weight(1.5f), fontSize = 11.sp)
                            Text("Value", fontWeight = FontWeight.Bold, modifier = Modifier.weight(0.8f), fontSize = 11.sp)
                            Text("Unit", fontWeight = FontWeight.Bold, modifier = Modifier.weight(0.7f), fontSize = 11.sp)
                            Text("Ref Range", fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f), fontSize = 11.sp)
                        }

                        HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))

                        items.forEach { item ->
                            val isAbnormal = item.isAbnormal == true
                            val tint = if (isAbnormal) Color(0xFFF44336) else Color.Unspecified
                            Row(
                                modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                if (selectable) {
                                    Checkbox(
                                        checked = item.itemId != null && selectedIds.contains(item.itemId),
                                        onCheckedChange = { checked ->
                                            item.itemId?.let {
                                                if (checked) selectedIds.add(it) else selectedIds.remove(it)
                                            }
                                        },
                                        modifier = Modifier.width(40.dp)
                                    )
                                }
                                Column(modifier = Modifier.weight(1.5f)) {
                                    Text(
                                        item.testName ?: "-", fontSize = 11.sp, color = tint,
                                        fontWeight = if (isAbnormal) FontWeight.Bold else FontWeight.Normal
                                    )
                                    if (item.sourceLabel != null && item.sourceLabel != item.testName) {
                                        Text("document: \"${item.sourceLabel}\"", fontSize = 9.sp,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    }
                                    when {
                                        item.isDuplicate -> Text("Already recorded", fontSize = 9.sp,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                                        item.isConflict -> Text("Differs from existing", fontSize = 9.sp,
                                            color = Color(0xFFB45309))
                                    }
                                    item.note?.let {
                                        Text(it, fontSize = 9.sp, color = Color(0xFFB45309))
                                    }
                                }
                                Text(
                                    item.value ?: "-", modifier = Modifier.weight(0.8f), fontSize = 11.sp,
                                    color = tint, fontWeight = if (isAbnormal) FontWeight.Bold else FontWeight.Normal
                                )
                                Text(item.unit ?: "", modifier = Modifier.weight(0.7f), fontSize = 11.sp, color = tint)
                                Text(item.referenceRange ?: "-", modifier = Modifier.weight(1f), fontSize = 11.sp, color = tint)
                            }
                        }
                    }
                }

                if (selectable) {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(
                            onClick = {
                                scope.launch {
                                    isImporting = true
                                    try {
                                        val response = ApiClient.getApiService().confirmDocumentImport(
                                            res.importId!!, ConfirmImportRequest(selectedIds.toList().sorted())
                                        )
                                        importMessage = response.message
                                    } catch (e: Exception) {
                                        Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                                    }
                                    isImporting = false
                                }
                            },
                            enabled = selectedIds.isNotEmpty() && !isImporting
                        ) {
                            Icon(Icons.Default.Check, contentDescription = null)
                            Spacer(Modifier.width(6.dp))
                            Text(if (isImporting) "Importing…" else "Import ${selectedIds.size} selected")
                        }
                        OutlinedButton(
                            onClick = {
                                scope.launch {
                                    try { ApiClient.getApiService().rejectDocumentImport(res.importId!!) }
                                    catch (_: Exception) { /* already gone */ }
                                    result = null; selectedIds.clear(); selectedUri = null; importMessage = null
                                }
                            },
                            enabled = !isImporting
                        ) { Text("Discard") }
                    }
                } else if (!res.canImport) {
                    Text(
                        "This document type can be read but not imported yet — the values above are shown for reference only.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        }
    }
}

@Composable
private fun NoticeCard(text: String, tint: Color) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = tint.copy(alpha = 0.12f))
    ) {
        Text(
            text,
            modifier = Modifier.padding(12.dp),
            style = MaterialTheme.typography.bodySmall,
            color = tint
        )
    }
}

private fun docTypeLabel(docType: String?): String = when (docType) {
    "lab_report" -> "Lab report"
    "medication_list" -> "Medication list"
    "discharge_summary" -> "Discharge summary"
    "dialysis_flowsheet" -> "Dialysis flowsheet"
    "imaging_report" -> "Imaging report"
    else -> "Document"
}

// ── Generate Flowsheet Tab ──────────────────────────────────────────────────

@Composable
private fun GenerateFlowsheetTab() {
    var sessionType by remember { mutableStateOf("hemodialysis") }
    var days by remember { mutableStateOf("30") }
    var result by remember { mutableStateOf<FlowsheetResponse?>(null) }
    var isLoading by remember { mutableStateOf(false) }
    var isDownloading by remember { mutableStateOf(false) }
    var expanded by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    // These are the values the API accepts. The list previously offered "all"
    // and "peritoneal", neither of which the backend recognises.
    val sessionTypes = listOf("hemodialysis", "peritoneal_dialysis")

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        // Session type dropdown
        ExposedDropdownMenuBox(
            expanded = expanded,
            onExpandedChange = { expanded = !expanded }
        ) {
            OutlinedTextField(
                value = sessionType.replaceFirstChar { it.uppercase() },
                onValueChange = {},
                readOnly = true,
                label = { Text("Session Type") },
                trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) },
                modifier = Modifier.fillMaxWidth().menuAnchor()
            )
            ExposedDropdownMenu(
                expanded = expanded,
                onDismissRequest = { expanded = false }
            ) {
                sessionTypes.forEach { type ->
                    DropdownMenuItem(
                        text = { Text(type.replaceFirstChar { it.uppercase() }) },
                        onClick = {
                            sessionType = type
                            expanded = false
                        }
                    )
                }
            }
        }

        OutlinedTextField(
            value = days,
            onValueChange = { days = it },
            label = { Text("Days") },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true
        )

        Button(
            onClick = {
                scope.launch {
                    isLoading = true
                    try {
                        val request = FlowsheetRequest(
                            sessionType = sessionType,
                            days = days.toIntOrNull() ?: 30
                        )
                        result = ApiClient.getApiService().generateFlowsheet(request)
                    } catch (e: Exception) {
                        Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                    }
                    isLoading = false
                }
            },
            modifier = Modifier.fillMaxWidth(),
            enabled = !isLoading
        ) {
            Icon(Icons.Default.TableChart, contentDescription = null)
            Spacer(Modifier.width(8.dp))
            Text("Generate Flowsheet")
        }

        if (isLoading) {
            Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        }

        result?.let { res ->
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    res.title?.let {
                        Text(it, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    }

                    Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                        res.generatedAt?.let {
                            Text("Generated: $it", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        res.sessionCount?.let {
                            Text("Sessions: $it", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }

                    // The real PDF, not the text preview — the same ReportSpec
                    // on the server renders both, so they cannot disagree.
                    OutlinedButton(
                        onClick = {
                            scope.launch {
                                isDownloading = true
                                try {
                                    val body = ApiClient.getApiService().downloadFlowsheetPdf(
                                        sessionType, days.toIntOrNull() ?: 30
                                    )
                                    val name = "flowsheet_${sessionType}_${System.currentTimeMillis()}.pdf"
                                    val file = java.io.File(context.cacheDir, name)
                                    body.byteStream().use { input ->
                                        file.outputStream().use { output -> input.copyTo(output) }
                                    }
                                    val uri = androidx.core.content.FileProvider.getUriForFile(
                                        context, "${context.packageName}.fileprovider", file
                                    )
                                    val share = android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                                        type = "application/pdf"
                                        putExtra(android.content.Intent.EXTRA_STREAM, uri)
                                        addFlags(android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION)
                                    }
                                    context.startActivity(
                                        android.content.Intent.createChooser(share, "Share flowsheet")
                                    )
                                } catch (e: Exception) {
                                    Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                                }
                                isDownloading = false
                            }
                        },
                        enabled = !isDownloading
                    ) {
                        Icon(Icons.Default.Download, contentDescription = null)
                        Spacer(Modifier.width(6.dp))
                        Text(if (isDownloading) "Preparing…" else "Download PDF")
                    }

                    res.content?.let {
                        HorizontalDivider()
                        Text(it, style = MaterialTheme.typography.bodyMedium)
                    }
                }
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
