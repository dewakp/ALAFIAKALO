@file:OptIn(ExperimentalMaterial3Api::class)

package com.alafia.android.views.lifestyle
import com.alafia.android.util.ErrorUtil

import android.widget.Toast
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.alafia.android.api.ApiClient
import com.alafia.android.models.LifestyleEntry
import com.alafia.android.schemas.LifestyleEntryRequest
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import androidx.navigation.NavHostController

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LifestyleScreen(navController: NavHostController) {
    var entries by remember { mutableStateOf<List<LifestyleEntry>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    var showForm by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    fun loadEntries() {
        scope.launch {
            isLoading = true
            try {
                entries = ApiClient.getApiService().getLifestyleEntries()
            } catch (e: Exception) {
                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
            }
            isLoading = false
        }
    }

    LaunchedEffect(Unit) { loadEntries() }

    Scaffold(
        topBar = { TopAppBar(
                title = { Text("Lifestyle") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                }
            ) },
        floatingActionButton = {
            FloatingActionButton(onClick = { showForm = true }) {
                Icon(Icons.Default.Add, "Add Entry")
            }
        }
    ) { padding ->
        if (isLoading) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        } else if (entries.isEmpty()) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(Icons.Default.SelfImprovement, "No entries", modifier = Modifier.size(64.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
                    Spacer(Modifier.height(12.dp))
                    Text("No lifestyle entries", style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text("Tap + to log your habits", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(entries, key = { it.id }) { entry ->
                    LifestyleEntryCard(
                        entry = entry,
                        onDelete = {
                            scope.launch {
                                try {
                                    ApiClient.getApiService().deleteLifestyleEntry(entry.id)
                                    loadEntries()
                                } catch (e: Exception) {
                                    Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                                }
                            }
                        }
                    )
                }
            }
        }
    }

    if (showForm) {
        AddLifestyleDialog(
            onDismiss = { showForm = false },
            onSave = { request ->
                scope.launch {
                    try {
                        ApiClient.getApiService().createLifestyleEntry(request)
                        showForm = false
                        loadEntries()
                        Toast.makeText(context, "Entry added!", Toast.LENGTH_SHORT).show()
                    } catch (e: Exception) {
                        Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                    }
                }
            }
        )
    }
}

@Composable
private fun LifestyleEntryCard(entry: LifestyleEntry, onDelete: () -> Unit) {
    val icon = when (entry.category.lowercase()) {
        "sleep" -> Icons.Default.Bedtime
        "water" -> Icons.Default.WaterDrop
        "exercise" -> Icons.Default.FitnessCenter
        "screen_time" -> Icons.Default.PhoneAndroid
        "steps" -> Icons.Default.DirectionsWalk
        "social" -> Icons.Default.People
        "meditation" -> Icons.Default.SelfImprovement
        else -> Icons.Default.Category
    }

    Card(modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.padding(16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(icon, entry.category, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(32.dp))
            Spacer(Modifier.width(12.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    entry.category.replace("_", " ").replaceFirstChar { it.uppercase() },
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold
                )
                Text(entry.value, style = MaterialTheme.typography.bodyMedium)
                Text(entry.log_date, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                if (entry.notes != null && entry.notes.isNotEmpty()) {
                    Text(entry.notes, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            IconButton(onClick = onDelete) {
                Icon(Icons.Default.Delete, "Delete", tint = MaterialTheme.colorScheme.error)
            }
        }
    }
}

@Composable
private fun AddLifestyleDialog(onDismiss: () -> Unit, onSave: (LifestyleEntryRequest) -> Unit) {
    val categories = listOf("sleep", "water", "exercise", "screen_time", "steps", "social", "meditation", "other")

    var category by remember { mutableStateOf("sleep") }
    var value by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }
    var expandedCategory by remember { mutableStateOf(false) }

    val valuePlaceholder = when (category) {
        "sleep" -> "e.g. 7.5 hours"
        "water" -> "e.g. 8 glasses"
        "screen_time" -> "e.g. 3 hours"
        "steps" -> "e.g. 8500"
        "social" -> "e.g. 45 minutes"
        "meditation" -> "e.g. 20 minutes"
        else -> "Value"
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Log Lifestyle") },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                ExposedDropdownMenuBox(expanded = expandedCategory, onExpandedChange = { expandedCategory = it }) {
                    OutlinedTextField(
                        value = category.replace("_", " ").replaceFirstChar { it.uppercase() },
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Category") },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expandedCategory) },
                        modifier = Modifier.menuAnchor().fillMaxWidth()
                    )
                    ExposedDropdownMenu(expanded = expandedCategory, onDismissRequest = { expandedCategory = false }) {
                        categories.forEach {
                            DropdownMenuItem(
                                text = { Text(it.replace("_", " ").replaceFirstChar { c -> c.uppercase() }) },
                                onClick = { category = it; expandedCategory = false }
                            )
                        }
                    }
                }

                OutlinedTextField(value = value, onValueChange = { value = it }, label = { Text(valuePlaceholder) }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = notes, onValueChange = { notes = it }, label = { Text("Notes") }, modifier = Modifier.fillMaxWidth(), minLines = 2)
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    onSave(LifestyleEntryRequest(
                        log_date = LocalDate.now().format(DateTimeFormatter.ISO_DATE),
                        category = category,
                        value = value,
                        notes = notes.ifBlank { null }
                    ))
                },
                enabled = value.isNotBlank()
            ) { Text("Save") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Cancel") }
        }
    )
}
