package com.alafia.android.views.nutrition

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import kotlin.math.roundToInt
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import com.alafia.android.api.ApiClient
import com.alafia.android.models.*
import com.alafia.android.schemas.NutritionLogRequest
import com.alafia.android.schemas.VisionItem
import com.alafia.android.schemas.VisionFeedbackItem
import com.alafia.android.schemas.VisionFeedbackRequest
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.format.DateTimeFormatter

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NutritionScreen() {
    var tab by remember { mutableIntStateOf(0) }             // 0=log, 1=summary
    var logs by remember { mutableStateOf<List<NutritionLog>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    var showAddSheet by remember { mutableStateOf(false) }
    var detailFdcId by remember { mutableIntStateOf(-1) }

    // Daily summary
    var summaryDate by remember { mutableStateOf(LocalDate.now().toString()) }
    var summary by remember { mutableStateOf<DailySummary?>(null) }
    var loadingSummary by remember { mutableStateOf(false) }
    var goals by remember { mutableStateOf<GoalProgressResponse?>(null) }

    val scope = rememberCoroutineScope()
    val api = ApiClient.getApiService()

    suspend fun loadLogs() {
        isLoading = true
        try { logs = api.getNutritionLogs() } catch (_: Exception) {}
        isLoading = false
    }

    suspend fun loadSummary(d: String) {
        loadingSummary = true
        try { summary = api.getNutritionDailySummary(d) } catch (_: Exception) { summary = null }
        try { goals = api.getNutritionGoalProgress(d) } catch (_: Exception) { goals = null }
        loadingSummary = false
    }

    LaunchedEffect(Unit) { loadLogs() }
    LaunchedEffect(tab, summaryDate) { if (tab == 1) loadSummary(summaryDate) }

    Column(modifier = Modifier.fillMaxSize()) {
        // Tab selector
        TabRow(selectedTabIndex = tab) {
            Tab(selected = tab == 0, onClick = { tab = 0 }, text = { Text("Food Log") },
                icon = { Icon(Icons.Filled.Restaurant, contentDescription = null, modifier = Modifier.size(18.dp)) })
            Tab(selected = tab == 1, onClick = { tab = 1 }, text = { Text("Daily Summary") },
                icon = { Icon(Icons.Filled.BarChart, contentDescription = null, modifier = Modifier.size(18.dp)) })
        }

        when (tab) {
            0 -> {
                // ─── Food Log Tab ───
                if (isLoading) {
                    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
                } else if (logs.isEmpty()) {
                    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Icon(Icons.Filled.RestaurantMenu, contentDescription = null, modifier = Modifier.size(48.dp),
                                tint = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.3f))
                            Spacer(Modifier.height(12.dp))
                            Text("No meals logged yet", style = MaterialTheme.typography.bodyLarge,
                                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f))
                            Text("Search the USDA database to add foods", style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.35f))
                        }
                    }
                } else {
                    LazyColumn(modifier = Modifier.weight(1f), contentPadding = PaddingValues(16.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        items(logs) { log ->
                            NutritionLogCard(log = log, onDelete = {
                                scope.launch {
                                    try { api.deleteNutritionLog(log.id); loadLogs() } catch (_: Exception) {}
                                }
                            }, onViewDetail = { fdcId -> detailFdcId = fdcId })
                        }
                    }
                }

                // FAB
                Box(Modifier.fillMaxWidth().padding(16.dp), contentAlignment = Alignment.BottomEnd) {
                    FloatingActionButton(onClick = { showAddSheet = true }) {
                        Icon(Icons.Filled.Add, contentDescription = "Add meal")
                    }
                }
            }
            1 -> {
                // ─── Daily Summary Tab ───
                Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp)) {
                    // Date picker row
                    OutlinedCard(Modifier.fillMaxWidth()) {
                        Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Filled.CalendarToday, contentDescription = null, modifier = Modifier.size(18.dp))
                            Spacer(Modifier.width(8.dp))
                            Text(summaryDate, style = MaterialTheme.typography.bodyMedium)
                            Spacer(Modifier.weight(1f))
                            IconButton(onClick = {
                                val prev = LocalDate.parse(summaryDate).minusDays(1)
                                summaryDate = prev.toString()
                            }) { Icon(Icons.Filled.ChevronLeft, contentDescription = "Previous day") }
                            IconButton(onClick = {
                                val next = LocalDate.parse(summaryDate).plusDays(1)
                                if (!next.isAfter(LocalDate.now())) summaryDate = next.toString()
                            }) { Icon(Icons.Filled.ChevronRight, contentDescription = "Next day") }
                        }
                    }

                    Spacer(Modifier.height(16.dp))

                    // Personalized daily nutrient targets / limits
                    goals?.let { g ->
                        DailyTargetsCard(g)
                        Spacer(Modifier.height(16.dp))
                    }

                    if (loadingSummary) {
                        Box(Modifier.fillMaxWidth().height(200.dp), contentAlignment = Alignment.Center) {
                            CircularProgressIndicator()
                        }
                    } else if (summary != null && summary!!.mealCount > 0) {
                        val s = summary!!
                        // Macro cards row
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            MacroCard("Calories", s.totalCalories, "kcal", 2000f, Color(0xFFF59E0B), Modifier.weight(1f))
                            MacroCard("Protein", s.totalProteinG, "g", 50f, Color(0xFF3B82F6), Modifier.weight(1f))
                            MacroCard("Carbs", s.totalCarbsG, "g", 275f, Color(0xFF8B5CF6), Modifier.weight(1f))
                            MacroCard("Fat", s.totalFatG, "g", 78f, Color(0xFFEF4444), Modifier.weight(1f))
                        }

                        Spacer(Modifier.height(8.dp))
                        Text("${s.mealCount} meal(s) logged", style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f),
                            modifier = Modifier.align(Alignment.CenterHorizontally))
                        Spacer(Modifier.height(16.dp))

                        // Nutrient breakdown
                        NutrientBreakdownCard(s.nutrients)
                    } else {
                        Box(Modifier.fillMaxWidth().height(200.dp), contentAlignment = Alignment.Center) {
                            Text("No meals logged for this date", color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f))
                        }
                    }
                }
            }
        }
    }

    // Add sheet dialog
    if (showAddSheet) {
        AddMealDialog(
            onDismiss = { showAddSheet = false },
            onSaved = { scope.launch { loadLogs(); if (tab == 1) loadSummary(summaryDate) } }
        )
    }

    // Food detail dialog
    if (detailFdcId > 0) {
        FoodDetailDialog(fdcId = detailFdcId, onDismiss = { detailFdcId = -1 })
    }
}

// ─── Nutrition Log Card ───

@Composable
private fun NutritionLogCard(
    log: NutritionLog,
    onDelete: () -> Unit,
    onViewDetail: (Int) -> Unit,
) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(log.foodName, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                        if (log.fdcId != null) {
                            Spacer(Modifier.width(6.dp))
                            Text("USDA", fontSize = 9.sp, fontWeight = FontWeight.Bold,
                                color = Color(0xFF22C55E),
                                modifier = Modifier.background(Color(0xFF22C55E).copy(alpha = 0.12f), CircleShape)
                                    .padding(horizontal = 6.dp, vertical = 1.dp)
                                    .clickable { onViewDetail(log.fdcId!!) })
                        }
                    }
                    Row {
                        Text(log.mealType.replaceFirstChar { it.uppercase() },
                            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f))
                        log.servingSize?.let {
                            Text(" · $it", style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.4f))
                        }
                    }
                }
                log.calories?.let {
                    Text("${it.toInt()} kcal", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold,
                        color = Color(0xFF22C55E))
                }
                IconButton(onClick = onDelete, modifier = Modifier.size(32.dp)) {
                    Icon(Icons.Filled.Delete, contentDescription = "Delete", modifier = Modifier.size(16.dp),
                        tint = MaterialTheme.colorScheme.error)
                }
            }
            // Macro pills
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.padding(top = 4.dp)) {
                log.proteinG?.let { NutrientPill("P", it, Color(0xFF3B82F6)) }
                log.carbsG?.let { NutrientPill("C", it, Color(0xFFF59E0B)) }
                log.fatG?.let { NutrientPill("F", it, Color(0xFFEF4444)) }
                log.fiberG?.let { NutrientPill("Fiber", it, Color(0xFF78350F)) }
            }
        }
    }
}

@Composable
private fun NutrientPill(label: String, value: Float, color: Color) {
    Text("$label: ${value.toInt()}g", fontSize = 10.sp, fontWeight = FontWeight.Medium,
        color = color,
        modifier = Modifier.background(color.copy(alpha = 0.12f), RoundedCornerShape(50))
            .padding(horizontal = 8.dp, vertical = 2.dp))
}

// ─── Macro Card ───

@Composable
private fun MacroCard(label: String, value: Float, unit: String, rda: Float, color: Color, modifier: Modifier) {
    val pct = (value / rda).coerceIn(0f, 1f)
    Card(modifier = modifier) {
        Column(Modifier.padding(10.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Text(label, fontSize = 10.sp, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f))
            Text(if (unit == "kcal") "${value.toInt()}" else String.format("%.1f", value),
                fontSize = 18.sp, fontWeight = FontWeight.Bold, color = color)
            Text(unit, fontSize = 9.sp, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.4f))
            Spacer(Modifier.height(4.dp))
            LinearProgressIndicator(progress = { pct }, modifier = Modifier.fillMaxWidth().height(4.dp).clip(RoundedCornerShape(2.dp)),
                color = color, trackColor = color.copy(alpha = 0.15f))
            Text("${(pct * 100).toInt()}% DV", fontSize = 8.sp, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.4f))
        }
    }
}

// ─── Nutrient Breakdown Card ───

@Composable
private fun NutrientBreakdownCard(nutrients: List<USDAFoodNutrient>) {
    val catOrder = listOf("Energy", "Macronutrients", "Fats", "Minerals", "Vitamins",
        "Other", "Amino Acids", "Fatty Acids", "Sterols", "Carotenoids", "Sugars")
    val grouped = nutrients.groupBy { it.category }
    var expandedCats by remember { mutableStateOf(setOf("Macronutrients", "Vitamins", "Minerals")) }

    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Text("Nutrient Breakdown — % Daily Value",
                style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(12.dp))

            catOrder.filter { grouped.containsKey(it) }.forEach { cat ->
                val items = grouped[cat]!!
                val expanded = expandedCats.contains(cat)

                Row(Modifier.fillMaxWidth().clickable {
                    expandedCats = if (expanded) expandedCats - cat else expandedCats + cat
                }.padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(if (expanded) Icons.Filled.ExpandMore else Icons.Filled.ChevronRight,
                        contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(4.dp))
                    Text(cat, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                    Spacer(Modifier.width(4.dp))
                    Text("(${items.size})", fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.4f))
                }

                if (expanded) {
                    items.forEach { n ->
                        NutrientRow(n)
                    }
                }
            }
        }
    }
}

@Composable
private fun NutrientRow(n: USDAFoodNutrient) {
    val dvColor = when {
        n.percentDv == null -> MaterialTheme.colorScheme.onSurface.copy(alpha = 0.4f)
        n.percentDv < 25 -> Color(0xFFEF4444)
        n.percentDv < 75 -> Color(0xFFF59E0B)
        else -> Color(0xFF22C55E)
    }

    Row(Modifier.fillMaxWidth().padding(start = 20.dp, top = 2.dp, bottom = 2.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Text(n.name, fontSize = 11.sp, modifier = Modifier.weight(1f),
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f), maxLines = 1, overflow = TextOverflow.Ellipsis)
        Text("${String.format("%.1f", n.value)} ${n.unit}", fontSize = 11.sp,
            fontFamily = FontFamily.Monospace, modifier = Modifier.width(70.dp))
        n.percentDv?.let { pct ->
            Text("${pct.toInt()}%", fontSize = 10.sp, fontWeight = FontWeight.SemiBold,
                fontFamily = FontFamily.Monospace, color = dvColor, modifier = Modifier.width(36.dp))
            LinearProgressIndicator(
                progress = { (pct / 100f).coerceIn(0f, 1f) },
                modifier = Modifier.width(40.dp).height(3.dp).clip(RoundedCornerShape(1.dp)),
                color = dvColor, trackColor = dvColor.copy(alpha = 0.15f)
            )
        }
    }
}

// ─── Add Meal Dialog ───

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AddMealDialog(onDismiss: () -> Unit, onSaved: () -> Unit) {
    var foodName by remember { mutableStateOf("") }
    var mealType by remember { mutableStateOf("breakfast") }
    var servingSize by remember { mutableStateOf("") }
    var fdcId by remember { mutableStateOf<Int?>(null) }
    var notes by remember { mutableStateOf("") }
    var startTime by remember { mutableStateOf("") }
    var endTime by remember { mutableStateOf("") }
    var preMealWeight by remember { mutableStateOf("") }
    var postMealWeight by remember { mutableStateOf("") }
    var recipeUrl by remember { mutableStateOf("") }
    var saving by remember { mutableStateOf(false) }

    // Recipe-URL analysis (third meal input: URL / description / photo)
    var analyzingRecipe by remember { mutableStateOf(false) }
    var recipeInfo by remember { mutableStateOf("") }
    var recipePreview by remember { mutableStateOf<RecipeAnalyzeResponse?>(null) }

    // USDA search
    var showSearch by remember { mutableStateOf(false) }
    var searchQuery by remember { mutableStateOf("") }
    var searchResults by remember { mutableStateOf<List<USDAFoodResult>>(emptyList()) }
    var searching by remember { mutableStateOf(false) }

    // Image analysis — ALAFIAModel VISION capability via /ai/vision
    var selectedImages by remember { mutableStateOf<List<ByteArray>>(emptyList()) }
    var isAnalysingImages by remember { mutableStateOf(false) }
    var imageAnalysisResult by remember { mutableStateOf("") }
    var visionItems by remember { mutableStateOf<List<VisionItem>>(emptyList()) }
    // Editable correction rows (name, grams, basis) — editing these teaches ALAFIA.
    var visionEdits by remember { mutableStateOf<List<Triple<String, String, String>>>(emptyList()) }
    var visionSampleId by remember { mutableStateOf<Int?>(null) }
    var visionWasRecall by remember { mutableStateOf(false) }
    var teachState by remember { mutableStateOf("") }
    var teaching by remember { mutableStateOf(false) }

    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var searchJob by remember { mutableStateOf<Job?>(null) }

    // Max 3 images, matching the backend cap on /ai/vision.
    val imagePicker = rememberLauncherForActivityResult(
        ActivityResultContracts.GetMultipleContents()
    ) { uris ->
        if (uris.isNullOrEmpty()) return@rememberLauncherForActivityResult
        val room = 3 - selectedImages.size
        if (room <= 0) return@rememberLauncherForActivityResult
        val loaded = uris.take(room).mapNotNull { uri ->
            runCatching {
                context.contentResolver.openInputStream(uri)?.use { it.readBytes() }
            }.getOrNull()?.takeIf { it.isNotEmpty() }
        }
        selectedImages = selectedImages + loaded
    }

    val mealTypes = listOf("breakfast", "lunch", "dinner", "snack")

    Dialog(onDismissRequest = onDismiss) {
        Card(Modifier.fillMaxWidth().heightIn(max = 680.dp), shape = RoundedCornerShape(16.dp)) {
            Column(Modifier.verticalScroll(rememberScrollState()).padding(20.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Log New Meal", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold,
                        modifier = Modifier.weight(1f))
                    IconButton(onClick = onDismiss) { Icon(Icons.Filled.Close, contentDescription = "Close") }
                }

                Spacer(Modifier.height(8.dp))

                // ── Image analysis section ──
                OutlinedCard(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(12.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Filled.Image, contentDescription = null, modifier = Modifier.size(16.dp),
                                tint = MaterialTheme.colorScheme.primary)
                            Spacer(Modifier.width(6.dp))
                            Text("Identify Food from Image (Optional – Max 3)",
                                style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.SemiBold)
                        }
                        Text("Upload image(s) for Alafia analysis. Several shots of the same meal are read together as one plate.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f))
                        Spacer(Modifier.height(8.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedButton(onClick = { imagePicker.launch("image/*") },
                                modifier = Modifier.weight(1f), enabled = selectedImages.size < 3) {
                                Icon(Icons.Filled.PhotoLibrary, contentDescription = null, modifier = Modifier.size(14.dp))
                                Spacer(Modifier.width(4.dp))
                                Text("Choose Files", fontSize = 12.sp)
                            }
                            if (selectedImages.isNotEmpty()) {
                                OutlinedButton(onClick = {
                                    selectedImages = emptyList()
                                    visionItems = emptyList()
                                    imageAnalysisResult = ""
                                }) {
                                    Icon(Icons.Filled.Close, contentDescription = "Clear images",
                                        modifier = Modifier.size(14.dp))
                                }
                            }
                        }
                        if (selectedImages.isNotEmpty()) {
                            Spacer(Modifier.height(4.dp))
                            Text("${selectedImages.size} image(s) selected",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
                        }
                        Spacer(Modifier.height(8.dp))
                        Button(onClick = {
                            isAnalysingImages = true
                            imageAnalysisResult = ""
                            visionItems = emptyList()
                            visionEdits = emptyList()
                            visionSampleId = null
                            visionWasRecall = false
                            teachState = ""
                            scope.launch {
                                try {
                                    val parts = selectedImages.mapIndexed { i, bytes ->
                                        MultipartBody.Part.createFormData(
                                            "files", "image$i.jpg",
                                            bytes.toRequestBody("image/jpeg".toMediaTypeOrNull())
                                        )
                                    }
                                    val res = ApiClient.getApiService().routeVisionMulti(
                                        parts,
                                        "food_photo_nutrition".toRequestBody("text/plain".toMediaTypeOrNull())
                                    )
                                    val items = res.items.orEmpty().filter { !it.name.isNullOrBlank() }
                                    if (items.isEmpty()) {
                                        imageAnalysisResult = res.notes?.takeIf { it.isNotBlank() }
                                            ?: "No food recognised in that photo — enter the meal below."
                                    } else {
                                        // Prefill; everything stays editable. fdcId is cleared
                                        // because a vision estimate is not a USDA-linked food.
                                        visionItems = items
                                        visionSampleId = res.sampleId
                                        visionWasRecall = res.isRecall
                                        visionEdits = items.map {
                                            Triple(
                                                it.name.orEmpty(),
                                                it.estimatedGrams?.let { g -> g.roundToInt().toString() }.orEmpty(),
                                                it.gramsBasis.orEmpty()
                                            )
                                        }
                                        foodName = items.mapNotNull { it.name }.joinToString(", ")
                                        fdcId = null
                                        if (servingSize.isBlank()) {
                                            servingSize = items.firstOrNull()?.estimatedPortion.orEmpty()
                                        }
                                        imageAnalysisResult = res.notes.orEmpty()
                                    }
                                } catch (_: Exception) {
                                    // 503 = no vision backend configured; manual entry still works.
                                    imageAnalysisResult = "Image analysis unavailable — enter the meal below."
                                }
                                isAnalysingImages = false
                            }
                        }, modifier = Modifier.fillMaxWidth(),
                            enabled = selectedImages.isNotEmpty() && !isAnalysingImages) {
                            if (isAnalysingImages) {
                                CircularProgressIndicator(Modifier.size(14.dp), color = MaterialTheme.colorScheme.onPrimary)
                                Spacer(Modifier.width(6.dp))
                                Text("Analysing…")
                            } else {
                                Icon(Icons.Filled.AutoAwesome, contentDescription = null, modifier = Modifier.size(14.dp))
                                Spacer(Modifier.width(6.dp))
                                Text("Analyse Image(s) with Alafia")
                            }
                        }
                        if (visionEdits.isNotEmpty()) {
                            Spacer(Modifier.height(6.dp))
                            if (visionWasRecall) {
                                Text("✓ Recognised from a meal you labelled before — no model needed.",
                                    style = MaterialTheme.typography.bodySmall, color = Color(0xFF16A34A))
                            }
                            // Editable rows: correcting these is what teaches ALAFIA.
                            visionEdits.forEachIndexed { i, row ->
                                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                    OutlinedTextField(
                                        value = row.first,
                                        onValueChange = { v ->
                                            visionEdits = visionEdits.toMutableList()
                                                .also { it[i] = row.copy(first = v) }
                                        },
                                        label = { Text("Food", fontSize = 10.sp) },
                                        singleLine = true,
                                        textStyle = LocalTextStyle.current.copy(fontSize = 12.sp),
                                        modifier = Modifier.weight(1f))
                                    OutlinedTextField(
                                        value = row.second,
                                        onValueChange = { v ->
                                            visionEdits = visionEdits.toMutableList()
                                                .also { it[i] = row.copy(second = v.filter(Char::isDigit)) }
                                        },
                                        label = { Text("g", fontSize = 10.sp) },
                                        singleLine = true,
                                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                                        textStyle = LocalTextStyle.current.copy(fontSize = 12.sp),
                                        modifier = Modifier.width(78.dp))
                                    IconButton(onClick = {
                                        visionEdits = visionEdits.toMutableList().also { it.removeAt(i) }
                                    }) { Icon(Icons.Filled.Close, contentDescription = "Remove", Modifier.size(14.dp)) }
                                }
                                if (row.third.isNotEmpty()) {
                                    Text(row.third, style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f))
                                }
                            }
                            Row(verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                TextButton(onClick = {
                                    visionEdits = visionEdits + Triple("", "", "")
                                }) { Text("+ Add food", fontSize = 12.sp) }
                                OutlinedButton(
                                    enabled = visionSampleId != null && !teaching,
                                    onClick = {
                                        val sid = visionSampleId ?: return@OutlinedButton
                                        teaching = true; teachState = ""
                                        scope.launch {
                                            try {
                                                val payload = visionEdits
                                                    .filter { it.first.isNotBlank() }
                                                    .map { VisionFeedbackItem(it.first.trim(), it.second.toDoubleOrNull()) }
                                                val res = ApiClient.getApiService()
                                                    .submitVisionFeedback(VisionFeedbackRequest(sid, payload))
                                                teachState = when (res.correctionKind) {
                                                    "accepted" -> "Confirmed — thanks, that matched."
                                                    "item" -> "Saved — ALAFIA learned the right foods."
                                                    "quantity" -> "Saved — ALAFIA learned the right amounts."
                                                    "both" -> "Saved — ALAFIA learned the foods and amounts."
                                                    else -> "Saved."
                                                }
                                                val names = payload.map { it.name }
                                                if (names.isNotEmpty()) foodName = names.joinToString(", ")
                                            } catch (_: Exception) {
                                                teachState = "Could not save your correction."
                                            }
                                            teaching = false
                                        }
                                    }) {
                                    if (teaching) {
                                        CircularProgressIndicator(Modifier.size(12.dp), strokeWidth = 2.dp)
                                    } else Text("Confirm / correct", fontSize = 12.sp)
                                }
                            }
                            if (teachState.isNotEmpty()) {
                                Text(teachState, style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f))
                            }
                            Text("Estimate only — check the food name and serving size before saving.",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f))
                        }
                        if (imageAnalysisResult.isNotEmpty()) {
                            Spacer(Modifier.height(4.dp))
                            Text(imageAnalysisResult, style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
                        }
                    }
                }

                Spacer(Modifier.height(12.dp))

                // USDA Search button
                OutlinedButton(onClick = { showSearch = !showSearch }, modifier = Modifier.fillMaxWidth()) {
                    Icon(Icons.Filled.Search, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("Search USDA Database")
                    if (fdcId != null) {
                        Spacer(Modifier.width(6.dp))
                        Icon(Icons.Filled.CheckCircle, contentDescription = null, modifier = Modifier.size(16.dp),
                            tint = Color(0xFF22C55E))
                    }
                }

                if (showSearch) {
                    Spacer(Modifier.height(8.dp))
                    OutlinedTextField(value = searchQuery, onValueChange = { q ->
                        searchQuery = q
                        searchJob?.cancel()
                        if (q.length >= 2) {
                            searchJob = scope.launch {
                                delay(400)
                                searching = true
                                try { searchResults = ApiClient.getApiService().searchUSDAFoods(q) } catch (_: Exception) {}
                                searching = false
                            }
                        }
                    }, modifier = Modifier.fillMaxWidth(), placeholder = { Text("e.g. banana, chicken breast…") },
                        singleLine = true,
                        trailingIcon = { if (searching) CircularProgressIndicator(Modifier.size(16.dp)) })

                    searchResults.take(8).forEach { food ->
                        Row(Modifier.fillMaxWidth().clickable {
                            foodName = food.description
                            fdcId = food.fdcId
                            servingSize = food.servingSize?.let { "${it.toInt()} ${food.servingSizeUnit ?: "g"}" } ?: "100 g"
                            showSearch = false; searchQuery = ""; searchResults = emptyList()
                        }.padding(vertical = 6.dp, horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text(food.description, fontSize = 13.sp, fontWeight = FontWeight.Medium, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                Text("${food.nutrients.size} nutrients" +
                                        (food.nutrients["calories"]?.let { " · ${it.toInt()} kcal" } ?: ""),
                                    fontSize = 10.sp, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f))
                            }
                        }
                        HorizontalDivider()
                    }
                }

                if (fdcId != null) {
                    Spacer(Modifier.height(6.dp))
                    Row(Modifier.background(Color(0xFF22C55E).copy(alpha = 0.08f), RoundedCornerShape(8.dp))
                        .padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Filled.Bolt, contentDescription = null, modifier = Modifier.size(14.dp), tint = Color(0xFF22C55E))
                        Spacer(Modifier.width(6.dp))
                        Text("Nutrients auto-populated from USDA", fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
                    }
                }

                Spacer(Modifier.height(12.dp))
                OutlinedTextField(value = foodName, onValueChange = { foodName = it; fdcId = null },
                    label = { Text("Food name") }, modifier = Modifier.fillMaxWidth(), singleLine = true)

                Spacer(Modifier.height(8.dp))
                // Meal type
                var mealExpanded by remember { mutableStateOf(false) }
                ExposedDropdownMenuBox(expanded = mealExpanded, onExpandedChange = { mealExpanded = it }) {
                    OutlinedTextField(value = mealType.replaceFirstChar { it.uppercase() }, onValueChange = {},
                        readOnly = true, label = { Text("Meal type") }, modifier = Modifier.fillMaxWidth().menuAnchor(),
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = mealExpanded) })
                    ExposedDropdownMenu(expanded = mealExpanded, onDismissRequest = { mealExpanded = false }) {
                        mealTypes.forEach { mt ->
                            DropdownMenuItem(text = { Text(mt.replaceFirstChar { it.uppercase() }) },
                                onClick = { mealType = mt; mealExpanded = false })
                        }
                    }
                }

                Spacer(Modifier.height(8.dp))
                OutlinedTextField(value = servingSize, onValueChange = { servingSize = it },
                    label = { Text("Serving size") }, modifier = Modifier.fillMaxWidth(), singleLine = true,
                    placeholder = { Text("e.g. 100 g") })

                // ── Meal Timing ──
                Spacer(Modifier.height(12.dp))
                Text("Meal Timing (Optional)", style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
                Spacer(Modifier.height(4.dp))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(value = startTime, onValueChange = { startTime = it },
                        label = { Text("Start Time") }, modifier = Modifier.weight(1f), singleLine = true,
                        placeholder = { Text("08:00") },
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number))
                    OutlinedTextField(value = endTime, onValueChange = { endTime = it },
                        label = { Text("End Time") }, modifier = Modifier.weight(1f), singleLine = true,
                        placeholder = { Text("08:30") },
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number))
                }

                // ── Weight Tracking ──
                Spacer(Modifier.height(8.dp))
                Text("Weight Tracking (Optional)", style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
                Spacer(Modifier.height(4.dp))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(value = preMealWeight, onValueChange = { preMealWeight = it },
                        label = { Text("Pre-Meal kg") }, modifier = Modifier.weight(1f), singleLine = true,
                        placeholder = { Text("70.0") },
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal))
                    OutlinedTextField(value = postMealWeight, onValueChange = { postMealWeight = it },
                        label = { Text("Post-Meal kg") }, modifier = Modifier.weight(1f), singleLine = true,
                        placeholder = { Text("70.5") },
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal))
                }

                Spacer(Modifier.height(8.dp))
                Text("Recipe URL (Optional)", style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
                Spacer(Modifier.height(4.dp))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    OutlinedTextField(value = recipeUrl, onValueChange = { recipeUrl = it },
                        modifier = Modifier.weight(1f), singleLine = true,
                        placeholder = { Text("https://example.com/recipe") },
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri))
                    Button(
                        onClick = {
                            val url = recipeUrl.trim()
                            if (url.isBlank()) return@Button
                            analyzingRecipe = true; recipeInfo = ""
                            scope.launch {
                                try {
                                    // Parse the page's structured recipe, price the ingredients, prefill
                                    // per-serving nutrition. Published nutrition is learned server-side.
                                    val data = ApiClient.getApiService()
                                        .analyzeRecipeUrl(RecipeAnalyzeRequest(url = url))
                                    if (foodName.isBlank()) { foodName = data.name; fdcId = null }
                                    if (servingSize.isBlank()) servingSize = "1 serving (of ${data.servings})"
                                    recipePreview = data
                                    recipeInfo = "${data.name} — ${data.ingredients.size} ingredients, " +
                                        "${data.servings} servings" +
                                        (if (data.learned) ". Published nutrition learned for this dish." else "")
                                } catch (e: Exception) {
                                    recipePreview = null
                                    recipeInfo = "Could not analyze that recipe link"
                                }
                                analyzingRecipe = false
                            }
                        },
                        enabled = recipeUrl.isNotBlank() && !analyzingRecipe
                    ) {
                        if (analyzingRecipe)
                            CircularProgressIndicator(Modifier.size(16.dp), color = MaterialTheme.colorScheme.onPrimary)
                        else Text("Analyze")
                    }
                }
                if (recipeInfo.isNotEmpty()) {
                    Spacer(Modifier.height(4.dp))
                    Text(recipeInfo, style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
                }
                recipePreview?.let { rp ->
                    Spacer(Modifier.height(6.dp))
                    RecipePreviewCard(rp)
                }

                Spacer(Modifier.height(8.dp))
                OutlinedTextField(value = notes, onValueChange = { notes = it },
                    label = { Text("Notes (optional)") }, modifier = Modifier.fillMaxWidth(), maxLines = 3)

                Spacer(Modifier.height(16.dp))
                Button(onClick = {
                    saving = true
                    scope.launch {
                        try {
                            ApiClient.getApiService().createNutritionLog(
                                NutritionLogRequest(
                                    logDate = LocalDate.now().toString(),
                                    mealType = mealType,
                                    foodName = foodName,
                                    servingSize = servingSize.ifBlank { null },
                                    fdcId = fdcId,
                                    notes = notes.ifBlank { null },
                                    startTime = startTime.ifBlank { null },
                                    endTime = endTime.ifBlank { null },
                                    preMealWeightKg = preMealWeight.toFloatOrNull(),
                                    postMealWeightKg = postMealWeight.toFloatOrNull(),
                                    recipeUrl = recipeUrl.ifBlank { null }
                                )
                            )
                            onSaved(); onDismiss()
                        } catch (_: Exception) {}
                        saving = false
                    }
                }, modifier = Modifier.fillMaxWidth(), enabled = foodName.isNotBlank() && !saving) {
                    if (saving) CircularProgressIndicator(Modifier.size(16.dp), color = MaterialTheme.colorScheme.onPrimary)
                    else Text("Save")
                }
            }
        }
    }
}

// ─── Food Detail Dialog ───

@Composable
private fun FoodDetailDialog(fdcId: Int, onDismiss: () -> Unit) {
    var detail by remember { mutableStateOf<USDAFoodDetail?>(null) }
    var loading by remember { mutableStateOf(true) }

    LaunchedEffect(fdcId) {
        try { detail = ApiClient.getApiService().getUSDAFoodDetail(fdcId) } catch (_: Exception) {}
        loading = false
    }

    Dialog(onDismissRequest = onDismiss) {
        Card(Modifier.fillMaxWidth().heightIn(max = 550.dp), shape = RoundedCornerShape(16.dp)) {
            Column(Modifier.padding(16.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Nutrient Profile", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold,
                        modifier = Modifier.weight(1f))
                    IconButton(onClick = onDismiss) { Icon(Icons.Filled.Close, contentDescription = "Close") }
                }

                if (loading) {
                    Box(Modifier.fillMaxWidth().height(200.dp), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator()
                    }
                } else if (detail != null) {
                    val d = detail!!
                    Text(d.description, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                    Row(Modifier.padding(top = 4.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        d.dataType?.let { InfoChip(it) }
                        d.foodCategory?.let { InfoChip(it) }
                        InfoChip("FDC ${d.fdcId}")
                    }
                    Spacer(Modifier.height(12.dp))

                    Column(Modifier.verticalScroll(rememberScrollState()).weight(1f)) {
                        NutrientBreakdownCard(d.nutrientBreakdown)
                    }
                } else {
                    Box(Modifier.fillMaxWidth().height(200.dp), contentAlignment = Alignment.Center) {
                        Text("Failed to load", color = MaterialTheme.colorScheme.error)
                    }
                }
            }
        }
    }
}

@Composable
private fun InfoChip(text: String) {
    Text(text, fontSize = 9.sp, fontWeight = FontWeight.Medium,
        color = Color(0xFF3B82F6),
        modifier = Modifier.background(Color(0xFF3B82F6).copy(alpha = 0.1f), RoundedCornerShape(50))
            .padding(horizontal = 8.dp, vertical = 3.dp))
}

// ─── Recipe Analysis Preview ───

@Composable
private fun RecipePreviewCard(data: RecipeAnalyzeResponse) {
    val ps = data.perServing
    fun macro(key: String, unit: String): String {
        val x = ps[key] ?: return "-"
        val num = if (x >= 10) x.roundToInt().toString() else String.format("%.1f", x)
        return "$num$unit"
    }
    val sourceLabel = if (data.source == "published") "recipe (published)" else "recipe (estimated)"

    Card(Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primary.copy(alpha = 0.06f))) {
        Column(Modifier.padding(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Filled.AutoAwesome, contentDescription = null, modifier = Modifier.size(14.dp),
                    tint = MaterialTheme.colorScheme.primary)
                Spacer(Modifier.width(6.dp))
                Text("Per serving · $sourceLabel", style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.SemiBold)
            }
            Spacer(Modifier.height(8.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                PreviewMacro("Calories", macro("calories", ""))
                PreviewMacro("Protein", macro("protein_g", " g"))
                PreviewMacro("Carbs", macro("carbs_g", " g"))
                PreviewMacro("Fat", macro("fat_g", " g"))
            }
            Text("Suggestions — final nutrients are computed server-side when you save.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.45f),
                modifier = Modifier.padding(top = 8.dp))
        }
    }
}

@Composable
private fun PreviewMacro(label: String, value: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, fontWeight = FontWeight.Bold, fontSize = 13.sp)
        Text(label, fontSize = 10.sp, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f))
    }
}

@Composable
private fun DailyTargetsCard(data: GoalProgressResponse) {
    val condLabels = mapOf(
        "ckd" to "CKD", "dialysis" to "Dialysis", "diabetes" to "Diabetes",
        "hypertension" to "Hypertension", "cardiovascular" to "Cardiac", "heart_failure" to "Heart failure"
    )
    fun statusColor(s: String) = when (s) {
        "ok" -> Color(0xFF22C55E)
        "over" -> Color(0xFFEF4444)
        else -> Color(0xFFF59E0B)   // low / warning
    }
    fun fmt(v: Float) = if (v < 10f) String.format("%.1f", v) else v.roundToInt().toString()

    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Text("Daily Targets", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)

            if (data.conditions.isNotEmpty()) {
                Spacer(Modifier.height(6.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    data.conditions.forEach { c ->
                        Text(condLabels[c] ?: c, fontSize = 10.sp, fontWeight = FontWeight.SemiBold,
                            color = Color(0xFFEF4444),
                            modifier = Modifier.background(Color(0xFFEF4444).copy(alpha = 0.12f), RoundedCornerShape(50))
                                .padding(horizontal = 8.dp, vertical = 3.dp))
                    }
                }
            }
            if (!data.profileComplete) {
                Spacer(Modifier.height(6.dp))
                Text("Add your age, height & weight in Profile for goals tailored to you.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
            }

            Spacer(Modifier.height(10.dp))
            data.goals.forEach { g ->
                val color = statusColor(g.status)
                Column(Modifier.padding(vertical = 4.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(
                            if (g.kind == "limit") Icons.Filled.ArrowDownward else Icons.Filled.ArrowUpward,
                            contentDescription = if (g.kind == "limit") "stay under" else "aim for",
                            tint = color, modifier = Modifier.size(14.dp)
                        )
                        Spacer(Modifier.width(4.dp))
                        Text(g.name, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Medium)
                        Spacer(Modifier.weight(1f))
                        Text("${fmt(g.current)}/${fmt(g.goal)} ${g.unit}",
                            style = MaterialTheme.typography.bodySmall, fontFamily = FontFamily.Monospace,
                            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
                    }
                    Spacer(Modifier.height(3.dp))
                    LinearProgressIndicator(
                        progress = { (g.pct / 100f).coerceIn(0f, 1f) },
                        color = color,
                        trackColor = color.copy(alpha = 0.2f),
                        modifier = Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(50))
                    )
                }
            }

            Spacer(Modifier.height(8.dp))
            Text("↑ aim for · ↓ stay under. Based on your biology & conditions — not medical advice.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.45f))
        }
    }
}
