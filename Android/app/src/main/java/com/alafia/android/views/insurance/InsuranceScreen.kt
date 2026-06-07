@file:OptIn(ExperimentalMaterial3Api::class)

package com.alafia.android.views.insurance

import androidx.compose.foundation.clickable
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.alafia.android.api.ApiClient
import com.alafia.android.models.InsuranceCountry
import com.alafia.android.models.InsurancePlan
import com.alafia.android.models.InsuranceProvider
import com.alafia.android.schemas.InsuranceCreateRequest
import kotlinx.coroutines.launch
import androidx.navigation.NavHostController

data class RegionInfo(val code: String, val name: String, val emoji: String)

private val REGIONS = listOf(
    RegionInfo("north_america", "North America", "🌎"),
    RegionInfo("europe", "Europe", "🌍"),
    RegionInfo("south_asia", "South Asia", "🌏"),
    RegionInfo("africa", "Africa", "🌍"),
    RegionInfo("middle_east", "Middle East", "🌍"),
)

private val PLAN_TYPES = listOf("HMO", "PPO", "EPO", "POS", "HDHP", "Indemnity", "Government", "Universal", "Other")

@Composable
fun InsuranceScreen(navController: NavHostController) {
    val scope = rememberCoroutineScope()
    var plans by remember { mutableStateOf<List<InsurancePlan>>(emptyList()) }
    var regionCountries by remember { mutableStateOf<Map<String, List<InsuranceCountry>>>(emptyMap()) }
    var providers by remember { mutableStateOf<List<InsuranceProvider>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    var showForm by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    // Form state
    var selectedRegion by remember { mutableStateOf("") }
    var selectedCountryCode by remember { mutableStateOf("") }
    var selectedCountryName by remember { mutableStateOf("") }
    var selectedProviderCode by remember { mutableStateOf("") }
    var selectedProviderName by remember { mutableStateOf("") }
    var policyNumber by remember { mutableStateOf("") }
    var groupNumber by remember { mutableStateOf("") }
    var memberId by remember { mutableStateOf("") }
    var planName by remember { mutableStateOf("") }
    var planType by remember { mutableStateOf("") }
    var isPrimary by remember { mutableStateOf(false) }
    var notes by remember { mutableStateOf("") }

    // Dropdown expansion
    var regionExpanded by remember { mutableStateOf(false) }
    var countryExpanded by remember { mutableStateOf(false) }
    var providerExpanded by remember { mutableStateOf(false) }
    var planTypeExpanded by remember { mutableStateOf(false) }

    fun resetForm() {
        selectedRegion = ""; selectedCountryCode = ""; selectedCountryName = ""
        selectedProviderCode = ""; selectedProviderName = ""
        policyNumber = ""; groupNumber = ""; memberId = ""
        planName = ""; planType = ""; isPrimary = false; notes = ""
        providers = emptyList()
    }

    fun loadPlans() {
        scope.launch {
            try {
                plans = ApiClient.getApiService().getInsurancePlans()
                isLoading = false
            } catch (e: Exception) {
                error = e.message; isLoading = false
            }
        }
    }

    fun loadRegions() {
        scope.launch {
            try {
                regionCountries = ApiClient.getApiService().getInsuranceRegions()
            } catch (_: Exception) {}
        }
    }

    LaunchedEffect(Unit) {
        loadRegions()
        loadPlans()
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Insurance Plans") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    IconButton(onClick = { showForm = !showForm; if (!showForm) resetForm() }) {
                        Icon(
                            if (showForm) Icons.Default.Close else Icons.Default.Add,
                            contentDescription = if (showForm) "Cancel" else "Add Plan"
                        )
                    }
                }
            )
        }
    ) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
            contentPadding = PaddingValues(vertical = 16.dp)
        ) {
            // Add form
            if (showForm) {
                item {
                    Card(modifier = Modifier.fillMaxWidth()) {
                        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                            Text("Add Insurance Plan", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)

                            // Region dropdown
                            ExposedDropdownMenuBox(expanded = regionExpanded, onExpandedChange = { regionExpanded = it }) {
                                OutlinedTextField(
                                    value = REGIONS.find { it.code == selectedRegion }?.let { "${it.emoji} ${it.name}" } ?: "",
                                    onValueChange = {},
                                    readOnly = true,
                                    label = { Text("Region *") },
                                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = regionExpanded) },
                                    modifier = Modifier.menuAnchor().fillMaxWidth()
                                )
                                ExposedDropdownMenu(expanded = regionExpanded, onDismissRequest = { regionExpanded = false }) {
                                    REGIONS.forEach { r ->
                                        DropdownMenuItem(
                                            text = { Text("${r.emoji} ${r.name}") },
                                            onClick = {
                                                selectedRegion = r.code
                                                selectedCountryCode = ""; selectedCountryName = ""
                                                selectedProviderCode = ""; selectedProviderName = ""
                                                providers = emptyList()
                                                regionExpanded = false
                                            }
                                        )
                                    }
                                }
                            }

                            // Country dropdown
                            val countries = regionCountries[selectedRegion] ?: emptyList()
                            ExposedDropdownMenuBox(expanded = countryExpanded, onExpandedChange = { if (selectedRegion.isNotEmpty()) countryExpanded = it }) {
                                OutlinedTextField(
                                    value = selectedCountryName,
                                    onValueChange = {},
                                    readOnly = true,
                                    label = { Text("Country *") },
                                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = countryExpanded) },
                                    modifier = Modifier.menuAnchor().fillMaxWidth(),
                                    enabled = selectedRegion.isNotEmpty()
                                )
                                ExposedDropdownMenu(expanded = countryExpanded, onDismissRequest = { countryExpanded = false }) {
                                    countries.forEach { c ->
                                        DropdownMenuItem(
                                            text = { Text(c.name) },
                                            onClick = {
                                                selectedCountryCode = c.code; selectedCountryName = c.name
                                                selectedProviderCode = ""; selectedProviderName = ""
                                                countryExpanded = false
                                                scope.launch {
                                                    try { providers = ApiClient.getApiService().getInsuranceProviders(c.code) }
                                                    catch (_: Exception) { providers = emptyList() }
                                                }
                                            }
                                        )
                                    }
                                }
                            }

                            // Provider dropdown
                            ExposedDropdownMenuBox(expanded = providerExpanded, onExpandedChange = { if (selectedCountryCode.isNotEmpty()) providerExpanded = it }) {
                                OutlinedTextField(
                                    value = selectedProviderName,
                                    onValueChange = {},
                                    readOnly = true,
                                    label = { Text("Insurance Provider *") },
                                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = providerExpanded) },
                                    modifier = Modifier.menuAnchor().fillMaxWidth(),
                                    enabled = selectedCountryCode.isNotEmpty()
                                )
                                ExposedDropdownMenu(expanded = providerExpanded, onDismissRequest = { providerExpanded = false }) {
                                    providers.forEach { p ->
                                        DropdownMenuItem(
                                            text = { Text(p.name) },
                                            onClick = {
                                                selectedProviderCode = p.code; selectedProviderName = p.name
                                                providerExpanded = false
                                            }
                                        )
                                    }
                                }
                            }

                            // Policy details
                            OutlinedTextField(value = policyNumber, onValueChange = { policyNumber = it }, label = { Text("Policy / ID Number") }, modifier = Modifier.fillMaxWidth())
                            OutlinedTextField(value = groupNumber, onValueChange = { groupNumber = it }, label = { Text("Group Number") }, modifier = Modifier.fillMaxWidth())
                            OutlinedTextField(value = memberId, onValueChange = { memberId = it }, label = { Text("Member ID") }, modifier = Modifier.fillMaxWidth())
                            OutlinedTextField(value = planName, onValueChange = { planName = it }, label = { Text("Plan Name") }, modifier = Modifier.fillMaxWidth())

                            // Plan type dropdown
                            ExposedDropdownMenuBox(expanded = planTypeExpanded, onExpandedChange = { planTypeExpanded = it }) {
                                OutlinedTextField(
                                    value = planType,
                                    onValueChange = {},
                                    readOnly = true,
                                    label = { Text("Plan Type") },
                                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = planTypeExpanded) },
                                    modifier = Modifier.menuAnchor().fillMaxWidth()
                                )
                                ExposedDropdownMenu(expanded = planTypeExpanded, onDismissRequest = { planTypeExpanded = false }) {
                                    PLAN_TYPES.forEach { t ->
                                        DropdownMenuItem(text = { Text(t) }, onClick = { planType = t; planTypeExpanded = false })
                                    }
                                }
                            }

                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Checkbox(checked = isPrimary, onCheckedChange = { isPrimary = it })
                                Text("Set as Primary Plan")
                            }

                            OutlinedTextField(value = notes, onValueChange = { notes = it }, label = { Text("Notes") }, modifier = Modifier.fillMaxWidth(), minLines = 2)

                            Button(
                                onClick = {
                                    scope.launch {
                                        try {
                                            ApiClient.getApiService().createInsurancePlan(
                                                InsuranceCreateRequest(
                                                    region = selectedRegion,
                                                    countryCode = selectedCountryCode,
                                                    countryName = selectedCountryName,
                                                    providerCode = selectedProviderCode,
                                                    providerName = selectedProviderName,
                                                    policyNumber = policyNumber.ifBlank { null },
                                                    groupNumber = groupNumber.ifBlank { null },
                                                    memberId = memberId.ifBlank { null },
                                                    planName = planName.ifBlank { null },
                                                    planType = planType.ifBlank { null },
                                                    isPrimary = isPrimary,
                                                    notes = notes.ifBlank { null }
                                                )
                                            )
                                            showForm = false; resetForm(); loadPlans()
                                        } catch (e: Exception) {
                                            error = e.message
                                        }
                                    }
                                },
                                modifier = Modifier.fillMaxWidth(),
                                enabled = selectedRegion.isNotEmpty() && selectedCountryCode.isNotEmpty() && selectedProviderCode.isNotEmpty()
                            ) {
                                Text("Save Plan")
                            }
                        }
                    }
                }
            }

            // Plans list
            if (isLoading) {
                item {
                    Box(modifier = Modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator()
                    }
                }
            } else if (plans.isEmpty() && !showForm) {
                item {
                    Card(modifier = Modifier.fillMaxWidth()) {
                        Column(modifier = Modifier.padding(32.dp).fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
                            Icon(Icons.Default.Shield, contentDescription = null, modifier = Modifier.size(48.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
                            Spacer(modifier = Modifier.height(16.dp))
                            Text("No Insurance Plans", style = MaterialTheme.typography.titleMedium)
                            Text("Tap + to add plans from any supported country", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            } else {
                val active = plans.filter { it.isActive }
                val inactive = plans.filter { !it.isActive }

                if (active.isNotEmpty()) {
                    item {
                        Text("Active Plans (${active.size})", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                    }
                    items(active, key = { it.id }) { plan ->
                        InsurancePlanCard(
                            plan = plan,
                            onSetPrimary = {
                                scope.launch {
                                    try { ApiClient.getApiService().setInsurancePrimary(plan.id); loadPlans() }
                                    catch (_: Exception) {}
                                }
                            },
                            onDelete = {
                                scope.launch {
                                    try { ApiClient.getApiService().deleteInsurancePlan(plan.id); loadPlans() }
                                    catch (_: Exception) {}
                                }
                            }
                        )
                    }
                }

                if (inactive.isNotEmpty()) {
                    item {
                        Text("Inactive Plans (${inactive.size})", style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    items(inactive, key = { it.id }) { plan ->
                        InsurancePlanCard(
                            plan = plan,
                            onSetPrimary = {},
                            onDelete = {
                                scope.launch {
                                    try { ApiClient.getApiService().deleteInsurancePlan(plan.id); loadPlans() }
                                    catch (_: Exception) {}
                                }
                            }
                        )
                    }
                }
            }

            error?.let {
                item {
                    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer)) {
                        Text(it, modifier = Modifier.padding(12.dp), color = MaterialTheme.colorScheme.onErrorContainer)
                    }
                }
            }
        }
    }
}

@Composable
fun InsurancePlanCard(plan: InsurancePlan, onSetPrimary: () -> Unit, onDelete: () -> Unit) {
    var expanded by remember { mutableStateOf(false) }

    Card(modifier = Modifier.fillMaxWidth().clickable { expanded = !expanded }) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(modifier = Modifier.weight(1f)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(plan.providerName, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                        if (plan.isPrimary) {
                            AssistChip(
                                onClick = {},
                                label = { Text("PRIMARY", style = MaterialTheme.typography.labelSmall) },
                                leadingIcon = { Icon(Icons.Default.Star, null, modifier = Modifier.size(14.dp)) },
                                colors = AssistChipDefaults.assistChipColors(
                                    containerColor = Color(0xFFFFF3E0),
                                    labelColor = Color(0xFFE65100),
                                    leadingIconContentColor = Color(0xFFE65100)
                                )
                            )
                        }
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        Text("🌍 ${plan.countryName}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        plan.planType?.let {
                            Text(it, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary)
                        }
                        plan.policyNumber?.let {
                            Text("# $it", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
                Row {
                    if (!plan.isPrimary && plan.isActive) {
                        IconButton(onClick = onSetPrimary) {
                            Icon(Icons.Default.Star, contentDescription = "Set Primary", tint = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                    IconButton(onClick = onDelete) {
                        Icon(Icons.Default.Delete, contentDescription = "Delete", tint = MaterialTheme.colorScheme.error)
                    }
                }
            }

            if (expanded) {
                HorizontalDivider(modifier = Modifier.padding(vertical = 8.dp))
                val details = listOfNotNull(
                    plan.planName?.let { "Plan" to it },
                    plan.groupNumber?.let { "Group" to it },
                    plan.memberId?.let { "Member ID" to it },
                    plan.coverageStart?.let { "Coverage Start" to it },
                    plan.coverageEnd?.let { "Coverage End" to it },
                    plan.subscriberName?.let { "Subscriber" to it },
                    plan.subscriberRelationship?.let { "Relationship" to it },
                    plan.insurancePhone?.let { "Phone" to it },
                    plan.notes?.let { "Notes" to it }
                )
                details.forEach { (label, value) ->
                    Row(modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
                        Text(label, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.width(120.dp))
                        Text(value, style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.Medium)
                    }
                }
            }
        }
    }
}
