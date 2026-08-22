package com.alafia.android.views.hd

import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Clear
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

/**
 * Structured capture for drugs given DURING a dialysis session.
 *
 * The HD flowsheet had no drugs field at all — a decade of Epogene, Venofer and
 * Doxercalciferol reached the database only by import, and nothing else in the
 * app could see it (CLAUDE.md §3aa: the medication picture has THREE sources,
 * and this is the unread one).
 *
 * It still serialises to the same `Name (dose); Name (dose)` string the 1,964
 * historical rows use, so a row typed in 2019 and a row captured here parse
 * identically and no migration is needed to make history readable.
 */
data class DrugRow(val name: String = "", val dose: String = "")

object FlowsheetDrugText {

    /** `Name (dose); Name` → rows. Mirrors the backend parser. */
    fun parse(text: String?): List<DrugRow> {
        if (text.isNullOrBlank()) return emptyList()

        // Split on ";" at paren depth 0 only. A semicolon also occurs INSIDE a
        // dose — "Sodium Citrate (12 ml Venous; 3ml Arterial)" is ONE drug, and
        // splitting naively invents one called "3ml Arterial)".
        val items = mutableListOf<String>()
        var depth = 0
        val current = StringBuilder()
        for (ch in text) {
            when (ch) {
                '(' -> depth++
                ')' -> depth = maxOf(0, depth - 1)
            }
            if (ch == ';' && depth == 0) {
                items.add(current.toString()); current.clear()
            } else current.append(ch)
        }
        items.add(current.toString())

        return items.mapNotNull { raw ->
            val item = raw.trim()
            if (item.isEmpty()) return@mapNotNull null
            val open = item.indexOf('(')
            val close = item.lastIndexOf(')')
            if (open < 0 || close < open) {
                DrugRow(name = item)
            } else {
                val name = item.substring(0, open).trim()
                if (name.isEmpty()) null
                else DrugRow(name = name, dose = item.substring(open + 1, close).trim())
            }
        }
    }

    /** Rows → `Name (dose); Name`. Round-trips with [parse]. */
    fun format(rows: List<DrugRow>): String = rows.mapNotNull { row ->
        // Parentheses delimit the dose; one inside a name would make the value
        // re-parse as something else.
        val name = row.name.replace("(", "").replace(")", "").trim()
        if (name.isEmpty()) return@mapNotNull null   // a dose with no drug is not a fact
        val dose = row.dose.replace("(", "").replace(")", "").trim()
        if (dose.isEmpty()) name else "$name ($dose)"
    }.joinToString("; ")

    /** Mirrors COMMON_DIALYSIS_DRUGS on the backend. Free text stays available. */
    val common = listOf(
        "Epogene" to "e.g. 3,000 SQ",
        "Aranesp" to "e.g. 60 mcg",
        "Venofer" to "e.g. 100 mg",
        "Ferrlecit" to "e.g. 125 mg",
        "Doxercalciferol" to "e.g. 2 mcg",
        "Paricalcitol" to "e.g. 5 mcg",
        "Calcitriol" to "e.g. 1 mcg",
        "Sodium Citrate" to "e.g. 2.5 ml x 2",
        "Heparin" to "e.g. 5,000 units",
        "Alteplase" to "e.g. 2 mg",
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DrugsAdministeredEditor(
    value: String,
    onChange: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    // Seeded once: re-parsing on every recomposition would fight the user's typing.
    var rows by remember { mutableStateOf(FlowsheetDrugText.parse(value)) }
    var menuOpen by remember { mutableStateOf(false) }

    fun push(next: List<DrugRow>) {
        rows = next
        onChange(FlowsheetDrugText.format(next))
    }

    Column(modifier = modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text("Drugs Given This Session", style = MaterialTheme.typography.labelLarge)

        if (rows.isEmpty()) {
            Text(
                "No drugs recorded for this session.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        rows.forEachIndexed { i, row ->
            Row(
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.fillMaxWidth(),
            ) {
                OutlinedTextField(
                    value = row.name,
                    onValueChange = { push(rows.toMutableList().also { l -> l[i] = row.copy(name = it) }) },
                    label = { Text("Drug") },
                    singleLine = true,
                    modifier = Modifier.weight(2f),
                )
                OutlinedTextField(
                    value = row.dose,
                    onValueChange = { push(rows.toMutableList().also { l -> l[i] = row.copy(dose = it) }) },
                    label = {
                        Text(FlowsheetDrugText.common
                            .firstOrNull { it.first.equals(row.name, true) }?.second ?: "Dose")
                    },
                    singleLine = true,
                    modifier = Modifier.weight(1.4f),
                )
                IconButton(onClick = { push(rows.filterIndexed { j, _ -> j != i }) }) {
                    Icon(Icons.Default.Clear, contentDescription = "Remove drug ${i + 1}")
                }
            }
        }

        Box {
            TextButton(onClick = { menuOpen = true }) {
                Icon(Icons.Default.Add, contentDescription = null)
                Spacer(Modifier.width(4.dp))
                Text("Add drug")
            }
            DropdownMenu(expanded = menuOpen, onDismissRequest = { menuOpen = false }) {
                FlowsheetDrugText.common.forEach { (name, _) ->
                    DropdownMenuItem(
                        text = { Text(name) },
                        onClick = { menuOpen = false; push(rows + DrugRow(name = name)) },
                    )
                }
                HorizontalDivider()
                DropdownMenuItem(
                    text = { Text("Other…") },
                    onClick = { menuOpen = false; push(rows + DrugRow()) },
                )
            }
        }
    }
}
