@file:OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)

package com.alafia.android.views.clinician

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.alafia.android.api.ApiClient
import com.alafia.android.models.*
import com.alafia.android.util.ErrorUtil
import kotlinx.coroutines.launch

/**
 * One patient, as a board of data-category cards.
 *
 * Opening a patient shows every category they share — latest values per
 * category plus their current wellness score — and opening a card gives trends
 * and the records behind it. Categories the patient did NOT share stay on the
 * board, greyed and locked: dropping them silently reads as "no data", which is
 * a different clinical fact.
 */
@Composable
fun PatientBoardScreen(patientId: Int, patientName: String, onBack: () -> Unit) {
    var board by remember(patientId) { mutableStateOf<PatientBoardResponse?>(null) }
    var error by remember(patientId) { mutableStateOf<String?>(null) }
    var openCategory by remember(patientId) { mutableStateOf<BoardCard?>(null) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(patientId) {
        scope.launch {
            try {
                board = ApiClient.getApiService().getPatientBoard(patientId)
            } catch (e: retrofit2.HttpException) {
                error = if (e.code() == 403) "This patient has revoked access."
                        else "Could not load this patient."
            } catch (e: Exception) {
                error = ErrorUtil.userMessage(e)
            }
        }
    }

    val category = openCategory
    if (category != null) {
        PatientCategoryScreen(
            patientId = patientId,
            categoryKey = category.key,
            categoryLabel = category.label,
            onBack = { openCategory = null },
        )
        return
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(patientName) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "All patients")
                    }
                }
            )
        }
    ) { padding ->
        when {
            error != null -> Box(Modifier.fillMaxSize().padding(padding), Alignment.Center) {
                Text(error!!, color = MaterialTheme.colorScheme.error)
            }
            board == null -> Box(Modifier.fillMaxSize().padding(padding), Alignment.Center) {
                CircularProgressIndicator()
            }
            else -> LazyVerticalGrid(
                columns = GridCells.Adaptive(minSize = 168.dp),
                modifier = Modifier.fillMaxSize().padding(padding),
                contentPadding = PaddingValues(12.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                item(span = { GridItemSpan(maxLineSpan) }) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Default.Lock, null, modifier = Modifier.size(13.dp),
                             tint = MaterialTheme.colorScheme.onSurfaceVariant)
                        Spacer(Modifier.width(6.dp))
                        Text(
                            if (board!!.permissions.contains("all"))
                                "This patient shares all of their data with you."
                            else "Shared with you: ${board!!.permissions.joinToString(", ")}",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
                items(board!!.cards, key = { it.key }) { card ->
                    BoardCategoryCard(card) { if (card.shared) openCategory = card }
                }
            }
        }
    }
}

private fun iconFor(icon: String) = when (icon) {
    "gauge" -> Icons.Default.Speed
    "heart-pulse" -> Icons.Default.MonitorHeart
    "flask" -> Icons.Default.Science
    "pill" -> Icons.Default.Medication
    "activity" -> Icons.Default.Favorite
    "apple" -> Icons.Default.Restaurant
    "dumbbell" -> Icons.Default.FitnessCenter
    "droplets" -> Icons.Default.WaterDrop
    "brain" -> Icons.Default.Psychology
    "book" -> Icons.Default.Book
    "link" -> Icons.Default.Link
    "thermometer" -> Icons.Default.Thermostat
    "cross" -> Icons.Default.MedicalServices
    "heart" -> Icons.Default.Favorite
    else -> Icons.Default.Dashboard
}

@Composable
private fun BoardCategoryCard(card: BoardCard, onOpen: () -> Unit) {
    Card(
        onClick = onOpen,
        enabled = card.shared,
        modifier = Modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
    ) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(iconFor(card.icon), null, modifier = Modifier.size(16.dp),
                     tint = MaterialTheme.colorScheme.primary)
                Spacer(Modifier.width(6.dp))
                Text(card.label, style = MaterialTheme.typography.titleSmall,
                     fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f),
                     maxLines = 1, overflow = TextOverflow.Ellipsis)
                card.count?.let {
                    Text("$it", style = MaterialTheme.typography.labelSmall,
                         color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Icon(if (card.shared) Icons.Default.ChevronRight else Icons.Default.Lock, null,
                     modifier = Modifier.size(14.dp),
                     tint = MaterialTheme.colorScheme.onSurfaceVariant)
            }

            if (card.items.isEmpty()) {
                Text(card.emptyReason ?: "Nothing recorded.",
                     style = MaterialTheme.typography.labelSmall,
                     color = MaterialTheme.colorScheme.onSurfaceVariant)
            } else {
                card.items.take(5).forEach { item ->
                    Row(Modifier.fillMaxWidth(), Arrangement.SpaceBetween) {
                        Text(item.label, style = MaterialTheme.typography.bodySmall,
                             maxLines = 1, overflow = TextOverflow.Ellipsis,
                             modifier = Modifier.weight(1f, fill = false),
                             color = if (item.danger) MaterialTheme.colorScheme.error
                                     else MaterialTheme.colorScheme.onSurface)
                        item.displayValue()?.let {
                            Spacer(Modifier.width(8.dp))
                            Text(it, style = MaterialTheme.typography.bodySmall,
                                 fontWeight = FontWeight.SemiBold, maxLines = 1,
                                 overflow = TextOverflow.Ellipsis,
                                 color = if (item.danger) MaterialTheme.colorScheme.error
                                         else MaterialTheme.colorScheme.onSurface)
                        }
                    }
                }
            }

            card.lastUpdated?.let {
                Text("Updated ${it.take(10)}", style = MaterialTheme.typography.labelSmall,
                     color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

/**
 * Trends and full records for one shared category.
 *
 * Series sharing a unit share a plot; different units get their own. Never a
 * second y-axis. Above six series (labs run to dozens) each measure gets its own
 * chart and the clinician picks which to show — a seventh series would have to
 * reuse a hue and identity by colour would be gone.
 */
@Composable
fun PatientCategoryScreen(
    patientId: Int,
    categoryKey: String,
    categoryLabel: String,
    onBack: () -> Unit,
) {
    var data by remember(categoryKey) { mutableStateOf<PatientCategoryResponse?>(null) }
    var error by remember(categoryKey) { mutableStateOf<String?>(null) }
    var days by remember(categoryKey) { mutableStateOf(90) }
    var picked by remember(categoryKey) { mutableStateOf<Set<String>>(emptySet()) }
    var openSession by remember(categoryKey) { mutableStateOf<Int?>(null) }
    val scope = rememberCoroutineScope()

    val sessionId = openSession
    if (sessionId != null) {
        TherapySessionScreen(
            patientId = patientId,
            sessionId = sessionId,
            onBack = { openSession = null },
        )
        return
    }

    LaunchedEffect(categoryKey, days) {
        scope.launch {
            error = null
            try {
                val r = ApiClient.getApiService().getPatientCategory(patientId, categoryKey, days)
                data = r
                if (r.series.size > MAX_SERIES_PER_CHART && picked.isEmpty()) {
                    // Backend sorts by point count: default to the measures with
                    // the most history — the ones that actually trend.
                    picked = r.series.take(4).map { it.label }.toSet()
                }
            } catch (e: retrofit2.HttpException) {
                error = if (e.code() == 403)
                    "This patient has not shared ${categoryLabel.lowercase()}."
                else "Could not load this category."
            } catch (e: Exception) {
                error = ErrorUtil.userMessage(e)
            }
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(categoryLabel) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                }
            )
        }
    ) { padding ->
        val d = data
        when {
            error != null -> Box(Modifier.fillMaxSize().padding(padding), Alignment.Center) {
                Text(error!!, color = MaterialTheme.colorScheme.error)
            }
            d == null -> Box(Modifier.fillMaxSize().padding(padding), Alignment.Center) {
                CircularProgressIndicator()
            }
            else -> {
                val many = d.series.size > MAX_SERIES_PER_CHART
                val groups = remember(d, picked) { groupSeries(d.series, many, picked) }

                LazyVerticalGrid(
                    columns = GridCells.Fixed(1),
                    modifier = Modifier.fillMaxSize().padding(padding),
                    contentPadding = PaddingValues(12.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    item {
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            listOf(30 to "30 days", 90 to "90 days",
                                   365 to "1 year", 1825 to "All").forEach { (dv, lbl) ->
                                FilterChip(selected = days == dv, onClick = { days = dv },
                                           label = { Text(lbl) })
                            }
                        }
                    }
                    if (many) {
                        item {
                            Column {
                                Text("${d.series.size} measures have enough history to trend — pick the ones to plot:",
                                     style = MaterialTheme.typography.labelSmall,
                                     color = MaterialTheme.colorScheme.onSurfaceVariant)
                                Spacer(Modifier.height(4.dp))
                                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp),
                                        verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                    d.series.forEach { s ->
                                        val on = picked.contains(s.label)
                                        FilterChip(
                                            selected = on,
                                            onClick = {
                                                picked = if (on) picked - s.label else picked + s.label
                                            },
                                            label = { Text(s.label, style = MaterialTheme.typography.labelSmall) }
                                        )
                                    }
                                }
                            }
                        }
                    }
                    items(groups) { g -> TrendCard(g) }
                    if (groups.isEmpty()) {
                        item {
                            Text("No trend to plot for this period — the records are below.",
                                 style = MaterialTheme.typography.bodySmall,
                                 color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                    // A dialysis session is a document a clinician opens, reads
                    // a curve from and signs — not a table row.
                    if (categoryKey == "dialysis") {
                        item {
                            TherapyReportSection(
                                patientId = patientId,
                                rows = d.rows,
                                days = days,
                                onOpenSession = { openSession = it },
                            )
                        }
                    } else {
                        items(d.rows) { row -> RecordRow(d.columns, row) }
                        if (d.rows.isEmpty()) {
                            item {
                                Text("No ${d.label.lowercase()} records in this period.",
                                     style = MaterialTheme.typography.bodySmall,
                                     color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    }
                }
            }
        }
    }
}

private const val MAX_SERIES_PER_CHART = 6

/** Validated categorical palette — the same six slots, same fixed order, as web. */
private val PALETTE = listOf(
    Color(0xFF2A78D6), Color(0xFFEB6834), Color(0xFF1BAF7A),
    Color(0xFFEDA100), Color(0xFFE87BA4), Color(0xFF008300),
)

private data class SeriesGroup(val unit: String, val series: List<TrendSeries>)

private fun groupSeries(
    series: List<TrendSeries>, many: Boolean, picked: Set<String>
): List<SeriesGroup> {
    if (series.isEmpty()) return emptyList()
    if (many) {
        return series.filter { picked.contains(it.label) }
            .map { SeriesGroup(it.unit ?: "", listOf(it)) }
    }
    val out = mutableListOf<SeriesGroup>()
    series.groupBy { it.unit ?: "" }.forEach { (unit, group) ->
        group.chunked(MAX_SERIES_PER_CHART).forEach { out += SeriesGroup(unit, it) }
    }
    return out
}

@Composable
private fun TrendCard(g: SeriesGroup) {
    val single = g.series.size == 1
    val unitSuffix = if (g.unit.isEmpty()) "" else " (${g.unit})"
    val title = if (single) "${g.series[0].label}$unitSuffix"
                else g.series.joinToString(" · ") { it.label } + unitSuffix
    val gridColor = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.12f)

    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            // The title names the measure, so a single series needs no legend.
            Text(title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(8.dp))
            Canvas(Modifier.fillMaxWidth().height(180.dp)) {
                val values = g.series.flatMap { s -> s.points.mapNotNull { it.value } }
                if (values.isEmpty()) return@Canvas
                val yMin = values.min()
                val yMax = values.max()
                val range = if (yMax - yMin > 0.0001) yMax - yMin else 1.0

                for (i in 0..4) {
                    val y = size.height * i / 4f
                    drawLine(gridColor, Offset(0f, y), Offset(size.width, y), strokeWidth = 1f)
                }

                g.series.forEachIndexed { idx, s ->
                    val pts = s.points.mapNotNull { p -> p.value?.let { it } }
                    if (pts.size < 2) return@forEachIndexed
                    val color = PALETTE[idx % PALETTE.size]
                    val stepX = size.width / (pts.size - 1).toFloat()
                    val path = Path()
                    pts.forEachIndexed { i, v ->
                        val x = stepX * i
                        val y = size.height - ((v - yMin) / range * size.height).toFloat()
                        if (i == 0) path.moveTo(x, y) else path.lineTo(x, y)
                        drawCircle(color, radius = 4f, center = Offset(x, y))
                    }
                    drawPath(path, color, style = Stroke(width = 2f))
                }
            }
            if (!single) {
                Spacer(Modifier.height(6.dp))
                FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    g.series.forEachIndexed { idx, s ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Canvas(Modifier.size(8.dp)) {
                                drawCircle(PALETTE[idx % PALETTE.size])
                            }
                            Spacer(Modifier.width(4.dp))
                            Text(s.label, style = MaterialTheme.typography.labelSmall,
                                 color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun RecordRow(columns: List<BoardColumn>, row: Map<String, Any?>) {
    val danger = row["danger"] == true
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            columns.forEach { col ->
                val raw = row[col.key] ?: return@forEach
                val text = when (raw) {
                    is Double -> if (raw == Math.floor(raw)) raw.toLong().toString()
                                 else String.format("%.2f", raw).trimEnd('0').trimEnd('.')
                    else -> raw.toString()
                }
                if (text.isBlank()) return@forEach
                Row(Modifier.fillMaxWidth(), Arrangement.SpaceBetween) {
                    Text(col.label, style = MaterialTheme.typography.labelSmall,
                         color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Spacer(Modifier.width(8.dp))
                    Text(text, style = MaterialTheme.typography.bodySmall,
                         color = if (danger) MaterialTheme.colorScheme.error
                                 else MaterialTheme.colorScheme.onSurface)
                }
            }
        }
    }
}
