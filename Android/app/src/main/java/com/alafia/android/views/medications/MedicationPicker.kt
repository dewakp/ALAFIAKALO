package com.alafia.android.views.medications

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.alafia.android.schemas.DoseGuardRefusal

/**
 * One option offered in the intake form, with the evidence for offering it.
 *
 * [timesLogged] is the difference between a drug this patient takes and one they
 * typed once by mistake, which is why provenance is shown rather than a bare
 * name: on this record "Calcium carbonate" has 489 logs and "Calcium Calcitriol"
 * has one. A null [timesLogged] means it came from the prescription list.
 */
data class MedicationSuggestion(
    val name: String,
    val timesLogged: Int? = null,
    val lastTaken: String? = null,
) {
    val provenance: String
        get() = when {
            timesLogged == null -> "On your prescription list"
            lastTaken != null -> "Taken ${timesLogged}× · last $lastTaken"
            else -> "Taken ${timesLogged}×"
        }
}

/**
 * Type-ahead over what this patient actually takes.
 *
 * The field was a plain text box beside a `DropdownMenu` listing PRESCRIPTIONS
 * only. On an account holding 943 dose logs and zero prescriptions that menu was
 * empty and typing "Calcium" offered nothing — while the patient's own history
 * held Calcium carbonate 489 times (canon 3aa: prescribed and taken are
 * different facts).
 *
 * Worth stating plainly: a picker is also a SAFETY control. The 422 that blocked
 * a real dose was "Calcium Carbonated", one letter off a drug logged hundreds of
 * times. **Choosing from a list cannot produce a typo** — that is the actual fix
 * for it, not a looser guard.
 *
 * Matching is local: the list is this patient's own drugs, so there is no
 * request per keystroke and no failure mode where the suggestions vanish.
 */
@Composable
fun MedicationPickerField(
    name: String,
    onNameChange: (String) -> Unit,
    options: List<MedicationSuggestion>,
    onSelect: (MedicationSuggestion) -> Unit = {},
) {
    var dismissed by remember { mutableStateOf(false) }

    val matches = remember(name, options) {
        val q = name.trim().lowercase()
        if (q.isEmpty()) options.take(8)
        else options.filter { it.name.lowercase().contains(q) }.take(8)
    }
    // An exact hit needs no list — it would only cover the next field.
    val typed = name.trim().lowercase()
    val showList = !dismissed && matches.isNotEmpty() &&
        !(matches.size == 1 && matches[0].name.lowercase() == typed)

    OutlinedTextField(
        value = name,
        onValueChange = { dismissed = false; onNameChange(it) },
        label = { Text("Medication name") },
        singleLine = true,
        modifier = Modifier.fillMaxWidth(),
    )

    if (showList) {
        Surface(
            shape = RoundedCornerShape(8.dp),
            tonalElevation = 2.dp,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Column {
                matches.forEach { option ->
                    Column(
                        Modifier
                            .fillMaxWidth()
                            .clickable {
                                onNameChange(option.name)
                                dismissed = true
                                onSelect(option)
                            }
                            .padding(horizontal = 12.dp, vertical = 8.dp)
                    ) {
                        Text(option.name, style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Medium)
                        Text(option.provenance, style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
    } else if (options.isEmpty()) {
        // Not an error, and not a silent blank: this account genuinely has
        // nothing logged yet. Say which it is (canon 3aa).
        Text(
            "Nothing logged yet — type the medication name.",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

/**
 * What the dose guard refused, rendered so the patient can act on it.
 *
 * The API returns `findings` naming the cause and `override_with`. Dropping them
 * left a generic "Something went wrong", which does not even say the dose was
 * questioned — so a correct 1000 mg calcium tablet looked like an app failure,
 * when it was the NAME that was wrong and RxNorm had already computed the fix.
 */
@Composable
fun DoseGuardFindings(
    refusal: DoseGuardRefusal,
    onUseSuggestion: (String) -> Unit,
    onAcknowledge: () -> Unit,
) {
    Surface(
        shape = RoundedCornerShape(8.dp),
        color = MaterialTheme.colorScheme.errorContainer,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(
                refusal.message.ifBlank { "This dose looks wrong — please check it." },
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.SemiBold,
                color = MaterialTheme.colorScheme.onErrorContainer,
            )
            refusal.findings.forEach { finding ->
                Text(
                    finding.message,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onErrorContainer,
                )
                finding.suggestion?.takeIf { it.isNotBlank() }?.let { suggestion ->
                    TextButton(onClick = { onUseSuggestion(suggestion) }) {
                        Text("Use “$suggestion”")
                    }
                }
            }
            if (refusal.overrideWith != null) {
                // A guard with no route forward blocks a true clinical record.
                TextButton(onClick = onAcknowledge) {
                    Text("This is correct — log it anyway")
                }
            }
        }
    }
}

/**
 * Offers to turn regularly-logged drugs into prescription rows.
 *
 * The Medications tab showed "No medications / Tap + to add a medication" on an
 * account holding 943 dose logs, because it read `/medications/` alone. That is
 * canon 3aa's "an error is not an empty state" in its quietest disguise: nothing
 * failed, the screen simply asked the wrong table and reported the answer as
 * fact. Promotion stays a button rather than an automatic write — a prescription
 * is a clinical statement, so the patient makes it.
 */
@Composable
fun PromoteLoggedCard(
    unlisted: List<com.alafia.android.schemas.FrequentMedication>,
    busy: Boolean,
    onPromote: () -> Unit,
) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(
                "You regularly log ${unlisted.size} medication${if (unlisted.size == 1) "" else "s"} " +
                    "that aren’t on this list",
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.SemiBold,
            )
            unlisted.forEach { m ->
                Text(
                    "• ${m.name} — taken ${m.timesLogged}×" +
                        (m.lastTaken?.let { ", last $it" } ?: ""),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            TextButton(onClick = onPromote, enabled = !busy) {
                if (busy) CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp)
                else Text("Add these to my medications")
            }
        }
    }
}
