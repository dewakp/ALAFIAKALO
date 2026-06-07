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
    val tabs = listOf("Parse Lab Report", "Generate Flowsheet")

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
    var selectedUri by remember { mutableStateOf<Uri?>(null) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    val pdfPicker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        if (uri != null) {
            selectedUri = uri
            scope.launch {
                isLoading = true
                try {
                    val inputStream = context.contentResolver.openInputStream(uri)
                    val bytes = inputStream?.readBytes() ?: byteArrayOf()
                    inputStream?.close()
                    val requestBody = bytes.toRequestBody("application/pdf".toMediaTypeOrNull())
                    val part = MultipartBody.Part.createFormData("file", "report.pdf", requestBody)
                    result = ApiClient.getApiService().parseLabReport(part)
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
        Button(
            onClick = { pdfPicker.launch("application/pdf") },
            modifier = Modifier.fillMaxWidth(),
            enabled = !isLoading
        ) {
            Icon(Icons.Default.PictureAsPdf, contentDescription = null)
            Spacer(Modifier.width(8.dp))
            Text("Select PDF Lab Report")
        }

        if (selectedUri != null) {
            Text("PDF selected", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.primary)
        }

        if (isLoading) {
            Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        }

        result?.let { res ->
            // Patient & Report Info
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("Report Information", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    res.patientName?.let { LabeledValue("Patient Name", it) }
                    res.reportDate?.let { LabeledValue("Report Date", it) }
                    res.labName?.let { LabeledValue("Lab Name", it) }
                    res.orderingPhysician?.let { LabeledValue("Ordering Physician", it) }
                }
            }

            // Lab Items Table
            res.items?.takeIf { it.isNotEmpty() }?.let { items ->
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.padding(12.dp)) {
                        Text("Test Results", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                        Spacer(Modifier.height(8.dp))

                        // Header row
                        Row(modifier = Modifier.fillMaxWidth()) {
                            Text("Test", fontWeight = FontWeight.Bold, modifier = Modifier.weight(1.5f), fontSize = 11.sp)
                            Text("Value", fontWeight = FontWeight.Bold, modifier = Modifier.weight(0.8f), fontSize = 11.sp)
                            Text("Unit", fontWeight = FontWeight.Bold, modifier = Modifier.weight(0.7f), fontSize = 11.sp)
                            Text("Ref Range", fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f), fontSize = 11.sp)
                        }

                        HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))

                        items.forEach { item ->
                            val isAbnormal = item.isAbnormal == true
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(vertical = 2.dp)
                            ) {
                                Text(
                                    item.testName ?: "-",
                                    modifier = Modifier.weight(1.5f),
                                    fontSize = 11.sp,
                                    color = if (isAbnormal) Color(0xFFF44336) else Color.Unspecified,
                                    fontWeight = if (isAbnormal) FontWeight.Bold else FontWeight.Normal
                                )
                                Text(
                                    item.value ?: "-",
                                    modifier = Modifier.weight(0.8f),
                                    fontSize = 11.sp,
                                    color = if (isAbnormal) Color(0xFFF44336) else Color.Unspecified,
                                    fontWeight = if (isAbnormal) FontWeight.Bold else FontWeight.Normal
                                )
                                Text(
                                    item.unit ?: "",
                                    modifier = Modifier.weight(0.7f),
                                    fontSize = 11.sp,
                                    color = if (isAbnormal) Color(0xFFF44336) else Color.Unspecified
                                )
                                Text(
                                    item.referenceRange ?: "-",
                                    modifier = Modifier.weight(1f),
                                    fontSize = 11.sp,
                                    color = if (isAbnormal) Color(0xFFF44336) else Color.Unspecified
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

// ── Generate Flowsheet Tab ──────────────────────────────────────────────────

@Composable
private fun GenerateFlowsheetTab() {
    var sessionType by remember { mutableStateOf("all") }
    var days by remember { mutableStateOf("30") }
    var result by remember { mutableStateOf<FlowsheetResponse?>(null) }
    var isLoading by remember { mutableStateOf(false) }
    var expanded by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    val sessionTypes = listOf("all", "hemodialysis", "peritoneal")

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
