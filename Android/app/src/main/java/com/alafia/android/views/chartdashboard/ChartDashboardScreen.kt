package com.alafia.android.views.chartdashboard

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.alafia.android.api.ApiClient
import com.alafia.android.models.ChartDataSeries
import com.alafia.android.models.ChartDatasetInfo
import com.alafia.android.models.ChartSummaryResponse
import kotlinx.coroutines.launch
import androidx.navigation.NavHostController

// ── Palette ─────────────────────────────────────────

private val PALETTE = listOf(
    Color(0xFF10B981), Color(0xFF3B82F6), Color(0xFFF59E0B),
    Color(0xFFEF4444), Color(0xFF8B5CF6), Color(0xFFEC4899),
    Color(0xFF14B8A6), Color(0xFFF97316), Color(0xFF6366F1),
    Color(0xFF84CC16),
)

private enum class ChartType(val label: String) {
    LINE("Line"), BAR("Bar"), AREA("Area"), POINT("Scatter")
}

private val AGG_OPTIONS = listOf("daily", "weekly", "monthly")
private val DAY_OPTIONS = listOf(30, 90, 180, 365)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChartDashboardScreen(navController: NavHostController) {
    val scope = rememberCoroutineScope()

    var datasets by remember { mutableStateOf<Map<String, List<ChartDatasetInfo>>>(emptyMap()) }
    var selectedKeys by remember { mutableStateOf<List<String>>(emptyList()) }
    var chartData by remember { mutableStateOf<Map<String, ChartDataSeries>>(emptyMap()) }
    var summaries by remember { mutableStateOf<Map<String, ChartSummaryResponse>>(emptyMap()) }
    var chartType by remember { mutableStateOf(ChartType.LINE) }
    var aggregation by remember { mutableStateOf("daily") }
    var days by remember { mutableStateOf(90) }
    var isLoading by remember { mutableStateOf(false) }
    var errorMsg by remember { mutableStateOf<String?>(null) }
    var showPicker by remember { mutableStateOf(false) }

    // Load datasets on mount
    LaunchedEffect(Unit) {
        try {
            datasets = ApiClient.getApiService().getChartDatasets()
        } catch (_: Exception) { }
    }

    // Fetch data when selections change
    fun refresh() {
        if (selectedKeys.isEmpty()) {
            chartData = emptyMap(); summaries = emptyMap(); return
        }
        scope.launch {
            isLoading = true; errorMsg = null
            try {
                val keys = selectedKeys.joinToString(",")
                chartData = ApiClient.getApiService().getChartData(keys, days, aggregation)
                val sums = mutableMapOf<String, ChartSummaryResponse>()
                for (k in selectedKeys) {
                    try {
                        sums[k] = ApiClient.getApiService().getChartSummary(k, days)
                    } catch (_: Exception) { }
                }
                summaries = sums
            } catch (e: Exception) {
                errorMsg = e.message ?: "Failed to load chart data"
            }
            isLoading = false
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Chart Dashboard") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                }
            )
        }
    ) { padding ->
    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(padding).padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {

        // Aggregation + Days
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                AGG_OPTIONS.forEach { a ->
                    FilterChip(
                        selected = aggregation == a,
                        onClick = { aggregation = a; refresh() },
                        label = { Text(a.replaceFirstChar { it.uppercase() }, fontSize = 12.sp) }
                    )
                }
                Spacer(Modifier.width(8.dp))
                DAY_OPTIONS.forEach { d ->
                    FilterChip(
                        selected = days == d,
                        onClick = { days = d; refresh() },
                        label = { Text(if (d < 365) "${d}d" else "${d/365}y", fontSize = 12.sp) }
                    )
                }
            }
        }

        // Selected tags
        if (selectedKeys.isNotEmpty()) {
            item {
                Row(
                    modifier = Modifier.horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    selectedKeys.forEachIndexed { idx, key ->
                        val color = PALETTE[idx % PALETTE.size]
                        AssistChip(
                            onClick = {
                                selectedKeys = selectedKeys - key
                                refresh()
                            },
                            label = {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Box(modifier = Modifier.size(8.dp).background(color, CircleShape))
                                    Spacer(Modifier.width(4.dp))
                                    Text(chartData[key]?.label ?: key, fontSize = 12.sp)
                                }
                            },
                            trailingIcon = { Icon(Icons.Default.Close, null, modifier = Modifier.size(14.dp)) }
                        )
                    }
                }
            }
        }

        // Loading
        if (isLoading) {
            item {
                Box(Modifier.fillMaxWidth().padding(40.dp), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
            }
        }

        // Error
        errorMsg?.let { msg ->
            item {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer)) {
                    Text(msg, modifier = Modifier.padding(16.dp), color = MaterialTheme.colorScheme.onErrorContainer)
                }
            }
        }

        // Empty state
        if (!isLoading && selectedKeys.isEmpty()) {
            item {
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(
                        modifier = Modifier.fillMaxWidth().padding(40.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Icon(Icons.Default.BarChart, null, modifier = Modifier.size(48.dp),
                            tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.4f))
                        Spacer(Modifier.height(12.dp))
                        Text("Select Datasets to Chart", fontWeight = FontWeight.Medium)
                        Spacer(Modifier.height(4.dp))
                        Text("Tap + to pick metrics", fontSize = 13.sp,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            textAlign = TextAlign.Center)
                    }
                }
            }
        }

        // Chart
        if (!isLoading && chartData.isNotEmpty() && selectedKeys.isNotEmpty()) {
            item {
                Card(modifier = Modifier.fillMaxWidth()) {
                    ComposeChart(
                        chartData = chartData,
                        selectedKeys = selectedKeys,
                        chartType = chartType,
                        modifier = Modifier.fillMaxWidth().height(300.dp).padding(16.dp)
                    )
                }
            }
        }

        // Summary cards
        if (summaries.isNotEmpty()) {
            items(selectedKeys.mapIndexedNotNull { idx, key ->
                summaries[key]?.let { idx to it }
            }) { (idx, s) ->
                SummaryCard(s, PALETTE[idx % PALETTE.size])
            }
        }

        item { Spacer(Modifier.height(16.dp)) }
    }

    // Dataset picker dialog
    if (showPicker) {
        DatasetPickerDialog(
            datasets = datasets,
            selected = selectedKeys,
            onToggle = { key ->
                selectedKeys = if (key in selectedKeys) selectedKeys - key else selectedKeys + key
            },
            onDismiss = {
                showPicker = false
                refresh()
            }
        )
    }
}
}

// ── Canvas-based Chart ─────────────────────────────────

@Composable
private fun ComposeChart(
    chartData: Map<String, ChartDataSeries>,
    selectedKeys: List<String>,
    chartType: ChartType,
    modifier: Modifier = Modifier
) {
    val surfaceColor = MaterialTheme.colorScheme.onSurface

    Canvas(modifier = modifier) {
        val leftPadding = 50f
        val bottomPadding = 30f
        val chartWidth = size.width - leftPadding
        val chartHeight = size.height - bottomPadding

        if (chartWidth <= 0 || chartHeight <= 0) return@Canvas

        // Collect all values for Y scale
        val allValues = selectedKeys.flatMap { key ->
            chartData[key]?.points?.mapNotNull { it.value } ?: emptyList()
        }
        if (allValues.isEmpty()) return@Canvas

        val yMin = allValues.min()
        val yMax = allValues.max()
        val yRange = if (yMax - yMin > 0.001) yMax - yMin else 1.0

        // Grid lines
        drawLine(surfaceColor.copy(alpha = 0.2f), Offset(leftPadding, 0f), Offset(leftPadding, chartHeight))
        drawLine(surfaceColor.copy(alpha = 0.2f), Offset(leftPadding, chartHeight), Offset(size.width, chartHeight))
        for (i in 0..4) {
            val y = chartHeight * i / 4f
            drawLine(surfaceColor.copy(alpha = 0.08f), Offset(leftPadding, y), Offset(size.width, y))
            drawContext.canvas.nativeCanvas.drawText(
                String.format("%.0f", yMax - (yRange * i / 4)),
                2f, y + 4f,
                android.graphics.Paint().apply {
                    color = android.graphics.Color.GRAY
                    textSize = 22f
                }
            )
        }

        // Draw each series
        selectedKeys.forEachIndexed { sIdx, key ->
            val series = chartData[key] ?: return@forEachIndexed
            val points = series.points.mapNotNull { pt -> pt.value?.let { pt.date to it } }
            if (points.isEmpty()) return@forEachIndexed

            val color = PALETTE[sIdx % PALETTE.size]
            val barWidth = if (selectedKeys.size > 1)
                (chartWidth / points.size / selectedKeys.size).coerceAtLeast(4f)
            else
                (chartWidth / points.size * 0.7f).coerceAtLeast(4f)

            when (chartType) {
                ChartType.LINE -> drawLineChart(points, color, leftPadding, chartWidth, chartHeight, yMin, yRange)
                ChartType.BAR -> drawBarChart(points, color, leftPadding, chartWidth, chartHeight, yMin, yRange, sIdx, selectedKeys.size)
                ChartType.AREA -> drawAreaChart(points, color, leftPadding, chartWidth, chartHeight, yMin, yRange)
                ChartType.POINT -> drawPointChart(points, color, leftPadding, chartWidth, chartHeight, yMin, yRange)
            }
        }
    }
}

private fun DrawScope.drawLineChart(
    points: List<Pair<String, Double>>,
    color: Color, left: Float, w: Float, h: Float, yMin: Double, yRange: Double
) {
    if (points.size < 2) return
    for (i in 0 until points.size - 1) {
        val x1 = left + w * i / (points.size - 1)
        val y1 = h - ((points[i].second - yMin) / yRange * h).toFloat()
        val x2 = left + w * (i + 1) / (points.size - 1)
        val y2 = h - ((points[i + 1].second - yMin) / yRange * h).toFloat()
        drawLine(color, Offset(x1, y1), Offset(x2, y2), strokeWidth = 3f, cap = StrokeCap.Round)
    }
    // dots
    points.forEachIndexed { i, (_, v) ->
        val x = left + w * i / (points.size - 1).coerceAtLeast(1)
        val y = h - ((v - yMin) / yRange * h).toFloat()
        drawCircle(color, radius = 4f, center = Offset(x, y))
    }
}

private fun DrawScope.drawBarChart(
    points: List<Pair<String, Double>>,
    color: Color, left: Float, w: Float, h: Float, yMin: Double, yRange: Double,
    seriesIdx: Int, totalSeries: Int
) {
    val barGroupWidth = w / points.size
    val barWidth = (barGroupWidth / totalSeries * 0.7f).coerceAtLeast(4f)
    points.forEachIndexed { i, (_, v) ->
        val barX = left + barGroupWidth * i + barWidth * seriesIdx + (barGroupWidth * 0.15f)
        val barH = ((v - yMin) / yRange * h).toFloat()
        drawRect(
            color = color,
            topLeft = Offset(barX, h - barH),
            size = androidx.compose.ui.geometry.Size(barWidth, barH)
        )
    }
}

private fun DrawScope.drawAreaChart(
    points: List<Pair<String, Double>>,
    color: Color, left: Float, w: Float, h: Float, yMin: Double, yRange: Double
) {
    if (points.size < 2) return
    val path = Path()
    val firstX = left
    val firstY = h - ((points[0].second - yMin) / yRange * h).toFloat()
    path.moveTo(firstX, h)
    path.lineTo(firstX, firstY)
    for (i in 1 until points.size) {
        val x = left + w * i / (points.size - 1)
        val y = h - ((points[i].second - yMin) / yRange * h).toFloat()
        path.lineTo(x, y)
    }
    path.lineTo(left + w, h)
    path.close()
    drawPath(path, color.copy(alpha = 0.2f))
    // line on top
    drawLineChart(points, color, left, w, h, yMin, yRange)
}

private fun DrawScope.drawPointChart(
    points: List<Pair<String, Double>>,
    color: Color, left: Float, w: Float, h: Float, yMin: Double, yRange: Double
) {
    points.forEachIndexed { i, (_, v) ->
        val x = left + w * i / (points.size - 1).coerceAtLeast(1)
        val y = h - ((v - yMin) / yRange * h).toFloat()
        drawCircle(color, radius = 6f, center = Offset(x, y))
    }
}

// ── Summary Card ────────────────────────────────────────

@Composable
private fun SummaryCard(s: ChartSummaryResponse, color: Color) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(modifier = Modifier.size(10.dp).background(color, CircleShape))
                Spacer(Modifier.width(8.dp))
                Text(s.label, fontWeight = FontWeight.Bold)
                Spacer(Modifier.width(4.dp))
                Text(s.unit, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Spacer(Modifier.weight(1f))
                TrendBadge(s.trend)
            }
            Spacer(Modifier.height(8.dp))
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly) {
                StatItem("Avg", s.avg)
                StatItem("Min", s.min)
                StatItem("Max", s.max)
                StatItem("Std", s.stddev)
                StatItem("Pts", s.count.toDouble())
            }
        }
    }
}

@Composable
private fun StatItem(label: String, value: Double?) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(label, fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(
            if (value != null) String.format("%.1f", value) else "–",
            fontSize = 14.sp, fontWeight = FontWeight.Bold
        )
    }
}

@Composable
private fun TrendBadge(trend: String) {
    val (icon, color) = when (trend) {
        "increasing" -> Icons.Default.TrendingUp to Color(0xFF10B981)
        "decreasing" -> Icons.Default.TrendingDown to Color(0xFFEF4444)
        else -> Icons.Default.Remove to Color.Gray
    }
    Surface(
        shape = RoundedCornerShape(12.dp),
        color = color.copy(alpha = 0.12f)
    ) {
        Row(modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp),
            verticalAlignment = Alignment.CenterVertically) {
            Icon(icon, null, modifier = Modifier.size(12.dp), tint = color)
            Spacer(Modifier.width(2.dp))
            Text(trend.replaceFirstChar { it.uppercase() }, fontSize = 11.sp, color = color)
        }
    }
}

// ── Dataset Picker Dialog ───────────────────────────────

@Composable
private fun DatasetPickerDialog(
    datasets: Map<String, List<ChartDatasetInfo>>,
    selected: List<String>,
    onToggle: (String) -> Unit,
    onDismiss: () -> Unit
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = {
            TextButton(onClick = onDismiss) { Text("Done") }
        },
        title = { Text("Select Datasets") },
        text = {
            LazyColumn(modifier = Modifier.heightIn(max = 400.dp)) {
                datasets.keys.sorted().forEach { domain ->
                    item {
                        Text(
                            domain.replaceFirstChar { it.uppercase() },
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.primary,
                            modifier = Modifier.padding(top = 12.dp, bottom = 4.dp)
                        )
                    }
                    items(datasets[domain] ?: emptyList()) { ds ->
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable { onToggle(ds.key) }
                                .padding(vertical = 6.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text("${ds.label} ${if (ds.unit.isNotEmpty()) "(${ds.unit})" else ""}", modifier = Modifier.weight(1f))
                            if (ds.key in selected) {
                                Icon(Icons.Default.CheckCircle, null, tint = MaterialTheme.colorScheme.primary)
                            }
                        }
                    }
                }
            }
        }
    )
}
