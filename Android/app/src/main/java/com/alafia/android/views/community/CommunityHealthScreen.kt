package com.alafia.android.views.community
import com.alafia.android.util.ErrorUtil

import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.alafia.android.api.ApiClient
import com.alafia.android.models.*
import com.alafia.android.schemas.*
import kotlinx.coroutines.launch
import java.time.LocalDate
import androidx.navigation.NavHostController

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CommunityHealthScreen(navController: NavHostController) {
    val scope = rememberCoroutineScope()
    val api = ApiClient.getApiService()

    // State
    var selectedTab by remember { mutableIntStateOf(0) }
    var isLoading by remember { mutableStateOf(true) }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    // Data
    var dashboardStats by remember { mutableStateOf<CommunityDashboardStats?>(null) }
    var alerts by remember { mutableStateOf<List<CommunityHealthAlert>>(emptyList()) }
    var guidelines by remember { mutableStateOf<List<HealthGuideline>>(emptyList()) }
    var reports by remember { mutableStateOf<List<CommunityHealthReport>>(emptyList()) }
    var categories by remember { mutableStateOf<List<AlertCategoryInfo>>(emptyList()) }
    var sources by remember { mutableStateOf<List<AlertSourceInfo>>(emptyList()) }

    // UI State
    var selectedAlert by remember { mutableStateOf<CommunityHealthAlert?>(null) }
    var selectedGuideline by remember { mutableStateOf<HealthGuideline?>(null) }
    var showReportDialog by remember { mutableStateOf(false) }
    var alertSearchQuery by remember { mutableStateOf("") }
    var selectedCategory by remember { mutableStateOf<String?>(null) }
    var selectedSeverity by remember { mutableStateOf<String?>(null) }
    var selectedSource by remember { mutableStateOf<String?>(null) }
    var guidelineSearchQuery by remember { mutableStateOf("") }
    var selectedGuidelineCategory by remember { mutableStateOf<String?>(null) }

    val tabs = listOf("Dashboard", "Alerts", "Guidelines", "Reports", "Settings")

    fun loadData() {
        scope.launch {
            isLoading = true
            errorMessage = null
            try {
                dashboardStats = api.getCommunityDashboard()
                alerts = api.getCommunityAlerts()
                guidelines = api.getCommunityGuidelines()
                reports = api.getCommunityReports()
                try { categories = api.getCommunityCategories() } catch (_: Exception) {}
                try { sources = api.getCommunitySources() } catch (_: Exception) {}
            } catch (e: Exception) {
                errorMessage = e.message ?: "Failed to load community health data"
                // Try seeding if no data
                try {
                    api.seedCommunityData()
                    dashboardStats = api.getCommunityDashboard()
                    alerts = api.getCommunityAlerts()
                    guidelines = api.getCommunityGuidelines()
                    reports = api.getCommunityReports()
                    errorMessage = null
                } catch (_: Exception) {}
            } finally {
                isLoading = false
            }
        }
    }

    LaunchedEffect(Unit) { loadData() }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Community Health") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    IconButton(onClick = { loadData() }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Refresh")
                    }
                }
            )
        }
    ) { paddingValues ->
        Column(modifier = Modifier.padding(paddingValues)) {
            // Tab Row
            TabRow(selectedTabIndex = selectedTab) {
                tabs.forEachIndexed { index, title ->
                    Tab(
                        selected = selectedTab == index,
                        onClick = { selectedTab = index },
                        text = { Text(title, fontSize = 12.sp) }
                    )
                }
            }

            if (isLoading) {
                Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center
                ) {
                    CircularProgressIndicator()
                }
            } else {
                when (selectedTab) {
                    0 -> DashboardTab(dashboardStats, onAlertClick = { selectedAlert = it })
                    1 -> AlertsTab(
                        alerts = alerts,
                        categories = categories,
                        sources = sources,
                        searchQuery = alertSearchQuery,
                        onSearchChange = { alertSearchQuery = it },
                        selectedCategory = selectedCategory,
                        onCategoryChange = { selectedCategory = it },
                        selectedSeverity = selectedSeverity,
                        onSeverityChange = { selectedSeverity = it },
                        selectedSource = selectedSource,
                        onSourceChange = { selectedSource = it },
                        onAlertClick = { selectedAlert = it },
                        onFilter = { cat, sev, src, search ->
                            scope.launch {
                                try {
                                    alerts = api.getCommunityAlerts(
                                        category = cat,
                                        severity = sev,
                                        source = src,
                                        search = search.ifBlank { null }
                                    )
                                } catch (_: Exception) {}
                            }
                        }
                    )
                    2 -> GuidelinesTab(
                        guidelines = guidelines,
                        searchQuery = guidelineSearchQuery,
                        onSearchChange = { guidelineSearchQuery = it },
                        selectedCategory = selectedGuidelineCategory,
                        onCategoryChange = { selectedGuidelineCategory = it },
                        onGuidelineClick = { selectedGuideline = it },
                        onFilter = { cat, search ->
                            scope.launch {
                                try {
                                    guidelines = api.getCommunityGuidelines(
                                        category = cat,
                                        search = search.ifBlank { null }
                                    )
                                } catch (_: Exception) {}
                            }
                        }
                    )
                    3 -> ReportsTab(
                        reports = reports,
                        onAddReport = { showReportDialog = true },
                        onDeleteReport = { reportId ->
                            scope.launch {
                                try {
                                    api.deleteCommunityReport(reportId)
                                    reports = api.getCommunityReports()
                                } catch (_: Exception) {}
                            }
                        }
                    )
                    4 -> SubscriptionSettingsTab()
                }
            }
        }
    }

    // Alert Detail Sheet
    if (selectedAlert != null) {
        AlertDetailSheet(
            alert = selectedAlert!!,
            onDismiss = { selectedAlert = null },
            onBookmark = {
                scope.launch {
                    try {
                        api.toggleAlertBookmark(selectedAlert!!.id)
                    } catch (_: Exception) {}
                }
            }
        )
    }

    // Guideline Detail Sheet
    if (selectedGuideline != null) {
        GuidelineDetailSheet(
            guideline = selectedGuideline!!,
            onDismiss = { selectedGuideline = null }
        )
    }

    // Report Form Dialog
    if (showReportDialog) {
        ReportFormDialog(
            onDismiss = { showReportDialog = false },
            onSubmit = { request ->
                scope.launch {
                    try {
                        api.createCommunityReport(request)
                        reports = api.getCommunityReports()
                        showReportDialog = false
                    } catch (_: Exception) {}
                }
            }
        )
    }
}

// ─── Dashboard Tab ───────────────────────────────────────────────────

@Composable
private fun DashboardTab(
    stats: CommunityDashboardStats?,
    onAlertClick: (CommunityHealthAlert) -> Unit
) {
    if (stats == null) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Text("No data available")
        }
        return
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        // Stats Grid
        item {
            Text("Overview", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(8.dp))
        }

        item {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                CommunityStatCard("🚨", stats.totalActiveAlerts, "Active Alerts", Color(0xFF3B82F6), Modifier.weight(1f))
                CommunityStatCard("🔴", stats.criticalAlerts, "Critical", Color(0xFFEF4444), Modifier.weight(1f))
            }
        }
        item {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                CommunityStatCard("💊", stats.activeRecalls, "Recalls", Color(0xFFF97316), Modifier.weight(1f))
                CommunityStatCard("🦠", stats.activeOutbreaks, "Outbreaks", Color(0xFF8B5CF6), Modifier.weight(1f))
            }
        }
        item {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                CommunityStatCard("📢", stats.activeAdvisories, "Advisories", Color(0xFF6366F1), Modifier.weight(1f))
                CommunityStatCard("☠️", stats.activePoisonAlerts, "Poison", Color(0xFF92400E), Modifier.weight(1f))
            }
        }
        item {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                CommunityStatCard("📋", stats.totalGuidelines, "Guidelines", Color(0xFF10B981), Modifier.weight(1f))
                CommunityStatCard("📬", stats.unreadAlerts, "Unread", Color(0xFFEC4899), Modifier.weight(1f))
            }
        }

        // Latest Outbreaks
        if (stats.latestOutbreaks.isNotEmpty()) {
            item {
                Spacer(Modifier.height(8.dp))
                Text("🦠 Latest Outbreaks", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            }
            items(stats.latestOutbreaks) { alert ->
                AlertCard(alert, onClick = { onAlertClick(alert) })
            }
        }

        // Latest Recalls
        if (stats.latestRecalls.isNotEmpty()) {
            item {
                Spacer(Modifier.height(8.dp))
                Text("💊 Latest Recalls", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            }
            items(stats.latestRecalls) { alert ->
                AlertCard(alert, onClick = { onAlertClick(alert) })
            }
        }

        // Latest Advisories
        if (stats.latestAdvisories.isNotEmpty()) {
            item {
                Spacer(Modifier.height(8.dp))
                Text("📢 Latest Advisories", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            }
            items(stats.latestAdvisories) { alert ->
                AlertCard(alert, onClick = { onAlertClick(alert) })
            }
        }

        item { Spacer(Modifier.height(16.dp)) }
    }
}

@Composable
private fun CommunityStatCard(icon: String, value: Int, label: String, color: Color, modifier: Modifier = Modifier) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(containerColor = color.copy(alpha = 0.1f))
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(icon, fontSize = 24.sp)
            Text("$value", fontSize = 28.sp, fontWeight = FontWeight.Bold, color = color)
            Text(label, fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun AlertCard(alert: CommunityHealthAlert, onClick: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
        colors = CardDefaults.cardColors(
            containerColor = when (alert.severity) {
                "critical" -> Color(0xFFEF4444).copy(alpha = 0.08f)
                "high" -> Color(0xFFF97316).copy(alpha = 0.08f)
                else -> MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
            }
        )
    ) {
        Column(Modifier.padding(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(categoryIcon(alert.category), fontSize = 20.sp)
                Spacer(Modifier.width(8.dp))
                Column(Modifier.weight(1f)) {
                    Text(alert.title, fontWeight = FontWeight.SemiBold, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    Text(alert.summary, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 2, overflow = TextOverflow.Ellipsis)
                }
            }
            Spacer(Modifier.height(4.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                SeverityBadge(alert.severity)
                SourceBadge(alert.source)
                if (alert.isGlobal) {
                    AssistChip(
                        onClick = {},
                        label = { Text("🌍 Global", fontSize = 10.sp) },
                        modifier = Modifier.height(24.dp)
                    )
                }
            }
        }
    }
}

@Composable
private fun SeverityBadge(severity: String) {
    val (color, label) = when (severity) {
        "critical" -> Color(0xFFEF4444) to "CRITICAL"
        "high" -> Color(0xFFF97316) to "HIGH"
        "moderate" -> Color(0xFFEAB308) to "MODERATE"
        "low" -> Color(0xFF3B82F6) to "LOW"
        else -> Color(0xFF6B7280) to "INFO"
    }
    Text(
        text = label,
        fontSize = 10.sp,
        fontWeight = FontWeight.Bold,
        color = Color.White,
        modifier = Modifier
            .background(color, RoundedCornerShape(4.dp))
            .padding(horizontal = 6.dp, vertical = 2.dp)
    )
}

@Composable
private fun SourceBadge(source: String) {
    val label = when (source) {
        "who" -> "WHO"
        "cdc" -> "CDC"
        "fda" -> "FDA"
        "ema" -> "EMA"
        "health_canada" -> "Health Canada"
        "poison_control" -> "Poison Control"
        else -> source.uppercase()
    }
    Text(
        text = label,
        fontSize = 10.sp,
        fontWeight = FontWeight.Medium,
        color = MaterialTheme.colorScheme.primary,
        modifier = Modifier
            .background(MaterialTheme.colorScheme.primaryContainer, RoundedCornerShape(4.dp))
            .padding(horizontal = 6.dp, vertical = 2.dp)
    )
}

private fun categoryIcon(category: String): String = when (category) {
    "pandemic", "outbreak" -> "🦠"
    "recall_drug", "recall_medical_device" -> "💊"
    "recall_food" -> "🍽️"
    "recall_consumer" -> "📦"
    "advisory" -> "📢"
    "poison" -> "☠️"
    "travel_health" -> "✈️"
    "environmental" -> "🌡️"
    "bioterrorism" -> "⚠️"
    "vaccination" -> "💉"
    "food_safety" -> "🥗"
    "water_safety" -> "💧"
    else -> "🏥"
}

// ─── Alerts Tab ──────────────────────────────────────────────────────

@Composable
private fun AlertsTab(
    alerts: List<CommunityHealthAlert>,
    categories: List<AlertCategoryInfo>,
    sources: List<AlertSourceInfo>,
    searchQuery: String,
    onSearchChange: (String) -> Unit,
    selectedCategory: String?,
    onCategoryChange: (String?) -> Unit,
    selectedSeverity: String?,
    onSeverityChange: (String?) -> Unit,
    selectedSource: String?,
    onSourceChange: (String?) -> Unit,
    onAlertClick: (CommunityHealthAlert) -> Unit,
    onFilter: (String?, String?, String?, String) -> Unit
) {
    Column(Modifier.fillMaxSize()) {
        // Search
        OutlinedTextField(
            value = searchQuery,
            onValueChange = {
                onSearchChange(it)
                onFilter(selectedCategory, selectedSeverity, selectedSource, it)
            },
            placeholder = { Text("Search alerts...") },
            leadingIcon = { Icon(Icons.Default.Search, "Search") },
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
            singleLine = true
        )

        // Category filter chips
        if (categories.isNotEmpty()) {
            Row(
                modifier = Modifier
                    .horizontalScroll(rememberScrollState())
                    .padding(horizontal = 16.dp),
                horizontalArrangement = Arrangement.spacedBy(4.dp)
            ) {
                FilterChip(
                    selected = selectedCategory == null,
                    onClick = {
                        onCategoryChange(null)
                        onFilter(null, selectedSeverity, selectedSource, searchQuery)
                    },
                    label = { Text("All", fontSize = 12.sp) }
                )
                categories.forEach { cat ->
                    FilterChip(
                        selected = selectedCategory == cat.id,
                        onClick = {
                            val newCat = if (selectedCategory == cat.id) null else cat.id
                            onCategoryChange(newCat)
                            onFilter(newCat, selectedSeverity, selectedSource, searchQuery)
                        },
                        label = { Text("${cat.icon} ${cat.name}", fontSize = 12.sp) }
                    )
                }
            }
        }

        // Severity filter chips
        Row(
            modifier = Modifier
                .horizontalScroll(rememberScrollState())
                .padding(horizontal = 16.dp, vertical = 4.dp),
            horizontalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            FilterChip(
                selected = selectedSeverity == null,
                onClick = {
                    onSeverityChange(null)
                    onFilter(selectedCategory, null, selectedSource, searchQuery)
                },
                label = { Text("All Severity", fontSize = 12.sp) }
            )
            listOf("critical" to Color(0xFFF44336), "high" to Color(0xFFFF9800), "moderate" to Color(0xFFFFEB3B),
                "low" to Color(0xFF4CAF50), "info" to Color(0xFF2196F3)).forEach { (sev, color) ->
                FilterChip(
                    selected = selectedSeverity == sev,
                    onClick = {
                        val newSev = if (selectedSeverity == sev) null else sev
                        onSeverityChange(newSev)
                        onFilter(selectedCategory, newSev, selectedSource, searchQuery)
                    },
                    label = { Text(sev.replaceFirstChar { it.uppercase() }, fontSize = 12.sp) }
                )
            }
        }

        // Source filter chips
        if (sources.isNotEmpty()) {
            Row(
                modifier = Modifier
                    .horizontalScroll(rememberScrollState())
                    .padding(horizontal = 16.dp),
                horizontalArrangement = Arrangement.spacedBy(4.dp)
            ) {
                FilterChip(
                    selected = selectedSource == null,
                    onClick = {
                        onSourceChange(null)
                        onFilter(selectedCategory, selectedSeverity, null, searchQuery)
                    },
                    label = { Text("All Sources", fontSize = 12.sp) }
                )
                sources.forEach { src ->
                    FilterChip(
                        selected = selectedSource == src.id,
                        onClick = {
                            val newSrc = if (selectedSource == src.id) null else src.id
                            onSourceChange(newSrc)
                            onFilter(selectedCategory, selectedSeverity, newSrc, searchQuery)
                        },
                        label = { Text(src.name.uppercase(), fontSize = 11.sp) }
                    )
                }
            }
        }

        // Alert List
        if (alerts.isEmpty()) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text("No alerts found", color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxSize().padding(horizontal = 16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
                contentPadding = PaddingValues(vertical = 8.dp)
            ) {
                items(alerts) { alert ->
                    AlertCard(alert, onClick = { onAlertClick(alert) })
                }
            }
        }
    }
}

// ─── Guidelines Tab ──────────────────────────────────────────────────

@Composable
private fun GuidelinesTab(
    guidelines: List<HealthGuideline>,
    searchQuery: String,
    onSearchChange: (String) -> Unit,
    selectedCategory: String?,
    onCategoryChange: (String?) -> Unit,
    onGuidelineClick: (HealthGuideline) -> Unit,
    onFilter: (String?, String) -> Unit
) {
    val guidelineCategories = listOf(
        "vaccination" to "💉 Vaccination",
        "infection_prevention" to "🧼 Infection Prevention",
        "chronic_disease" to "🏥 Chronic Disease",
        "antimicrobial_resistance" to "🦠 AMR",
        "ncd_prevention" to "❤️ NCD Prevention",
        "substance_use" to "🚬 Substance Use"
    )

    Column(Modifier.fillMaxSize()) {
        // Search
        OutlinedTextField(
            value = searchQuery,
            onValueChange = {
                onSearchChange(it)
                onFilter(selectedCategory, it)
            },
            placeholder = { Text("Search guidelines...") },
            leadingIcon = { Icon(Icons.Default.Search, "Search") },
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
            singleLine = true
        )

        // Category filter chips
        Row(
            modifier = Modifier
                .horizontalScroll(rememberScrollState())
                .padding(horizontal = 16.dp),
            horizontalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            FilterChip(
                selected = selectedCategory == null,
                onClick = {
                    onCategoryChange(null)
                    onFilter(null, searchQuery)
                },
                label = { Text("All", fontSize = 12.sp) }
            )
            guidelineCategories.forEach { (id, label) ->
                FilterChip(
                    selected = selectedCategory == id,
                    onClick = {
                        val newCat = if (selectedCategory == id) null else id
                        onCategoryChange(newCat)
                        onFilter(newCat, searchQuery)
                    },
                    label = { Text(label, fontSize = 12.sp) }
                )
            }
        }

        // Guidelines List
        if (guidelines.isEmpty()) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text("No guidelines found", color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxSize().padding(horizontal = 16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
                contentPadding = PaddingValues(vertical = 8.dp)
            ) {
                items(guidelines) { guideline ->
                    GuidelineCard(guideline, onClick = { onGuidelineClick(guideline) })
                }
            }
        }
    }
}

@Composable
private fun GuidelineCard(guideline: HealthGuideline, onClick: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
        colors = CardDefaults.cardColors(containerColor = Color(0xFF10B981).copy(alpha = 0.06f))
    ) {
        Column(Modifier.padding(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    guidelineCategoryIcon(guideline.category),
                    fontSize = 24.sp,
                    modifier = Modifier
                        .size(40.dp)
                        .background(Color(0xFF10B981).copy(alpha = 0.1f), CircleShape)
                        .wrapContentSize(Alignment.Center)
                )
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(guideline.title, fontWeight = FontWeight.SemiBold, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    Text(guideline.summary, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 2, overflow = TextOverflow.Ellipsis)
                }
            }
            Spacer(Modifier.height(6.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                SourceBadge(guideline.source)
                if (guideline.version != null) {
                    Text(
                        "v${guideline.version}",
                        fontSize = 10.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier
                            .background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(4.dp))
                            .padding(horizontal = 6.dp, vertical = 2.dp)
                    )
                }
                if (guideline.isCurrent) {
                    Text(
                        "✓ Current",
                        fontSize = 10.sp,
                        fontWeight = FontWeight.Medium,
                        color = Color(0xFF10B981),
                        modifier = Modifier
                            .background(Color(0xFF10B981).copy(alpha = 0.1f), RoundedCornerShape(4.dp))
                            .padding(horizontal = 6.dp, vertical = 2.dp)
                    )
                }
            }
        }
    }
}

private fun guidelineCategoryIcon(category: String): String = when (category) {
    "vaccination" -> "💉"
    "infection_prevention" -> "🧼"
    "chronic_disease" -> "🏥"
    "antimicrobial_resistance" -> "🦠"
    "ncd_prevention" -> "❤️"
    "substance_use" -> "🚬"
    "mental_health" -> "🧠"
    "nutrition" -> "🥗"
    "maternal_health" -> "🤰"
    "child_health" -> "👶"
    "environmental_health" -> "🌿"
    "occupational_health" -> "🏗️"
    else -> "📋"
}

// ─── Reports Tab ─────────────────────────────────────────────────────

@Composable
private fun ReportsTab(
    reports: List<CommunityHealthReport>,
    onAddReport: () -> Unit,
    onDeleteReport: (Int) -> Unit
) {
    Column(Modifier.fillMaxSize()) {
        // Header
        Row(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("Community Reports", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            Button(onClick = onAddReport) {
                Icon(Icons.Default.Add, "Add", modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(4.dp))
                Text("Report")
            }
        }

        if (reports.isEmpty()) {
            Box(
                modifier = Modifier.fillMaxSize(),
                contentAlignment = Alignment.Center
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("📝", fontSize = 48.sp)
                    Spacer(Modifier.height(8.dp))
                    Text("No reports yet", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text("Help your community by reporting health concerns",
                        fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxSize().padding(horizontal = 16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(reports) { report ->
                    ReportCard(report, onDelete = { onDeleteReport(report.id) })
                }
                item { Spacer(Modifier.height(16.dp)) }
            }
        }
    }
}

@Composable
private fun ReportCard(report: CommunityHealthReport, onDelete: () -> Unit) {
    val reportIcon = when (report.reportType) {
        "symptom_cluster" -> "🤒"
        "foodborne_illness" -> "🍽️"
        "poisoning" -> "☠️"
        "environmental_hazard" -> "🌡️"
        "water_contamination" -> "💧"
        "disease_outbreak" -> "🦠"
        "medication_side_effect" -> "💊"
        "animal_bite" -> "🐕"
        "air_quality" -> "🌫️"
        else -> "📋"
    }

    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(reportIcon, fontSize = 24.sp)
                Spacer(Modifier.width(8.dp))
                Column(Modifier.weight(1f)) {
                    Text(report.title, fontWeight = FontWeight.SemiBold)
                    Text(
                        report.reportType.replace("_", " ").replaceFirstChar { it.uppercase() },
                        fontSize = 12.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                IconButton(onClick = onDelete) {
                    Icon(Icons.Default.Delete, "Delete", tint = MaterialTheme.colorScheme.error, modifier = Modifier.size(20.dp))
                }
            }
            Text(report.description, fontSize = 13.sp, maxLines = 3, overflow = TextOverflow.Ellipsis)
            Spacer(Modifier.height(4.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                SeverityBadge(report.severity)
                if (report.locationName != null) {
                    Text(
                        "📍 ${report.locationName}",
                        fontSize = 10.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                if (report.isVerified) {
                    Text(
                        "✓ Verified",
                        fontSize = 10.sp,
                        color = Color(0xFF10B981),
                        fontWeight = FontWeight.Medium
                    )
                }
            }
        }
    }
}

// ─── Alert Detail Sheet ──────────────────────────────────────────────

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AlertDetailSheet(
    alert: CommunityHealthAlert,
    onDismiss: () -> Unit,
    onBookmark: () -> Unit
) {
    val context = LocalContext.current
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp, vertical = 8.dp)
        ) {
            // Header
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(categoryIcon(alert.category), fontSize = 32.sp)
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(alert.title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        SeverityBadge(alert.severity)
                        SourceBadge(alert.source)
                    }
                }
            }

            Spacer(Modifier.height(12.dp))

            // Summary
            Text(alert.summary, style = MaterialTheme.typography.bodyLarge)

            // Description
            if (!alert.description.isNullOrBlank()) {
                Spacer(Modifier.height(8.dp))
                Text(alert.description, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }

            Spacer(Modifier.height(12.dp))

            // Dates
            Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f))) {
                Column(Modifier.padding(12.dp)) {
                    Text("📅 Details", fontWeight = FontWeight.SemiBold)
                    Spacer(Modifier.height(4.dp))
                    Text("Issued: ${alert.issuedDate}", fontSize = 13.sp)
                    alert.effectiveDate?.let { Text("Effective: $it", fontSize = 13.sp) }
                    alert.expiryDate?.let { Text("Expires: $it", fontSize = 13.sp) }
                    if (alert.isGlobal) Text("🌍 Global Alert", fontSize = 13.sp, fontWeight = FontWeight.Medium)
                    alert.affectedCountries?.let { countries ->
                        if (countries.isNotEmpty()) Text("Countries: ${countries.joinToString(", ")}", fontSize = 13.sp)
                    }
                }
            }

            // Outbreak-specific info
            if (alert.diseaseName != null || alert.pathogen != null) {
                Spacer(Modifier.height(8.dp))
                Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = Color(0xFF8B5CF6).copy(alpha = 0.06f))) {
                    Column(Modifier.padding(12.dp)) {
                        Text("🦠 Outbreak Info", fontWeight = FontWeight.SemiBold)
                        Spacer(Modifier.height(4.dp))
                        alert.diseaseName?.let { Text("Disease: $it", fontSize = 13.sp) }
                        alert.pathogen?.let { Text("Pathogen: $it", fontSize = 13.sp) }
                        alert.confirmedCases?.let { Text("Confirmed Cases: $it", fontSize = 13.sp) }
                        alert.deaths?.let { Text("Deaths: $it", fontSize = 13.sp, color = Color(0xFFEF4444)) }
                    }
                }
            }

            // Recall-specific info
            if (alert.productName != null || alert.manufacturer != null) {
                Spacer(Modifier.height(8.dp))
                Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = Color(0xFFF97316).copy(alpha = 0.06f))) {
                    Column(Modifier.padding(12.dp)) {
                        Text("💊 Recall Info", fontWeight = FontWeight.SemiBold)
                        Spacer(Modifier.height(4.dp))
                        alert.productName?.let { Text("Product: $it", fontSize = 13.sp) }
                        alert.productType?.let { Text("Type: $it", fontSize = 13.sp) }
                        alert.manufacturer?.let { Text("Manufacturer: $it", fontSize = 13.sp) }
                        alert.recallClass?.let { Text("Recall Class: $it", fontSize = 13.sp) }
                        alert.reasonForRecall?.let { Text("Reason: $it", fontSize = 13.sp) }
                        alert.lotNumbers?.let { lots ->
                            if (lots.isNotEmpty()) Text("Lot Numbers: ${lots.joinToString(", ")}", fontSize = 13.sp)
                        }
                    }
                }
            }

            // Recommended Actions
            alert.recommendedActions?.let { actions ->
                if (actions.isNotEmpty()) {
                    Spacer(Modifier.height(8.dp))
                    Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = Color(0xFF10B981).copy(alpha = 0.06f))) {
                        Column(Modifier.padding(12.dp)) {
                            Text("✅ Recommended Actions", fontWeight = FontWeight.SemiBold)
                            Spacer(Modifier.height(4.dp))
                            actions.forEachIndexed { idx, action ->
                                Text("${idx + 1}. $action", fontSize = 13.sp, modifier = Modifier.padding(bottom = 2.dp))
                            }
                        }
                    }
                }
            }

            // Target Population
            alert.targetPopulation?.let { pop ->
                if (pop.isNotEmpty()) {
                    Spacer(Modifier.height(8.dp))
                    Text("👥 Target Population", fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                    Spacer(Modifier.height(4.dp))
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(4.dp),
                        modifier = Modifier.horizontalScroll(rememberScrollState())
                    ) {
                        pop.forEach { p ->
                            AssistChip(onClick = {}, label = { Text(p, fontSize = 11.sp) })
                        }
                    }
                }
            }

            // Source link
            alert.sourceUrl?.let { url ->
                Spacer(Modifier.height(12.dp))
                OutlinedButton(
                    onClick = {
                        try {
                            context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
                        } catch (_: Exception) {}
                    },
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Icon(Icons.Default.OpenInNew, "Open", modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(4.dp))
                    Text("View Original Source")
                }
            }

            // Tags
            alert.tags?.let { tags ->
                if (tags.isNotEmpty()) {
                    Spacer(Modifier.height(8.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        tags.forEach { tag ->
                            Text("#$tag", fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }

            // Action buttons
            Spacer(Modifier.height(12.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(
                    onClick = onBookmark,
                    modifier = Modifier.weight(1f)
                ) {
                    Icon(Icons.Default.Bookmark, "Bookmark", modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(4.dp))
                    Text("Bookmark")
                }
                Button(
                    onClick = onDismiss,
                    modifier = Modifier.weight(1f)
                ) {
                    Text("Close")
                }
            }

            Spacer(Modifier.height(32.dp))
        }
    }
}

// ─── Guideline Detail Sheet ──────────────────────────────────────────

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun GuidelineDetailSheet(
    guideline: HealthGuideline,
    onDismiss: () -> Unit
) {
    val context = LocalContext.current
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp, vertical = 8.dp)
        ) {
            // Header
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(guidelineCategoryIcon(guideline.category), fontSize = 32.sp)
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(guideline.title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        SourceBadge(guideline.source)
                        guideline.version?.let {
                            Text("v$it", fontSize = 10.sp, color = MaterialTheme.colorScheme.onSurfaceVariant,
                                modifier = Modifier.background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(4.dp)).padding(horizontal = 6.dp, vertical = 2.dp))
                        }
                    }
                }
            }

            Spacer(Modifier.height(12.dp))
            Text(guideline.summary, style = MaterialTheme.typography.bodyLarge)

            // Full text
            guideline.fullText?.let { text ->
                Spacer(Modifier.height(8.dp))
                Text(text, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }

            // Recommendations
            guideline.recommendations?.let { recs ->
                if (recs.isNotEmpty()) {
                    Spacer(Modifier.height(12.dp))
                    Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = Color(0xFF10B981).copy(alpha = 0.06f))) {
                        Column(Modifier.padding(12.dp)) {
                            Text("📋 Recommendations", fontWeight = FontWeight.SemiBold)
                            Spacer(Modifier.height(4.dp))
                            recs.forEachIndexed { idx, rec ->
                                Text("${idx + 1}. $rec", fontSize = 13.sp, modifier = Modifier.padding(bottom = 2.dp))
                            }
                        }
                    }
                }
            }

            // Target Population
            guideline.targetPopulation?.let { pop ->
                if (pop.isNotEmpty()) {
                    Spacer(Modifier.height(8.dp))
                    Text("👥 Target Population", fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                    Spacer(Modifier.height(4.dp))
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(4.dp),
                        modifier = Modifier.horizontalScroll(rememberScrollState())
                    ) {
                        pop.forEach { p ->
                            AssistChip(onClick = {}, label = { Text(p, fontSize = 11.sp) })
                        }
                    }
                }
            }

            // Applicable Conditions
            guideline.applicableConditions?.let { conditions ->
                if (conditions.isNotEmpty()) {
                    Spacer(Modifier.height(8.dp))
                    Text("🏥 Applicable Conditions", fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                    Spacer(Modifier.height(4.dp))
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(4.dp),
                        modifier = Modifier.horizontalScroll(rememberScrollState())
                    ) {
                        conditions.forEach { c ->
                            AssistChip(onClick = {}, label = { Text(c, fontSize = 11.sp) })
                        }
                    }
                }
            }

            // Info
            Card(Modifier.fillMaxWidth().padding(top = 8.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f))) {
                Column(Modifier.padding(12.dp)) {
                    guideline.effectiveDate?.let { Text("Effective: $it", fontSize = 13.sp) }
                    guideline.supersededDate?.let { Text("Superseded: $it", fontSize = 13.sp) }
                    Text(if (guideline.isCurrent) "✓ Current guideline" else "⚠️ Superseded", fontSize = 13.sp,
                        fontWeight = FontWeight.Medium, color = if (guideline.isCurrent) Color(0xFF10B981) else Color(0xFFF97316))
                }
            }

            // Source link
            guideline.sourceUrl?.let { url ->
                Spacer(Modifier.height(12.dp))
                OutlinedButton(
                    onClick = {
                        try {
                            context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
                        } catch (_: Exception) {}
                    },
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Icon(Icons.Default.OpenInNew, "Open", modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(4.dp))
                    Text("View Full Guideline")
                }
            }

            // Tags
            guideline.tags?.let { tags ->
                if (tags.isNotEmpty()) {
                    Spacer(Modifier.height(8.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        tags.forEach { tag ->
                            Text("#$tag", fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }

            Spacer(Modifier.height(12.dp))
            Button(onClick = onDismiss, modifier = Modifier.fillMaxWidth()) {
                Text("Close")
            }

            Spacer(Modifier.height(32.dp))
        }
    }
}

// ─── Report Form Dialog ──────────────────────────────────────────────

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ReportFormDialog(
    onDismiss: () -> Unit,
    onSubmit: (CommunityReportRequest) -> Unit
) {
    var reportType by remember { mutableStateOf("symptom_cluster") }
    var title by remember { mutableStateOf("") }
    var description by remember { mutableStateOf("") }
    var severity by remember { mutableStateOf("moderate") }
    var locationName by remember { mutableStateOf("") }
    var symptomsText by remember { mutableStateOf("") }
    var reportTypeExpanded by remember { mutableStateOf(false) }
    var severityExpanded by remember { mutableStateOf(false) }

    val reportTypes = listOf(
        "symptom_cluster" to "Symptom Cluster",
        "foodborne_illness" to "Foodborne Illness",
        "poisoning" to "Poisoning",
        "environmental_hazard" to "Environmental Hazard",
        "water_contamination" to "Water Contamination",
        "disease_outbreak" to "Disease Outbreak",
        "medication_side_effect" to "Medication Side Effect",
        "animal_bite" to "Animal Bite/Attack",
        "air_quality" to "Air Quality Issue",
        "other" to "Other"
    )

    val severities = listOf("low", "moderate", "high", "critical")

    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = {
            Button(
                onClick = {
                    if (title.isNotBlank() && description.isNotBlank()) {
                        onSubmit(
                            CommunityReportRequest(
                                reportType = reportType,
                                title = title,
                                description = description,
                                severity = severity,
                                locationName = locationName.ifBlank { null },
                                symptomsReported = symptomsText.split(",").map { it.trim() }.filter { it.isNotEmpty() }.ifEmpty { null }
                            )
                        )
                    }
                },
                enabled = title.isNotBlank() && description.isNotBlank()
            ) {
                Text("Submit Report")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Cancel") }
        },
        title = { Text("Submit Health Report") },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                // Report Type
                ExposedDropdownMenuBox(
                    expanded = reportTypeExpanded,
                    onExpandedChange = { reportTypeExpanded = it }
                ) {
                    OutlinedTextField(
                        value = reportTypes.find { it.first == reportType }?.second ?: reportType,
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Report Type") },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = reportTypeExpanded) },
                        modifier = Modifier.menuAnchor().fillMaxWidth()
                    )
                    ExposedDropdownMenu(
                        expanded = reportTypeExpanded,
                        onDismissRequest = { reportTypeExpanded = false }
                    ) {
                        reportTypes.forEach { (id, label) ->
                            DropdownMenuItem(
                                text = { Text(label) },
                                onClick = {
                                    reportType = id
                                    reportTypeExpanded = false
                                }
                            )
                        }
                    }
                }

                // Title
                OutlinedTextField(
                    value = title,
                    onValueChange = { title = it },
                    label = { Text("Title *") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )

                // Description
                OutlinedTextField(
                    value = description,
                    onValueChange = { description = it },
                    label = { Text("Description *") },
                    modifier = Modifier.fillMaxWidth(),
                    minLines = 3,
                    maxLines = 5
                )

                // Severity
                ExposedDropdownMenuBox(
                    expanded = severityExpanded,
                    onExpandedChange = { severityExpanded = it }
                ) {
                    OutlinedTextField(
                        value = severity.replaceFirstChar { it.uppercase() },
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Severity") },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = severityExpanded) },
                        modifier = Modifier.menuAnchor().fillMaxWidth()
                    )
                    ExposedDropdownMenu(
                        expanded = severityExpanded,
                        onDismissRequest = { severityExpanded = false }
                    ) {
                        severities.forEach { s ->
                            DropdownMenuItem(
                                text = { Text(s.replaceFirstChar { it.uppercase() }) },
                                onClick = {
                                    severity = s
                                    severityExpanded = false
                                }
                            )
                        }
                    }
                }

                // Location
                OutlinedTextField(
                    value = locationName,
                    onValueChange = { locationName = it },
                    label = { Text("Location") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    leadingIcon = { Icon(Icons.Default.LocationOn, "Location") }
                )

                // Symptoms
                OutlinedTextField(
                    value = symptomsText,
                    onValueChange = { symptomsText = it },
                    label = { Text("Symptoms (comma-separated)") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    placeholder = { Text("fever, cough, headache...") }
                )
            }
        }
    )
}

// ─── Subscription Settings Tab ───────────────────────────────────────

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
private fun SubscriptionSettingsTab() {
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    val api = ApiClient.getApiService()

    var isLoading by remember { mutableStateOf(true) }
    var saving by remember { mutableStateOf(false) }

    var selectedCategories by remember { mutableStateOf<List<String>>(emptyList()) }
    var selectedSources by remember { mutableStateOf<List<String>>(emptyList()) }
    var selectedSeverities by remember { mutableStateOf(listOf("critical", "high")) }
    var selectedCountries by remember { mutableStateOf<List<String>>(emptyList()) }
    var pushEnabled by remember { mutableStateOf(true) }
    var emailEnabled by remember { mutableStateOf(false) }
    var smsEnabled by remember { mutableStateOf(false) }
    var countryInput by remember { mutableStateOf("") }

    val allCategories = listOf(
        "disease_outbreak", "drug_recall", "food_recall", "medical_device_recall",
        "safety_advisory", "travel_advisory", "environmental_hazard", "public_health_emergency",
        "vaccine_update", "drug_safety", "food_safety", "water_safety", "air_quality",
        "chemical_exposure", "radiation", "natural_disaster", "biological_threat"
    )
    val allSeverities = listOf("info", "low", "moderate", "high", "critical")
    val allSources = listOf("who", "cdc", "fda", "ema", "ecdc", "paho", "local_health",
        "state_health", "national_health", "hospital", "research", "public_report")

    LaunchedEffect(Unit) {
        try {
            val sub = api.getCommunitySubscriptions()
            selectedCategories = sub.categories ?: emptyList()
            selectedSources = sub.sources ?: emptyList()
            selectedSeverities = sub.severities ?: listOf("critical", "high")
            selectedCountries = sub.countries ?: emptyList()
            pushEnabled = sub.pushEnabled
            emailEnabled = sub.emailEnabled
            smsEnabled = sub.smsEnabled
        } catch (_: Exception) {}
        isLoading = false
    }

    if (isLoading) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator()
        }
        return
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        item {
            Text("Alert Categories", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            Text("Select which alert types to receive", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(8.dp))
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                allCategories.forEach { cat ->
                    FilterChip(
                        selected = selectedCategories.contains(cat),
                        onClick = {
                            selectedCategories = if (selectedCategories.contains(cat))
                                selectedCategories - cat else selectedCategories + cat
                        },
                        label = { Text(cat.replace("_", " ").replaceFirstChar { it.uppercase() }, fontSize = 11.sp) }
                    )
                }
            }
        }

        item {
            Text("Sources", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(8.dp))
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                allSources.forEach { src ->
                    FilterChip(
                        selected = selectedSources.contains(src),
                        onClick = {
                            selectedSources = if (selectedSources.contains(src))
                                selectedSources - src else selectedSources + src
                        },
                        label = { Text(src.uppercase(), fontSize = 11.sp) }
                    )
                }
            }
        }

        item {
            Text("Severity Levels", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(8.dp))
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                allSeverities.forEach { sev ->
                    FilterChip(
                        selected = selectedSeverities.contains(sev),
                        onClick = {
                            selectedSeverities = if (selectedSeverities.contains(sev))
                                selectedSeverities - sev else selectedSeverities + sev
                        },
                        label = { Text(sev.replaceFirstChar { it.uppercase() }, fontSize = 11.sp) }
                    )
                }
            }
        }

        item {
            Text("Countries", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(8.dp))
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = countryInput,
                    onValueChange = { countryInput = it.uppercase() },
                    label = { Text("Country code") },
                    modifier = Modifier.weight(1f),
                    singleLine = true
                )
                Button(onClick = {
                    val code = countryInput.trim()
                    if (code.isNotEmpty() && !selectedCountries.contains(code)) {
                        selectedCountries = selectedCountries + code
                        countryInput = ""
                    }
                }, enabled = countryInput.trim().isNotEmpty()) { Text("Add") }
            }
            if (selectedCountries.isNotEmpty()) {
                Spacer(Modifier.height(8.dp))
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    selectedCountries.forEach { c ->
                        InputChip(
                            selected = true,
                            onClick = { selectedCountries = selectedCountries - c },
                            label = { Text(c) },
                            trailingIcon = { Icon(Icons.Default.Close, "Remove", modifier = Modifier.size(14.dp)) }
                        )
                    }
                }
            }
        }

        item {
            Text("Notification Channels", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(8.dp))
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("Push Notifications", Modifier.weight(1f))
                        Switch(checked = pushEnabled, onCheckedChange = { pushEnabled = it })
                    }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("Email Notifications", Modifier.weight(1f))
                        Switch(checked = emailEnabled, onCheckedChange = { emailEnabled = it })
                    }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("SMS Notifications", Modifier.weight(1f))
                        Switch(checked = smsEnabled, onCheckedChange = { smsEnabled = it })
                    }
                }
            }
        }

        item {
            Button(
                onClick = {
                    saving = true
                    scope.launch {
                        try {
                            api.updateCommunitySubscriptions(
                                CommunitySubscriptionRequest(
                                    categories = selectedCategories.ifEmpty { null },
                                    sources = selectedSources.ifEmpty { null },
                                    countries = selectedCountries.ifEmpty { null },
                                    severities = selectedSeverities.ifEmpty { null },
                                    pushEnabled = pushEnabled,
                                    emailEnabled = emailEnabled,
                                    smsEnabled = smsEnabled
                                )
                            )
                            Toast.makeText(context, "Preferences saved", Toast.LENGTH_SHORT).show()
                        } catch (e: Exception) {
                            Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                        }
                        saving = false
                    }
                },
                modifier = Modifier.fillMaxWidth(),
                enabled = !saving
            ) {
                Text(if (saving) "Saving..." else "Save Preferences")
            }
        }
    }
}
