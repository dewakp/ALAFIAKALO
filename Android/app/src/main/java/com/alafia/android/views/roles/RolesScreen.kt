package com.alafia.android.views.roles

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.alafia.android.api.ApiClient
import com.alafia.android.models.*
import com.alafia.android.schemas.*
import kotlinx.coroutines.launch
import androidx.navigation.NavHostController
import androidx.compose.ui.res.stringResource
import com.alafia.android.R

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RolesScreen(navController: NavHostController) {
    val scope = rememberCoroutineScope()
    val api = ApiClient.getApiService()

    var persona by remember { mutableStateOf<UserPersonaSummary?>(null) }
    var catalog by remember { mutableStateOf<List<RoleCategoryInfo>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var selectedTab by remember { mutableIntStateOf(0) }

    // Add role state
    var searchQuery by remember { mutableStateOf("") }
    var selectedCategory by remember { mutableStateOf("") }

    // Profile editor state
    var editingRole by remember { mutableStateOf<RoleAssignment?>(null) }
    var showProfileSheet by remember { mutableStateOf(false) }

    fun loadAll() {
        scope.launch {
            loading = true
            error = null
            try {
                persona = api.getMyPersona()
                catalog = api.getRoleCatalog()
            } catch (e: Exception) {
                error = e.message ?: "Failed to load"
            }
            loading = false
        }
    }

    LaunchedEffect(Unit) { loadAll() }

    if (showProfileSheet && editingRole != null) {
        ProfessionalProfileSheet(
            roleAssignment = editingRole!!,
            onDismiss = { showProfileSheet = false },
            onSaved = { showProfileSheet = false; loadAll() }
        )
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.roles)) },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = stringResource(R.string.back))
                    }
                }
            )
        }
    ) { padding ->
    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(padding).padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item {
            Text(stringResource(R.string.role), style = MaterialTheme.typography.headlineLarge,
                modifier = Modifier.padding(bottom = 8.dp))
        }

        if (loading) {
            item {
                Box(Modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
            }
            return@LazyColumn
        }

        if (error != null) {
            item {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer)) {
                    Column(Modifier.padding(16.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(error ?: "", color = MaterialTheme.colorScheme.onErrorContainer)
                        Spacer(Modifier.height(8.dp))
                        Button(onClick = { loadAll() }) { Text(stringResource(R.string.retry)) }
                    }
                }
            }
            return@LazyColumn
        }

        val p = persona ?: return@LazyColumn

        // Persona summary card
        item { PersonaSummaryCard(p) }

        // Tab row
        item {
            TabRow(selectedTabIndex = selectedTab) {
                Tab(selected = selectedTab == 0, onClick = { selectedTab = 0 },
                    text = { Text(stringResource(R.string.my_roles)) })
                Tab(selected = selectedTab == 1, onClick = { selectedTab = 1 },
                    text = { Text(stringResource(R.string.add_role)) })
            }
        }

        if (selectedTab == 0) {
            // Patient card (always present)
            item {
                Card(modifier = Modifier.fillMaxWidth()) {
                    Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(44.dp).clip(CircleShape)
                            .background(MaterialTheme.colorScheme.primaryContainer),
                            contentAlignment = Alignment.Center) {
                            Icon(Icons.Default.Person, contentDescription = null,
                                tint = MaterialTheme.colorScheme.onPrimaryContainer)
                        }
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) {
                            Text(stringResource(R.string.patient_2), fontWeight = FontWeight.SemiBold)
                            Text(stringResource(R.string.core_role_always_active), style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        AssistChip(onClick = {}, label = { Text(stringResource(R.string.always), fontSize = 11.sp) })
                    }
                }
            }

            // Professional roles
            items(p.roleDetails) { rd ->
                RoleCard(
                    rd = rd,
                    catalog = catalog,
                    onSetPrimary = {
                        scope.launch {
                            try { api.setPrimaryRole(rd.id); loadAll() }
                            catch (e: Exception) { error = e.message }
                        }
                    },
                    onEditProfile = { editingRole = rd; showProfileSheet = true },
                    onRemove = {
                        scope.launch {
                            try { api.removeRole(rd.id); loadAll() }
                            catch (e: Exception) { error = e.message }
                        }
                    }
                )
            }

            if (p.roleDetails.isEmpty()) {
                item {
                    Card(Modifier.fillMaxWidth()) {
                        Column(Modifier.padding(32.dp).fillMaxWidth(),
                            horizontalAlignment = Alignment.CenterHorizontally) {
                            Icon(Icons.Default.PersonAdd, contentDescription = null,
                                modifier = Modifier.size(48.dp),
                                tint = MaterialTheme.colorScheme.onSurfaceVariant)
                            Spacer(Modifier.height(8.dp))
                            Text(stringResource(R.string.no_professional_roles), color = MaterialTheme.colorScheme.onSurfaceVariant)
                            Text(stringResource(R.string.switch_to_add_role_tab), style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }
        } else {
            // Add Role tab
            item {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        value = searchQuery,
                        onValueChange = { searchQuery = it },
                        label = { Text(stringResource(R.string.search_roles)) },
                        leadingIcon = { Icon(Icons.Default.Search, contentDescription = null) },
                        modifier = Modifier.weight(1f),
                        singleLine = true
                    )
                }
            }

            // Category filter chips
            item {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    FilterChip(
                        selected = selectedCategory.isEmpty(),
                        onClick = { selectedCategory = "" },
                        label = { Text(stringResource(R.string.all), fontSize = 12.sp) }
                    )
                }
            }
            item {
                // Using a simple flow of filter chips for categories
                val catChunks = catalog.chunked(4)
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    catChunks.forEach { chunk ->
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            chunk.forEach { cat ->
                                FilterChip(
                                    selected = selectedCategory == cat.id,
                                    onClick = { selectedCategory = if (selectedCategory == cat.id) "" else cat.id },
                                    label = { Text(cat.name, fontSize = 11.sp, maxLines = 1,
                                        overflow = TextOverflow.Ellipsis) },
                                    modifier = Modifier.widthIn(max = 120.dp)
                                )
                            }
                        }
                    }
                }
            }

            // Filtered catalog
            val existingRoles = p.activeRoles.toSet()
            val filteredCats = catalog
                .filter { selectedCategory.isEmpty() || it.id == selectedCategory }
                .map { cat ->
                    cat.copy(roles = cat.roles.filter { role ->
                        !existingRoles.contains(role.id) &&
                        (searchQuery.isEmpty() || role.name.contains(searchQuery, ignoreCase = true))
                    })
                }
                .filter { it.roles.isNotEmpty() }

            filteredCats.forEach { cat ->
                item {
                    Text(cat.name, style = MaterialTheme.typography.titleSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(top = 8.dp, bottom = 4.dp))
                }

                items(cat.roles.chunked(2)) { pair ->
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        pair.forEach { role ->
                            Card(
                                modifier = Modifier.weight(1f).clickable {
                                    scope.launch {
                                        try {
                                            val isPrimary = p.activeRoles.size <= 1
                                            api.addRole(RoleAssignmentRequest(role.id, isPrimary))
                                            loadAll()
                                            selectedTab = 0
                                        } catch (e: Exception) { error = e.message }
                                    }
                                },
                            ) {
                                Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                                    Text(role.name, fontSize = 13.sp, modifier = Modifier.weight(1f),
                                        maxLines = 1, overflow = TextOverflow.Ellipsis)
                                    Icon(Icons.Default.Add, contentDescription = stringResource(R.string.add),
                                        modifier = Modifier.size(18.dp),
                                        tint = MaterialTheme.colorScheme.primary)
                                }
                            }
                        }
                        if (pair.size == 1) Spacer(Modifier.weight(1f))
                    }
                }
            }

            if (filteredCats.isEmpty()) {
                item {
                    Card(Modifier.fillMaxWidth()) {
                        Column(Modifier.padding(32.dp).fillMaxWidth(),
                            horizontalAlignment = Alignment.CenterHorizontally) {
                            Icon(Icons.Default.CheckCircle, contentDescription = null,
                                modifier = Modifier.size(48.dp), tint = MaterialTheme.colorScheme.primary)
                            Spacer(Modifier.height(8.dp))
                            Text(
                                if (searchQuery.isEmpty() && selectedCategory.isEmpty())
                                    stringResource(R.string.all_available_roles_have_been_added)
                                else stringResource(R.string.no_matching_roles_found),
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                }
            }
        }

        // Bottom spacer
        item { Spacer(Modifier.height(32.dp)) }
    }
    }
}

@Composable
private fun PersonaSummaryCard(persona: UserPersonaSummary) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(52.dp).clip(CircleShape)
                    .background(MaterialTheme.colorScheme.primaryContainer),
                    contentAlignment = Alignment.Center) {
                    Icon(
                        if (persona.isHealthcareProfessional) Icons.Default.LocalHospital
                        else Icons.Default.Person,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.onPrimaryContainer,
                        modifier = Modifier.size(28.dp)
                    )
                }
                Spacer(Modifier.width(14.dp))
                Column(Modifier.weight(1f)) {
                    Text(persona.fullName, fontWeight = FontWeight.Bold, fontSize = 18.sp)
                    Text(persona.email, style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Column(horizontalAlignment = Alignment.End) {
                    AssistChip(onClick = {},
                        label = { Text(persona.primaryRole.replace("_", " ").uppercase(),
                            fontSize = 10.sp, fontWeight = FontWeight.Bold) })
                    if (persona.isHealthcareProfessional) {
                        AssistChip(onClick = {},
                            label = { Text(stringResource(R.string.healthcare_pro), fontSize = 10.sp) },
                            colors = AssistChipDefaults.assistChipColors(
                                containerColor = MaterialTheme.colorScheme.tertiaryContainer))
                    }
                }
            }

            Spacer(Modifier.height(12.dp))

            // Active roles
            Text(stringResource(R.string.active_roles), style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(4.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                persona.activeRoles.take(6).forEach { role ->
                    SuggestionChip(onClick = {},
                        label = { Text(role.replace("_", " "), fontSize = 11.sp) })
                }
                if (persona.activeRoles.size > 6) {
                    SuggestionChip(onClick = {},
                        label = { Text("+${persona.activeRoles.size - 6}", fontSize = 11.sp) })
                }
            }

            // Categories
            if (persona.roleCategories.isNotEmpty()) {
                Spacer(Modifier.height(8.dp))
                Text(stringResource(R.string.categories), style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                Spacer(Modifier.height(4.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    persona.roleCategories.forEach { cat ->
                        SuggestionChip(onClick = {},
                            label = { Text(cat.replace("_", " "), fontSize = 11.sp) },
                            colors = SuggestionChipDefaults.suggestionChipColors(
                                containerColor = MaterialTheme.colorScheme.surfaceVariant))
                    }
                }
            }

            // Permissions count
            if (persona.permissions.isNotEmpty()) {
                Spacer(Modifier.height(8.dp))
                Text(stringResource(R.string.permissions_derived_from_roles, persona.permissions.size),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

@Composable
private fun RoleCard(
    rd: RoleAssignment,
    catalog: List<RoleCategoryInfo>,
    onSetPrimary: () -> Unit,
    onEditProfile: () -> Unit,
    onRemove: () -> Unit
) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(40.dp).clip(CircleShape)
                    .background(MaterialTheme.colorScheme.secondaryContainer),
                    contentAlignment = Alignment.Center) {
                    Icon(Icons.Default.Badge, contentDescription = null,
                        tint = MaterialTheme.colorScheme.onSecondaryContainer)
                }
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(rd.role.replace("_", " ").split(" ")
                        .joinToString(" ") { it.replaceFirstChar { c -> c.uppercase() } },
                        fontWeight = FontWeight.SemiBold)
                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        if (rd.isPrimary) {
                            AssistChip(onClick = {},
                                label = { Text("PRIMARY", fontSize = 9.sp, fontWeight = FontWeight.Bold) },
                                colors = AssistChipDefaults.assistChipColors(
                                    containerColor = MaterialTheme.colorScheme.primaryContainer))
                        }
                        AssistChip(onClick = {},
                            label = { Text(if (rd.isActive) stringResource(R.string.active) else stringResource(R.string.inactive), fontSize = 9.sp) },
                            colors = AssistChipDefaults.assistChipColors(
                                containerColor = if (rd.isActive) Color(0xFFD1FAE5) else Color(0xFFE2E8F0)))
                        rd.professionalProfile?.verificationStatus?.let { vs ->
                            AssistChip(onClick = {},
                                label = { Text(vs.replaceFirstChar { it.uppercase() }, fontSize = 9.sp) },
                                colors = AssistChipDefaults.assistChipColors(
                                    containerColor = when (vs) {
                                        "verified" -> Color(0xFFD1FAE5)
                                        "pending" -> Color(0xFFFEF3C7)
                                        "rejected" -> Color(0xFFFEE2E2)
                                        else -> Color(0xFFE2E8F0)
                                    }))
                        }
                    }
                }
            }

            // Profile summary
            rd.professionalProfile?.let { prof ->
                val details = listOfNotNull(
                    prof.specialty,
                    prof.practiceName,
                    prof.yearsOfExperience?.let { "$it yrs exp" }
                )
                if (details.isNotEmpty()) {
                    Spacer(Modifier.height(6.dp))
                    Text(details.joinToString(" • "), style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }

            // Actions
            Spacer(Modifier.height(8.dp))
            // Acting on a clinical role switches the whole app into clinician
            // mode and lands on the patient grid, rather than pushing a screen
            // inside the patient tab bar.
            if (rd.isActive && rd.role in com.alafia.android.views.main.CLINICIAN_ROLES) {
                Button(
                    onClick = { com.alafia.android.views.main.ClinicianModeState.enter(listOf(rd.role)) },
                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 4.dp)
                ) {
                    Icon(Icons.Default.MedicalServices, contentDescription = null, modifier = Modifier.size(14.dp))
                    Spacer(Modifier.width(4.dp))
                    Text(stringResource(R.string.open_clinician_view), fontSize = 12.sp)
                }
                Spacer(Modifier.height(8.dp))
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (!rd.isPrimary) {
                    OutlinedButton(onClick = onSetPrimary, contentPadding = PaddingValues(horizontal = 12.dp, vertical = 4.dp)) {
                        Icon(Icons.Default.Star, contentDescription = null, modifier = Modifier.size(14.dp))
                        Spacer(Modifier.width(4.dp))
                        Text(stringResource(R.string.set_primary), fontSize = 12.sp)
                    }
                }
                OutlinedButton(onClick = onEditProfile, contentPadding = PaddingValues(horizontal = 12.dp, vertical = 4.dp)) {
                    Icon(Icons.Default.Edit, contentDescription = null, modifier = Modifier.size(14.dp))
                    Spacer(Modifier.width(4.dp))
                    Text(if (rd.professionalProfile != null) stringResource(R.string.edit_profile) else stringResource(R.string.add_profile), fontSize = 12.sp)
                }
                Spacer(Modifier.weight(1f))
                OutlinedButton(
                    onClick = onRemove,
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = MaterialTheme.colorScheme.error),
                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 4.dp)
                ) {
                    Icon(Icons.Default.Delete, contentDescription = null, modifier = Modifier.size(14.dp))
                    Spacer(Modifier.width(4.dp))
                    Text(stringResource(R.string.remove_2), fontSize = 12.sp)
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ProfessionalProfileSheet(
    roleAssignment: RoleAssignment,
    onDismiss: () -> Unit,
    onSaved: () -> Unit
) {
    val scope = rememberCoroutineScope()
    val api = ApiClient.getApiService()
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    val existing = roleAssignment.professionalProfile

    var licenseNumber by remember { mutableStateOf(existing?.licenseNumber ?: "") }
    var licenseState by remember { mutableStateOf(existing?.licenseState ?: "") }
    var licenseCountry by remember { mutableStateOf(existing?.licenseCountry ?: "") }
    var licenseExpiry by remember { mutableStateOf(existing?.licenseExpiry ?: "") }
    var npiNumber by remember { mutableStateOf(existing?.npiNumber ?: "") }
    var deaNumber by remember { mutableStateOf(existing?.deaNumber ?: "") }
    var boardCerts by remember { mutableStateOf(existing?.boardCertifications?.joinToString(", ") ?: "") }
    var medicalSchool by remember { mutableStateOf(existing?.medicalSchool ?: "") }
    var degree by remember { mutableStateOf(existing?.degree ?: "") }
    var graduationYear by remember { mutableStateOf(existing?.graduationYear?.toString() ?: "") }
    var residencyProgram by remember { mutableStateOf(existing?.residencyProgram ?: "") }
    var fellowshipProgram by remember { mutableStateOf(existing?.fellowshipProgram ?: "") }
    var specialty by remember { mutableStateOf(existing?.specialty ?: "") }
    var subSpecialty by remember { mutableStateOf(existing?.subSpecialty ?: "") }
    var yearsExp by remember { mutableStateOf(existing?.yearsOfExperience?.toString() ?: "") }
    var practiceName by remember { mutableStateOf(existing?.practiceName ?: "") }
    var practiceType by remember { mutableStateOf(existing?.practiceType ?: "") }
    var practiceAddress by remember { mutableStateOf(existing?.practiceAddress ?: "") }
    var practicePhone by remember { mutableStateOf(existing?.practicePhone ?: "") }
    var practiceEmail by remember { mutableStateOf(existing?.practiceEmail ?: "") }
    var practiceWebsite by remember { mutableStateOf(existing?.practiceWebsite ?: "") }
    var acceptingPatients by remember { mutableStateOf(existing?.acceptingPatients ?: false) }
    var hospitalAffiliations by remember { mutableStateOf(existing?.hospitalAffiliations?.joinToString(", ") ?: "") }
    var department by remember { mutableStateOf(existing?.department ?: "") }
    var titleField by remember { mutableStateOf(existing?.title ?: "") }
    var clinicalLanguages by remember { mutableStateOf(existing?.clinicalLanguages?.joinToString(", ") ?: "") }
    var telemedicineAvailable by remember { mutableStateOf(existing?.telemedicineAvailable ?: false) }
    var telemedicinePlatforms by remember { mutableStateOf(existing?.telemedicinePlatforms?.joinToString(", ") ?: "") }
    var professionalBio by remember { mutableStateOf(existing?.professionalBio ?: "") }
    var publications by remember { mutableStateOf(existing?.publications?.joinToString(", ") ?: "") }
    var researchInterests by remember { mutableStateOf(existing?.researchInterests?.joinToString(", ") ?: "") }

    var saving by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("") }

    fun splitCsv(s: String): List<String>? {
        val items = s.split(",").map { it.trim() }.filter { it.isNotEmpty() }
        return items.ifEmpty { null }
    }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        modifier = Modifier.fillMaxHeight(0.92f)
    ) {
        LazyColumn(
            modifier = Modifier.padding(horizontal = 20.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            item {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically) {
                    Text(stringResource(R.string.professional_profile), style = MaterialTheme.typography.titleLarge)
                    Button(
                        onClick = {
                            scope.launch {
                                saving = true; message = ""
                                try {
                                    api.upsertProfessionalProfile(roleAssignment.id,
                                        ProfessionalProfileRequest(
                                            licenseNumber = licenseNumber.ifBlank { null },
                                            licenseState = licenseState.ifBlank { null },
                                            licenseCountry = licenseCountry.ifBlank { null },
                                            licenseExpiry = licenseExpiry.ifBlank { null },
                                            npiNumber = npiNumber.ifBlank { null },
                                            deaNumber = deaNumber.ifBlank { null },
                                            boardCertifications = splitCsv(boardCerts),
                                            medicalSchool = medicalSchool.ifBlank { null },
                                            degree = degree.ifBlank { null },
                                            graduationYear = graduationYear.toIntOrNull(),
                                            residencyProgram = residencyProgram.ifBlank { null },
                                            fellowshipProgram = fellowshipProgram.ifBlank { null },
                                            specialty = specialty.ifBlank { null },
                                            subSpecialty = subSpecialty.ifBlank { null },
                                            yearsOfExperience = yearsExp.toIntOrNull(),
                                            practiceName = practiceName.ifBlank { null },
                                            practiceType = practiceType.ifBlank { null },
                                            practiceAddress = practiceAddress.ifBlank { null },
                                            practicePhone = practicePhone.ifBlank { null },
                                            practiceEmail = practiceEmail.ifBlank { null },
                                            practiceWebsite = practiceWebsite.ifBlank { null },
                                            acceptingPatients = acceptingPatients,
                                            hospitalAffiliations = splitCsv(hospitalAffiliations),
                                            department = department.ifBlank { null },
                                            title = titleField.ifBlank { null },
                                            clinicalLanguages = splitCsv(clinicalLanguages),
                                            telemedicineAvailable = telemedicineAvailable,
                                            telemedicinePlatforms = splitCsv(telemedicinePlatforms),
                                            professionalBio = professionalBio.ifBlank { null },
                                            publications = splitCsv(publications),
                                            researchInterests = splitCsv(researchInterests)
                                        ))
                                    message = "Saved!"
                                    onSaved()
                                } catch (e: Exception) {
                                    message = e.message ?: "Failed to save"
                                }
                                saving = false
                            }
                        },
                        enabled = !saving
                    ) { Text(if (saving) stringResource(R.string.saving_2) else stringResource(R.string.save)) }
                }
            }

            if (message.isNotEmpty()) {
                item {
                    Text(message, color = if (message == "Saved!") MaterialTheme.colorScheme.primary
                        else MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall)
                }
            }

            // Credentials
            item { SectionHeader(stringResource(R.string.credentials_licensing)) }
            item {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(value = licenseNumber, onValueChange = { licenseNumber = it },
                        label = { Text(stringResource(R.string.license_number)) }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedTextField(value = licenseState, onValueChange = { licenseState = it },
                            label = { Text(stringResource(R.string.license_state)) }, modifier = Modifier.weight(1f), singleLine = true)
                        OutlinedTextField(value = licenseCountry, onValueChange = { licenseCountry = it },
                            label = { Text(stringResource(R.string.license_country)) }, modifier = Modifier.weight(1f), singleLine = true)
                    }
                    OutlinedTextField(value = licenseExpiry, onValueChange = { licenseExpiry = it },
                        label = { Text(stringResource(R.string.license_expiry_yyyy_mm_dd)) }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedTextField(value = npiNumber, onValueChange = { npiNumber = it },
                            label = { Text(stringResource(R.string.npi_number)) }, modifier = Modifier.weight(1f), singleLine = true)
                        OutlinedTextField(value = deaNumber, onValueChange = { deaNumber = it },
                            label = { Text(stringResource(R.string.dea_number)) }, modifier = Modifier.weight(1f), singleLine = true)
                    }
                    OutlinedTextField(value = boardCerts, onValueChange = { boardCerts = it },
                        label = { Text(stringResource(R.string.board_certifications_comma_separated)) }, modifier = Modifier.fillMaxWidth())
                }
            }

            // Education
            item { SectionHeader(stringResource(R.string.education_training)) }
            item {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(value = medicalSchool, onValueChange = { medicalSchool = it },
                        label = { Text(stringResource(R.string.medical_school_institution)) }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedTextField(value = degree, onValueChange = { degree = it },
                            label = { Text(stringResource(R.string.degree)) }, modifier = Modifier.weight(1f), singleLine = true)
                        OutlinedTextField(value = graduationYear, onValueChange = { graduationYear = it },
                            label = { Text(stringResource(R.string.grad_year)) }, modifier = Modifier.weight(1f), singleLine = true)
                    }
                    OutlinedTextField(value = residencyProgram, onValueChange = { residencyProgram = it },
                        label = { Text(stringResource(R.string.residency_program)) }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                    OutlinedTextField(value = fellowshipProgram, onValueChange = { fellowshipProgram = it },
                        label = { Text(stringResource(R.string.fellowship_program)) }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                }
            }

            // Practice
            item { SectionHeader(stringResource(R.string.specialty_practice)) }
            item {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedTextField(value = specialty, onValueChange = { specialty = it },
                            label = { Text(stringResource(R.string.specialty)) }, modifier = Modifier.weight(1f), singleLine = true)
                        OutlinedTextField(value = subSpecialty, onValueChange = { subSpecialty = it },
                            label = { Text(stringResource(R.string.sub_specialty)) }, modifier = Modifier.weight(1f), singleLine = true)
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedTextField(value = yearsExp, onValueChange = { yearsExp = it },
                            label = { Text(stringResource(R.string.years_exp)) }, modifier = Modifier.weight(1f), singleLine = true)
                        OutlinedTextField(value = practiceType, onValueChange = { practiceType = it },
                            label = { Text(stringResource(R.string.practice_type)) }, modifier = Modifier.weight(1f), singleLine = true)
                    }
                    OutlinedTextField(value = practiceName, onValueChange = { practiceName = it },
                        label = { Text(stringResource(R.string.practice_name)) }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                    OutlinedTextField(value = practiceAddress, onValueChange = { practiceAddress = it },
                        label = { Text(stringResource(R.string.practice_address)) }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedTextField(value = practicePhone, onValueChange = { practicePhone = it },
                            label = { Text(stringResource(R.string.phone)) }, modifier = Modifier.weight(1f), singleLine = true)
                        OutlinedTextField(value = practiceEmail, onValueChange = { practiceEmail = it },
                            label = { Text(stringResource(R.string.email)) }, modifier = Modifier.weight(1f), singleLine = true)
                    }
                    OutlinedTextField(value = practiceWebsite, onValueChange = { practiceWebsite = it },
                        label = { Text(stringResource(R.string.website)) }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = acceptingPatients, onCheckedChange = { acceptingPatients = it })
                        Text(stringResource(R.string.accepting_patients_2))
                    }
                }
            }

            // Hospital
            item { SectionHeader(stringResource(R.string.hospital_affiliations)) }
            item {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(value = hospitalAffiliations, onValueChange = { hospitalAffiliations = it },
                        label = { Text(stringResource(R.string.hospital_affiliations_comma_separated)) }, modifier = Modifier.fillMaxWidth())
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedTextField(value = department, onValueChange = { department = it },
                            label = { Text(stringResource(R.string.department)) }, modifier = Modifier.weight(1f), singleLine = true)
                        OutlinedTextField(value = titleField, onValueChange = { titleField = it },
                            label = { Text(stringResource(R.string.title)) }, modifier = Modifier.weight(1f), singleLine = true)
                    }
                }
            }

            // Languages & Telemedicine
            item { SectionHeader(stringResource(R.string.languages_telemedicine)) }
            item {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(value = clinicalLanguages, onValueChange = { clinicalLanguages = it },
                        label = { Text(stringResource(R.string.clinical_languages_comma_separated)) }, modifier = Modifier.fillMaxWidth())
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = telemedicineAvailable, onCheckedChange = { telemedicineAvailable = it })
                        Text(stringResource(R.string.telemedicine_available))
                    }
                    if (telemedicineAvailable) {
                        OutlinedTextField(value = telemedicinePlatforms, onValueChange = { telemedicinePlatforms = it },
                            label = { Text(stringResource(R.string.platforms_comma_separated)) }, modifier = Modifier.fillMaxWidth())
                    }
                }
            }

            // Bio
            item { SectionHeader(stringResource(R.string.bio_research)) }
            item {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(value = professionalBio, onValueChange = { professionalBio = it },
                        label = { Text(stringResource(R.string.professional_bio)) }, modifier = Modifier.fillMaxWidth(), minLines = 3)
                    OutlinedTextField(value = publications, onValueChange = { publications = it },
                        label = { Text(stringResource(R.string.publications_comma_separated)) }, modifier = Modifier.fillMaxWidth())
                    OutlinedTextField(value = researchInterests, onValueChange = { researchInterests = it },
                        label = { Text(stringResource(R.string.research_interests_comma_separated)) }, modifier = Modifier.fillMaxWidth())
                }
            }

            item { Spacer(Modifier.height(40.dp)) }
        }
    }
}

@Composable
private fun SectionHeader(text: String) {
    Text(text, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.padding(top = 8.dp))
}
