package com.alafia.android.views.chronic

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Clear
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.alafia.android.api.ApiClient
import com.alafia.android.models.ICD11Code
import kotlinx.coroutines.delay
import androidx.compose.ui.res.stringResource
import com.alafia.android.R

/**
 * ICD-11 code picker.
 *
 * Search runs on the backend against the full WHO MMS linearization, so the
 * app carries no code list and cannot drift from what the server accepts. The
 * patient types what they know — "ESRD", "sickle cell", "kidney" — and the
 * backend resolves lay terms, US spellings and any word order.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun Icd11PickerField(
    code: String,
    title: String,
    onChange: (code: String, title: String) -> Unit,
    modifier: Modifier = Modifier
) {
    var showSearch by remember { mutableStateOf(false) }

    OutlinedTextField(
        value = if (code.isBlank()) "" else "$code — $title",
        onValueChange = {},
        readOnly = true,
        enabled = false,
        label = { Text(stringResource(R.string.icd_11_code)) },
        placeholder = { Text(stringResource(R.string.search_by_name_abbreviation_or_code)) },
        trailingIcon = {
            if (code.isBlank()) {
                Icon(Icons.Default.Search, contentDescription = stringResource(R.string.search_icd_11))
            } else {
                IconButton(onClick = { onChange("", "") }) {
                    Icon(Icons.Default.Clear, contentDescription = stringResource(R.string.clear_icd_11_code))
                }
            }
        },
        colors = OutlinedTextFieldDefaults.colors(
            // `enabled = false` is what makes the whole field tappable rather
            // than focusable, so the disabled colours are overridden back to
            // the normal ones — otherwise a filled-in code looks greyed out.
            disabledTextColor = MaterialTheme.colorScheme.onSurface,
            disabledBorderColor = MaterialTheme.colorScheme.outline,
            disabledLabelColor = MaterialTheme.colorScheme.onSurfaceVariant,
            disabledPlaceholderColor = MaterialTheme.colorScheme.onSurfaceVariant,
            disabledTrailingIconColor = MaterialTheme.colorScheme.onSurfaceVariant
        ),
        modifier = modifier
            .fillMaxWidth()
            .clickable { showSearch = true }
    )

    if (showSearch) {
        Icd11SearchDialog(
            onDismiss = { showSearch = false },
            onSelect = { entry ->
                onChange(entry.code, entry.title)
                showSearch = false
            }
        )
    }
}

@Composable
private fun Icd11SearchDialog(
    onDismiss: () -> Unit,
    onSelect: (ICD11Code) -> Unit
) {
    var query by remember { mutableStateOf("") }
    var results by remember { mutableStateOf<List<ICD11Code>>(emptyList()) }
    var isSearching by remember { mutableStateOf(false) }
    // Held apart from `results` on purpose: rendering a failed lookup as an
    // empty list tells the patient their condition is not in the catalog,
    // which is the recurring failure of this app's clinical surfaces
    // (CLAUDE.md §3aa).
    var loadError by remember { mutableStateOf<String?>(null) }
    var retryToken by remember { mutableStateOf(0) }

    LaunchedEffect(query, retryToken) {
        val term = query.trim()
        if (term.isEmpty()) {
            results = emptyList()
            loadError = null
            isSearching = false
            return@LaunchedEffect
        }
        isSearching = true
        // Debounce. Re-running the effect cancels the previous coroutine, so a
        // slow earlier response cannot land after a newer one.
        delay(250)
        try {
            val response = ApiClient.getApiService().searchIcd11(term)
            results = response.results
            loadError = null
        } catch (e: Exception) {
            results = emptyList()
            loadError = "Could not reach the ICD-11 catalog. Your condition may still be there."
        }
        isSearching = false
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.icd_11_code)) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedTextField(
                    value = query,
                    onValueChange = { query = it },
                    label = { Text(stringResource(R.string.condition_abbreviation_or_code)) },
                    placeholder = { Text(stringResource(R.string.e_g_kidney_esrd_gb61_5)) },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )

                when {
                    loadError != null -> {
                        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text(
                                loadError!!,
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.error
                            )
                            TextButton(onClick = { retryToken++ }) { Text(stringResource(R.string.retry)) }
                        }
                    }

                    isSearching -> {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(10.dp)
                        ) {
                            CircularProgressIndicator(modifier = Modifier.size(18.dp))
                            Text(stringResource(R.string.searching), style = MaterialTheme.typography.bodySmall)
                        }
                    }

                    query.isBlank() -> {
                        Text(
                            stringResource(R.string.try_kidney_esrd_sickle_cell_or_a_code),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }

                    results.isEmpty() -> {
                        Text(
                            "No ICD-11 match for “${query.trim()}”. " +
                                "You can still save the condition by name.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }

                    else -> {
                        LazyColumn(
                            verticalArrangement = Arrangement.spacedBy(2.dp),
                            modifier = Modifier.heightIn(max = 320.dp)
                        ) {
                            items(results, key = { it.code }) { entry ->
                                Column(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .clickable { onSelect(entry) }
                                        .padding(vertical = 8.dp)
                                ) {
                                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                        Text(
                                            entry.code,
                                            fontFamily = FontFamily.Monospace,
                                            fontWeight = FontWeight.Bold,
                                            style = MaterialTheme.typography.bodyMedium
                                        )
                                        Text(
                                            entry.title,
                                            style = MaterialTheme.typography.bodyMedium
                                        )
                                    }
                                    Text(
                                        entry.chapterTitle,
                                        style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                }
                                HorizontalDivider()
                            }
                        }
                    }
                }
            }
        },
        confirmButton = {},
        dismissButton = {
            TextButton(onClick = onDismiss) { Text(stringResource(R.string.cancel)) }
        }
    )
}
