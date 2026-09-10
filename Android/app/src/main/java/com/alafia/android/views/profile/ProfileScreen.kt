package com.alafia.android.views.profile
import com.alafia.android.util.ErrorUtil

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.alafia.android.views.components.AvatarImage
import com.alafia.android.views.components.rememberCameraCapture
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody
import com.alafia.android.api.ApiClient
import com.alafia.android.schemas.UserSchema
import com.alafia.android.schemas.UserUpdateRequest
import kotlinx.coroutines.launch
import androidx.navigation.NavHostController

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProfileScreen(navController: NavHostController) {
    val scope = rememberCoroutineScope()
    var loading by remember { mutableStateOf(true) }
    var saving by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("") }
    var profile by remember { mutableStateOf<UserSchema?>(null) }
    val context = LocalContext.current

    // ── Photo ──
    //
    // Declared before the form so both controls can reach them. `send` reads
    // the bytes off the content Uri: a camera capture and a gallery pick arrive
    // the same way, so one upload path serves both.
    var avatarUrl by remember { mutableStateOf<String?>(null) }
    var avatarBusy by remember { mutableStateOf(false) }

    fun sendAvatar(uri: android.net.Uri) {
        avatarBusy = true
        scope.launch {
            try {
                val bytes = context.contentResolver.openInputStream(uri)?.use { it.readBytes() }
                if (bytes == null || bytes.isEmpty()) {
                    // An unreadable Uri must say so. Uploading zero bytes would
                    // be refused by the server as "not an image", which reads as
                    // the photo being wrong rather than never having been read.
                    message = "That photo could not be read."
                } else {
                    val part = MultipartBody.Part.createFormData(
                        "file", "avatar.jpg",
                        bytes.toRequestBody("image/*".toMediaTypeOrNull()),
                    )
                    val u = ApiClient.getApiService().uploadAvatar(part)
                    avatarUrl = u.profile_picture_url
                }
            } catch (e: Exception) {
                message = ErrorUtil.userMessage(e)
            }
            avatarBusy = false
        }
    }

    val avatarCamera = rememberCameraCapture { uri -> sendAvatar(uri) }
    val avatarPicker = rememberLauncherForActivityResult(
        ActivityResultContracts.GetContent()
    ) { uri -> uri?.let { sendAvatar(it) } }

    // ── Mutable fields ──
    var fullName by remember { mutableStateOf("") }
    var firstName by remember { mutableStateOf("") }
    var lastName by remember { mutableStateOf("") }
    var middleName by remember { mutableStateOf("") }
    var namePrefix by remember { mutableStateOf("") }
    var nameSuffix by remember { mutableStateOf("") }
    var gender by remember { mutableStateOf("") }
    var dateOfBirth by remember { mutableStateOf("") }
    var genderAtBirth by remember { mutableStateOf("") }
    var bloodType by remember { mutableStateOf("") }
    var insuranceId by remember { mutableStateOf("") }
    var insuranceProvider by remember { mutableStateOf("") }
    var insuranceCountry by remember { mutableStateOf("") }
    var heightCm by remember { mutableStateOf("") }
    var currentWeightKg by remember { mutableStateOf("") }
    var targetWeightKg by remember { mutableStateOf("") }
    var country by remember { mutableStateOf("") }
    var tz by remember { mutableStateOf("") }
    var preferredLanguage by remember { mutableStateOf("") }
    var preferredUnits by remember { mutableStateOf("") }
    var allergies by remember { mutableStateOf("") }
    var foodIntolerances by remember { mutableStateOf("") }
    var dietaryRestrictions by remember { mutableStateOf("") }
    var dietaryPreferences by remember { mutableStateOf("") }
    var familyHistory by remember { mutableStateOf("") }
    var activityLevel by remember { mutableStateOf("") }
    var exercisePerWeek by remember { mutableStateOf("") }
    var fitnessGoals by remember { mutableStateOf("") }
    var preferredActivities by remember { mutableStateOf("") }
    var occupation by remember { mutableStateOf("") }
    var smokingStatus by remember { mutableStateOf("") }
    var alcoholConsumption by remember { mutableStateOf("") }
    var sleepSchedule by remember { mutableStateOf("") }
    var stressLevel by remember { mutableStateOf("") }
    var aiCoachingEnabled by remember { mutableStateOf(true) }
    var aiPersonality by remember { mutableStateOf("") }
    var aiComplexity by remember { mutableStateOf("") }
    var dataSharingConsent by remember { mutableStateOf(false) }
    var aiTrainingConsent by remember { mutableStateOf(false) }

    // Track immutable locked state
    var dobLocked by remember { mutableStateOf(false) }
    var gabLocked by remember { mutableStateOf(false) }
    var btLocked by remember { mutableStateOf(false) }

    fun populateFields(p: UserSchema) {
        fullName = p.full_name
        firstName = p.first_name ?: ""
        lastName = p.last_name ?: ""
        middleName = p.middle_name ?: ""
        namePrefix = p.name_prefix ?: ""
        nameSuffix = p.name_suffix ?: ""
        avatarUrl = p.profile_picture_url
        gender = p.gender ?: ""
        dateOfBirth = p.date_of_birth ?: ""
        genderAtBirth = p.gender_at_birth ?: ""
        bloodType = p.blood_type ?: ""
        insuranceId = p.insurance_id ?: ""
        insuranceProvider = p.insurance_provider ?: ""
        insuranceCountry = p.insurance_country ?: ""
        heightCm = p.height_cm?.toString() ?: ""
        currentWeightKg = p.current_weight_kg?.toString() ?: ""
        targetWeightKg = p.target_weight_kg?.toString() ?: ""
        country = p.country ?: ""
        tz = p.timezone ?: ""
        preferredLanguage = p.preferred_language ?: ""
        preferredUnits = p.preferred_units ?: ""
        allergies = p.allergies ?: ""
        foodIntolerances = p.food_intolerances ?: ""
        dietaryRestrictions = p.dietary_restrictions ?: ""
        dietaryPreferences = p.dietary_preferences ?: ""
        familyHistory = p.family_history ?: ""
        activityLevel = p.activity_level ?: ""
        exercisePerWeek = p.exercise_frequency_per_week?.toString() ?: ""
        fitnessGoals = p.fitness_goals ?: ""
        preferredActivities = p.preferred_activities ?: ""
        occupation = p.occupation ?: ""
        smokingStatus = p.smoking_status ?: ""
        alcoholConsumption = p.alcohol_consumption ?: ""
        sleepSchedule = p.sleep_schedule ?: ""
        stressLevel = p.stress_level ?: ""
        aiCoachingEnabled = p.ai_coaching_enabled ?: true
        aiPersonality = p.ai_personality_preference ?: ""
        aiComplexity = p.ai_language_complexity ?: ""
        dataSharingConsent = p.data_sharing_consent ?: false
        aiTrainingConsent = p.ai_training_consent ?: false
        dobLocked = !p.date_of_birth.isNullOrBlank()
        gabLocked = !p.gender_at_birth.isNullOrBlank()
        btLocked = !p.blood_type.isNullOrBlank()
    }

    LaunchedEffect(Unit) {
        try {
            val p = ApiClient.getApiService().getCurrentUser()
            profile = p
            populateFields(p)
        } catch (e: Exception) {
            message = "Failed to load profile: ${e.message}"
        }
        loading = false
    }

    if (loading) {
        Box(modifier = Modifier.fillMaxSize(), contentAlignment = androidx.compose.ui.Alignment.Center) {
            CircularProgressIndicator()
        }
        return
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Profile") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                }
            )
        }
    ) { padding ->
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(padding)
            .padding(horizontal = 16.dp)
    ) {

        // Email (read-only)
        OutlinedTextField(
            value = profile?.email ?: "",
            onValueChange = {},
            label = { Text("Email") },
            readOnly = true,
            modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp)
        )

        // ── Identity ──
        SectionHeader("Identity")
        // Tap the face for the camera; the gallery is the long-press on the
        // button beside it. The subject — the patient's own face — is present
        // at the moment they tap, so the camera is the right default.
        Row(verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.fillMaxWidth().padding(bottom = 12.dp)) {
            AvatarImage(url = avatarUrl, name = fullName, userId = profile?.id ?: 0, size = 72.dp)
            Spacer(Modifier.width(12.dp))
            Column {
                TextButton(onClick = { if (!avatarBusy) avatarCamera.capture() }, enabled = !avatarBusy) {
                    Text(if (avatarBusy) "Uploading…" else if (avatarUrl != null) "Change Photo" else "Take Photo")
                }
                TextButton(onClick = { if (!avatarBusy) avatarPicker.launch("image/*") }, enabled = !avatarBusy) {
                    Text("Choose from Gallery")
                }
                if (avatarUrl != null) {
                    TextButton(onClick = {
                        if (avatarBusy) return@TextButton
                        avatarBusy = true
                        scope.launch {
                            try {
                                val u = ApiClient.getApiService().deleteAvatar()
                                avatarUrl = u.profile_picture_url
                            } catch (e: Exception) {
                                message = ErrorUtil.userMessage(e)
                            }
                            avatarBusy = false
                        }
                    }, enabled = !avatarBusy) { Text("Remove Photo") }
                }
            }
        }

        OutlinedTextField(value = firstName, onValueChange = { firstName = it },
            label = { Text("First Name") },
            isError = firstName.isNotEmpty() && firstName.trim().length < 3,
            modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp))
        OutlinedTextField(value = lastName, onValueChange = { lastName = it },
            label = { Text("Last Name") },
            isError = lastName.isNotEmpty() && lastName.trim().length < 3,
            modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp))
        OutlinedTextField(value = middleName, onValueChange = { middleName = it },
            label = { Text("Middle Name") },
            modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp))
        OutlinedTextField(value = namePrefix, onValueChange = { namePrefix = it },
            label = { Text("Prefix (Dr., Mrs., Chief)") },
            modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp))
        OutlinedTextField(value = nameSuffix, onValueChange = { nameSuffix = it },
            label = { Text("Suffix (Jr., III, RN)") },
            modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp))
        OutlinedTextField(
            value = dateOfBirth, onValueChange = { if (!dobLocked) dateOfBirth = it },
            label = { Text(if (dobLocked) "Date of Birth (locked)" else "Date of Birth") },
            readOnly = dobLocked, modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp),
            placeholder = { Text("YYYY-MM-DD") }
        )
        DropdownField("Gender Identity", gender, listOf("", "Male", "Female", "Non-binary", "Prefer not to say")) { gender = it }
        DropdownField(
            if (gabLocked) "Sex at Birth (locked)" else "Sex at Birth",
            genderAtBirth, listOf("", "Male", "Female", "Intersex"), enabled = !gabLocked
        ) { genderAtBirth = it }
        DropdownField(
            if (btLocked) "Blood Type (locked)" else "Blood Type",
            bloodType, listOf("", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"), enabled = !btLocked
        ) { bloodType = it }

        // ── Insurance ──
        SectionHeader("Insurance")
        OutlinedTextField(value = insuranceId, onValueChange = { insuranceId = it }, label = { Text("Insurance ID") }, modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp))
        OutlinedTextField(value = insuranceProvider, onValueChange = { insuranceProvider = it }, label = { Text("Provider") }, modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp))
        OutlinedTextField(value = insuranceCountry, onValueChange = { insuranceCountry = it }, label = { Text("Country") }, modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp))

        // ── Physical ──
        SectionHeader("Physical")
        OutlinedTextField(value = heightCm, onValueChange = { heightCm = it }, label = { Text("Height (cm)") }, modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp))
        OutlinedTextField(value = currentWeightKg, onValueChange = { currentWeightKg = it }, label = { Text("Current Weight (kg)") }, modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp))
        OutlinedTextField(value = targetWeightKg, onValueChange = { targetWeightKg = it }, label = { Text("Target Weight (kg)") }, modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp))

        // ── Location ──
        SectionHeader("Location & Preferences")
        OutlinedTextField(value = country, onValueChange = { country = it }, label = { Text("Country") }, modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp))
        OutlinedTextField(value = tz, onValueChange = { tz = it }, label = { Text("Timezone") }, modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp), placeholder = { Text("e.g. America/New_York") })
        DropdownField("Language", preferredLanguage, listOf("", "en", "fr", "es", "pt", "ar", "sw")) { preferredLanguage = it }
        DropdownField("Units", preferredUnits, listOf("", "metric", "imperial")) { preferredUnits = it }

        // ── Health ──
        SectionHeader("Health Profile")
        OutlinedTextField(value = allergies, onValueChange = { allergies = it }, label = { Text("Allergies") }, modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp))
        OutlinedTextField(value = foodIntolerances, onValueChange = { foodIntolerances = it }, label = { Text("Food Intolerances") }, modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp))
        OutlinedTextField(value = dietaryRestrictions, onValueChange = { dietaryRestrictions = it }, label = { Text("Dietary Restrictions") }, modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp))
        OutlinedTextField(value = dietaryPreferences, onValueChange = { dietaryPreferences = it }, label = { Text("Dietary Preferences") }, modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp))
        OutlinedTextField(value = familyHistory, onValueChange = { familyHistory = it }, label = { Text("Family History") }, modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp))

        // ── Fitness ──
        SectionHeader("Fitness")
        DropdownField("Activity Level", activityLevel, listOf("", "sedentary", "lightly_active", "moderately_active", "very_active", "extremely_active")) { activityLevel = it }
        OutlinedTextField(value = exercisePerWeek, onValueChange = { exercisePerWeek = it }, label = { Text("Exercise / Week") }, modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp))
        OutlinedTextField(value = fitnessGoals, onValueChange = { fitnessGoals = it }, label = { Text("Fitness Goals") }, modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp))
        OutlinedTextField(value = preferredActivities, onValueChange = { preferredActivities = it }, label = { Text("Preferred Activities") }, modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp))

        // ── Lifestyle ──
        SectionHeader("Lifestyle")
        OutlinedTextField(value = occupation, onValueChange = { occupation = it }, label = { Text("Occupation") }, modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp))
        DropdownField("Smoking", smokingStatus, listOf("", "never", "former", "current")) { smokingStatus = it }
        DropdownField("Alcohol", alcoholConsumption, listOf("", "none", "occasional", "moderate", "heavy")) { alcoholConsumption = it }
        DropdownField("Sleep", sleepSchedule, listOf("", "early_bird", "night_owl", "shift_worker")) { sleepSchedule = it }
        DropdownField("Stress", stressLevel, listOf("", "low", "moderate", "high")) { stressLevel = it }

        // ── AI Preferences ──
        SectionHeader("AI Preferences")
        Row(modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("AI Coaching", modifier = Modifier.padding(top = 12.dp))
            Switch(checked = aiCoachingEnabled, onCheckedChange = { aiCoachingEnabled = it })
        }
        DropdownField("Personality", aiPersonality, listOf("", "supportive", "motivational", "clinical", "casual")) { aiPersonality = it }
        DropdownField("Complexity", aiComplexity, listOf("", "simple", "moderate", "technical")) { aiComplexity = it }

        // ── Privacy ──
        SectionHeader("Privacy & Consent")
        Row(modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("Data Sharing Consent", modifier = Modifier.padding(top = 12.dp))
            Switch(checked = dataSharingConsent, onCheckedChange = { dataSharingConsent = it })
        }
        Row(modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("AI Training Consent", modifier = Modifier.padding(top = 12.dp))
            Switch(checked = aiTrainingConsent, onCheckedChange = { aiTrainingConsent = it })
        }

        if (message.isNotEmpty()) {
            Text(message, color = MaterialTheme.colorScheme.primary, modifier = Modifier.padding(vertical = 8.dp))
        }

        Button(
            onClick = {
                saving = true
                message = ""
                scope.launch {
                    try {
                        val req = UserUpdateRequest(
                            // The parts are what this form edits; the server
                            // recomputes full_name from them, so the two forms
                            // cannot drift apart.
                            first_name = firstName.trim().ifBlank { null },
                            last_name = lastName.trim().ifBlank { null },
                            middle_name = middleName.trim().ifBlank { null },
                            name_prefix = namePrefix.trim().ifBlank { null },
                            name_suffix = nameSuffix.trim().ifBlank { null },
                            gender = gender.ifBlank { null },
                            date_of_birth = if (!dobLocked) dateOfBirth.ifBlank { null } else null,
                            gender_at_birth = if (!gabLocked) genderAtBirth.ifBlank { null } else null,
                            blood_type = if (!btLocked) bloodType.ifBlank { null } else null,
                            insurance_id = insuranceId.ifBlank { null },
                            insurance_provider = insuranceProvider.ifBlank { null },
                            insurance_country = insuranceCountry.ifBlank { null },
                            height_cm = heightCm.toDoubleOrNull(),
                            current_weight_kg = currentWeightKg.toDoubleOrNull(),
                            target_weight_kg = targetWeightKg.toDoubleOrNull(),
                            country = country.ifBlank { null },
                            timezone = tz.ifBlank { null },
                            preferred_language = preferredLanguage.ifBlank { null },
                            preferred_units = preferredUnits.ifBlank { null },
                            allergies = allergies.ifBlank { null },
                            food_intolerances = foodIntolerances.ifBlank { null },
                            dietary_restrictions = dietaryRestrictions.ifBlank { null },
                            dietary_preferences = dietaryPreferences.ifBlank { null },
                            family_history = familyHistory.ifBlank { null },
                            activity_level = activityLevel.ifBlank { null },
                            exercise_frequency_per_week = exercisePerWeek.toIntOrNull(),
                            fitness_goals = fitnessGoals.ifBlank { null },
                            preferred_activities = preferredActivities.ifBlank { null },
                            occupation = occupation.ifBlank { null },
                            smoking_status = smokingStatus.ifBlank { null },
                            alcohol_consumption = alcoholConsumption.ifBlank { null },
                            sleep_schedule = sleepSchedule.ifBlank { null },
                            stress_level = stressLevel.ifBlank { null },
                            ai_coaching_enabled = aiCoachingEnabled,
                            ai_personality_preference = aiPersonality.ifBlank { null },
                            ai_language_complexity = aiComplexity.ifBlank { null },
                            data_sharing_consent = dataSharingConsent,
                            ai_training_consent = aiTrainingConsent
                        )
                        val updated = ApiClient.getApiService().updateUser(req)
                        populateFields(updated)
                        message = "Profile updated."
                    } catch (e: Exception) {
                        message = ErrorUtil.userMessage(e)
                    }
                    saving = false
                }
            },
            modifier = Modifier.fillMaxWidth().padding(top = 16.dp),
            enabled = !saving
        ) {
            Text(if (saving) "Saving..." else "Save Profile")
        }

        Spacer(modifier = Modifier.height(32.dp))
    }
}
}

@Composable
fun SectionHeader(title: String) {
    Text(
        text = title,
        style = MaterialTheme.typography.titleMedium,
        color = MaterialTheme.colorScheme.primary,
        modifier = Modifier.padding(top = 16.dp, bottom = 8.dp)
    )
    HorizontalDivider(modifier = Modifier.padding(bottom = 8.dp))
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DropdownField(
    label: String,
    selected: String,
    options: List<String>,
    enabled: Boolean = true,
    onSelect: (String) -> Unit
) {
    var expanded by remember { mutableStateOf(false) }
    ExposedDropdownMenuBox(
        expanded = expanded && enabled,
        onExpandedChange = { if (enabled) expanded = !expanded },
        modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp)
    ) {
        OutlinedTextField(
            value = if (selected.isBlank()) "—" else selected.replace("_", " ").replaceFirstChar { it.uppercase() },
            onValueChange = {},
            readOnly = true,
            label = { Text(label) },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) },
            modifier = Modifier.menuAnchor().fillMaxWidth(),
            enabled = enabled
        )
        ExposedDropdownMenu(expanded = expanded && enabled, onDismissRequest = { expanded = false }) {
            options.forEach { option ->
                DropdownMenuItem(
                    text = { Text(if (option.isBlank()) "—" else option.replace("_", " ").replaceFirstChar { it.uppercase() }) },
                    onClick = {
                        onSelect(option)
                        expanded = false
                    }
                )
            }
        }
    }
}
