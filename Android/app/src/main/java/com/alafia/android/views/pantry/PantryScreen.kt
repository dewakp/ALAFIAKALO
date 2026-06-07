@file:OptIn(ExperimentalMaterial3Api::class)

package com.alafia.android.views.pantry
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.alafia.android.api.ApiClient
import com.alafia.android.models.PantryItem
import com.alafia.android.models.PantryItemCreate
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit
import androidx.navigation.NavHostController

@Composable
fun PantryScreen(navController: NavHostController) {
    var items by remember { mutableStateOf<List<PantryItem>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    var showForm by remember { mutableStateOf(false) }
    var filterLocation by remember { mutableStateOf<String?>(null) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    fun loadItems() {
        scope.launch {
            isLoading = true
            try {
                val all = ApiClient.getApiService().getPantryItems()
                items = if (filterLocation != null) all.filter { it.location == filterLocation } else all
            } catch (e: Exception) {
                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
            }
            isLoading = false
        }
    }

    LaunchedEffect(Unit) { loadItems() }
    LaunchedEffect(filterLocation) { loadItems() }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Pantry & Fridge") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                }
            )
        },
        floatingActionButton = {
            FloatingActionButton(onClick = { showForm = true }) {
                Icon(Icons.Default.Add, "Add Item")
            }
        }
    ) { padding ->
        Column(modifier = Modifier.fillMaxSize().padding(padding)) {
            // Location filter chips
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                FilterChip(
                    selected = filterLocation == null,
                    onClick = { filterLocation = null },
                    label = { Text("All") }
                )
                FilterChip(
                    selected = filterLocation == "refrigerator",
                    onClick = { filterLocation = if (filterLocation == "refrigerator") null else "refrigerator" },
                    label = { Text("Fridge") },
                    leadingIcon = { Icon(Icons.Default.Kitchen, null, Modifier.size(16.dp)) }
                )
                FilterChip(
                    selected = filterLocation == "freezer",
                    onClick = { filterLocation = if (filterLocation == "freezer") null else "freezer" },
                    label = { Text("Freezer") },
                    leadingIcon = { Icon(Icons.Default.AcUnit, null, Modifier.size(16.dp)) }
                )
                FilterChip(
                    selected = filterLocation == "pantry",
                    onClick = { filterLocation = if (filterLocation == "pantry") null else "pantry" },
                    label = { Text("Pantry") },
                    leadingIcon = { Icon(Icons.Default.Inventory2, null, Modifier.size(16.dp)) }
                )
            }

            if (isLoading) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
            } else if (items.isEmpty()) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(Icons.Default.Kitchen, "Empty", modifier = Modifier.size(64.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
                        Spacer(Modifier.height(12.dp))
                        Text("No items", style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text("Tap + to add items from your fridge, freezer, or pantry", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            } else {
                // Group by location
                val grouped = items.groupBy { it.location }
                LazyColumn(
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    listOf("refrigerator" to "Refrigerator", "freezer" to "Freezer", "pantry" to "Pantry").forEach { (key, label) ->
                        val locationItems = grouped[key] ?: emptyList()
                        if (locationItems.isNotEmpty()) {
                            item {
                                Text(
                                    "$label (${locationItems.size})",
                                    style = MaterialTheme.typography.titleSmall,
                                    color = MaterialTheme.colorScheme.primary,
                                    modifier = Modifier.padding(top = 8.dp, bottom = 4.dp)
                                )
                            }
                            items(locationItems, key = { it.id }) { pantryItem ->
                                PantryItemCard(
                                    item = pantryItem,
                                    onDelete = {
                                        scope.launch {
                                            try {
                                                ApiClient.getApiService().deletePantryItem(pantryItem.id)
                                                loadItems()
                                            } catch (e: Exception) {
                                                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                                            }
                                        }
                                    }
                                )
                            }
                        }
                    }

                    // Future feature callout
                    item {
                        Card(
                            modifier = Modifier.fillMaxWidth().padding(top = 16.dp),
                            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer)
                        ) {
                            Row(modifier = Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                                Icon(Icons.Default.ShoppingCart, "Auto-replenish", tint = MaterialTheme.colorScheme.onSecondaryContainer)
                                Spacer(Modifier.width(12.dp))
                                Column {
                                    Text("Auto-Replenish (Coming Soon)", fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
                                    Text(
                                        "Connect to grocery services (Instacart, Kroger, Walmart) for automatic reordering when items run low.",
                                        style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSecondaryContainer.copy(alpha = 0.7f)
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    if (showForm) {
        AddPantryItemDialog(
            onDismiss = { showForm = false },
            onSave = { request ->
                scope.launch {
                    try {
                        ApiClient.getApiService().createPantryItem(request)
                        showForm = false
                        loadItems()
                        Toast.makeText(context, "Item added!", Toast.LENGTH_SHORT).show()
                    } catch (e: Exception) {
                        Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                    }
                }
            }
        )
    }
}

@Composable
private fun PantryItemCard(item: PantryItem, onDelete: () -> Unit) {
    val today = LocalDate.now()
    val expDate = item.expirationDate?.let {
        try { LocalDate.parse(it) } catch (_: Exception) { null }
    }
    val daysUntilExpiry = expDate?.let { d -> ChronoUnit.DAYS.between(today, d) }
    val isExpired = daysUntilExpiry != null && daysUntilExpiry < 0
    val isExpiringSoon = daysUntilExpiry != null && daysUntilExpiry in 0..3

    val locationIcon = when (item.location) {
        "refrigerator" -> Icons.Default.Kitchen
        "freezer" -> Icons.Default.AcUnit
        else -> Icons.Default.Inventory2
    }
    val categoryColor = when (item.category) {
        "produce" -> Color(0xFF4CAF50)
        "dairy" -> Color(0xFF2196F3)
        "meat", "seafood" -> Color(0xFFF44336)
        "frozen" -> Color(0xFF00BCD4)
        "beverages" -> Color(0xFF9C27B0)
        "condiments", "spices" -> Color(0xFFFF9800)
        else -> MaterialTheme.colorScheme.onSurfaceVariant
    }

    val cardColors = when {
        isExpired -> CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer.copy(alpha = 0.3f))
        isExpiringSoon -> CardDefaults.cardColors(containerColor = Color(0xFFFFF3E0))
        else -> CardDefaults.cardColors()
    }

    Card(modifier = Modifier.fillMaxWidth(), colors = cardColors) {
        Row(modifier = Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(locationIcon, item.location, tint = categoryColor, modifier = Modifier.size(28.dp))
            Spacer(Modifier.width(12.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(item.name, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyLarge, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("${item.quantity} ${item.unit}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Surface(color = categoryColor.copy(alpha = 0.15f), shape = MaterialTheme.shapes.small) {
                        Text(
                            item.category.replaceFirstChar { it.uppercase() },
                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                            style = MaterialTheme.typography.labelSmall,
                            color = categoryColor
                        )
                    }
                }
                if (!item.notes.isNullOrEmpty()) {
                    Text(item.notes, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
            }
            Column(horizontalAlignment = Alignment.End) {
                if (isExpired) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Default.Warning, "Expired", tint = MaterialTheme.colorScheme.error, modifier = Modifier.size(14.dp))
                        Spacer(Modifier.width(2.dp))
                        Text("Expired", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.error)
                    }
                } else if (isExpiringSoon) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Default.Warning, "Expiring", tint = Color(0xFFFF9800), modifier = Modifier.size(14.dp))
                        Spacer(Modifier.width(2.dp))
                        Text("Expiring", style = MaterialTheme.typography.labelSmall, color = Color(0xFFFF9800))
                    }
                }
                if (item.expirationDate != null) {
                    Text(item.expirationDate, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                IconButton(onClick = onDelete, modifier = Modifier.size(32.dp)) {
                    Icon(Icons.Default.Delete, "Delete", tint = MaterialTheme.colorScheme.error, modifier = Modifier.size(18.dp))
                }
            }
        }
    }
}

@Composable
private fun AddPantryItemDialog(onDismiss: () -> Unit, onSave: (PantryItemCreate) -> Unit) {
    val categories = listOf("produce", "dairy", "meat", "seafood", "grains", "canned", "frozen", "beverages", "condiments", "snacks", "baking", "spices", "other")
    val units = listOf("pieces", "lbs", "oz", "kg", "g", "liters", "ml", "cups", "gallons", "bags", "boxes", "cans", "bottles")
    val locations = listOf("pantry" to "Pantry", "refrigerator" to "Refrigerator", "freezer" to "Freezer")

    var name by remember { mutableStateOf("") }
    var category by remember { mutableStateOf("other") }
    var quantity by remember { mutableStateOf("1") }
    var unit by remember { mutableStateOf("pieces") }
    var location by remember { mutableStateOf("pantry") }
    var expirationDate by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }
    var expandedCategory by remember { mutableStateOf(false) }
    var expandedUnit by remember { mutableStateOf(false) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Add Pantry Item") },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                OutlinedTextField(value = name, onValueChange = { name = it }, label = { Text("Item Name") }, modifier = Modifier.fillMaxWidth())

                // Category dropdown
                ExposedDropdownMenuBox(expanded = expandedCategory, onExpandedChange = { expandedCategory = it }) {
                    OutlinedTextField(
                        value = category.replaceFirstChar { it.uppercase() },
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Category") },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expandedCategory) },
                        modifier = Modifier.menuAnchor().fillMaxWidth()
                    )
                    ExposedDropdownMenu(expanded = expandedCategory, onDismissRequest = { expandedCategory = false }) {
                        categories.forEach {
                            DropdownMenuItem(
                                text = { Text(it.replaceFirstChar { c -> c.uppercase() }) },
                                onClick = { category = it; expandedCategory = false }
                            )
                        }
                    }
                }

                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        value = quantity,
                        onValueChange = { quantity = it },
                        label = { Text("Qty") },
                        modifier = Modifier.weight(1f)
                    )
                    ExposedDropdownMenuBox(expanded = expandedUnit, onExpandedChange = { expandedUnit = it }, modifier = Modifier.weight(1.5f)) {
                        OutlinedTextField(
                            value = unit,
                            onValueChange = {},
                            readOnly = true,
                            label = { Text("Unit") },
                            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expandedUnit) },
                            modifier = Modifier.menuAnchor().fillMaxWidth()
                        )
                        ExposedDropdownMenu(expanded = expandedUnit, onDismissRequest = { expandedUnit = false }) {
                            units.forEach {
                                DropdownMenuItem(text = { Text(it) }, onClick = { unit = it; expandedUnit = false })
                            }
                        }
                    }
                }

                // Location selector
                Text("Location", style = MaterialTheme.typography.labelMedium)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    locations.forEach { (value, label) ->
                        FilterChip(
                            selected = location == value,
                            onClick = { location = value },
                            label = { Text(label) }
                        )
                    }
                }

                OutlinedTextField(
                    value = expirationDate,
                    onValueChange = { expirationDate = it },
                    label = { Text("Expiration (YYYY-MM-DD)") },
                    modifier = Modifier.fillMaxWidth()
                )
                OutlinedTextField(value = notes, onValueChange = { notes = it }, label = { Text("Notes") }, modifier = Modifier.fillMaxWidth(), minLines = 2)
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    if (name.isNotBlank()) {
                        onSave(PantryItemCreate(
                            name = name,
                            category = category,
                            quantity = quantity.toFloatOrNull() ?: 1f,
                            unit = unit,
                            location = location,
                            expirationDate = expirationDate.ifBlank { null },
                            notes = notes.ifBlank { null }
                        ))
                    }
                },
                enabled = name.isNotBlank()
            ) { Text("Save") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Cancel") }
        }
    )
}
