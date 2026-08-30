@file:OptIn(ExperimentalMaterial3Api::class)

package com.alafia.android.views.wellness
import com.alafia.android.util.ErrorUtil

import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
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
fun WellnessScreen(navController: NavHostController) {
    var selectedTab by remember { mutableIntStateOf(0) }
    val tabs = listOf("Score", "HEBCS Ω", "Trends", "Recommendations", "Improvements")

    Scaffold(
        topBar = { TopAppBar(
                title = { Text("Wellness") },
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
                0 -> ScoreTab()
                1 -> HEBCSTab()
                2 -> TrendsTab()
                3 -> RecommendationsTab()
                4 -> ImprovementsTab()
            }
        }
    }
}

// ── Score Tab ────────────────────────────────────────────────────────────────

@Composable
private fun ScoreTab() {
    var score by remember { mutableStateOf<WellnessScore?>(null) }
    var isLoading by remember { mutableStateOf(true) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    LaunchedEffect(Unit) {
        scope.launch {
            isLoading = true
            try {
                score = ApiClient.getApiService().getWellnessScore()
            } catch (e: Exception) {
                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
            }
            isLoading = false
        }
    }

    if (isLoading) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator()
        }
    } else if (score == null) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Text("No wellness score available", color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    } else {
        val s = score!!
        LazyColumn(
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    elevation = CardDefaults.cardElevation(defaultElevation = 4.dp)
                ) {
                    Column(
                        modifier = Modifier.fillMaxWidth().padding(24.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Text("Overall Wellness Score", style = MaterialTheme.typography.titleMedium)
                        Spacer(Modifier.height(8.dp))
                        // null means nothing could be measured. Formatting it as
                        // a number would print a confident 0 for a patient we
                        // have no data on.
                        val overall = s.overallScore
                        if (overall == null) {
                            Text(
                                "Not enough data yet",
                                style = MaterialTheme.typography.titleLarge,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        } else {
                            Text(
                                String.format("%.0f", overall),
                                style = MaterialTheme.typography.displayLarge,
                                fontWeight = FontWeight.Bold,
                                color = MaterialTheme.colorScheme.primary
                            )
                            Spacer(Modifier.height(8.dp))
                            LinearProgressIndicator(
                                progress = { (overall / 100.0).toFloat().coerceIn(0f, 1f) },
                                modifier = Modifier.fillMaxWidth().height(8.dp),
                                trackColor = MaterialTheme.colorScheme.surfaceVariant,
                            )
                        }
                        s.confidence?.let { c ->
                            if (c < 1.0) {
                                Spacer(Modifier.height(6.dp))
                                Text(
                                    "Based on ${(c * 100).toInt()}% of the usual picture.",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                        }
                        if (s.explanation != null) {
                            Spacer(Modifier.height(12.dp))
                            Text(s.explanation, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }

            item {
                Text("Sub-Scores", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            }

            val subScores = listOf(
                "Nutrition" to s.nutritionScore,
                "Fitness" to s.fitnessScore,
                "Sleep" to s.sleepScore,
                "Mood" to s.moodScore,
                "Vitals" to s.vitalsScore,
                "Medication Adherence" to s.medicationAdherenceScore
            )

            items(subScores) { (label, value) ->
                SubScoreRow(label = label, value = value)
            }
        }
    }
}

@Composable
private fun SubScoreRow(label: String, value: Double?) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(label, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Medium)
                Spacer(Modifier.height(4.dp))
                // An empty bar reads as a zero score. Where the domain was
                // never measured, say so instead of drawing one.
                if (value == null) {
                    Text("not measured", style = MaterialTheme.typography.bodySmall,
                         color = MaterialTheme.colorScheme.onSurfaceVariant)
                } else {
                    LinearProgressIndicator(
                        progress = { (value / 100.0).toFloat().coerceIn(0f, 1f) },
                        modifier = Modifier.fillMaxWidth().height(6.dp),
                        trackColor = MaterialTheme.colorScheme.surfaceVariant,
                    )
                }
            }
            Spacer(Modifier.width(12.dp))
            Text(
                if (value != null) String.format("%.0f", value) else "—",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.primary
            )
        }
    }
}

// ── Trends Tab ──────────────────────────────────────────────────────────────

@Composable
private fun TrendsTab() {
    var trendsResponse by remember { mutableStateOf<HealthTrendResponse?>(null) }
    var isLoading by remember { mutableStateOf(true) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    LaunchedEffect(Unit) {
        scope.launch {
            isLoading = true
            try {
                trendsResponse = ApiClient.getApiService().getHealthTrends()
            } catch (e: Exception) {
                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
            }
            isLoading = false
        }
    }

    if (isLoading) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator()
        }
    } else if (trendsResponse == null || trendsResponse!!.streams.isEmpty()) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Text("No trend data available", color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    } else {
        val resp = trendsResponse!!
        LazyColumn(
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            if (resp.overallSummary != null) {
                item {
                    Card(modifier = Modifier.fillMaxWidth()) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            Text("Summary", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                            Spacer(Modifier.height(4.dp))
                            Text(resp.overallSummary, style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
            }

            items(resp.streams) { stream ->
                TrendStreamCard(stream = stream)
            }

            if (!resp.correlations.isNullOrEmpty()) {
                item {
                    Card(modifier = Modifier.fillMaxWidth()) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            Text("Correlations", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                            Spacer(Modifier.height(4.dp))
                            resp.correlations.forEach { c ->
                                Text("• $c", style = MaterialTheme.typography.bodySmall)
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun TrendStreamCard(stream: TrendStream) {
    val trendIcon = when (stream.trend?.lowercase()) {
        "up", "increasing" -> Icons.Default.TrendingUp
        "down", "decreasing" -> Icons.Default.TrendingDown
        else -> Icons.Default.TrendingFlat
    }
    val trendColor = when (stream.trend?.lowercase()) {
        "up", "increasing" -> Color(0xFF388E3C)
        "down", "decreasing" -> Color(0xFFD32F2F)
        else -> MaterialTheme.colorScheme.onSurfaceVariant
    }

    Card(modifier = Modifier.fillMaxWidth(), elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(stream.name, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(trendIcon, contentDescription = stream.trend, tint = trendColor, modifier = Modifier.size(20.dp))
                    Spacer(Modifier.width(4.dp))
                    Text(
                        stream.trend?.replaceFirstChar { it.uppercase() } ?: "Steady",
                        style = MaterialTheme.typography.labelSmall,
                        color = trendColor
                    )
                }
            }

            if (stream.data.isNotEmpty()) {
                Spacer(Modifier.height(8.dp))
                stream.data.takeLast(5).forEach { point ->
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(point.date, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(
                            String.format("%.1f", point.value) + (if (point.label != null) " ${point.label}" else ""),
                            style = MaterialTheme.typography.bodySmall,
                            fontWeight = FontWeight.Medium
                        )
                    }
                }
            }
        }
    }
}

// ── Recommendations Tab ─────────────────────────────────────────────────────

@Composable
private fun RecommendationsTab() {
    var recsResponse by remember { mutableStateOf<DailyRecommendationsResponse?>(null) }
    var isLoading by remember { mutableStateOf(true) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    LaunchedEffect(Unit) {
        scope.launch {
            isLoading = true
            try {
                recsResponse = ApiClient.getApiService().getDailyRecommendations()
            } catch (e: Exception) {
                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
            }
            isLoading = false
        }
    }

    if (isLoading) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator()
        }
    } else if (recsResponse == null || recsResponse!!.recommendations.isEmpty()) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Text("No recommendations available", color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    } else {
        val grouped = recsResponse!!.recommendations.groupBy { it.category }
        LazyColumn(
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            item {
                Text("Date: ${recsResponse!!.date}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }

            grouped.forEach { (category, items) ->
                item {
                    Text(
                        category.replaceFirstChar { it.uppercase() },
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(top = 4.dp)
                    )
                }
                items(items) { rec ->
                    RecommendationCard(rec = rec)
                }
            }
        }
    }
}

@Composable
private fun RecommendationCard(rec: RecommendationItem) {
    val priorityColor = when (rec.priority.lowercase()) {
        "high" -> Color(0xFFD32F2F)
        "medium" -> Color(0xFFF9A825)
        "low" -> Color(0xFF388E3C)
        else -> MaterialTheme.colorScheme.onSurfaceVariant
    }

    Card(modifier = Modifier.fillMaxWidth(), elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(rec.title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                Spacer(Modifier.width(8.dp))
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = priorityColor.copy(alpha = 0.15f)
                ) {
                    Text(
                        rec.priority.uppercase(),
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp),
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.Bold,
                        color = priorityColor
                    )
                }
            }
            Spacer(Modifier.height(4.dp))
            Text(rec.description, style = MaterialTheme.typography.bodySmall)
            if (rec.action != null) {
                Spacer(Modifier.height(6.dp))
                Text("Action: ${rec.action}", style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.Medium, color = MaterialTheme.colorScheme.primary)
            }
        }
    }
}

// ── Improvements Tab ────────────────────────────────────────────────────────

@Composable
private fun ImprovementsTab() {
    var improvements by remember { mutableStateOf<HealthImprovementsResponse?>(null) }
    var isLoading by remember { mutableStateOf(true) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    LaunchedEffect(Unit) {
        scope.launch {
            isLoading = true
            try {
                improvements = ApiClient.getApiService().getHealthImprovements()
            } catch (e: Exception) {
                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
            }
            isLoading = false
        }
    }

    if (isLoading) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator()
        }
    } else if (improvements == null) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Text("No improvement data available", color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    } else {
        val imp = improvements!!
        LazyColumn(
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            if (imp.summary != null) {
                item {
                    Card(modifier = Modifier.fillMaxWidth(), elevation = CardDefaults.cardElevation(defaultElevation = 4.dp)) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            Text("Summary", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                            Spacer(Modifier.height(4.dp))
                            Text(imp.summary, style = MaterialTheme.typography.bodyMedium)
                            if (imp.wellnessScore != null) {
                                Spacer(Modifier.height(8.dp))
                                Text(
                                    "Wellness Score: ${String.format("%.0f", imp.wellnessScore)}",
                                    style = MaterialTheme.typography.titleSmall,
                                    color = MaterialTheme.colorScheme.primary,
                                    fontWeight = FontWeight.Bold
                                )
                            }
                        }
                    }
                }
            }

            val categories = listOf(
                "Nutrition" to imp.nutritionImprovements,
                "Fitness" to imp.fitnessImprovements,
                "Sleep" to imp.sleepImprovements,
                "Mood" to imp.moodImprovements,
                "Medical" to imp.medicalImprovements
            )

            categories.forEach { (name, items) ->
                if (!items.isNullOrEmpty()) {
                    item {
                        ImprovementCategoryCard(name = name, items = items)
                    }
                }
            }
        }
    }
}

@Composable
private fun ImprovementCategoryCard(name: String, items: List<String>) {
    Card(modifier = Modifier.fillMaxWidth(), elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(name, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(8.dp))
            items.forEach { item ->
                Row(modifier = Modifier.padding(vertical = 2.dp)) {
                    Icon(Icons.Default.CheckCircle, contentDescription = null, modifier = Modifier.size(16.dp), tint = Color(0xFF388E3C))
                    Spacer(Modifier.width(8.dp))
                    Text(item, style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}

// ── HEBCS Ω Tab ─────────────────────────────────────────────────────────────

private val PATHWAY_COLORS = mapOf(
    "Metabolic" to Color(0xFF10B981),
    "Hematologic" to Color(0xFFEF4444),
    "Bone_Mineral" to Color(0xFFF59E0B),
    "Cardiovascular" to Color(0xFF3B82F6),
    "Nutritional" to Color(0xFF8B5CF6),
    "Dialysis_Adequacy" to Color(0xFF06B6D4),
    "Inflammatory" to Color(0xFFEC4899),
)

private data class WhatIfParam(
    val label: String, val unit: String,
    val min: Double, val max: Double, val step: Double
)

private val WHATIF_PARAMS = listOf(
    WhatIfParam("Phosphorus",  "mg/dL", 1.5,   9.0,  0.1),
    WhatIfParam("Potassium",   "mEq/L", 2.5,   7.0,  0.1),
    WhatIfParam("Albumin",     "g/dL",  1.5,   5.5,  0.1),
    WhatIfParam("Hemoglobin",  "g/dL",  6.0,  18.0,  0.1),
    WhatIfParam("Ferritin",    "µg/L",  10.0, 2000.0, 10.0),
    WhatIfParam("KtV",         "",      0.5,   2.5,  0.05),
    WhatIfParam("PTH",         "pg/mL", 15.0, 2000.0, 10.0),
    WhatIfParam("Calcium",     "mg/dL", 6.5,  12.0,  0.1),
)

@Composable
private fun HEBCSTab() {
    var data by remember { mutableStateOf<HEBCSScoreResponse?>(null) }
    var isLoading by remember { mutableStateOf(true) }
    var errorMsg by remember { mutableStateOf<String?>(null) }
    var showWhatIf by remember { mutableStateOf(false) }
    val enabled = remember { mutableStateMapOf<String, Boolean>() }
    val sliderValues = remember { mutableStateMapOf<String, Float>() }
    var whatIfResult by remember { mutableStateOf<WhatIfResponse?>(null) }
    var isRunning by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    fun load() {
        scope.launch {
            isLoading = true; errorMsg = null
            try {
                data = ApiClient.getApiService().getHEBCSScore()
            } catch (e: Exception) {
                errorMsg = e.message ?: "Failed to load HEBCS Ω"
            }
            isLoading = false
        }
    }

    LaunchedEffect(Unit) { load() }

    if (isLoading) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
        return
    }
    if (errorMsg != null || data == null) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(errorMsg ?: "No data", color = MaterialTheme.colorScheme.error)
                Spacer(Modifier.height(8.dp))
                Button(onClick = { load() }) { Text("Retry") }
            }
        }
        return
    }

    val d = data!!
    val omegaColor = when {
        d.omega >= 0.65 -> Color(0xFF10B981)
        d.omega >= 0.45 -> Color(0xFFF59E0B)
        else -> Color(0xFFEF4444)
    }
    val omegaLabel = when {
        d.omega >= 0.65 -> "Good"
        d.omega >= 0.45 -> "Moderate"
        else -> "Critical"
    }

    LazyColumn(
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        // Ω Gauge card
        item {
            Card(modifier = Modifier.fillMaxWidth(), elevation = CardDefaults.cardElevation(4.dp)) {
                Column(
                    modifier = Modifier.fillMaxWidth().padding(24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Box(contentAlignment = Alignment.Center, modifier = Modifier.size(160.dp)) {
                        CircularProgressIndicator(
                            progress = { 1f },
                            modifier = Modifier.fillMaxSize(),
                            color = Color.Gray.copy(alpha = 0.12f),
                            strokeWidth = 14.dp,
                            strokeCap = StrokeCap.Round,
                        )
                        CircularProgressIndicator(
                            progress = { d.omega.toFloat().coerceIn(0.001f, 0.999f) },
                            modifier = Modifier.fillMaxSize(),
                            color = omegaColor,
                            strokeWidth = 14.dp,
                            strokeCap = StrokeCap.Round,
                        )
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(
                                String.format("Ω %.3f", d.omega),
                                style = MaterialTheme.typography.headlineSmall,
                                fontWeight = FontWeight.Black,
                                color = omegaColor
                            )
                            Text(omegaLabel, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                    Spacer(Modifier.height(16.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(32.dp)) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(
                                String.format("%.0f%%", d.omegaPct),
                                style = MaterialTheme.typography.titleLarge,
                                fontWeight = FontWeight.Bold,
                                color = MaterialTheme.colorScheme.primary
                            )
                            Text("Score 0–100", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            val covColor = if (d.dataCoverage >= 0.6) Color(0xFF10B981) else Color(0xFFF59E0B)
                            Text(
                                String.format("%.0f%%", d.dataCoverage * 100),
                                style = MaterialTheme.typography.titleLarge,
                                fontWeight = FontWeight.Bold,
                                color = covColor
                            )
                            Text("Data coverage", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                    if (d.labDateUsed != null) {
                        Spacer(Modifier.height(4.dp))
                        Text("Latest labs: ${d.labDateUsed}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }

        // Interpretation
        if (d.interpretation != null) {
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = Color(0xFFF0FDF4))
                ) {
                    Row(modifier = Modifier.padding(16.dp)) {
                        Icon(Icons.Default.CheckCircle, contentDescription = null, tint = Color(0xFF15803D), modifier = Modifier.size(20.dp))
                        Spacer(Modifier.width(8.dp))
                        Text(d.interpretation, style = MaterialTheme.typography.bodySmall, color = Color(0xFF15803D))
                    }
                }
            }
        }

        // Pathway Breakdown
        item {
            Card(modifier = Modifier.fillMaxWidth(), elevation = CardDefaults.cardElevation(2.dp)) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text("Pathway Breakdown", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                    Spacer(Modifier.height(12.dp))
                    d.pathways.entries.sortedBy { it.key }.forEach { (name, pw) ->
                        val color = PATHWAY_COLORS[name] ?: Color.Gray
                        val pct = ((pw.score ?: 0.0) * 100).toInt()
                        Column(modifier = Modifier.padding(vertical = 6.dp)) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text(
                                    name.replace("_", " "),
                                    style = MaterialTheme.typography.bodySmall,
                                    fontWeight = FontWeight.Medium
                                )
                                Text(
                                    if (pw.score != null) "$pct%" else "N/A",
                                    style = MaterialTheme.typography.bodySmall,
                                    fontWeight = FontWeight.Bold,
                                    color = if (pw.score != null) color else MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                            Spacer(Modifier.height(4.dp))
                            LinearProgressIndicator(
                                progress = { ((pw.score ?: 0.0).toFloat()).coerceIn(0f, 1f) },
                                modifier = Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(3.dp)),
                                color = color,
                                trackColor = Color.Gray.copy(alpha = 0.12f),
                            )
                        }
                    }
                }
            }
        }

        // What-If Simulator
        item {
            Card(modifier = Modifier.fillMaxWidth(), elevation = CardDefaults.cardElevation(2.dp)) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Default.Tune, contentDescription = null, tint = Color(0xFF8B5CF6), modifier = Modifier.size(20.dp))
                            Spacer(Modifier.width(6.dp))
                            Text("What-If Simulator", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                        }
                        IconButton(onClick = { showWhatIf = !showWhatIf }, modifier = Modifier.size(32.dp)) {
                            Icon(
                                if (showWhatIf) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                                contentDescription = null,
                                modifier = Modifier.size(20.dp)
                            )
                        }
                    }

                    if (showWhatIf) {
                        Spacer(Modifier.height(8.dp))
                        Text(
                            "Enable checkboxes to override biomarkers, then run simulation.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Spacer(Modifier.height(12.dp))

                        WHATIF_PARAMS.forEach { param ->
                            val isOn = enabled[param.label] ?: false
                            val sliderMid = ((param.min + param.max) / 2).toFloat()
                            val sliderVal = sliderValues[param.label] ?: sliderMid
                            val fmt = if (param.step < 1) "%.1f" else "%.0f"

                            Column(modifier = Modifier.padding(vertical = 4.dp).then(if (!isOn) Modifier else Modifier)) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Checkbox(
                                        checked = isOn,
                                        onCheckedChange = { enabled[param.label] = it }
                                    )
                                    Text(
                                        "${param.label}${if (param.unit.isNotEmpty()) " (${param.unit})" else ""}",
                                        style = MaterialTheme.typography.bodySmall,
                                        modifier = Modifier.weight(1f),
                                        color = if (isOn) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                    if (isOn) {
                                        Text(
                                            String.format(fmt, sliderVal),
                                            style = MaterialTheme.typography.bodySmall,
                                            fontWeight = FontWeight.Bold,
                                            color = Color(0xFF8B5CF6)
                                        )
                                    }
                                }
                                if (isOn) {
                                    Slider(
                                        value = sliderVal,
                                        onValueChange = { sliderValues[param.label] = it },
                                        valueRange = param.min.toFloat()..param.max.toFloat(),
                                        steps = ((param.max - param.min) / param.step).toInt() - 1,
                                        modifier = Modifier.fillMaxWidth()
                                    )
                                }
                            }
                        }

                        Spacer(Modifier.height(8.dp))
                        val activeCount = enabled.values.count { it }
                        Button(
                            onClick = {
                                scope.launch {
                                    isRunning = true
                                    try {
                                        val req = WhatIfRequest(
                                            phosphorus  = if (enabled["Phosphorus"]  == true) sliderValues["Phosphorus"]?.toDouble()  else null,
                                            potassium   = if (enabled["Potassium"]   == true) sliderValues["Potassium"]?.toDouble()   else null,
                                            albumin     = if (enabled["Albumin"]     == true) sliderValues["Albumin"]?.toDouble()     else null,
                                            hemoglobin  = if (enabled["Hemoglobin"]  == true) sliderValues["Hemoglobin"]?.toDouble()  else null,
                                            ferritin    = if (enabled["Ferritin"]    == true) sliderValues["Ferritin"]?.toDouble()    else null,
                                            ktv         = if (enabled["KtV"]         == true) sliderValues["KtV"]?.toDouble()         else null,
                                            pthIntact   = if (enabled["PTH"]         == true) sliderValues["PTH"]?.toDouble()         else null,
                                            calcium     = if (enabled["Calcium"]     == true) sliderValues["Calcium"]?.toDouble()     else null,
                                        )
                                        whatIfResult = ApiClient.getApiService().whatIfScenario(req)
                                    } catch (e: Exception) {
                                        Toast.makeText(context, "What-If failed: ${e.message}", Toast.LENGTH_SHORT).show()
                                    }
                                    isRunning = false
                                }
                            },
                            enabled = activeCount > 0 && !isRunning,
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            if (isRunning) {
                                CircularProgressIndicator(modifier = Modifier.size(16.dp), strokeWidth = 2.dp, color = MaterialTheme.colorScheme.onPrimary)
                                Spacer(Modifier.width(8.dp))
                            }
                            Text(if (isRunning) "Simulating…" else "Run What-If${if (activeCount > 0) " ($activeCount)" else ""}")
                        }

                        // What-If result
                        whatIfResult?.let { res ->
                            Spacer(Modifier.height(12.dp))
                            val dColor = when {
                                res.deltaOmega > 0.001 -> Color(0xFF10B981)
                                res.deltaOmega < -0.001 -> Color(0xFFEF4444)
                                else -> MaterialTheme.colorScheme.onSurfaceVariant
                            }
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(8.dp))
                                    .padding(12.dp),
                                horizontalArrangement = Arrangement.SpaceEvenly
                            ) {
                                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                    Text(String.format("%.3f", res.baselineOmega), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                                    Text("Baseline Ω", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                }
                                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                    Text(String.format("%.3f", res.scenarioOmega), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = dColor)
                                    Text("Scenario Ω", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                }
                                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                    Text(String.format("%+.1fpp", res.deltaPct), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = dColor)
                                    Text("Change", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                }
                            }

                            Spacer(Modifier.height(8.dp))
                            res.pathwayDeltas.entries.sortedBy { it.key }.forEach { (name, pd) ->
                                val delta = pd.delta ?: return@forEach
                                val pColor = PATHWAY_COLORS[name] ?: Color.Gray
                                val dCol = when {
                                    delta > 0.005 -> Color(0xFF10B981)
                                    delta < -0.005 -> Color(0xFFEF4444)
                                    else -> MaterialTheme.colorScheme.onSurfaceVariant
                                }
                                Row(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(vertical = 3.dp)
                                        .background(MaterialTheme.colorScheme.surfaceVariant.copy(0.5f), RoundedCornerShape(6.dp))
                                        .padding(horizontal = 10.dp, vertical = 6.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Box(Modifier.size(10.dp).background(pColor, CircleShape))
                                    Spacer(Modifier.width(8.dp))
                                    Text(name.replace("_", " "), style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(1f))
                                    if (pd.baselineScore != null) Text(String.format("%.0f%%", pd.baselineScore * 100), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    Spacer(Modifier.width(4.dp))
                                    Icon(
                                        when { delta > 0.005 -> Icons.Default.TrendingUp; delta < -0.005 -> Icons.Default.TrendingDown; else -> Icons.Default.TrendingFlat },
                                        contentDescription = null, tint = dCol, modifier = Modifier.size(14.dp)
                                    )
                                    Spacer(Modifier.width(4.dp))
                                    if (pd.scenarioScore != null) Text(String.format("%.0f%%", pd.scenarioScore * 100), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    Spacer(Modifier.width(8.dp))
                                    Text(String.format("%+.1fpp", delta * 100), style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold, color = dCol)
                                }
                            }

                            Spacer(Modifier.height(8.dp))
                            Text(res.interpretation, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }
        }
    }
}
