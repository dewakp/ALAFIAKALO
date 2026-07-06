@file:OptIn(ExperimentalMaterial3Api::class)

package com.alafia.android.views.fda
import com.alafia.android.util.ErrorUtil

import android.widget.Toast
import androidx.compose.animation.AnimatedVisibility
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
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.alafia.android.api.ApiClient
import com.alafia.android.models.FDARecallItem
import com.alafia.android.models.FDARecallResponse
import kotlinx.coroutines.launch
import androidx.navigation.NavHostController

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FDARecallsScreen(navController: NavHostController) {
    var recallResponse by remember { mutableStateOf<FDARecallResponse?>(null) }
    var isLoading by remember { mutableStateOf(true) }
    var searchQuery by remember { mutableStateOf("") }
    var kind by remember { mutableStateOf("both") }   // food | drug | both
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    fun loadRecent() {
        scope.launch {
            isLoading = true
            try {
                recallResponse = ApiClient.getApiService().getRecentFDARecalls(kind = kind)
            } catch (e: Exception) {
                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
            }
            isLoading = false
        }
    }

    fun search(query: String) {
        scope.launch {
            isLoading = true
            try {
                recallResponse = ApiClient.getApiService().searchFDARecalls(searchTerm = query, kind = kind)
            } catch (e: Exception) {
                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
            }
            isLoading = false
        }
    }

    LaunchedEffect(kind) { if (searchQuery.isNotBlank()) search(searchQuery) else loadRecent() }

    Scaffold(
        topBar = { TopAppBar(
                title = { Text("FDA Recalls") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                }
            ) }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
        ) {
            // Search bar
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                OutlinedTextField(
                    value = searchQuery,
                    onValueChange = { searchQuery = it },
                    label = { Text("Search recalls") },
                    modifier = Modifier.weight(1f),
                    singleLine = true,
                    trailingIcon = {
                        if (searchQuery.isNotEmpty()) {
                            IconButton(onClick = {
                                searchQuery = ""
                                loadRecent()
                            }) {
                                Icon(Icons.Default.Clear, "Clear")
                            }
                        }
                    }
                )
                Spacer(Modifier.width(8.dp))
                Button(
                    onClick = {
                        if (searchQuery.isNotBlank()) search(searchQuery) else loadRecent()
                    },
                    enabled = !isLoading
                ) {
                    Icon(Icons.Default.Search, "Search")
                    Spacer(Modifier.width(4.dp))
                    Text("Search")
                }
            }

            // Food / Drug / Both filter
            SingleChoiceSegmentedButtonRow(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 4.dp)
            ) {
                listOf("both" to "Food & Drug", "food" to "Food", "drug" to "Drug")
                    .forEachIndexed { i, (tag, label) ->
                        SegmentedButton(
                            selected = kind == tag,
                            onClick = { kind = tag },
                            shape = SegmentedButtonDefaults.itemShape(index = i, count = 3)
                        ) { Text(label) }
                    }
            }

            // Total count
            recallResponse?.let { resp ->
                Text(
                    text = "${resp.total} result${if (resp.total != 1) "s" else ""} found",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp)
                )
            }

            // Content
            if (isLoading) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
            } else if (recallResponse == null || recallResponse!!.results.isEmpty()) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(
                            Icons.Default.Warning,
                            "No recalls",
                            modifier = Modifier.size(64.dp),
                            tint = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Spacer(Modifier.height(12.dp))
                        Text(
                            "No recalls found",
                            style = MaterialTheme.typography.titleMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            "Try a different search term",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    items(recallResponse!!.results, key = { it.recallNumber ?: it.hashCode() }) { item ->
                        FDARecallCard(item)
                    }
                }
            }
        }
    }
}

@Composable
private fun FDARecallCard(item: FDARecallItem) {
    var expanded by remember { mutableStateOf(false) }

    val classificationColor = when {
        item.classification?.contains("I", ignoreCase = true) == true &&
                item.classification.contains("II", ignoreCase = true).not() &&
                item.classification.contains("III", ignoreCase = true).not() -> Color(0xFFD32F2F) // Class I - red
        item.classification?.contains("III", ignoreCase = true) == true -> Color(0xFFFBC02D) // Class III - yellow
        item.classification?.contains("II", ignoreCase = true) == true -> Color(0xFFFF9800) // Class II - orange
        else -> MaterialTheme.colorScheme.surfaceVariant
    }

    val classificationLabel = when {
        item.classification?.contains("I", ignoreCase = true) == true &&
                item.classification.contains("II", ignoreCase = true).not() &&
                item.classification.contains("III", ignoreCase = true).not() -> "Dangerous"
        item.classification?.contains("III", ignoreCase = true) == true -> "Unlikely harm"
        item.classification?.contains("II", ignoreCase = true) == true -> "Less severe"
        else -> ""
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            // Product description
            Text(
                text = item.productDescription ?: "Unknown Product",
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold,
                maxLines = if (expanded) Int.MAX_VALUE else 2,
                overflow = TextOverflow.Ellipsis
            )

            Spacer(Modifier.height(8.dp))

            // Type + classification + source badges
            Row(verticalAlignment = Alignment.CenterVertically) {
                item.productType?.let { type ->
                    val typeColor = if (type == "drug") Color(0xFF7B1FA2) else Color(0xFF2E7D32)
                    Surface(color = typeColor.copy(alpha = 0.15f), shape = MaterialTheme.shapes.small) {
                        Text(
                            text = type.replaceFirstChar { it.uppercase() },
                            color = typeColor,
                            style = MaterialTheme.typography.labelSmall,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                        )
                    }
                    Spacer(Modifier.width(6.dp))
                }
                item.classification?.let { classification ->
                    Surface(
                        color = classificationColor.copy(alpha = 0.15f),
                        shape = MaterialTheme.shapes.small
                    ) {
                        Text(
                            text = "$classification${if (classificationLabel.isNotEmpty()) " — $classificationLabel" else ""}",
                            color = classificationColor,
                            style = MaterialTheme.typography.labelSmall,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                        )
                    }
                    Spacer(Modifier.width(6.dp))
                }
                item.source?.let { source ->
                    Text(
                        text = source,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
            Spacer(Modifier.height(8.dp))

            // Reason
            item.reason?.let { reason ->
                Text(
                    text = reason,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = if (expanded) Int.MAX_VALUE else 3,
                    overflow = TextOverflow.Ellipsis
                )
                Spacer(Modifier.height(8.dp))
            }

            // Recalling firm & location
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    Icons.Default.Business,
                    contentDescription = null,
                    modifier = Modifier.size(16.dp),
                    tint = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Spacer(Modifier.width(4.dp))
                Text(
                    text = buildString {
                        append(item.recallingFirm ?: "Unknown Firm")
                        val location = listOfNotNull(item.city, item.state, item.country)
                            .joinToString(", ")
                        if (location.isNotEmpty()) append(" — $location")
                    },
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            Spacer(Modifier.height(4.dp))

            // Date and status
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                (item.recallInitiationDate ?: item.reportDate)?.let { date ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(
                            Icons.Default.CalendarToday,
                            contentDescription = null,
                            modifier = Modifier.size(14.dp),
                            tint = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Spacer(Modifier.width(4.dp))
                        Text(
                            text = date,
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
                item.status?.let { status ->
                    Surface(
                        color = MaterialTheme.colorScheme.secondaryContainer,
                        shape = MaterialTheme.shapes.small
                    ) {
                        Text(
                            text = status,
                            style = MaterialTheme.typography.labelSmall,
                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                        )
                    }
                }
            }

            // Geographic coverage
            val coverage = when {
                item.nationwide -> "Coverage: Nationwide (US)"
                item.states.isNotEmpty() -> "Coverage: ${item.states.joinToString(", ")}"
                else -> null
            }
            coverage?.let {
                Spacer(Modifier.height(4.dp))
                Text(it, style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            if (item.countries.size > 1) {
                Text("Countries: ${item.countries.joinToString(", ")}",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }

            // Expandable distribution pattern
            item.distribution?.let { pattern ->
                Spacer(Modifier.height(4.dp))
                TextButton(
                    onClick = { expanded = !expanded },
                    contentPadding = PaddingValues(0.dp)
                ) {
                    Icon(
                        if (expanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                        contentDescription = null,
                        modifier = Modifier.size(18.dp)
                    )
                    Spacer(Modifier.width(4.dp))
                    Text(
                        if (expanded) "Hide distribution" else "Show distribution",
                        style = MaterialTheme.typography.labelSmall
                    )
                }
                AnimatedVisibility(visible = expanded) {
                    Surface(
                        color = MaterialTheme.colorScheme.surfaceVariant,
                        shape = MaterialTheme.shapes.small,
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text(
                            text = pattern,
                            style = MaterialTheme.typography.bodySmall,
                            modifier = Modifier.padding(8.dp)
                        )
                    }
                }
            }
        }
    }
}
