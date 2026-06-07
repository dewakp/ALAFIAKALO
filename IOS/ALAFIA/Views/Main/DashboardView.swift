import SwiftUI

struct DashboardView: View {
    @EnvironmentObject var authManager: AuthManager
    @State private var showProfile = false
    
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    // Greeting
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Welcome back,")
                            .font(.title3)
                            .foregroundStyle(.secondary)
                        Text(authManager.currentUser?.firstName ?? "")
                            .font(.largeTitle)
                            .fontWeight(.bold)
                    }
                    .padding(.horizontal)
                    
                    // Quick Stats Grid
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                        NavigationLink { NutritionView() } label: {
                            StatCard(icon: "leaf.fill", title: "Nutrition", subtitle: "Track meals & macros", color: .green)
                        }
                        .buttonStyle(.plain)

                        NavigationLink { FitnessView() } label: {
                            StatCard(icon: "figure.run", title: "Fitness", subtitle: "Log workouts", color: .blue)
                        }
                        .buttonStyle(.plain)

                        NavigationLink { LabsView() } label: {
                            StatCard(icon: "flask.fill", title: "Labs", subtitle: "Store results", color: .purple)
                        }
                        .buttonStyle(.plain)

                        NavigationLink { MedicationsView() } label: {
                            StatCard(icon: "pills.fill", title: "Medications", subtitle: "Manage Rx", color: .orange)
                        }
                        .buttonStyle(.plain)

                        NavigationLink { MoodView() } label: {
                            StatCard(icon: "brain", title: "Mood", subtitle: "Mental health", color: .pink)
                        }
                        .buttonStyle(.plain)

                        NavigationLink { LifestyleView() } label: {
                            StatCard(icon: "heart.fill", title: "Lifestyle", subtitle: "Vitals & habits", color: .red)
                        }
                        .buttonStyle(.plain)
                    }
                    .padding(.horizontal)
                    
                    // Info Card
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Your Holistic Health Journey")
                            .font(.headline)
                        Text("ALAFIA helps you track nutrition, fitness, lab results, medications, mood, and lifestyle — all in one place. Use the AI assistant for personalized health insights.")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    .padding()
                    .background(Color(.systemBackground))
                    .cornerRadius(16)
                    .shadow(color: .black.opacity(0.04), radius: 8, y: 2)
                    .padding(.horizontal)
                }
                .padding(.vertical)
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("ALAFIA")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        showProfile = true
                    } label: {
                        Image(systemName: "person.circle")
                            .font(.title3)
                    }
                }
            }
            .sheet(isPresented: $showProfile) {
                ProfileSheet()
            }
        }
    }
}

struct ProfileSheet: View {
    @EnvironmentObject var authManager: AuthManager
    @Environment(\.dismiss) var dismiss

    // ── Identity ──
    @State private var fullName = ""
    @State private var dateOfBirth = ""
    @State private var gender = ""
    @State private var genderAtBirth = ""
    @State private var bloodType = ""

    // ── Insurance ──
    @State private var insuranceId = ""
    @State private var insuranceProvider = ""
    @State private var insuranceCountry = ""

    // ── Physical ──
    @State private var heightCm = ""
    @State private var currentWeightKg = ""
    @State private var targetWeightKg = ""

    // ── Location ──
    @State private var country = ""
    @State private var tz = ""
    @State private var preferredLanguage = ""
    @State private var preferredUnits = ""

    // ── Health ──
    @State private var allergies = ""
    @State private var foodIntolerances = ""
    @State private var dietaryRestrictions = ""
    @State private var dietaryPreferences = ""
    @State private var familyHistory = ""

    // ── Fitness ──
    @State private var activityLevel = ""
    @State private var exercisePerWeek = ""
    @State private var fitnessGoals = ""
    @State private var preferredActivities = ""

    // ── Lifestyle ──
    @State private var occupation = ""
    @State private var smokingStatus = ""
    @State private var alcoholConsumption = ""
    @State private var sleepSchedule = ""
    @State private var stressLevel = ""

    // ── AI ──
    @State private var aiCoachingEnabled = true
    @State private var aiPersonality = ""
    @State private var aiComplexity = ""

    // ── Privacy ──
    @State private var dataSharingConsent = false
    @State private var aiTrainingConsent = false

    // ── UI State ──
    @State private var isSaving = false
    @State private var message: String?

    // Track immutable fields already set
    @State private var dobLocked = false
    @State private var genderAtBirthLocked = false
    @State private var bloodTypeLocked = false

    private let genderOptions = ["", "Male", "Female", "Non-binary", "Prefer not to say"]
    private let sexAtBirthOptions = ["", "Male", "Female", "Intersex"]
    private let bloodOptions = ["", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
    private let unitOptions = ["", "metric", "imperial"]
    private let langOptions = ["", "en", "fr", "es", "pt", "ar", "sw"]
    private let activityOptions = ["", "sedentary", "lightly_active", "moderately_active", "very_active", "extremely_active"]
    private let smokingOptions = ["", "never", "former", "current"]
    private let alcoholOptions = ["", "none", "occasional", "moderate", "heavy"]
    private let sleepOptions = ["", "early_bird", "night_owl", "shift_worker"]
    private let stressOptions = ["", "low", "moderate", "high"]
    private let personalityOptions = ["", "supportive", "motivational", "clinical", "casual"]
    private let complexityOptions = ["", "simple", "moderate", "technical"]

    var body: some View {
        NavigationStack {
            Form {
                // ── Header ──
                Section {
                    HStack(spacing: 16) {
                        Image(systemName: "person.crop.circle.fill")
                            .font(.system(size: 56))
                            .foregroundStyle(.green)
                        VStack(alignment: .leading) {
                            Text(authManager.currentUser?.fullName ?? "")
                                .font(.headline)
                            Text(authManager.currentUser?.email ?? "")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                        }
                    }
                    .padding(.vertical, 8)
                }

                // ── Identity ──
                Section("Identity") {
                    LKTextField(title: "Full Name", text: $fullName)
                    LKTextField(title: dobLocked ? "Date of Birth (locked)" : "Date of Birth", text: $dateOfBirth)
                        .disabled(dobLocked)
                    Picker("Gender Identity", selection: $gender) {
                        ForEach(genderOptions, id: \.self) { Text($0.isEmpty ? "—" : $0) }
                    }
                    Picker(genderAtBirthLocked ? "Sex at Birth (locked)" : "Sex at Birth", selection: $genderAtBirth) {
                        ForEach(sexAtBirthOptions, id: \.self) { Text($0.isEmpty ? "—" : $0) }
                    }
                    .disabled(genderAtBirthLocked)
                    Picker(bloodTypeLocked ? "Blood Type (locked)" : "Blood Type", selection: $bloodType) {
                        ForEach(bloodOptions, id: \.self) { Text($0.isEmpty ? "—" : $0) }
                    }
                    .disabled(bloodTypeLocked)
                }

                // ── Insurance ──
                Section("Insurance") {
                    LKTextField(title: "Insurance ID", text: $insuranceId)
                    LKTextField(title: "Provider", text: $insuranceProvider)
                    LKTextField(title: "Country", text: $insuranceCountry)
                }

                // ── Physical ──
                Section("Physical") {
                    LKTextField(title: "Height (cm)", text: $heightCm)
                        .keyboardType(.decimalPad)
                    LKTextField(title: "Current Weight (kg)", text: $currentWeightKg)
                        .keyboardType(.decimalPad)
                    LKTextField(title: "Target Weight (kg)", text: $targetWeightKg)
                        .keyboardType(.decimalPad)
                }

                // ── Location ──
                Section("Location & Preferences") {
                    LKTextField(title: "Country", text: $country)
                    LKTextField(title: "Timezone", text: $tz)
                    Picker("Language", selection: $preferredLanguage) {
                        ForEach(langOptions, id: \.self) { Text($0.isEmpty ? "—" : $0.uppercased()) }
                    }
                    Picker("Units", selection: $preferredUnits) {
                        ForEach(unitOptions, id: \.self) { Text($0.isEmpty ? "—" : $0.capitalized) }
                    }
                }

                // ── Health Profile ──
                Section("Health Profile") {
                    LKTextField(title: "Allergies", text: $allergies)
                    LKTextField(title: "Food Intolerances", text: $foodIntolerances)
                    LKTextField(title: "Dietary Restrictions", text: $dietaryRestrictions)
                    LKTextField(title: "Dietary Preferences", text: $dietaryPreferences)
                    LKTextField(title: "Family History", text: $familyHistory)
                }

                // ── Fitness ──
                Section("Fitness") {
                    Picker("Activity Level", selection: $activityLevel) {
                        ForEach(activityOptions, id: \.self) { Text($0.isEmpty ? "—" : $0.replacingOccurrences(of: "_", with: " ").capitalized) }
                    }
                    LKTextField(title: "Exercise / Week", text: $exercisePerWeek)
                        .keyboardType(.numberPad)
                    LKTextField(title: "Goals", text: $fitnessGoals)
                    LKTextField(title: "Preferred Activities", text: $preferredActivities)
                }

                // ── Lifestyle ──
                Section("Lifestyle") {
                    LKTextField(title: "Occupation", text: $occupation)
                    Picker("Smoking", selection: $smokingStatus) {
                        ForEach(smokingOptions, id: \.self) { Text($0.isEmpty ? "—" : $0.capitalized) }
                    }
                    Picker("Alcohol", selection: $alcoholConsumption) {
                        ForEach(alcoholOptions, id: \.self) { Text($0.isEmpty ? "—" : $0.capitalized) }
                    }
                    Picker("Sleep", selection: $sleepSchedule) {
                        ForEach(sleepOptions, id: \.self) { Text($0.isEmpty ? "—" : $0.replacingOccurrences(of: "_", with: " ").capitalized) }
                    }
                    Picker("Stress", selection: $stressLevel) {
                        ForEach(stressOptions, id: \.self) { Text($0.isEmpty ? "—" : $0.capitalized) }
                    }
                }

                // ── AI Preferences ──
                Section("AI Preferences") {
                    Toggle("AI Coaching", isOn: $aiCoachingEnabled)
                    Picker("Personality", selection: $aiPersonality) {
                        ForEach(personalityOptions, id: \.self) { Text($0.isEmpty ? "—" : $0.capitalized) }
                    }
                    Picker("Complexity", selection: $aiComplexity) {
                        ForEach(complexityOptions, id: \.self) { Text($0.isEmpty ? "—" : $0.capitalized) }
                    }
                }

                // ── Privacy ──
                Section("Privacy & Consent") {
                    Toggle("Data Sharing Consent", isOn: $dataSharingConsent)
                    Toggle("AI Training Consent", isOn: $aiTrainingConsent)
                }

                // ── Message & Logout ──
                if let message {
                    Section {
                        Text(message)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                Section {
                    Button(role: .destructive) {
                        authManager.logout()
                        dismiss()
                    } label: {
                        Label("Sign Out", systemImage: "rectangle.portrait.and.arrow.right")
                    }
                }
            }
            .navigationTitle("Profile")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
                ToolbarItem(placement: .topBarLeading) {
                    Button(isSaving ? "Saving..." : "Save") { saveProfile() }
                        .disabled(isSaving)
                }
            }
            .task { loadFields() }
        }
    }

    private func loadFields() {
        guard let u = authManager.currentUser else { return }
        fullName = u.fullName
        dateOfBirth = u.dateOfBirth ?? ""
        gender = u.gender ?? ""
        genderAtBirth = u.genderAtBirth ?? ""
        bloodType = u.bloodType ?? ""
        insuranceId = u.insuranceId ?? ""
        insuranceProvider = u.insuranceProvider ?? ""
        insuranceCountry = u.insuranceCountry ?? ""
        heightCm = u.heightCm.map { String($0) } ?? ""
        currentWeightKg = u.currentWeightKg.map { String($0) } ?? ""
        targetWeightKg = u.targetWeightKg.map { String($0) } ?? ""
        country = u.country ?? ""
        tz = u.timezone ?? ""
        preferredLanguage = u.preferredLanguage ?? ""
        preferredUnits = u.preferredUnits ?? ""
        allergies = u.allergies ?? ""
        foodIntolerances = u.foodIntolerances ?? ""
        dietaryRestrictions = u.dietaryRestrictions ?? ""
        dietaryPreferences = u.dietaryPreferences ?? ""
        familyHistory = u.familyHistory ?? ""
        activityLevel = u.activityLevel ?? ""
        exercisePerWeek = u.exerciseFrequencyPerWeek.map { String($0) } ?? ""
        fitnessGoals = u.fitnessGoals ?? ""
        preferredActivities = u.preferredActivities ?? ""
        occupation = u.occupation ?? ""
        smokingStatus = u.smokingStatus ?? ""
        alcoholConsumption = u.alcoholConsumption ?? ""
        sleepSchedule = u.sleepSchedule ?? ""
        stressLevel = u.stressLevel ?? ""
        aiCoachingEnabled = u.aiCoachingEnabled ?? true
        aiPersonality = u.aiPersonalityPreference ?? ""
        aiComplexity = u.aiLanguageComplexity ?? ""
        dataSharingConsent = u.dataSharingConsent ?? false
        aiTrainingConsent = u.aiTrainingConsent ?? false

        // Lock immutable fields that already have values
        dobLocked = !(u.dateOfBirth ?? "").isEmpty
        genderAtBirthLocked = !(u.genderAtBirth ?? "").isEmpty
        bloodTypeLocked = !(u.bloodType ?? "").isEmpty
    }

    private func saveProfile() {
        isSaving = true
        message = nil
        Task {
            do {
                var payload = UserUpdate()
                payload.fullName = fullName.isEmpty ? nil : fullName
                if !dobLocked { payload.dateOfBirth = dateOfBirth.isEmpty ? nil : dateOfBirth }
                payload.gender = gender.isEmpty ? nil : gender
                if !genderAtBirthLocked { payload.genderAtBirth = genderAtBirth.isEmpty ? nil : genderAtBirth }
                if !bloodTypeLocked { payload.bloodType = bloodType.isEmpty ? nil : bloodType }
                payload.insuranceId = insuranceId.isEmpty ? nil : insuranceId
                payload.insuranceProvider = insuranceProvider.isEmpty ? nil : insuranceProvider
                payload.insuranceCountry = insuranceCountry.isEmpty ? nil : insuranceCountry
                payload.heightCm = Double(heightCm)
                payload.currentWeightKg = Double(currentWeightKg)
                payload.targetWeightKg = Double(targetWeightKg)
                payload.country = country.isEmpty ? nil : country
                payload.timezone = tz.isEmpty ? nil : tz
                payload.preferredLanguage = preferredLanguage.isEmpty ? nil : preferredLanguage
                payload.preferredUnits = preferredUnits.isEmpty ? nil : preferredUnits
                payload.allergies = allergies.isEmpty ? nil : allergies
                payload.foodIntolerances = foodIntolerances.isEmpty ? nil : foodIntolerances
                payload.dietaryRestrictions = dietaryRestrictions.isEmpty ? nil : dietaryRestrictions
                payload.dietaryPreferences = dietaryPreferences.isEmpty ? nil : dietaryPreferences
                payload.familyHistory = familyHistory.isEmpty ? nil : familyHistory
                payload.activityLevel = activityLevel.isEmpty ? nil : activityLevel
                payload.exerciseFrequencyPerWeek = Int(exercisePerWeek)
                payload.fitnessGoals = fitnessGoals.isEmpty ? nil : fitnessGoals
                payload.preferredActivities = preferredActivities.isEmpty ? nil : preferredActivities
                payload.occupation = occupation.isEmpty ? nil : occupation
                payload.smokingStatus = smokingStatus.isEmpty ? nil : smokingStatus
                payload.alcoholConsumption = alcoholConsumption.isEmpty ? nil : alcoholConsumption
                payload.sleepSchedule = sleepSchedule.isEmpty ? nil : sleepSchedule
                payload.stressLevel = stressLevel.isEmpty ? nil : stressLevel
                payload.aiCoachingEnabled = aiCoachingEnabled
                payload.aiPersonalityPreference = aiPersonality.isEmpty ? nil : aiPersonality
                payload.aiLanguageComplexity = aiComplexity.isEmpty ? nil : aiComplexity
                payload.dataSharingConsent = dataSharingConsent
                payload.aiTrainingConsent = aiTrainingConsent

                let user: User = try await APIClient.shared.patch("/users/me", body: payload)
                authManager.currentUser = user
                message = "Saved"
                // Re-lock immutable fields
                dobLocked = !(user.dateOfBirth ?? "").isEmpty
                genderAtBirthLocked = !(user.genderAtBirth ?? "").isEmpty
                bloodTypeLocked = !(user.bloodType ?? "").isEmpty
            } catch {
                message = error.localizedDescription
            }
            isSaving = false
        }
    }
}
