package com.alafia.android.views.sync

import android.widget.Toast
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.*
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import kotlin.reflect.KClass as KotlinKClass
import com.alafia.android.api.ApiClient
import com.alafia.android.models.SyncConnection
import com.alafia.android.models.SyncStatusResponse
import com.alafia.android.models.SyncBatchResponse
import com.alafia.android.schemas.SyncBatchRequest
import com.alafia.android.schemas.SyncConnectionRequest
import com.alafia.android.schemas.SyncRecordRequest
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import kotlin.reflect.KClass
import androidx.navigation.NavHostController

// ── Data Types Configuration ─────────────────────────────────────────

data class HealthDataType(
    val key: String,
    val label: String,
    val icon: @Composable () -> Unit,
    val recordClass: KotlinKClass<out Record>,
    val permission: String
)

private val ALL_DATA_TYPES = listOf(
    HealthDataType("steps", "Steps", { Icon(Icons.Default.DirectionsWalk, null) },
        StepsRecord::class, HealthPermission.getReadPermission(StepsRecord::class)),
    HealthDataType("heart_rate", "Heart Rate", { Icon(Icons.Default.Favorite, null) },
        HeartRateRecord::class, HealthPermission.getReadPermission(HeartRateRecord::class)),
    HealthDataType("workout", "Workouts", { Icon(Icons.Default.FitnessCenter, null) },
        ExerciseSessionRecord::class, HealthPermission.getReadPermission(ExerciseSessionRecord::class)),
    HealthDataType("sleep", "Sleep", { Icon(Icons.Default.Bedtime, null) },
        SleepSessionRecord::class, HealthPermission.getReadPermission(SleepSessionRecord::class)),
    HealthDataType("weight", "Body Mass", { Icon(Icons.Default.MonitorWeight, null) },
        WeightRecord::class, HealthPermission.getReadPermission(WeightRecord::class)),
    HealthDataType("blood_pressure", "Blood Pressure", { Icon(Icons.Default.MonitorHeart, null) },
        BloodPressureRecord::class, HealthPermission.getReadPermission(BloodPressureRecord::class)),
    HealthDataType("blood_oxygen", "Blood Oxygen", { Icon(Icons.Default.Air, null) },
        OxygenSaturationRecord::class, HealthPermission.getReadPermission(OxygenSaturationRecord::class)),
    HealthDataType("body_temperature", "Body Temperature", { Icon(Icons.Default.Thermostat, null) },
        BodyTemperatureRecord::class, HealthPermission.getReadPermission(BodyTemperatureRecord::class)),
    HealthDataType("nutrition", "Nutrition", { Icon(Icons.Default.Restaurant, null) },
        NutritionRecord::class, HealthPermission.getReadPermission(NutritionRecord::class)),
)

// ── Main Screen ──────────────────────────────────────────────────────

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HealthSyncScreen(navController: NavHostController) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val api = ApiClient.getApiService()

    var isAvailable by remember { mutableStateOf(false) }
    var isAuthorized by remember { mutableStateOf(false) }
    var isSyncing by remember { mutableStateOf(false) }
    var connection by remember { mutableStateOf<SyncConnection?>(null) }
    var syncStatus by remember { mutableStateOf<SyncStatusResponse?>(null) }
    var lastResult by remember { mutableStateOf<SyncBatchResponse?>(null) }
    var errorMsg by remember { mutableStateOf<String?>(null) }
    var enabledTypes by remember { mutableStateOf(ALL_DATA_TYPES.map { it.key }.toSet()) }

    // Check Health Connect availability
    val sdkStatus = HealthConnectClient.getSdkStatus(context)
    isAvailable = sdkStatus == HealthConnectClient.SDK_AVAILABLE

    val healthConnectClient = remember(isAvailable) {
        if (isAvailable) HealthConnectClient.getOrCreate(context) else null
    }

    // Permission launcher
    val permissionLauncher = androidx.activity.compose.rememberLauncherForActivityResult(
        contract = PermissionController.createRequestPermissionResultContract()
    ) { granted ->
        isAuthorized = granted.containsAll(ALL_DATA_TYPES.map { it.permission }.toSet())
    }

    // Load status on launch
    LaunchedEffect(Unit) {
        if (!isAvailable) return@LaunchedEffect
        try {
            val granted = healthConnectClient?.permissionController
                ?.getGrantedPermissions() ?: emptySet()
            isAuthorized = granted.containsAll(ALL_DATA_TYPES.map { it.permission }.toSet())
        } catch (_: Exception) {}

        try {
            val conns = api.getSyncConnections()
            connection = conns.firstOrNull { it.platform == "health_connect" }
        } catch (_: Exception) {}

        try {
            syncStatus = api.getSyncStatus("health_connect")
        } catch (_: Exception) {}
    }

    Scaffold(
        topBar = { TopAppBar(
                title = { Text("Health Sync") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                }
            ) }
    ) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // ── Connection Status ────────────────────
            item {
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(16.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Default.Favorite, null,
                                tint = Color(0xFF4CAF50),
                                modifier = Modifier.size(32.dp))
                            Spacer(Modifier.width(12.dp))
                            Column(Modifier.weight(1f)) {
                                Text("Health Connect", fontWeight = FontWeight.Bold, fontSize = 18.sp)
                                Text(
                                    if (!isAvailable) "Not available on this device"
                                    else if (isAuthorized) "Connected"
                                    else "Not connected",
                                    fontSize = 13.sp,
                                    color = if (isAuthorized) Color(0xFF4CAF50) else MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                            if (isAvailable && !isAuthorized) {
                                Button(onClick = {
                                    permissionLauncher.launch(ALL_DATA_TYPES.map { it.permission }.toSet())
                                }) { Text("Connect") }
                            }
                        }

                        syncStatus?.let { status ->
                            Spacer(Modifier.height(12.dp))
                            HorizontalDivider()
                            Spacer(Modifier.height(8.dp))
                            Row {
                                Icon(Icons.Default.Sync, null, modifier = Modifier.size(16.dp),
                                    tint = MaterialTheme.colorScheme.onSurfaceVariant)
                                Spacer(Modifier.width(4.dp))
                                Text("${status.totalSyncedRecords} records synced",
                                    fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                status.lastSyncAt?.let {
                                    Spacer(Modifier.weight(1f))
                                    Text("Last: ${it.take(10)}", fontSize = 12.sp,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                                }
                            }
                            status.lastSyncStatus?.let { st ->
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Surface(
                                        shape = MaterialTheme.shapes.small,
                                        color = when (st) {
                                            "success" -> Color(0xFF4CAF50)
                                            "partial" -> Color(0xFFFF9800)
                                            else -> Color(0xFFF44336)
                                        }.copy(alpha = 0.15f),
                                        modifier = Modifier.padding(top = 4.dp)
                                    ) {
                                        Text(
                                            st.replaceFirstChar { it.uppercase() },
                                            fontSize = 11.sp,
                                            color = when (st) {
                                                "success" -> Color(0xFF4CAF50)
                                                "partial" -> Color(0xFFFF9800)
                                                else -> Color(0xFFF44336)
                                            },
                                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp)
                                        )
                                    }
                                    status.lastSyncRecords?.let { created ->
                                        Spacer(Modifier.width(8.dp))
                                        Text("${created} new", fontSize = 11.sp,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                                            modifier = Modifier.padding(top = 4.dp))
                                    }
                                    status.lastSyncDuplicates?.let { dups ->
                                        Text(", ${dups} skipped", fontSize = 11.sp,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                                            modifier = Modifier.padding(top = 4.dp))
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // ── Data Types ───────────────────────────
            item {
                Text("Data Types", fontWeight = FontWeight.Bold, fontSize = 16.sp)
            }

            items(ALL_DATA_TYPES) { dt ->
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    dt.icon()
                    Spacer(Modifier.width(12.dp))
                    Text(dt.label, modifier = Modifier.weight(1f))
                    Switch(
                        checked = enabledTypes.contains(dt.key),
                        onCheckedChange = { checked ->
                            enabledTypes = if (checked) enabledTypes + dt.key
                            else enabledTypes - dt.key
                        }
                    )
                }
            }

            // ── Records Breakdown ────────────────────
            syncStatus?.recordsByType?.let { byType ->
                if (byType.isNotEmpty()) {
                    item {
                        Text("Synced Records", fontWeight = FontWeight.Bold, fontSize = 16.sp)
                    }
                    items(byType.entries.sortedByDescending { it.value }) { (type, count) ->
                        Row(Modifier.fillMaxWidth()) {
                            Text(type.replace("_", " ").replaceFirstChar { it.uppercase() },
                                fontSize = 14.sp)
                            Spacer(Modifier.weight(1f))
                            Text("$count", fontSize = 14.sp,
                                color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }

            // ── Sync Button ──────────────────────────
            item {
                Spacer(Modifier.height(4.dp))
                Button(
                    onClick = {
                        scope.launch {
                            isSyncing = true
                            errorMsg = null
                            lastResult = null

                            try {
                                // Ensure connection
                                if (connection == null) {
                                    connection = api.createSyncConnection(
                                        SyncConnectionRequest("health_connect", enabledTypes.toList())
                                    )
                                }

                                // Read from Health Connect
                                val client = healthConnectClient ?: throw Exception("Health Connect not available")
                                val since = if (connection?.lastSyncAt != null) {
                                    try { Instant.parse(connection!!.lastSyncAt!!) }
                                    catch (_: Exception) { Instant.now().minusSeconds(90L * 24 * 3600) }
                                } else {
                                    Instant.now().minusSeconds(90L * 24 * 3600) // 3 months
                                }

                                val allRecords = mutableListOf<SyncRecordRequest>()
                                val fmt = DateTimeFormatter.ISO_INSTANT

                                for (dt in ALL_DATA_TYPES) {
                                    if (!enabledTypes.contains(dt.key)) continue
                                    try {
                                        val records = readRecords(client, dt, since)
                                        allRecords.addAll(records)
                                    } catch (e: Exception) {
                                        // Log but continue with other types
                                    }
                                }

                                if (allRecords.isEmpty()) {
                                    lastResult = SyncBatchResponse(0, 0, 0, 0, emptyList())
                                    Toast.makeText(context, "No new records to sync", Toast.LENGTH_SHORT).show()
                                } else {
                                    // Send in batches of 200
                                    var totalCreated = 0; var totalDups = 0; var totalErrors = 0
                                    allRecords.chunked(200).forEach { chunk ->
                                        try {
                                            val resp = api.syncIngest(
                                                SyncBatchRequest("health_connect", chunk)
                                            )
                                            totalCreated += resp.created
                                            totalDups += resp.duplicates
                                            totalErrors += resp.errors
                                        } catch (e: Exception) {
                                            totalErrors += chunk.size
                                        }
                                    }
                                    lastResult = SyncBatchResponse(allRecords.size, totalCreated, totalDups, totalErrors, emptyList())
                                    Toast.makeText(context, "Synced: $totalCreated new, $totalDups skipped", Toast.LENGTH_LONG).show()
                                }

                                // Reload status
                                try { syncStatus = api.getSyncStatus("health_connect") } catch (_: Exception) {}

                            } catch (e: Exception) {
                                errorMsg = e.message
                                Toast.makeText(context, "Sync error: ${e.message}", Toast.LENGTH_LONG).show()
                            }
                            isSyncing = false
                        }
                    },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = isAuthorized && !isSyncing && enabledTypes.isNotEmpty()
                ) {
                    if (isSyncing) {
                        CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp,
                            color = MaterialTheme.colorScheme.onPrimary)
                        Spacer(Modifier.width(8.dp))
                        Text("Syncing...")
                    } else {
                        Icon(Icons.Default.Sync, null)
                        Spacer(Modifier.width(8.dp))
                        Text("Sync Now")
                    }
                }
            }

            // ── Last Result ──────────────────────────
            lastResult?.let { result ->
                item {
                    Card(Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text("Sync Result", fontWeight = FontWeight.Bold)
                            Row { Text("Total records:", Modifier.weight(1f)); Text("${result.total}") }
                            Row { Text("Created:", Modifier.weight(1f)); Text("${result.created}", color = Color(0xFF4CAF50)) }
                            Row { Text("Duplicates skipped:", Modifier.weight(1f)); Text("${result.duplicates}", color = Color(0xFFFF9800)) }
                            if (result.errors > 0) {
                                Row { Text("Errors:", Modifier.weight(1f)); Text("${result.errors}", color = Color(0xFFF44336)) }
                            }
                        }
                    }
                }
            }

            // ── Error ────────────────────────────────
            errorMsg?.let { err ->
                item {
                    Card(Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(containerColor = Color(0xFFFDEDED))) {
                        Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Default.Warning, null, tint = Color(0xFFF44336))
                            Spacer(Modifier.width(8.dp))
                            Text(err, fontSize = 13.sp, color = Color(0xFFF44336))
                        }
                    }
                }
            }

            // ── Info ─────────────────────────────────
            item {
                Card(Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f))) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Default.ArrowForward, null, modifier = Modifier.size(16.dp))
                            Spacer(Modifier.width(8.dp))
                            Text("One-way sync", fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                        }
                        Text("Data flows from Health Connect → ALAFIA only.", fontSize = 12.sp,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)

                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Default.Shield, null, modifier = Modifier.size(16.dp))
                            Spacer(Modifier.width(8.dp))
                            Text("Deduplication", fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                        }
                        Text("Each record has a unique ID. Re-syncing won't create duplicates.", fontSize = 12.sp,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)

                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Default.LocalHospital, null, modifier = Modifier.size(16.dp))
                            Spacer(Modifier.width(8.dp))
                            Text("EHR & Apps", fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                        }
                        Text("Any app or EHR connected to Health Connect is automatically included.", fontSize = 12.sp,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
    }
}

// ── Health Connect Record Readers ────────────────────────────────────

private suspend fun readRecords(
    client: HealthConnectClient,
    dt: HealthDataType,
    since: Instant
): List<SyncRecordRequest> {
    val timeRange = TimeRangeFilter.between(since, Instant.now())
    val fmt = DateTimeFormatter.ISO_DATE

    return when (dt.key) {
        "steps" -> {
            val resp = client.readRecords(ReadRecordsRequest(StepsRecord::class, timeRange))
            resp.records.map { r ->
                SyncRecordRequest(
                    externalId = r.metadata.id,
                    dataType = "steps",
                    sourceTimestamp = r.startTime.toString(),
                    data = mapOf(
                        "count" to r.count,
                        "date" to r.startTime.atOffset(ZoneOffset.UTC).toLocalDate().format(fmt)
                    )
                )
            }
        }
        "heart_rate" -> {
            val resp = client.readRecords(ReadRecordsRequest(HeartRateRecord::class, timeRange))
            resp.records.flatMap { r ->
                r.samples.mapIndexed { idx, sample ->
                    SyncRecordRequest(
                        externalId = "${r.metadata.id}_$idx",
                        dataType = "heart_rate",
                        sourceTimestamp = sample.time.toString(),
                        data = mapOf(
                            "bpm" to sample.beatsPerMinute,
                            "date" to sample.time.atOffset(ZoneOffset.UTC).toLocalDate().format(fmt)
                        )
                    )
                }
            }
        }
        "workout" -> {
            val resp = client.readRecords(ReadRecordsRequest(ExerciseSessionRecord::class, timeRange))
            resp.records.map { r ->
                val durationMin = (r.endTime.epochSecond - r.startTime.epochSecond) / 60
                SyncRecordRequest(
                    externalId = r.metadata.id,
                    dataType = "workout",
                    sourceTimestamp = r.startTime.toString(),
                    data = mapOf(
                        "activity_type" to mapExerciseType(r.exerciseType),
                        "workout_type" to mapExerciseType(r.exerciseType),
                        "duration_minutes" to durationMin,
                        "date" to r.startTime.atOffset(ZoneOffset.UTC).toLocalDate().format(fmt)
                    )
                )
            }
        }
        "sleep" -> {
            val resp = client.readRecords(ReadRecordsRequest(SleepSessionRecord::class, timeRange))
            resp.records.map { r ->
                val hours = (r.endTime.epochSecond - r.startTime.epochSecond) / 3600.0
                SyncRecordRequest(
                    externalId = r.metadata.id,
                    dataType = "sleep",
                    sourceTimestamp = r.startTime.toString(),
                    data = mapOf(
                        "duration_hours" to (Math.round(hours * 10) / 10.0),
                        "date" to r.endTime.atOffset(ZoneOffset.UTC).toLocalDate().format(fmt)
                    )
                )
            }
        }
        "weight" -> {
            val resp = client.readRecords(ReadRecordsRequest(WeightRecord::class, timeRange))
            resp.records.map { r ->
                SyncRecordRequest(
                    externalId = r.metadata.id,
                    dataType = "weight",
                    sourceTimestamp = r.time.toString(),
                    data = mapOf(
                        "value_kg" to (Math.round(r.weight.inKilograms * 10) / 10.0),
                        "date" to r.time.atOffset(ZoneOffset.UTC).toLocalDate().format(fmt)
                    )
                )
            }
        }
        "blood_pressure" -> {
            val resp = client.readRecords(ReadRecordsRequest(BloodPressureRecord::class, timeRange))
            resp.records.map { r ->
                SyncRecordRequest(
                    externalId = r.metadata.id,
                    dataType = "blood_pressure",
                    sourceTimestamp = r.time.toString(),
                    data = mapOf(
                        "systolic" to r.systolic.inMillimetersOfMercury.toInt(),
                        "diastolic" to r.diastolic.inMillimetersOfMercury.toInt(),
                        "date" to r.time.atOffset(ZoneOffset.UTC).toLocalDate().format(fmt)
                    )
                )
            }
        }
        "blood_oxygen" -> {
            val resp = client.readRecords(ReadRecordsRequest(OxygenSaturationRecord::class, timeRange))
            resp.records.map { r ->
                SyncRecordRequest(
                    externalId = r.metadata.id,
                    dataType = "blood_oxygen",
                    sourceTimestamp = r.time.toString(),
                    data = mapOf(
                        "percentage" to r.percentage.value,
                        "date" to r.time.atOffset(ZoneOffset.UTC).toLocalDate().format(fmt)
                    )
                )
            }
        }
        "body_temperature" -> {
            val resp = client.readRecords(ReadRecordsRequest(BodyTemperatureRecord::class, timeRange))
            resp.records.map { r ->
                SyncRecordRequest(
                    externalId = r.metadata.id,
                    dataType = "body_temperature",
                    sourceTimestamp = r.time.toString(),
                    data = mapOf(
                        "value_celsius" to (Math.round(r.temperature.inCelsius * 10) / 10.0),
                        "date" to r.time.atOffset(ZoneOffset.UTC).toLocalDate().format(fmt)
                    )
                )
            }
        }
        "nutrition" -> {
            val resp = client.readRecords(ReadRecordsRequest(NutritionRecord::class, timeRange))
            resp.records.map { r ->
                SyncRecordRequest(
                    externalId = r.metadata.id,
                    dataType = "nutrition",
                    sourceTimestamp = r.startTime.toString(),
                    data = mapOf(
                        "food_name" to (r.name ?: "Health Connect import"),
                        "energy_kcal" to r.energy?.inKilocalories,
                        "protein_g" to r.protein?.inGrams,
                        "carbs_g" to r.totalCarbohydrate?.inGrams,
                        "fat_g" to r.totalFat?.inGrams,
                        "fiber_g" to r.dietaryFiber?.inGrams,
                        "sugar_g" to r.sugar?.inGrams,
                        "sodium_mg" to r.sodium?.inMilligrams,
                        "date" to r.startTime.atOffset(ZoneOffset.UTC).toLocalDate().format(fmt)
                    )
                )
            }
        }
        else -> emptyList()
    }
}

private fun mapExerciseType(type: Int): String = when (type) {
    ExerciseSessionRecord.EXERCISE_TYPE_RUNNING -> "running"
    ExerciseSessionRecord.EXERCISE_TYPE_BIKING -> "cycling"
    ExerciseSessionRecord.EXERCISE_TYPE_SWIMMING_POOL, ExerciseSessionRecord.EXERCISE_TYPE_SWIMMING_OPEN_WATER -> "swimming"
    ExerciseSessionRecord.EXERCISE_TYPE_WALKING -> "walking"
    ExerciseSessionRecord.EXERCISE_TYPE_HIKING -> "hiking"
    ExerciseSessionRecord.EXERCISE_TYPE_YOGA -> "yoga"
    ExerciseSessionRecord.EXERCISE_TYPE_WEIGHTLIFTING -> "weightlifting"
    ExerciseSessionRecord.EXERCISE_TYPE_HIGH_INTENSITY_INTERVAL_TRAINING -> "hiit"
    ExerciseSessionRecord.EXERCISE_TYPE_DANCING -> "dance"
    ExerciseSessionRecord.EXERCISE_TYPE_ELLIPTICAL -> "elliptical"
    ExerciseSessionRecord.EXERCISE_TYPE_ROWING_MACHINE -> "rowing"
    ExerciseSessionRecord.EXERCISE_TYPE_STAIR_CLIMBING -> "stair_climbing"
    ExerciseSessionRecord.EXERCISE_TYPE_PILATES -> "pilates"
    ExerciseSessionRecord.EXERCISE_TYPE_TENNIS -> "tennis"
    ExerciseSessionRecord.EXERCISE_TYPE_BASKETBALL -> "basketball"
    ExerciseSessionRecord.EXERCISE_TYPE_SOCCER -> "soccer"
    else -> "other"
}
