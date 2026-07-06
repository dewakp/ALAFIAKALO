@file:OptIn(ExperimentalMaterial3Api::class)

package com.alafia.android.views.chartdashboard

import android.widget.Toast
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.navigation.NavHostController
import com.alafia.android.api.ApiClient
import com.alafia.android.models.WeightSeriesResponse
import com.alafia.android.models.WeightSeriesSummary
import com.alafia.android.util.ErrorUtil
import kotlinx.coroutines.launch
import kotlin.math.max
import kotlin.math.min

/** Composite weight trend — unifies weight recorded anywhere in the app (vitals, meals,
 *  elimination, dialysis therapy, labs, lifestyle, fitness) via /chart-dashboard/weight-series,
 *  with a 7-day rolling average and the profile target-weight goal line. */
@Composable
fun WeightTrendScreen(navController: NavHostController) {
    var days by remember { mutableStateOf(90) }
    var data by remember { mutableStateOf<WeightSeriesResponse?>(null) }
    var isLoading by remember { mutableStateOf(true) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    fun load() {
        scope.launch {
            isLoading = true
            try {
                data = ApiClient.getApiService().getWeightSeries(days = days)
            } catch (e: Exception) {
                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
            }
            isLoading = false
        }
    }

    LaunchedEffect(days) { load() }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Weight Trend") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                }
            )
        }
    ) { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState())
                .padding(16.dp)
        ) {
            val options = listOf(30 to "30d", 90 to "90d", 180 to "6mo", 365 to "1yr")
            SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                options.forEachIndexed { i, (d, label) ->
                    SegmentedButton(
                        selected = days == d,
                        onClick = { days = d },
                        shape = SegmentedButtonDefaults.itemShape(index = i, count = options.size)
                    ) { Text(label) }
                }
            }
            Spacer(Modifier.height(16.dp))

            when {
                isLoading -> Box(Modifier.fillMaxWidth().height(240.dp),
                    contentAlignment = Alignment.Center) { CircularProgressIndicator() }
                data == null || data!!.points.isEmpty() ->
                    Box(Modifier.fillMaxWidth().height(240.dp), contentAlignment = Alignment.Center) {
                        Text("No weight data — log weight in Vitals, Meals, Elimination or Therapy.",
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                else -> {
                    WeightChart(data!!)
                    Spacer(Modifier.height(8.dp))
                    LegendRow()
                    Spacer(Modifier.height(16.dp))
                    SummaryCard(data!!.summary)
                    Spacer(Modifier.height(12.dp))
                    SourcesCard(data!!.summary)
                }
            }
        }
    }
}

@Composable
private fun WeightChart(data: WeightSeriesResponse) {
    val points = data.points
    val target = data.summary.profileTargetWeightKg
    val values = points.map { it.value } + points.map { it.rolling7d } + listOfNotNull(target)
    // Lift the baseline (~40 kg, never above data) so the curve isn't flattened.
    val lo = min(40.0, (values.min()) - 5.0).toFloat()
    val hi = ((values.max()) * 1.03).toFloat()

    Canvas(Modifier.fillMaxWidth().height(240.dp)) {
        val w = size.width
        val h = size.height
        fun x(i: Int) = if (points.size <= 1) 0f else w * i / (points.size - 1).toFloat()
        fun y(v: Double) = h - ((v.toFloat() - lo) / (hi - lo).coerceAtLeast(0.01f)) * h

        fun path(sel: (Int) -> Double): Path {
            val p = Path()
            points.forEachIndexed { i, _ ->
                val px = x(i); val py = y(sel(i))
                if (i == 0) p.moveTo(px, py) else p.lineTo(px, py)
            }
            return p
        }

        drawPath(path { points[it].value }, Color(0xFF2E7D32), style = Stroke(width = 4f))
        drawPath(path { points[it].rolling7d }, Color(0xFF1565C0), style = Stroke(width = 4f))
        target?.let {
            val ty = y(it)
            drawLine(
                Color(0xFFD32F2F), Offset(0f, ty), Offset(w, ty), strokeWidth = 3f,
                pathEffect = PathEffect.dashPathEffect(floatArrayOf(16f, 8f))
            )
        }
    }
}

@Composable
private fun LegendRow() {
    Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
        LegendItem(Color(0xFF2E7D32), "Daily mean")
        LegendItem(Color(0xFF1565C0), "7-day average")
        LegendItem(Color(0xFFD32F2F), "Target")
    }
}

@Composable
private fun LegendItem(color: Color, label: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Surface(color = color, shape = MaterialTheme.shapes.small) { Box(Modifier.size(10.dp)) }
        Spacer(Modifier.width(6.dp))
        Text(label, style = MaterialTheme.typography.labelSmall)
    }
}

@Composable
private fun SummaryCard(s: WeightSeriesSummary) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Text("Statistics", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(8.dp))
            StatRow("Average", s.avg, "Std Dev", s.stddev)
            StatRow("Min", s.min, "Max", s.max)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("Points: ${s.count}", style = MaterialTheme.typography.bodySmall)
                Text("Trend: ${s.trend.replaceFirstChar { it.uppercase() }}",
                    style = MaterialTheme.typography.bodySmall)
            }
            s.dryWeightKg?.let { StatRow("Dry Weight", it, "Target", s.profileTargetWeightKg) }
        }
    }
}

@Composable
private fun StatRow(l1: String, v1: Double?, l2: String, v2: Double?) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text("$l1: ${v1?.let { "%.1f kg".format(it) } ?: "–"}",
            style = MaterialTheme.typography.bodySmall)
        Text("$l2: ${v2?.let { "%.1f kg".format(it) } ?: "–"}",
            style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun SourcesCard(s: WeightSeriesSummary) {
    if (s.sources.isEmpty()) return
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Text("Data Sources", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(8.dp))
            s.sources.entries.sortedByDescending { it.value }.forEach { (source, count) ->
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(source.replaceFirstChar { it.uppercase() },
                        style = MaterialTheme.typography.bodySmall)
                    Text("$count", style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }
}
