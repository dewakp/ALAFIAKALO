package com.alafia.android.views.fda

import android.content.Context
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * The states a recall reached, drawn as a real map.
 *
 * Deliberately NOT Google Maps: that needs an API key and a billing account for
 * what is a static thumbnail with no panning, no tiles and no search. This draws
 * the same `us-states.geojson` the web and iOS maps use, straight onto a Compose
 * canvas — no key, no SDK, no dependency, and it works offline because the file
 * is bundled in assets.
 *
 * A comma-separated list of eleven postal codes is not something anyone can
 * picture, and "is this near me?" is the only question this section answers.
 */

// ── Albers conic for the contiguous 48 ────────────────────────────────────
// Ported from WEB/frontend/src/components/USCoverageMap.jsx and kept identical
// on purpose: three renderings of one dataset should not disagree about where
// Missouri is.
private const val DEG = Math.PI / 180.0
private val LAT0 = 23.0 * DEG
private val LAT1 = 45.0 * DEG
private val LON0 = -96.0 * DEG
private val N = (sin(LAT0) + sin(LAT1)) / 2.0
private val C = cos(LAT0) * cos(LAT0) + 2.0 * N * sin(LAT0)
private val RHO0 = sqrt(C - 2.0 * N * sin(39.0 * DEG)) / N

/**
 * y grows DOWNWARD on a canvas, so north must map to a smaller y. The textbook
 * form (RHO0 - rho·cosθ) gives the opposite and renders the country upside
 * down — which is exactly what the web version did on its first attempt.
 */
internal fun albers(lon: Double, lat: Double): Pair<Double, Double> {
    val theta = N * (lon * DEG - LON0)
    val rho = sqrt(C - 2.0 * N * sin(lat * DEG)) / N
    return Pair(rho * sin(theta), rho * cos(theta) - RHO0)
}

private data class StateShape(val code: String, val rings: List<List<Pair<Double, Double>>>)

private fun parseStates(json: String): List<StateShape> {
    val out = mutableListOf<StateShape>()
    val features = JSONObject(json).getJSONArray("features")
    for (i in 0 until features.length()) {
        val f = features.getJSONObject(i)
        val code = f.getJSONObject("properties").optString("code").uppercase()
        if (code.isEmpty()) continue
        val geom = f.getJSONObject("geometry")
        val coords = geom.getJSONArray("coordinates")
        val rings = mutableListOf<List<Pair<Double, Double>>>()

        fun ring(arr: org.json.JSONArray): List<Pair<Double, Double>> {
            val pts = mutableListOf<Pair<Double, Double>>()
            for (k in 0 until arr.length()) {
                val p = arr.getJSONArray(k)
                pts.add(Pair(p.getDouble(0), p.getDouble(1)))
            }
            return pts
        }

        when (geom.getString("type")) {
            "Polygon" -> for (r in 0 until coords.length()) rings.add(ring(coords.getJSONArray(r)))
            "MultiPolygon" -> for (p in 0 until coords.length()) {
                val poly = coords.getJSONArray(p)
                for (r in 0 until poly.length()) rings.add(ring(poly.getJSONArray(r)))
            }
        }
        if (rings.isNotEmpty()) out.add(StateShape(code, rings))
    }
    return out
}

private fun loadStates(context: Context): List<StateShape> =
    runCatching {
        parseStates(context.assets.open("us-states.geojson").bufferedReader().use { it.readText() })
    }.getOrDefault(emptyList())

@Composable
fun RecallCoverageMap(states: List<String>, nationwide: Boolean, modifier: Modifier = Modifier) {
    val context = LocalContext.current
    var shapes by remember { mutableStateOf<List<StateShape>?>(null) }

    LaunchedEffect(Unit) {
        shapes = withContext(Dispatchers.IO) { loadStates(context) }
    }

    val loaded = shapes
    // No frame while loading and none on failure: an empty map reads as
    // "no coverage", and the text line above already states it.
    if (loaded.isNullOrEmpty()) return

    val covered = states.map { it.uppercase() }.toSet()
    val coveredColor = Color(0xFFF97316)
    val plainColor = MaterialTheme.colorScheme.surfaceVariant

    Box(modifier.fillMaxWidth().height(170.dp)) {
        Canvas(Modifier.fillMaxWidth().height(170.dp)) {
            // Alaska and Hawaii are excluded from the projection fit. Left in,
            // Alaska owns it — its Aleutians cross the antimeridian, so the
            // lower 48 shrink into a third of the frame.
            val main = loaded.filter { it.code !in setOf("AK", "HI", "PR") }
            val projected = main.map { s ->
                s.code to s.rings.map { r -> r.map { (lon, lat) -> albers(lon, lat) } }
            }
            val all = projected.flatMap { it.second.flatten() }
            if (all.isEmpty()) return@Canvas

            val minX = all.minOf { it.first }
            val maxX = all.maxOf { it.first }
            val minY = all.minOf { it.second }
            val maxY = all.maxOf { it.second }
            val k = minOf(size.width / (maxX - minX), size.height / (maxY - minY))
            val offX = (size.width - (maxX - minX) * k) / 2.0
            val offY = (size.height - (maxY - minY) * k) / 2.0

            projected.forEach { (code, rings) ->
                val path = Path()
                rings.forEach { r ->
                    r.forEachIndexed { i, (x, y) ->
                        val px = (offX + (x - minX) * k).toFloat()
                        val py = (offY + (y - minY) * k).toFloat()
                        if (i == 0) path.moveTo(px, py) else path.lineTo(px, py)
                    }
                    path.close()
                }
                drawPath(path, if (nationwide || code in covered) coveredColor else plainColor)
            }
        }
    }
}
