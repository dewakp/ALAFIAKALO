@file:OptIn(ExperimentalMaterial3Api::class)

package com.alafia.android.views.imageai
import com.alafia.android.util.ErrorUtil

import android.net.Uri
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import com.alafia.android.views.components.rememberCameraCapture
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
import androidx.compose.ui.res.stringResource
import com.alafia.android.R

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ImageAIScreen(navController: NavHostController) {
    var selectedTab by remember { mutableIntStateOf(0) }
    val tabs = listOf("Nutrition from Image", "Medication from Image", "Dosage Verification")

    Scaffold(
        topBar = { TopAppBar(
                title = { Text(stringResource(R.string.image_ai)) },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = stringResource(R.string.back))
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
                        text = { Text(title, maxLines = 1, fontSize = 11.sp) }
                    )
                }
            }

            when (selectedTab) {
                0 -> NutritionFromImageTab()
                1 -> MedicationFromImageTab()
                2 -> DosageVerificationTab()
            }
        }
    }
}

// ── Nutrition from Image Tab ────────────────────────────────────────────────

@Composable
private fun NutritionFromImageTab() {
    var result by remember { mutableStateOf<NutritionFromImageResponse?>(null) }
    var isLoading by remember { mutableStateOf(false) }
    var selectedUri by remember { mutableStateOf<Uri?>(null) }
    var imageBytes by remember { mutableStateOf<ByteArray?>(null) }
    var correction by remember { mutableStateOf("") }
    var isTeaching by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    val imagePicker = rememberCameraCapture { uri ->
        if (uri != null) {
            selectedUri = uri
            scope.launch {
                isLoading = true
                try {
                    val inputStream = context.contentResolver.openInputStream(uri)
                    val bytes = inputStream?.readBytes() ?: byteArrayOf()
                    inputStream?.close()
                    imageBytes = bytes
                    val requestBody = bytes.toRequestBody("image/*".toMediaTypeOrNull())
                    val part = MultipartBody.Part.createFormData("file", "image.jpg", requestBody)
                    result = ApiClient.getApiService().nutritionFromImage(part)
                    correction = result?.foodItems?.joinToString("; ") { it.name } ?: ""
                } catch (e: Exception) {
                    Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                }
                isLoading = false
            }
        }
    }

    // Teach ALAFIA: store the ground-truth foods for this photo (visual memory)
    fun teach() {
        val bytes = imageBytes ?: return
        if (correction.isBlank()) return
        scope.launch {
            isTeaching = true
            try {
                result = ApiClient.getApiService().labelFoodImage(
                    FoodLabelRequest(
                        imageBase64 = android.util.Base64.encodeToString(bytes, android.util.Base64.NO_WRAP),
                        foods = correction.trim(),
                    )
                )
                Toast.makeText(context, "Learned — this meal will be recognized next time", Toast.LENGTH_SHORT).show()
            } catch (e: Exception) {
                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
            }
            isTeaching = false
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
            onClick = { imagePicker.capture() },
            modifier = Modifier.fillMaxWidth(),
            enabled = !isLoading
        ) {
            Icon(Icons.Default.Image, contentDescription = null)
            Spacer(Modifier.width(8.dp))
            Text(stringResource(R.string.select_food_image))
        }

        if (selectedUri != null) {
            Text(stringResource(R.string.image_selected), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.primary)
        }

        if (isLoading) {
            Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        }

        result?.let { res ->
            res.confidenceNote?.let {
                Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }

            Card(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(12.dp)) {
                    // Header row
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(stringResource(R.string.food), fontWeight = FontWeight.Bold, modifier = Modifier.weight(1.5f), fontSize = 12.sp)
                        Text(stringResource(R.string.cal), fontWeight = FontWeight.Bold, modifier = Modifier.weight(0.8f), fontSize = 12.sp)
                        Text(stringResource(R.string.prot), fontWeight = FontWeight.Bold, modifier = Modifier.weight(0.8f), fontSize = 12.sp)
                        Text(stringResource(R.string.carb), fontWeight = FontWeight.Bold, modifier = Modifier.weight(0.8f), fontSize = 12.sp)
                        Text(stringResource(R.string.fat), fontWeight = FontWeight.Bold, modifier = Modifier.weight(0.8f), fontSize = 12.sp)
                    }

                    HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))

                    res.foodItems.forEach { item ->
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text(item.name, modifier = Modifier.weight(1.5f), fontSize = 12.sp)
                            Text("${item.calories ?: "-"}", modifier = Modifier.weight(0.8f), fontSize = 12.sp)
                            Text("${item.proteinG ?: "-"}", modifier = Modifier.weight(0.8f), fontSize = 12.sp)
                            Text("${item.carbsG ?: "-"}", modifier = Modifier.weight(0.8f), fontSize = 12.sp)
                            Text("${item.fatG ?: "-"}", modifier = Modifier.weight(0.8f), fontSize = 12.sp)
                        }
                    }

                    HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))

                    // Total row
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(stringResource(R.string.total), fontWeight = FontWeight.Bold, modifier = Modifier.weight(1.5f), fontSize = 12.sp)
                        Text("${res.totalCalories ?: "-"}", fontWeight = FontWeight.Bold, modifier = Modifier.weight(0.8f), fontSize = 12.sp)
                        Text("${res.totalProteinG ?: "-"}", fontWeight = FontWeight.Bold, modifier = Modifier.weight(0.8f), fontSize = 12.sp)
                        Text("${res.totalCarbsG ?: "-"}", fontWeight = FontWeight.Bold, modifier = Modifier.weight(0.8f), fontSize = 12.sp)
                        Text("${res.totalFatG ?: "-"}", fontWeight = FontWeight.Bold, modifier = Modifier.weight(0.8f), fontSize = 12.sp)
                    }
                }
            }

            // Teach ALAFIA: correct the food list → learned for future photos
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(stringResource(R.string.not_right_teach_alafia_what_this),
                        style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold)
                    OutlinedTextField(
                        value = correction,
                        onValueChange = { correction = it },
                        modifier = Modifier.fillMaxWidth(),
                        placeholder = { Text(stringResource(R.string.e_g_beans_in_palm_oil_grilled_chicken), fontSize = 12.sp) },
                        textStyle = MaterialTheme.typography.bodySmall,
                    )
                    Button(
                        onClick = { teach() },
                        enabled = !isTeaching && correction.isNotBlank(),
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text(if (isTeaching) stringResource(R.string.saving) else stringResource(R.string.teach))
                    }
                    Text(stringResource(R.string.separate_foods_with_semicolons_alafia),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }
}

// ── Medication from Image Tab ───────────────────────────────────────────────

@Composable
private fun MedicationFromImageTab() {
    var result by remember { mutableStateOf<MedicationFromImageResponse?>(null) }
    var isLoading by remember { mutableStateOf(false) }
    var selectedUri by remember { mutableStateOf<Uri?>(null) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    val imagePicker = rememberCameraCapture { uri ->
        if (uri != null) {
            selectedUri = uri
            scope.launch {
                isLoading = true
                try {
                    val inputStream = context.contentResolver.openInputStream(uri)
                    val bytes = inputStream?.readBytes() ?: byteArrayOf()
                    inputStream?.close()
                    val requestBody = bytes.toRequestBody("image/*".toMediaTypeOrNull())
                    val part = MultipartBody.Part.createFormData("file", "image.jpg", requestBody)
                    result = ApiClient.getApiService().medicationFromImage(part)
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
            onClick = { imagePicker.capture() },
            modifier = Modifier.fillMaxWidth(),
            enabled = !isLoading
        ) {
            Icon(Icons.Default.CameraAlt, contentDescription = null)
            Spacer(Modifier.width(8.dp))
            Text(stringResource(R.string.select_medication_image))
        }

        if (selectedUri != null) {
            Text(stringResource(R.string.image_selected), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.primary)
        }

        if (isLoading) {
            Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        }

        result?.let { res ->
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(stringResource(R.string.medication_details), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)

                    res.medicationName?.let { LabeledValue(stringResource(R.string.name), it) }
                    res.dosage?.let { LabeledValue(stringResource(R.string.dosage_strength), it) }
                    res.instructions?.let { LabeledValue(stringResource(R.string.instructions), it) }
                    res.ndcCode?.let { LabeledValue(stringResource(R.string.ndc_code_2), it) }
                    res.manufacturer?.let { LabeledValue(stringResource(R.string.manufacturer_2), it) }
                    res.fields.forEach { f ->
                        if (!f.label.isNullOrBlank() && !f.value.isNullOrBlank()) LabeledValue(f.label, f.value)
                    }
                }
            }

            res.notes?.takeIf { it.isNotBlank() }?.let { note ->
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.tertiaryContainer)
                ) {
                    Row(modifier = Modifier.padding(16.dp), verticalAlignment = Alignment.Top) {
                        Icon(Icons.Default.Info, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(8.dp))
                        Text(note, style = MaterialTheme.typography.bodyMedium)
                    }
                }
            }
        }
    }
}

// ── Dosage Verification Tab ─────────────────────────────────────────────────

@Composable
private fun DosageVerificationTab() {
    var medicationName by remember { mutableStateOf("") }
    var dosage by remember { mutableStateOf("") }
    var frequency by remember { mutableStateOf("") }
    var result by remember { mutableStateOf<DosageVerificationResponse?>(null) }
    var isLoading by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        OutlinedTextField(
            value = medicationName,
            onValueChange = { medicationName = it },
            label = { Text(stringResource(R.string.medication_name)) },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true
        )

        OutlinedTextField(
            value = dosage,
            onValueChange = { dosage = it },
            label = { Text(stringResource(R.string.dosage)) },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
            placeholder = { Text(stringResource(R.string.e_g_500mg)) }
        )

        OutlinedTextField(
            value = frequency,
            onValueChange = { frequency = it },
            label = { Text(stringResource(R.string.frequency_optional)) },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
            placeholder = { Text(stringResource(R.string.e_g_twice_daily)) }
        )

        Button(
            onClick = {
                if (medicationName.isBlank() || dosage.isBlank()) {
                    Toast.makeText(context, "Medication name and dosage are required", Toast.LENGTH_SHORT).show()
                    return@Button
                }
                scope.launch {
                    isLoading = true
                    try {
                        val request = DosageVerificationRequest(
                            medicationName = medicationName.trim(),
                            dosage = dosage.trim(),
                            frequency = frequency.trim().ifBlank { null }
                        )
                        result = ApiClient.getApiService().verifyDosage(request)
                    } catch (e: Exception) {
                        Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                    }
                    isLoading = false
                }
            },
            modifier = Modifier.fillMaxWidth(),
            enabled = !isLoading
        ) {
            Icon(Icons.Default.Verified, contentDescription = null)
            Spacer(Modifier.width(8.dp))
            Text(stringResource(R.string.verify_dosage))
        }

        if (isLoading) {
            Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        }

        result?.let { res ->
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(
                    containerColor = if (res.isTypical == true)
                        Color(0xFFE8F5E9) else Color(0xFFFFEBEE)
                )
            ) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        if (res.isTypical == true) {
                            Icon(Icons.Default.CheckCircle, "Typical", tint = Color(0xFF4CAF50), modifier = Modifier.size(28.dp))
                        } else {
                            Icon(Icons.Default.Warning, "Atypical", tint = Color(0xFFF44336), modifier = Modifier.size(28.dp))
                        }
                        Spacer(Modifier.width(8.dp))
                        Text(
                            if (res.isTypical == true) stringResource(R.string.typical_dosage) else stringResource(R.string.atypical_please_verify),
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold
                        )
                    }

                    res.medicationName?.let { LabeledValue(stringResource(R.string.medication), it) }
                    res.dosage?.let { LabeledValue(stringResource(R.string.dosage), it) }
                    res.typicalRange?.let { LabeledValue(stringResource(R.string.typical_range), it) }
                    res.feedback?.let { LabeledValue(stringResource(R.string.assessment), it) }

                    res.precautions.takeIf { it.isNotEmpty() }?.let { precautions ->
                        HorizontalDivider()
                        Text(stringResource(R.string.precautions), fontWeight = FontWeight.Bold, color = Color(0xFFF44336))
                        precautions.forEach { p ->
                            Row(verticalAlignment = Alignment.Top) {
                                Text("⚠ ")
                                Text(p, style = MaterialTheme.typography.bodyMedium)
                            }
                        }
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
