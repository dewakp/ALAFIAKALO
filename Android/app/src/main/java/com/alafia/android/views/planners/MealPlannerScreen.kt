@file:OptIn(ExperimentalMaterial3Api::class)

package com.alafia.android.views.planners
import com.alafia.android.util.ErrorUtil

import android.widget.Toast
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.alafia.android.api.ApiClient
import com.alafia.android.models.*
import kotlinx.coroutines.launch
import androidx.navigation.NavHostController

private val DIETARY_PATTERNS = listOf("Mediterranean", "DASH", "Plant-Based", "Keto", "Balanced")

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MealPlannerScreen(navController: NavHostController) {
    var plans by remember { mutableStateOf<List<MealPlanResponse>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    var isGenerating by remember { mutableStateOf(false) }
    var showForm by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    // Form fields
    var selectedPattern by remember { mutableStateOf(DIETARY_PATTERNS[0]) }
    var calorieTarget by remember { mutableStateOf("") }
    var allergies by remember { mutableStateOf("") }
    var preferences by remember { mutableStateOf("") }

    fun loadPlans() {
        scope.launch {
            isLoading = true
            try {
                plans = ApiClient.getApiService().getMealPlans()
            } catch (e: Exception) {
                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
            }
            isLoading = false
        }
    }

    LaunchedEffect(Unit) { loadPlans() }

    Scaffold(
        topBar = { TopAppBar(
                title = { Text("Meal Planner") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                }
            ) },
        floatingActionButton = {
            FloatingActionButton(onClick = { showForm = !showForm }) {
                Icon(
                    if (showForm) Icons.Default.Close else Icons.Default.Add,
                    contentDescription = if (showForm) "Close" else "New Plan"
                )
            }
        }
    ) { padding ->
        if (isLoading) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                // ── Generate Form ───────────────────────────────────────
                if (showForm) {
                    item {
                        Card(
                            modifier = Modifier.fillMaxWidth(),
                            elevation = CardDefaults.cardElevation(defaultElevation = 4.dp)
                        ) {
                            Column(modifier = Modifier.padding(16.dp)) {
                                Text("Generate Meal Plan", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                                Spacer(Modifier.height(12.dp))

                                // Dietary pattern dropdown
                                var patternExpanded by remember { mutableStateOf(false) }
                                ExposedDropdownMenuBox(
                                    expanded = patternExpanded,
                                    onExpandedChange = { patternExpanded = it }
                                ) {
                                    OutlinedTextField(
                                        value = selectedPattern,
                                        onValueChange = {},
                                        readOnly = true,
                                        label = { Text("Dietary Pattern") },
                                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = patternExpanded) },
                                        modifier = Modifier.fillMaxWidth().menuAnchor()
                                    )
                                    ExposedDropdownMenu(
                                        expanded = patternExpanded,
                                        onDismissRequest = { patternExpanded = false }
                                    ) {
                                        DIETARY_PATTERNS.forEach { pattern ->
                                            DropdownMenuItem(
                                                text = { Text(pattern) },
                                                onClick = {
                                                    selectedPattern = pattern
                                                    patternExpanded = false
                                                }
                                            )
                                        }
                                    }
                                }

                                Spacer(Modifier.height(8.dp))

                                OutlinedTextField(
                                    value = calorieTarget,
                                    onValueChange = { calorieTarget = it.filter { ch -> ch.isDigit() } },
                                    label = { Text("Daily Calorie Target") },
                                    placeholder = { Text("e.g. 2000") },
                                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                                    modifier = Modifier.fillMaxWidth()
                                )

                                Spacer(Modifier.height(8.dp))

                                OutlinedTextField(
                                    value = allergies,
                                    onValueChange = { allergies = it },
                                    label = { Text("Allergies") },
                                    placeholder = { Text("e.g. nuts, dairy") },
                                    modifier = Modifier.fillMaxWidth()
                                )

                                Spacer(Modifier.height(8.dp))

                                OutlinedTextField(
                                    value = preferences,
                                    onValueChange = { preferences = it },
                                    label = { Text("Preferences") },
                                    placeholder = { Text("e.g. high protein, low sodium") },
                                    modifier = Modifier.fillMaxWidth()
                                )

                                Spacer(Modifier.height(12.dp))

                                Button(
                                    onClick = {
                                        scope.launch {
                                            isGenerating = true
                                            try {
                                                val request = MealPlanRequest(
                                                    dietaryPattern = selectedPattern,
                                                    dailyCalorieTarget = calorieTarget.toIntOrNull(),
                                                    allergies = allergies.ifBlank { null },
                                                    preferences = preferences.ifBlank { null }
                                                )
                                                ApiClient.getApiService().createMealPlan(request)
                                                showForm = false
                                                calorieTarget = ""
                                                allergies = ""
                                                preferences = ""
                                                loadPlans()
                                                Toast.makeText(context, "Meal plan created!", Toast.LENGTH_SHORT).show()
                                            } catch (e: Exception) {
                                                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                                            }
                                            isGenerating = false
                                        }
                                    },
                                    modifier = Modifier.fillMaxWidth(),
                                    enabled = !isGenerating
                                ) {
                                    if (isGenerating) {
                                        CircularProgressIndicator(modifier = Modifier.size(20.dp), strokeWidth = 2.dp)
                                        Spacer(Modifier.width(8.dp))
                                    }
                                    Text("Generate Plan")
                                }
                            }
                        }
                    }
                }

                // ── Existing Plans ──────────────────────────────────────
                if (plans.isEmpty()) {
                    item {
                        Box(modifier = Modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) {
                            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                Icon(Icons.Default.RestaurantMenu, "No plans", modifier = Modifier.size(64.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
                                Spacer(Modifier.height(12.dp))
                                Text("No meal plans yet", style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                Text("Tap + to generate a plan", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    }
                } else {
                    item {
                        Text("Your Meal Plans", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    }
                    items(plans, key = { it.id }) { plan ->
                        MealPlanCard(plan = plan)
                    }
                }
            }
        }
    }
}

@Composable
private fun MealPlanCard(plan: MealPlanResponse) {
    var expanded by remember { mutableStateOf(false) }
    var showShoppingList by remember { mutableStateOf(false) }

    Card(
        modifier = Modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(plan.planName, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                    if (plan.dietaryPattern != null) {
                        Text(plan.dietaryPattern, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.primary)
                    }
                    if (plan.totalDailyCalories != null) {
                        Text("${plan.totalDailyCalories} cal/day", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
                IconButton(onClick = { expanded = !expanded }) {
                    Icon(
                        if (expanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                        contentDescription = if (expanded) "Collapse" else "Expand"
                    )
                }
            }

            AnimatedVisibility(visible = expanded) {
                Column(modifier = Modifier.padding(top = 8.dp)) {
                    if (plan.advice != null) {
                        Text(plan.advice, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Spacer(Modifier.height(8.dp))
                    }

                    // Days
                    plan.planData?.entries?.sortedBy { it.key }?.forEach { (dayKey, dayMeals) ->
                        DayMealsSection(dayLabel = dayKey, meals = dayMeals)
                        Spacer(Modifier.height(8.dp))
                    }

                    // Shopping list toggle
                    if (!plan.shoppingList.isNullOrEmpty()) {
                        HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))
                        TextButton(onClick = { showShoppingList = !showShoppingList }) {
                            Icon(Icons.Default.ShoppingCart, contentDescription = null, modifier = Modifier.size(18.dp))
                            Spacer(Modifier.width(4.dp))
                            Text(if (showShoppingList) "Hide Shopping List" else "Show Shopping List")
                        }
                        AnimatedVisibility(visible = showShoppingList) {
                            ShoppingListSection(items = plan.shoppingList)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun DayMealsSection(dayLabel: String, meals: DayMeals) {
    val displayLabel = dayLabel.replaceFirstChar { it.uppercase() }.replace("_", " ")

    Surface(
        shape = RoundedCornerShape(8.dp),
        color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(displayLabel, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(4.dp))

            @Composable
            fun MealSection(label: String, items: List<MealItem>?) {
                if (!items.isNullOrEmpty()) {
                    Text(label, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.SemiBold, color = MaterialTheme.colorScheme.primary)
                    items.forEach { meal ->
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(start = 8.dp, top = 2.dp),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text("• ${meal.name}", style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(1f))
                            if (meal.calories != null) {
                                Text("${meal.calories} cal", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    }
                    Spacer(Modifier.height(4.dp))
                }
            }

            MealSection("Breakfast", meals.breakfast)
            MealSection("Lunch", meals.lunch)
            MealSection("Dinner", meals.dinner)
            MealSection("Snacks", meals.snacks)
        }
    }
}

@Composable
private fun ShoppingListSection(items: List<String>) {
    Column(modifier = Modifier.padding(start = 8.dp)) {
        items.forEach { item ->
            var checked by remember { mutableStateOf(false) }
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.padding(vertical = 2.dp)
            ) {
                Checkbox(
                    checked = checked,
                    onCheckedChange = { checked = it },
                    modifier = Modifier.size(24.dp)
                )
                Spacer(Modifier.width(8.dp))
                Text(
                    item,
                    style = MaterialTheme.typography.bodySmall,
                    color = if (checked) MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.onSurface
                )
            }
        }
    }
}
