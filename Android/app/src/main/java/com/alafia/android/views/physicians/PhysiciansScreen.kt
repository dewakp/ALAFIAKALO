package com.alafia.android.views.physicians
import com.alafia.android.util.ErrorUtil

import android.widget.Toast
import androidx.compose.foundation.clickable
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
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.alafia.android.api.ApiClient
import com.alafia.android.models.*
import com.alafia.android.schemas.*
import kotlinx.coroutines.launch
import androidx.navigation.NavHostController

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PhysiciansScreen(navController: NavHostController) {
    var physicians by remember { mutableStateOf<List<Physician>>(emptyList()) }
    var savedPhysicians by remember { mutableStateOf<List<SavedPhysician>>(emptyList()) }
    var specialtyCategories by remember { mutableStateOf<Map<String, List<String>>>(emptyMap()) }
    var isLoading by remember { mutableStateOf(true) }
    var selectedTab by remember { mutableIntStateOf(0) }

    // Search / filters
    var searchQuery by remember { mutableStateOf("") }
    var filterSpecialty by remember { mutableStateOf("") }
    var filterCity by remember { mutableStateOf("") }
    var showFilters by remember { mutableStateOf(false) }

    // Dialogs
    var showAddForm by remember { mutableStateOf(false) }
    var selectedPhysician by remember { mutableStateOf<Physician?>(null) }
    var showSaveDialog by remember { mutableStateOf<Physician?>(null) }
    var showReviewDialog by remember { mutableStateOf<Physician?>(null) }

    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val savedIds = savedPhysicians.map { it.physicianId }.toSet()

    fun loadAll() {
        scope.launch {
            isLoading = true
            try {
                physicians = ApiClient.getApiService().getPhysicians()
                savedPhysicians = ApiClient.getApiService().getSavedPhysicians()
                specialtyCategories = ApiClient.getApiService().getPhysicianSpecialties().categories
            } catch (e: Exception) {
                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
            }
            isLoading = false
        }
    }

    fun search() {
        scope.launch {
            isLoading = true
            try {
                physicians = ApiClient.getApiService().getPhysicians(
                    q = searchQuery.ifBlank { null },
                    specialty = filterSpecialty.ifBlank { null },
                    city = filterCity.ifBlank { null }
                )
            } catch (e: Exception) {
                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
            }
            isLoading = false
        }
    }

    LaunchedEffect(Unit) { loadAll() }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Physician Directory") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                }
            )
        },
        floatingActionButton = {
            FloatingActionButton(onClick = { showAddForm = true }) {
                Icon(Icons.Default.Add, "Add Physician")
            }
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
        ) {
            // ── Tab Selector ──
            TabRow(selectedTabIndex = selectedTab) {
                Tab(selected = selectedTab == 0, onClick = { selectedTab = 0 },
                    text = { Text("Directory") })
                Tab(selected = selectedTab == 1, onClick = { selectedTab = 1 },
                    text = { Text("Saved (${savedPhysicians.size})") })
            }

            when (selectedTab) {
                // ── DIRECTORY TAB ──
                0 -> {
                    // Search bar
                    OutlinedTextField(
                        value = searchQuery,
                        onValueChange = { searchQuery = it },
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 16.dp, vertical = 8.dp),
                        placeholder = { Text("Search physicians...") },
                        leadingIcon = { Icon(Icons.Default.Search, null) },
                        trailingIcon = {
                            Row {
                                IconButton(onClick = { showFilters = !showFilters }) {
                                    Icon(Icons.Default.FilterList, "Filters")
                                }
                                IconButton(onClick = { search() }) {
                                    Icon(Icons.Default.Search, "Search")
                                }
                            }
                        },
                        singleLine = true
                    )

                    if (showFilters) {
                        Card(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 16.dp, vertical = 4.dp)
                        ) {
                            Column(modifier = Modifier.padding(12.dp)) {
                                // Specialty dropdown
                                val allSpecs = specialtyCategories.values.flatten().sorted()
                                var specExpanded by remember { mutableStateOf(false) }
                                ExposedDropdownMenuBox(
                                    expanded = specExpanded,
                                    onExpandedChange = { specExpanded = !specExpanded }
                                ) {
                                    OutlinedTextField(
                                        value = filterSpecialty.ifBlank { "All Specialties" },
                                        onValueChange = {},
                                        readOnly = true,
                                        modifier = Modifier.menuAnchor().fillMaxWidth(),
                                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(specExpanded) },
                                        label = { Text("Specialty") }
                                    )
                                    ExposedDropdownMenu(expanded = specExpanded, onDismissRequest = { specExpanded = false }) {
                                        DropdownMenuItem(text = { Text("All Specialties") }, onClick = { filterSpecialty = ""; specExpanded = false })
                                        allSpecs.forEach { spec ->
                                            DropdownMenuItem(text = { Text(spec) }, onClick = { filterSpecialty = spec; specExpanded = false })
                                        }
                                    }
                                }
                                Spacer(Modifier.height(8.dp))
                                OutlinedTextField(
                                    value = filterCity,
                                    onValueChange = { filterCity = it },
                                    modifier = Modifier.fillMaxWidth(),
                                    label = { Text("City") },
                                    singleLine = true
                                )
                                Spacer(Modifier.height(8.dp))
                                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    OutlinedButton(onClick = { filterSpecialty = ""; filterCity = ""; searchQuery = ""; loadAll() }) {
                                        Text("Clear")
                                    }
                                    Button(onClick = { search() }) { Text("Apply") }
                                }
                            }
                        }
                    }

                    if (isLoading) {
                        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                            CircularProgressIndicator()
                        }
                    } else if (physicians.isEmpty()) {
                        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                Icon(Icons.Default.LocalHospital, null, modifier = Modifier.size(64.dp),
                                    tint = MaterialTheme.colorScheme.onSurfaceVariant)
                                Spacer(Modifier.height(12.dp))
                                Text("No physicians found", style = MaterialTheme.typography.titleMedium)
                                Text("Tap + to add one", style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    } else {
                        LazyColumn(
                            contentPadding = PaddingValues(16.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            items(physicians, key = { it.id }) { p ->
                                PhysicianCard(
                                    physician = p,
                                    isSaved = savedIds.contains(p.id),
                                    onClick = { selectedPhysician = p },
                                    onSave = { showSaveDialog = p },
                                    onUnsave = {
                                        val s = savedPhysicians.find { it.physicianId == p.id }
                                        if (s != null) {
                                            scope.launch {
                                                try {
                                                    ApiClient.getApiService().unsavePhysician(s.id)
                                                    loadAll()
                                                } catch (e: Exception) {
                                                    Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                                                }
                                            }
                                        }
                                    },
                                    onReview = { showReviewDialog = p },
                                    onDelete = {
                                        scope.launch {
                                            try {
                                                ApiClient.getApiService().deletePhysician(p.id)
                                                loadAll()
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

                // ── SAVED TAB ──
                1 -> {
                    if (savedPhysicians.isEmpty()) {
                        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                Icon(Icons.Default.FavoriteBorder, null, modifier = Modifier.size(64.dp),
                                    tint = MaterialTheme.colorScheme.onSurfaceVariant)
                                Spacer(Modifier.height(12.dp))
                                Text("No saved physicians", style = MaterialTheme.typography.titleMedium)
                                Text("Bookmark physicians from the directory", style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    } else {
                        LazyColumn(
                            contentPadding = PaddingValues(16.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            items(savedPhysicians, key = { it.id }) { saved ->
                                SavedPhysicianCard(
                                    saved = saved,
                                    onClick = { saved.physician?.let { selectedPhysician = it } },
                                    onUnsave = {
                                        scope.launch {
                                            try {
                                                ApiClient.getApiService().unsavePhysician(saved.id)
                                                loadAll()
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
            }
        }
    }

    // ── Dialogs ──

    if (showAddForm) {
        AddPhysicianDialog(
            specialtyCategories = specialtyCategories,
            onDismiss = { showAddForm = false },
            onSave = { request ->
                scope.launch {
                    try {
                        ApiClient.getApiService().createPhysician(request)
                        showAddForm = false
                        loadAll()
                        Toast.makeText(context, "Physician added", Toast.LENGTH_SHORT).show()
                    } catch (e: Exception) {
                        Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                    }
                }
            }
        )
    }

    selectedPhysician?.let { p ->
        PhysicianDetailDialog(
            physician = p,
            isSaved = savedIds.contains(p.id),
            onDismiss = { selectedPhysician = null },
            onSave = { showSaveDialog = p },
            onReview = { showReviewDialog = p }
        )
    }

    showSaveDialog?.let { p ->
        SavePhysicianDialog(
            physician = p,
            onDismiss = { showSaveDialog = null },
            onSave = { request ->
                scope.launch {
                    try {
                        ApiClient.getApiService().savePhysician(request)
                        showSaveDialog = null
                        loadAll()
                        Toast.makeText(context, "Physician saved", Toast.LENGTH_SHORT).show()
                    } catch (e: Exception) {
                        Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                    }
                }
            }
        )
    }

    showReviewDialog?.let { p ->
        ReviewPhysicianDialog(
            physician = p,
            onDismiss = { showReviewDialog = null },
            onSubmit = { request ->
                scope.launch {
                    try {
                        ApiClient.getApiService().createPhysicianReview(p.id, request)
                        showReviewDialog = null
                        loadAll()
                        Toast.makeText(context, "Review submitted", Toast.LENGTH_SHORT).show()
                    } catch (e: Exception) {
                        Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                    }
                }
            }
        )
    }
}

// ── Physician Card ──

@Composable
fun PhysicianCard(
    physician: Physician,
    isSaved: Boolean,
    onClick: () -> Unit,
    onSave: () -> Unit,
    onUnsave: () -> Unit,
    onReview: () -> Unit,
    onDelete: () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { onClick() }
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Top
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text(physician.fullName, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                        physician.credentials?.let { c ->
                            Text(c, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        if (physician.isVerified) {
                            Icon(Icons.Default.Verified, "Verified", modifier = Modifier.size(16.dp), tint = Color(0xFF22C55E))
                        }
                    }
                    Text(
                        "${physician.specialty}${physician.specialtyCategory?.let { " • $it" } ?: ""}",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.primary,
                        fontWeight = FontWeight.Medium
                    )
                }
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    IconButton(onClick = { if (isSaved) onUnsave() else onSave() }, modifier = Modifier.size(32.dp)) {
                        Icon(
                            if (isSaved) Icons.Default.Favorite else Icons.Default.FavoriteBorder,
                            "Save", tint = if (isSaved) Color.Red else MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.size(18.dp)
                        )
                    }
                    IconButton(onClick = onReview, modifier = Modifier.size(32.dp)) {
                        Icon(Icons.Default.RateReview, "Review", modifier = Modifier.size(18.dp))
                    }
                    IconButton(onClick = onDelete, modifier = Modifier.size(32.dp)) {
                        Icon(Icons.Default.Delete, "Delete", modifier = Modifier.size(18.dp), tint = MaterialTheme.colorScheme.error)
                    }
                }
            }

            Spacer(Modifier.height(4.dp))

            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                physician.facilityName?.let { f ->
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        Icon(Icons.Default.Business, null, modifier = Modifier.size(14.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(f, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                }
                if (physician.locationDisplay.isNotBlank()) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        Icon(Icons.Default.LocationOn, null, modifier = Modifier.size(14.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(physician.locationDisplay, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                }
            }

            if (physician.reviewCount > 0) {
                Spacer(Modifier.height(4.dp))
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    repeat(5) { i ->
                        Icon(
                            if (i < (physician.averageRating?.toInt() ?: 0)) Icons.Default.Star else Icons.Default.StarBorder,
                            null, modifier = Modifier.size(14.dp), tint = Color(0xFFF59E0B)
                        )
                    }
                    Text(
                        "${physician.averageRating?.let { String.format("%.1f", it) } ?: "-"} (${physician.reviewCount})",
                        style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            Spacer(Modifier.height(4.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                if (physician.acceptingNewPatients) {
                    Surface(color = Color(0xFF22C55E).copy(alpha = 0.12f), shape = MaterialTheme.shapes.small) {
                        Text("Accepting patients", modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp),
                            style = MaterialTheme.typography.labelSmall, color = Color(0xFF22C55E))
                    }
                }
                if (physician.telehealthAvailable) {
                    Surface(color = Color(0xFF06B6D4).copy(alpha = 0.12f), shape = MaterialTheme.shapes.small) {
                        Text("Telehealth", modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp),
                            style = MaterialTheme.typography.labelSmall, color = Color(0xFF06B6D4))
                    }
                }
            }
        }
    }
}

// ── Saved Physician Card ──

@Composable
fun SavedPhysicianCard(saved: SavedPhysician, onClick: () -> Unit, onUnsave: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth().clickable { onClick() }) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Top
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(saved.physician?.fullName ?: "Unknown", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    Text(saved.physician?.specialty ?: "", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.primary)
                }
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                    if (saved.isPrimaryCare) {
                        Surface(color = Color(0xFF22C55E).copy(alpha = 0.15f), shape = MaterialTheme.shapes.small) {
                            Text("PCP", modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp),
                                style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold, color = Color(0xFF22C55E))
                        }
                    }
                    saved.relationshipType?.let { rel ->
                        Surface(color = MaterialTheme.colorScheme.primary.copy(alpha = 0.12f), shape = MaterialTheme.shapes.small) {
                            Text(rel, modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp),
                                style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary)
                        }
                    }
                    IconButton(onClick = onUnsave, modifier = Modifier.size(32.dp)) {
                        Icon(Icons.Default.Delete, "Remove", modifier = Modifier.size(18.dp), tint = MaterialTheme.colorScheme.error)
                    }
                }
            }
            saved.nickname?.let { Text("\"$it\"", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            saved.notes?.let { Text(it, style = MaterialTheme.typography.bodySmall, fontStyle = FontStyle.Italic, color = MaterialTheme.colorScheme.onSurfaceVariant) }
        }
    }
}

// ── Detail Dialog ──

@Composable
fun PhysicianDetailDialog(
    physician: Physician,
    isSaved: Boolean,
    onDismiss: () -> Unit,
    onSave: () -> Unit,
    onReview: () -> Unit
) {
    var reviews by remember { mutableStateOf<List<PhysicianReview>>(emptyList()) }
    val scope = rememberCoroutineScope()
    val context = LocalContext.current

    LaunchedEffect(physician.id) {
        try { reviews = ApiClient.getApiService().getPhysicianReviews(physician.id) }
        catch (_: Exception) {}
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = { TextButton(onClick = onDismiss) { Text("Close") } },
        title = {
            Column {
                Text(physician.fullName, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                Text("${physician.specialty}${physician.credentials?.let { " • $it" } ?: ""}",
                    style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.primary)
            }
        },
        text = {
            Column(modifier = Modifier.verticalScroll(rememberScrollState())) {
                // Contact info
                physician.facilityName?.let { InfoRow(Icons.Default.Business, it) }
                if (physician.locationDisplay.isNotBlank()) InfoRow(Icons.Default.LocationOn, physician.locationDisplay)
                physician.phone?.let { InfoRow(Icons.Default.Phone, it) }
                physician.email?.let { InfoRow(Icons.Default.Email, it) }
                physician.website?.let { InfoRow(Icons.Default.Language, it) }
                physician.operatingHours?.let { InfoRow(Icons.Default.Schedule, it) }
                physician.languagesSpoken?.let { InfoRow(Icons.Default.Translate, it) }
                physician.insuranceAccepted?.let { InfoRow(Icons.Default.Shield, it) }

                Spacer(Modifier.height(12.dp))

                // Ratings
                if (physician.reviewCount > 0) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        repeat(5) { i ->
                            Icon(if (i < (physician.averageRating?.toInt() ?: 0)) Icons.Default.Star else Icons.Default.StarBorder,
                                null, modifier = Modifier.size(18.dp), tint = Color(0xFFF59E0B))
                        }
                        Text("${physician.averageRating?.let { String.format("%.1f", it) } ?: "-"} (${physician.reviewCount} reviews)",
                            style = MaterialTheme.typography.bodyMedium)
                    }
                    Spacer(Modifier.height(8.dp))
                }

                // Reviews
                Text("Reviews", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(4.dp))
                if (reviews.isEmpty()) {
                    Text("No reviews yet", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
                } else {
                    reviews.forEach { r ->
                        Column(modifier = Modifier.padding(vertical = 4.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                                repeat(5) { i ->
                                    Icon(if (i < r.rating) Icons.Default.Star else Icons.Default.StarBorder,
                                        null, modifier = Modifier.size(12.dp), tint = Color(0xFFF59E0B))
                                }
                                Text(r.reviewerName ?: "Anonymous", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                            r.title?.let { Text(it, fontWeight = FontWeight.Medium, style = MaterialTheme.typography.bodySmall) }
                            r.reviewText?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
                            HorizontalDivider(modifier = Modifier.padding(top = 4.dp))
                        }
                    }
                }

                Spacer(Modifier.height(12.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (!isSaved) {
                        OutlinedButton(onClick = onSave) {
                            Icon(Icons.Default.FavoriteBorder, null, modifier = Modifier.size(16.dp))
                            Spacer(Modifier.width(4.dp)); Text("Save")
                        }
                    }
                    OutlinedButton(onClick = onReview) {
                        Icon(Icons.Default.RateReview, null, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(4.dp)); Text("Review")
                    }
                }
            }
        }
    )
}

@Composable
private fun InfoRow(icon: androidx.compose.ui.graphics.vector.ImageVector, text: String) {
    Row(
        modifier = Modifier.padding(vertical = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        Icon(icon, null, modifier = Modifier.size(16.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(text, style = MaterialTheme.typography.bodySmall)
    }
}

// ── Add Physician Dialog ──

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AddPhysicianDialog(
    specialtyCategories: Map<String, List<String>>,
    onDismiss: () -> Unit,
    onSave: (PhysicianCreateRequest) -> Unit
) {
    var fullName by remember { mutableStateOf("") }
    var specialty by remember { mutableStateOf("") }
    var credentials by remember { mutableStateOf("") }
    var facilityName by remember { mutableStateOf("") }
    var phone by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var city by remember { mutableStateOf("") }
    var stateProvince by remember { mutableStateOf("") }
    var country by remember { mutableStateOf("") }
    var acceptingNew by remember { mutableStateOf(true) }
    var telehealth by remember { mutableStateOf(false) }
    var languages by remember { mutableStateOf("") }
    var specExpanded by remember { mutableStateOf(false) }

    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = {
            TextButton(
                onClick = {
                    onSave(PhysicianCreateRequest(
                        fullName = fullName, specialty = specialty,
                        credentials = credentials.ifBlank { null },
                        facilityName = facilityName.ifBlank { null },
                        phone = phone.ifBlank { null }, email = email.ifBlank { null },
                        city = city.ifBlank { null }, stateProvince = stateProvince.ifBlank { null },
                        country = country.ifBlank { null },
                        acceptingNewPatients = acceptingNew, telehealthAvailable = telehealth,
                        languagesSpoken = languages.ifBlank { null }
                    ))
                },
                enabled = fullName.isNotBlank() && specialty.isNotBlank()
            ) { Text("Save") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
        title = { Text("Add Physician") },
        text = {
            Column(modifier = Modifier.verticalScroll(rememberScrollState())) {
                OutlinedTextField(value = fullName, onValueChange = { fullName = it }, label = { Text("Full Name *") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                Spacer(Modifier.height(8.dp))
                ExposedDropdownMenuBox(expanded = specExpanded, onExpandedChange = { specExpanded = !specExpanded }) {
                    OutlinedTextField(
                        value = specialty.ifBlank { "Select Specialty *" }, onValueChange = {}, readOnly = true,
                        modifier = Modifier.menuAnchor().fillMaxWidth(),
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(specExpanded) },
                        label = { Text("Specialty *") }
                    )
                    ExposedDropdownMenu(expanded = specExpanded, onDismissRequest = { specExpanded = false }) {
                        specialtyCategories.forEach { (cat, specs) ->
                            Text(cat, modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
                                style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
                            specs.forEach { s ->
                                DropdownMenuItem(text = { Text(s) }, onClick = { specialty = s; specExpanded = false })
                            }
                        }
                    }
                }
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(value = credentials, onValueChange = { credentials = it }, label = { Text("Credentials") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(value = facilityName, onValueChange = { facilityName = it }, label = { Text("Facility") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(value = phone, onValueChange = { phone = it }, label = { Text("Phone") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(value = email, onValueChange = { email = it }, label = { Text("Email") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                Spacer(Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(value = city, onValueChange = { city = it }, label = { Text("City") }, modifier = Modifier.weight(1f), singleLine = true)
                    OutlinedTextField(value = stateProvince, onValueChange = { stateProvince = it }, label = { Text("State") }, modifier = Modifier.weight(1f), singleLine = true)
                }
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(value = country, onValueChange = { country = it }, label = { Text("Country") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(value = languages, onValueChange = { languages = it }, label = { Text("Languages") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                Spacer(Modifier.height(8.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = acceptingNew, onCheckedChange = { acceptingNew = it })
                    Text("Accepting patients", style = MaterialTheme.typography.bodySmall)
                    Spacer(Modifier.width(12.dp))
                    Checkbox(checked = telehealth, onCheckedChange = { telehealth = it })
                    Text("Telehealth", style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    )
}

// ── Save Physician Dialog ──

@Composable
fun SavePhysicianDialog(
    physician: Physician,
    onDismiss: () -> Unit,
    onSave: (SavePhysicianRequest) -> Unit
) {
    var nickname by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }
    var isPrimary by remember { mutableStateOf(false) }
    var relationship by remember { mutableStateOf("") }
    val relationships = listOf("PCP", "Specialist", "Dentist", "Therapist", "Surgeon", "Pharmacist", "Other")
    var relExpanded by remember { mutableStateOf(false) }

    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = {
            TextButton(onClick = {
                onSave(SavePhysicianRequest(
                    physicianId = physician.id,
                    nickname = nickname.ifBlank { null },
                    notes = notes.ifBlank { null },
                    isPrimaryCare = isPrimary,
                    relationshipType = relationship.ifBlank { null }
                ))
            }) { Text("Save") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
        title = { Text("Save ${physician.fullName}") },
        text = {
            Column {
                OutlinedTextField(value = nickname, onValueChange = { nickname = it }, label = { Text("Nickname") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                Spacer(Modifier.height(8.dp))
                ExposedDropdownMenuBox(expanded = relExpanded, onExpandedChange = { relExpanded = !relExpanded }) {
                    OutlinedTextField(
                        value = relationship.ifBlank { "Relationship" }, onValueChange = {}, readOnly = true,
                        modifier = Modifier.menuAnchor().fillMaxWidth(), trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(relExpanded) }
                    )
                    ExposedDropdownMenu(expanded = relExpanded, onDismissRequest = { relExpanded = false }) {
                        relationships.forEach { r ->
                            DropdownMenuItem(text = { Text(r) }, onClick = { relationship = r; relExpanded = false })
                        }
                    }
                }
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(value = notes, onValueChange = { notes = it }, label = { Text("Notes") }, modifier = Modifier.fillMaxWidth(), minLines = 2, maxLines = 4)
                Spacer(Modifier.height(8.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = isPrimary, onCheckedChange = { isPrimary = it })
                    Text("Primary Care Provider")
                }
            }
        }
    )
}

// ── Review Dialog ──

@Composable
fun ReviewPhysicianDialog(
    physician: Physician,
    onDismiss: () -> Unit,
    onSubmit: (PhysicianReviewRequest) -> Unit
) {
    var rating by remember { mutableIntStateOf(5) }
    var title by remember { mutableStateOf("") }
    var reviewText by remember { mutableStateOf("") }
    var anonymous by remember { mutableStateOf(false) }

    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = {
            TextButton(onClick = {
                onSubmit(PhysicianReviewRequest(
                    rating = rating,
                    title = title.ifBlank { null },
                    reviewText = reviewText.ifBlank { null },
                    isAnonymous = anonymous
                ))
            }) { Text("Submit") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
        title = { Text("Review ${physician.fullName}") },
        text = {
            Column {
                Text("Rating", style = MaterialTheme.typography.labelMedium)
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    (1..5).forEach { i ->
                        IconButton(onClick = { rating = i }, modifier = Modifier.size(36.dp)) {
                            Icon(
                                if (i <= rating) Icons.Default.Star else Icons.Default.StarBorder,
                                null, tint = Color(0xFFF59E0B), modifier = Modifier.size(28.dp)
                            )
                        }
                    }
                }
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(value = title, onValueChange = { title = it }, label = { Text("Title (optional)") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(value = reviewText, onValueChange = { reviewText = it }, label = { Text("Review") }, modifier = Modifier.fillMaxWidth(), minLines = 3, maxLines = 6)
                Spacer(Modifier.height(8.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = anonymous, onCheckedChange = { anonymous = it })
                    Text("Post anonymously")
                }
            }
        }
    )
}
