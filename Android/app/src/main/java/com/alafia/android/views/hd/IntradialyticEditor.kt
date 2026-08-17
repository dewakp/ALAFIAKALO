package com.alafia.android.views.hd

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.snapshots.SnapshotStateList
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.alafia.android.api.ApiClient
import com.alafia.android.models.IntradialyticReading
import java.util.UUID

/**
 * The intradialytic readings grid on the patient's own flowsheet.
 *
 * Android could not record a reading at all: `ApiService` has carried
 * `getIntradialyticReadings`/`createIntradialyticReading` for a while and NOTHING
 * called them, so the endpoints were dead code and a patient on Android had no
 * way to enter a BP/pulse/UF timeline. Web has had this grid all along and iOS
 * gained it in `bf24307`.
 *
 * Write semantics match web and iOS exactly, and they matter:
 *
 *   - A row that already exists is PUT, never re-POSTed. Re-posting is how
 *     editing a session grew its flowsheet — the corrected row differs from the
 *     stored one, so it landed as an extra reading rather than replacing it.
 *   - A row removed here is DELETEd server-side, or it silently returns on
 *     reload.
 *   - `reading_time` is NORMALISED, not merely validated. "14:30 " passes a
 *     trimmed regex and is then rejected by the API as an invalid timezone sign,
 *     on a completed flowsheet.
 *   - A blank time is OMITTED rather than sent as 00:00. On create the column
 *     defaults to NULL, so "not stated" survives as not stated — 3664 rows
 *     (22.6% of the table) were fabricated as measured midnight readings by
 *     picking a value to satisfy a non-null type.
 *
 * Note the one thing this cannot do, which iOS cannot either: CLEAR a value on an
 * existing row. Gson omits nulls and Swift's synthesized Codable omits nil, so
 * both clients send the same body, and the API applies it with
 * `model_dump(exclude_unset=True)` — an absent key means "leave alone". Blanking
 * a field therefore leaves the stored value; deleting the row is the way to
 * remove it.
 */

/** One row of the grid. Immutable so Compose sees a change: rows are replaced
 *  via `copy()`, never mutated in place, which a `var` field would not recompose. */
data class EditableReading(
    val uid: String = UUID.randomUUID().toString(),
    /** Server id, and therefore what decides PUT vs POST — a row that came from
     *  the server is updated in place, a new one is created. */
    val serverId: Int? = null,
    val readingTime: String = "",
    val systolicBp: String = "",
    val diastolicBp: String = "",
    val pulse: String = "",
    val meanArterialPressure: String = "",
    val dialysateRate: String = "",
    val ufRate: String = "",
    val ufVolumeRemoved: String = "",
    val bloodFlowRate: String = "",
    val arterialPressure: String = "",
    val venousPressure: String = "",
    val remarks: String = "",
) {
    /** Canonical "HH:MM", or null when the text cannot be one. NORMALISE rather
     *  than validate: an earlier web fix tested the trimmed value and then posted
     *  the untrimmed one, so "14:30 " passed the guard and the API rejected it. */
    val normalisedTime: String?
        get() {
            val t = readingTime.trim()
            if (t.isEmpty()) return null
            val parts = t.split(":")
            if (parts.size < 2) return null
            val h = parts[0].toIntOrNull() ?: return null
            val m = parts[1].toIntOrNull() ?: return null
            if (h !in 0..23 || m !in 0..59) return null
            return "%02d:%02d".format(h, m)
        }

    /** True when the row holds nothing worth sending. An empty row added and then
     *  abandoned must not become a reading. */
    val isBlank: Boolean
        get() = normalisedTime == null && listOf(
            systolicBp, diastolicBp, pulse, meanArterialPressure, dialysateRate,
            ufRate, ufVolumeRemoved, bloodFlowRate, arterialPressure,
            venousPressure, remarks,
        ).all { it.isBlank() }

    /** Body for create/update. Absent keys are deliberate — see the note above. */
    fun payload(sessionId: Int?): Map<String, Any?> {
        val body = linkedMapOf<String, Any?>()
        if (sessionId != null) body["session_id"] = sessionId
        normalisedTime?.let { body["reading_time"] = it }
        fun i(k: String, v: String) { v.trim().toIntOrNull()?.let { body[k] = it } }
        fun d(k: String, v: String) { v.trim().toDoubleOrNull()?.let { body[k] = it } }
        fun s(k: String, v: String) { if (v.isNotBlank()) body[k] = v.trim() }
        i("systolic_bp", systolicBp); i("diastolic_bp", diastolicBp); i("pulse", pulse)
        d("mean_arterial_pressure", meanArterialPressure)
        d("dialysate_rate", dialysateRate)
        d("uf_rate", ufRate); d("uf_volume_removed", ufVolumeRemoved)
        d("blood_flow_rate", bloodFlowRate)
        d("arterial_pressure", arterialPressure); d("venous_pressure", venousPressure)
        s("remarks", remarks)
        return body
    }

    companion object {
        fun from(r: IntradialyticReading) = EditableReading(
            serverId = r.id,
            // "14:30:00" from the server, "14:30" in the field.
            readingTime = r.readingTime?.take(5).orEmpty(),
            systolicBp = r.systolicBp?.toString().orEmpty(),
            diastolicBp = r.diastolicBp?.toString().orEmpty(),
            pulse = r.pulse?.toString().orEmpty(),
            meanArterialPressure = num(r.meanArterialPressure),
            dialysateRate = num(r.dialysateRate),
            ufRate = num(r.ufRate),
            ufVolumeRemoved = num(r.ufVolumeRemoved),
            bloodFlowRate = num(r.bloodFlowRate),
            arterialPressure = num(r.arterialPressure),
            venousPressure = num(r.venousPressure),
            remarks = r.remarks.orEmpty(),
        )

        /** 250.0 reads as "250" in a text field; 250.5 keeps its fraction. */
        private fun num(value: Float?): String {
            if (value == null) return ""
            return if (value == value.toLong().toFloat()) value.toLong().toString()
            else value.toString()
        }
    }
}

/**
 * Persist the grid. Ordering is deliberate: deletes first, so a row removed and a
 * row added in the same edit cannot collide on the server's reading numbering.
 *
 * Runs after the session itself is saved, because a NEW session has no id until
 * the server assigns one.
 */
suspend fun persistReadings(
    sessionId: Int,
    rows: List<EditableReading>,
    removedIds: List<Int>,
) {
    val api = ApiClient.getApiService()
    for (id in removedIds.distinct()) api.deleteIntradialyticReading(id)
    for (row in rows) {
        if (row.isBlank) continue
        val existing = row.serverId
        if (existing != null) api.updateIntradialyticReading(existing, row.payload(null))
        else api.createIntradialyticReading(sessionId, row.payload(sessionId))
    }
}

@Composable
fun IntradialyticEditor(
    rows: SnapshotStateList<EditableReading>,
    removedIds: SnapshotStateList<Int>,
) {
    Column(Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text("Intradialytic Readings", fontWeight = FontWeight.Bold, fontSize = 14.sp,
                 color = MaterialTheme.colorScheme.primary, modifier = Modifier.weight(1f))
            Text(if (rows.size == 1) "1 row" else "${rows.size} rows",
                 fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Spacer(Modifier.height(6.dp))

        rows.forEachIndexed { index, row ->
            ReadingRowEditor(
                row = row,
                onChange = { updated -> if (index < rows.size) rows[index] = updated },
                onDelete = {
                    if (index < rows.size) {
                        rows[index].serverId?.let { removedIds.add(it) }
                        rows.removeAt(index)
                    }
                },
            )
            Spacer(Modifier.height(6.dp))
        }

        Row(
            Modifier.fillMaxWidth().clickable {
                // Carry the previous row's machine settings forward: on a real
                // flowsheet blood flow and dialysate rate rarely change between
                // timepoints, and retyping them invites transcription errors.
                val last = rows.lastOrNull()
                rows.add(
                    EditableReading(
                        bloodFlowRate = last?.bloodFlowRate.orEmpty(),
                        dialysateRate = last?.dialysateRate.orEmpty(),
                        ufRate = last?.ufRate.orEmpty(),
                    )
                )
            }.padding(vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(Icons.Default.Add, contentDescription = null,
                 tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.width(6.dp))
            Text("Add reading", color = MaterialTheme.colorScheme.primary, fontSize = 14.sp)
        }
    }
}

@Composable
private fun ReadingRowEditor(
    row: EditableReading,
    onChange: (EditableReading) -> Unit,
    onDelete: () -> Unit,
) {
    Card(colors = CardDefaults.cardColors(
        containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.4f))) {
        Column(Modifier.padding(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.width(96.dp)) {
                    N("HH:MM", row.readingTime, KeyboardType.Text) { onChange(row.copy(readingTime = it)) }
                }
                if (row.readingTime.isNotBlank() && row.normalisedTime == null) {
                    // Say it here rather than let the API reject the save.
                    Spacer(Modifier.width(6.dp))
                    Icon(Icons.Default.Warning, contentDescription = "Not a valid time",
                         tint = Color(0xFFFF9800))
                }
                Spacer(Modifier.weight(1f))
                Icon(Icons.Default.Delete, contentDescription = "Delete reading",
                     tint = MaterialTheme.colorScheme.error,
                     modifier = Modifier.clickable { onDelete() }.padding(4.dp))
            }
            Spacer(Modifier.height(4.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Box(Modifier.weight(1f)) { N("Sys", row.systolicBp) { onChange(row.copy(systolicBp = it)) } }
                Box(Modifier.weight(1f)) { N("Dia", row.diastolicBp) { onChange(row.copy(diastolicBp = it)) } }
                Box(Modifier.weight(1f)) { N("Pulse", row.pulse) { onChange(row.copy(pulse = it)) } }
                Box(Modifier.weight(1f)) { N("MAP", row.meanArterialPressure) { onChange(row.copy(meanArterialPressure = it)) } }
            }
            Spacer(Modifier.height(4.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Box(Modifier.weight(1f)) { N("BFR", row.bloodFlowRate) { onChange(row.copy(bloodFlowRate = it)) } }
                Box(Modifier.weight(1f)) { N("DR", row.dialysateRate) { onChange(row.copy(dialysateRate = it)) } }
                Box(Modifier.weight(1f)) { N("UFR", row.ufRate) { onChange(row.copy(ufRate = it)) } }
                Box(Modifier.weight(1f)) { N("UF Vol", row.ufVolumeRemoved) { onChange(row.copy(ufVolumeRemoved = it)) } }
            }
            Spacer(Modifier.height(4.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Box(Modifier.weight(1f)) { N("Art P", row.arterialPressure) { onChange(row.copy(arterialPressure = it)) } }
                Box(Modifier.weight(1f)) { N("Ven P", row.venousPressure) { onChange(row.copy(venousPressure = it)) } }
                Box(Modifier.weight(2f)) { N("Remarks", row.remarks, KeyboardType.Text) { onChange(row.copy(remarks = it)) } }
            }
        }
    }
}

@Composable
private fun N(
    label: String,
    value: String,
    keyboard: KeyboardType = KeyboardType.Decimal,
    onChange: (String) -> Unit,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        label = { Text(label, fontSize = 11.sp) },
        singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = keyboard),
        modifier = Modifier.fillMaxWidth(),
    )
}
