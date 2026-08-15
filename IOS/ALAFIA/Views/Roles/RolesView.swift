import SwiftUI

// MARK: - Main Roles View

struct RolesView: View {
    @EnvironmentObject private var authManager: AuthManager
    @EnvironmentObject private var clinicianMode: ClinicianMode
    @State private var persona: UserPersonaSummary?
    @State private var catalog: [RoleCategoryInfo] = []
    @State private var loading = true
    @State private var error: String?
    @State private var selectedTab = 0  // 0=overview, 1=add
    @State private var editingRole: RoleAssignment?
    
    var body: some View {
            Group {
                if loading {
                    ProgressView("Loading roles...")
                } else if let error {
                    VStack(spacing: 12) {
                        Image(systemName: "exclamationmark.triangle")
                            .font(.largeTitle).foregroundStyle(.orange)
                        Text(error).foregroundStyle(.secondary)
                        Button("Retry") { Task { await loadAll() } }
                            .buttonStyle(.borderedProminent).tint(.green)
                    }
                } else if let persona {
                    mainContent(persona)
                }
            }
            .navigationTitle("Role")
            .task { await loadAll() }
            .sheet(item: $editingRole) { role in
                ProfessionalProfileEditor(roleAssignment: role) {
                    Task { await loadAll() }
                }
            }
    }
    
    @ViewBuilder
    private func mainContent(_ persona: UserPersonaSummary) -> some View {
        ScrollView {
            VStack(spacing: 16) {
                personaSummaryCard(persona)
                
                Picker("", selection: $selectedTab) {
                    Text("My Roles").tag(0)
                    Text("Add Role").tag(1)
                }
                .pickerStyle(.segmented)
                .padding(.horizontal)
                
                if selectedTab == 0 {
                    myRolesSection(persona)
                } else {
                    addRoleSection(persona)
                }
            }
            .padding()
        }
    }
    
    // MARK: - Persona Summary Card
    
    private func personaSummaryCard(_ persona: UserPersonaSummary) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 14) {
                ZStack {
                    Circle()
                        .fill(Color.green.opacity(0.15))
                        .frame(width: 56, height: 56)
                    Image(systemName: persona.isHealthcareProfessional ? "stethoscope" : "person.fill")
                        .font(.title2)
                        .foregroundStyle(.green)
                }
                
                VStack(alignment: .leading, spacing: 2) {
                    Text(persona.fullName)
                        .font(.headline)
                    Text(persona.email)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                
                Spacer()
                
                VStack(alignment: .trailing, spacing: 4) {
                    Text(persona.primaryRole.replacingOccurrences(of: "_", with: " ").uppercased())
                        .font(.caption2).fontWeight(.bold)
                        .padding(.horizontal, 10).padding(.vertical, 3)
                        .background(Color.green).foregroundStyle(.white)
                        .clipShape(Capsule())
                    
                    if persona.isHealthcareProfessional {
                        Text("Healthcare Pro")
                            .font(.caption2).fontWeight(.semibold)
                            .padding(.horizontal, 8).padding(.vertical, 2)
                            .background(Color.blue.opacity(0.15))
                            .foregroundStyle(.blue)
                            .clipShape(Capsule())
                    }
                }
            }
            
            // Active roles
            VStack(alignment: .leading, spacing: 6) {
                Text("Active Roles").font(.caption).foregroundStyle(.secondary)
                FlowLayoutRoles(spacing: 6) {
                    ForEach(persona.activeRoles, id: \.self) { r in
                        Text(r.replacingOccurrences(of: "_", with: " "))
                            .font(.caption2).fontWeight(.medium)
                            .padding(.horizontal, 10).padding(.vertical, 4)
                            .background(Color.green.opacity(0.1))
                            .foregroundStyle(.green)
                            .clipShape(Capsule())
                            .overlay(Capsule().stroke(Color.green.opacity(0.3), lineWidth: 1))
                    }
                }
            }
            
            // Categories
            if !persona.roleCategories.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Categories").font(.caption).foregroundStyle(.secondary)
                    FlowLayoutRoles(spacing: 6) {
                        ForEach(persona.roleCategories, id: \.self) { cat in
                            Label(
                                cat.replacingOccurrences(of: "_", with: " "),
                                systemImage: roleCategoryIcons[cat] ?? "person.fill"
                            )
                            .font(.caption2).fontWeight(.medium)
                            .padding(.horizontal, 8).padding(.vertical, 4)
                            .background(Color(.systemGray5))
                            .clipShape(Capsule())
                        }
                    }
                }
            }
            
            // Permissions (collapsible)
            if !persona.permissions.isEmpty {
                DisclosureGroup {
                    FlowLayoutRoles(spacing: 4) {
                        ForEach(persona.permissions, id: \.self) { perm in
                            Text(perm.replacingOccurrences(of: "_", with: " "))
                                .font(.caption2)
                                .padding(.horizontal, 6).padding(.vertical, 2)
                                .background(Color(.systemGray6))
                                .clipShape(RoundedRectangle(cornerRadius: 4))
                        }
                    }
                } label: {
                    Text("Permissions (\(persona.permissions.count))")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .shadow(color: .black.opacity(0.06), radius: 8, y: 2)
    }
    
    // MARK: - My Roles Section
    
    private func myRolesSection(_ persona: UserPersonaSummary) -> some View {
        VStack(spacing: 12) {
            // Patient (always present)
            HStack(spacing: 14) {
                Image(systemName: "person.fill")
                    .font(.title2).foregroundStyle(.green)
                    .frame(width: 44, height: 44)
                    .background(Color.green.opacity(0.1))
                    .clipShape(Circle())
                
                VStack(alignment: .leading) {
                    Text("Patient").font(.headline)
                    Text("Core role — always active")
                        .font(.caption).foregroundStyle(.secondary)
                }
                
                Spacer()
                
                Text("ALWAYS")
                    .font(.caption2).fontWeight(.bold)
                    .padding(.horizontal, 8).padding(.vertical, 3)
                    .background(Color(.systemGray4))
                    .foregroundStyle(.white).clipShape(Capsule())
            }
            .padding()
            .background(Color(.systemBackground))
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .shadow(color: .black.opacity(0.04), radius: 4, y: 1)
            
            // Professional roles
            ForEach(persona.roleDetails) { rd in
                roleCard(rd)
            }
            
            if persona.roleDetails.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "person.badge.plus")
                        .font(.largeTitle).foregroundStyle(.secondary)
                    Text("No professional roles")
                        .foregroundStyle(.secondary)
                    Text("Switch to the 'Add Role' tab to add your professional roles.")
                        .font(.caption).foregroundStyle(.tertiary).multilineTextAlignment(.center)
                }
                .padding(32)
            }
        }
    }
    
    private func roleCard(_ rd: RoleAssignment) -> some View {
        let catIcon = catalog.first(where: { $0.roles.contains(where: { $0.id == rd.role }) })?.id ?? ""
        
        return VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 12) {
                Image(systemName: roleCategoryIcons[catIcon] ?? "person.fill")
                    .font(.title3).foregroundStyle(.blue)
                    .frame(width: 40, height: 40)
                    .background(Color.blue.opacity(0.1))
                    .clipShape(Circle())
                
                VStack(alignment: .leading, spacing: 2) {
                    Text(rd.displayName).font(.subheadline).fontWeight(.semibold)
                    HStack(spacing: 6) {
                        if rd.isPrimary {
                            Text("PRIMARY").font(.caption2).fontWeight(.bold)
                                .padding(.horizontal, 6).padding(.vertical, 2)
                                .background(Color.blue).foregroundStyle(.white)
                                .clipShape(Capsule())
                        }
                        Text(rd.isActive ? "Active" : "Inactive")
                            .font(.caption2).fontWeight(.medium)
                            .padding(.horizontal, 6).padding(.vertical, 2)
                            .background(rd.isActive ? Color.green.opacity(0.15) : Color.gray.opacity(0.15))
                            .foregroundStyle(rd.isActive ? .green : .gray)
                            .clipShape(Capsule())
                        if let vs = rd.professionalProfile?.verificationStatus {
                            Text(vs.capitalized)
                                .font(.caption2).fontWeight(.medium)
                                .padding(.horizontal, 6).padding(.vertical, 2)
                                .background(verificationColor(vs).opacity(0.15))
                                .foregroundStyle(verificationColor(vs))
                                .clipShape(Capsule())
                        }
                    }
                }
                
                Spacer()
            }
            
            // Profile summary
            if let prof = rd.professionalProfile {
                let details = [
                    prof.specialty,
                    prof.practiceName,
                    prof.yearsOfExperience.map { "\($0) yrs exp" },
                ].compactMap { $0 }
                if !details.isEmpty {
                    Text(details.joined(separator: " • "))
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            
            // Actions
            HStack(spacing: 10) {
                // Acting on a clinical role switches the whole app into
                // clinician mode and lands on the patient grid, rather than
                // pushing a screen inside the patient tab bar.
                if rd.isActive && ClinicianRoles.all.contains(rd.role) {
                    Button {
                        clinicianMode.enter(as: authManager.currentUser)
                    } label: {
                        Label("Open Clinician View", systemImage: "stethoscope")
                            .font(.caption)
                    }
                    .buttonStyle(.borderedProminent).tint(.blue).controlSize(.small)
                }

                if !rd.isPrimary {
                    Button {
                        Task { await setPrimary(rd.id) }
                    } label: {
                        Label("Set Primary", systemImage: "star")
                            .font(.caption)
                    }
                    .buttonStyle(.bordered).tint(.orange).controlSize(.small)
                }
                
                Button {
                    editingRole = rd
                } label: {
                    Label(rd.professionalProfile != nil ? "Edit Profile" : "Add Profile",
                          systemImage: "pencil")
                        .font(.caption)
                }
                .buttonStyle(.bordered).tint(.green).controlSize(.small)
                
                Spacer()
                
                Button(role: .destructive) {
                    Task { await removeRole(rd.id) }
                } label: {
                    Label("Remove", systemImage: "trash")
                        .font(.caption)
                }
                .buttonStyle(.bordered).controlSize(.small)
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .shadow(color: .black.opacity(0.04), radius: 4, y: 1)
    }
    
    // MARK: - Add Role Section
    
    @State private var searchText = ""
    @State private var selectedCategoryFilter = ""
    
    private func addRoleSection(_ persona: UserPersonaSummary) -> some View {
        let existingRoles = Set(persona.activeRoles)
        let filteredCats = catalog
            .filter { selectedCategoryFilter.isEmpty || $0.id == selectedCategoryFilter }
            .map { cat in
                RoleCategoryInfo(
                    id: cat.id, name: cat.name,
                    roles: cat.roles.filter { !existingRoles.contains($0.id) &&
                        (searchText.isEmpty || $0.name.localizedCaseInsensitiveContains(searchText))
                    }
                )
            }
            .filter { !$0.roles.isEmpty }
        
        return VStack(spacing: 12) {
            // Search & filter
            HStack(spacing: 10) {
                HStack {
                    Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                    TextField("Search roles...", text: $searchText)
                        .textFieldStyle(.plain)
                }
                .padding(8)
                .background(Color(.systemGray6))
                .clipShape(RoundedRectangle(cornerRadius: 10))
                
                Menu {
                    Button("All Categories") { selectedCategoryFilter = "" }
                    Divider()
                    ForEach(catalog) { cat in
                        Button(cat.name) { selectedCategoryFilter = cat.id }
                    }
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "line.3.horizontal.decrease.circle")
                        Text(selectedCategoryFilter.isEmpty ? "All" :
                                selectedCategoryFilter.replacingOccurrences(of: "_", with: " ").capitalized)
                            .lineLimit(1)
                    }
                    .font(.caption)
                    .padding(.horizontal, 10).padding(.vertical, 8)
                    .background(Color(.systemGray6))
                    .clipShape(RoundedRectangle(cornerRadius: 10))
                }
            }
            
            // Categories with roles
            ForEach(filteredCats) { cat in
                VStack(alignment: .leading, spacing: 8) {
                    Label(cat.name, systemImage: roleCategoryIcons[cat.id] ?? "person.fill")
                        .font(.subheadline).fontWeight(.semibold)
                        .foregroundStyle(.secondary)
                    
                    LazyVGrid(columns: [
                        GridItem(.flexible(), spacing: 8),
                        GridItem(.flexible(), spacing: 8),
                    ], spacing: 8) {
                        ForEach(cat.roles) { role in
                            Button {
                                Task { await addRole(role.id) }
                            } label: {
                                HStack {
                                    Text(role.name)
                                        .font(.caption)
                                        .lineLimit(1)
                                    Spacer()
                                    Image(systemName: "plus.circle.fill")
                                        .font(.caption)
                                }
                                .padding(.horizontal, 10).padding(.vertical, 8)
                                .background(Color(.systemBackground))
                                .clipShape(RoundedRectangle(cornerRadius: 8))
                                .shadow(color: .black.opacity(0.04), radius: 2, y: 1)
                            }
                            .buttonStyle(.plain)
                            .foregroundStyle(.primary)
                        }
                    }
                }
                .padding(.vertical, 4)
            }
            
            if filteredCats.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "checkmark.circle")
                        .font(.largeTitle).foregroundStyle(.green)
                    Text(searchText.isEmpty && selectedCategoryFilter.isEmpty
                         ? "All available roles have been added."
                         : "No matching roles found.")
                        .foregroundStyle(.secondary)
                }
                .padding(32)
            }
        }
    }
    
    // MARK: - Actions
    
    private func loadAll() async {
        loading = true
        error = nil
        do {
            async let p: UserPersonaSummary = APIClient.shared.get("/users/roles/me")
            async let c: [RoleCategoryInfo] = APIClient.shared.get("/users/roles/catalog")
            persona = try await p
            catalog = try await c
        } catch {
            self.error = error.localizedDescription
        }
        loading = false
    }
    
    private func addRole(_ roleId: String) async {
        let isPrimary = persona?.activeRoles.count ?? 0 <= 1
        let body = RoleAssignmentCreate(role: roleId, isPrimary: isPrimary)
        do {
            let _: RoleAssignment = try await APIClient.shared.post("/users/roles", body: body)
            await loadAll()
        } catch {
            self.error = error.localizedDescription
        }
    }
    
    private func removeRole(_ roleId: Int) async {
        do {
            try await APIClient.shared.delete("/users/roles/\(roleId)")
            await loadAll()
        } catch {
            self.error = error.localizedDescription
        }
    }
    
    private func setPrimary(_ roleId: Int) async {
        do {
            let _: RoleAssignment = try await APIClient.shared.putNoBody("/users/roles/\(roleId)/primary")
            await loadAll()
        } catch {
            self.error = error.localizedDescription
        }
    }
    
    private func verificationColor(_ status: String) -> Color {
        switch status {
        case "verified": return .green
        case "pending": return .orange
        case "rejected": return .red
        case "expired": return .gray
        default: return .secondary
        }
    }
}

// MARK: - Professional Profile Editor Sheet

struct ProfessionalProfileEditor: View {
    let roleAssignment: RoleAssignment
    let onSave: () -> Void
    @Environment(\.dismiss) private var dismiss
    
    @State private var licenseNumber = ""
    @State private var licenseState = ""
    @State private var licenseCountry = ""
    @State private var licenseExpiry = ""
    @State private var npiNumber = ""
    @State private var deaNumber = ""
    @State private var boardCerts = ""
    @State private var medicalSchool = ""
    @State private var degree = ""
    @State private var graduationYear = ""
    @State private var residencyProgram = ""
    @State private var fellowshipProgram = ""
    @State private var specialty = ""
    @State private var subSpecialty = ""
    @State private var yearsOfExperience = ""
    @State private var practiceName = ""
    @State private var practiceType = ""
    @State private var practiceAddress = ""
    @State private var practicePhone = ""
    @State private var practiceEmail = ""
    @State private var practiceWebsite = ""
    @State private var acceptingPatients = false
    @State private var hospitalAffiliations = ""
    @State private var department = ""
    @State private var titleField = ""
    @State private var clinicalLanguages = ""
    @State private var telemedicineAvailable = false
    @State private var telemedicinePlatforms = ""
    @State private var professionalBio = ""
    @State private var publicationsField = ""
    @State private var researchInterests = ""
    
    @State private var saving = false
    @State private var message = ""
    
    var body: some View {
        NavigationStack {
            Form {
                Section("Credentials & Licensing") {
                    TextField("License Number", text: $licenseNumber)
                    TextField("License State", text: $licenseState)
                    TextField("License Country", text: $licenseCountry)
                    TextField("License Expiry (YYYY-MM-DD)", text: $licenseExpiry)
                    TextField("NPI Number", text: $npiNumber)
                    TextField("DEA Number", text: $deaNumber)
                    TextField("Board Certifications (comma-separated)", text: $boardCerts)
                }
                
                Section("Education & Training") {
                    TextField("Medical School / Institution", text: $medicalSchool)
                    TextField("Degree (e.g. MD, DO, DNP)", text: $degree)
                    TextField("Graduation Year", text: $graduationYear)
                        .keyboardType(.numberPad)
                    TextField("Residency Program", text: $residencyProgram)
                    TextField("Fellowship Program", text: $fellowshipProgram)
                }
                
                Section("Specialty & Practice") {
                    TextField("Specialty", text: $specialty)
                    TextField("Sub-specialty", text: $subSpecialty)
                    TextField("Years of Experience", text: $yearsOfExperience)
                        .keyboardType(.numberPad)
                    TextField("Practice Name", text: $practiceName)
                    Picker("Practice Type", selection: $practiceType) {
                        Text("Select...").tag("")
                        Text("Solo Practice").tag("solo")
                        Text("Group Practice").tag("group")
                        Text("Hospital").tag("hospital")
                        Text("Clinic").tag("clinic")
                        Text("Academic/Teaching").tag("academic")
                        Text("Government").tag("government")
                        Text("Telehealth Only").tag("telehealth")
                        Text("Community Health Center").tag("community_health")
                        Text("Research Institution").tag("research")
                    }
                    TextField("Practice Address", text: $practiceAddress)
                    TextField("Practice Phone", text: $practicePhone)
                        .keyboardType(.phonePad)
                    TextField("Practice Email", text: $practiceEmail)
                        .keyboardType(.emailAddress)
                    TextField("Practice Website", text: $practiceWebsite)
                    Toggle("Accepting Patients", isOn: $acceptingPatients)
                }
                
                Section("Hospital & Affiliations") {
                    TextField("Hospital Affiliations (comma-separated)", text: $hospitalAffiliations)
                    TextField("Department", text: $department)
                    TextField("Title (e.g. Chief of Surgery)", text: $titleField)
                }
                
                Section("Languages & Telemedicine") {
                    TextField("Clinical Languages (comma-separated)", text: $clinicalLanguages)
                    Toggle("Telemedicine Available", isOn: $telemedicineAvailable)
                    if telemedicineAvailable {
                        TextField("Telemedicine Platforms (comma-separated)", text: $telemedicinePlatforms)
                    }
                }
                
                Section("Bio & Research") {
                    TextField("Professional Bio", text: $professionalBio, axis: .vertical)
                        .lineLimit(3...6)
                    TextField("Publications (comma-separated)", text: $publicationsField, axis: .vertical)
                        .lineLimit(2...4)
                    TextField("Research Interests (comma-separated)", text: $researchInterests)
                }
                
                if !message.isEmpty {
                    Section {
                        Text(message)
                            .foregroundStyle(message.contains("success") ? .green : .red)
                    }
                }
            }
            .navigationTitle("Professional Profile")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(saving ? "Saving..." : "Save") {
                        Task { await save() }
                    }
                    .disabled(saving)
                }
            }
            .onAppear { populateFromExisting() }
        }
    }
    
    private func populateFromExisting() {
        guard let p = roleAssignment.professionalProfile else { return }
        licenseNumber = p.licenseNumber ?? ""
        licenseState = p.licenseState ?? ""
        licenseCountry = p.licenseCountry ?? ""
        licenseExpiry = p.licenseExpiry ?? ""
        npiNumber = p.npiNumber ?? ""
        deaNumber = p.deaNumber ?? ""
        boardCerts = (p.boardCertifications ?? []).joined(separator: ", ")
        medicalSchool = p.medicalSchool ?? ""
        degree = p.degree ?? ""
        graduationYear = p.graduationYear.map { "\($0)" } ?? ""
        residencyProgram = p.residencyProgram ?? ""
        fellowshipProgram = p.fellowshipProgram ?? ""
        specialty = p.specialty ?? ""
        subSpecialty = p.subSpecialty ?? ""
        yearsOfExperience = p.yearsOfExperience.map { "\($0)" } ?? ""
        practiceName = p.practiceName ?? ""
        practiceType = p.practiceType ?? ""
        practiceAddress = p.practiceAddress ?? ""
        practicePhone = p.practicePhone ?? ""
        practiceEmail = p.practiceEmail ?? ""
        practiceWebsite = p.practiceWebsite ?? ""
        acceptingPatients = p.acceptingPatients ?? false
        hospitalAffiliations = (p.hospitalAffiliations ?? []).joined(separator: ", ")
        department = p.department ?? ""
        titleField = p.title ?? ""
        clinicalLanguages = (p.clinicalLanguages ?? []).joined(separator: ", ")
        telemedicineAvailable = p.telemedicineAvailable ?? false
        telemedicinePlatforms = (p.telemedicinePlatforms ?? []).joined(separator: ", ")
        professionalBio = p.professionalBio ?? ""
        publicationsField = (p.publications ?? []).joined(separator: ", ")
        researchInterests = (p.researchInterests ?? []).joined(separator: ", ")
    }
    
    private func save() async {
        saving = true
        message = ""
        do {
            let body = ProfessionalProfileCreate(
                licenseNumber: licenseNumber.isEmpty ? nil : licenseNumber,
                licenseState: licenseState.isEmpty ? nil : licenseState,
                licenseCountry: licenseCountry.isEmpty ? nil : licenseCountry,
                licenseExpiry: licenseExpiry.isEmpty ? nil : licenseExpiry,
                npiNumber: npiNumber.isEmpty ? nil : npiNumber,
                deaNumber: deaNumber.isEmpty ? nil : deaNumber,
                boardCertifications: splitCSV(boardCerts),
                medicalSchool: medicalSchool.isEmpty ? nil : medicalSchool,
                degree: degree.isEmpty ? nil : degree,
                graduationYear: Int(graduationYear),
                residencyProgram: residencyProgram.isEmpty ? nil : residencyProgram,
                fellowshipProgram: fellowshipProgram.isEmpty ? nil : fellowshipProgram,
                specialty: specialty.isEmpty ? nil : specialty,
                subSpecialty: subSpecialty.isEmpty ? nil : subSpecialty,
                yearsOfExperience: Int(yearsOfExperience),
                practiceName: practiceName.isEmpty ? nil : practiceName,
                practiceType: practiceType.isEmpty ? nil : practiceType,
                practiceAddress: practiceAddress.isEmpty ? nil : practiceAddress,
                practicePhone: practicePhone.isEmpty ? nil : practicePhone,
                practiceEmail: practiceEmail.isEmpty ? nil : practiceEmail,
                practiceWebsite: practiceWebsite.isEmpty ? nil : practiceWebsite,
                acceptingPatients: acceptingPatients,
                hospitalAffiliations: splitCSV(hospitalAffiliations),
                department: department.isEmpty ? nil : department,
                title: titleField.isEmpty ? nil : titleField,
                clinicalLanguages: splitCSV(clinicalLanguages),
                telemedicineAvailable: telemedicineAvailable,
                telemedicinePlatforms: splitCSV(telemedicinePlatforms),
                professionalBio: professionalBio.isEmpty ? nil : professionalBio,
                publications: splitCSV(publicationsField),
                researchInterests: splitCSV(researchInterests)
            )
            let _: ProfessionalProfile = try await APIClient.shared.put(
                "/users/roles/\(roleAssignment.id)/profile", body: body
            )
            message = "Profile saved successfully!"
            onSave()
            try? await Task.sleep(for: .seconds(1))
            dismiss()
        } catch {
            message = error.localizedDescription
        }
        saving = false
    }
    
    private func splitCSV(_ s: String) -> [String]? {
        let items = s.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
        return items.isEmpty ? nil : items
    }
}

// MARK: - Flow Layout Helper

struct FlowLayoutRoles: Layout {
    var spacing: CGFloat = 6
    
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let result = arrangeSubviews(proposal: proposal, subviews: subviews)
        return result.size
    }
    
    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let result = arrangeSubviews(proposal: proposal, subviews: subviews)
        for (index, position) in result.positions.enumerated() {
            subviews[index].place(
                at: CGPoint(x: bounds.minX + position.x, y: bounds.minY + position.y),
                proposal: ProposedViewSize(result.sizes[index])
            )
        }
    }
    
    private func arrangeSubviews(proposal: ProposedViewSize, subviews: Subviews) -> ArrangementResult {
        let maxWidth = proposal.width ?? .infinity
        var positions: [CGPoint] = []
        var sizes: [CGSize] = []
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0
        
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > maxWidth && x > 0 {
                x = 0
                y += rowHeight + spacing
                rowHeight = 0
            }
            positions.append(CGPoint(x: x, y: y))
            sizes.append(size)
            rowHeight = max(rowHeight, size.height)
            x += size.width + spacing
        }
        
        return ArrangementResult(
            size: CGSize(width: maxWidth, height: y + rowHeight),
            positions: positions,
            sizes: sizes
        )
    }
    
    struct ArrangementResult {
        var size: CGSize
        var positions: [CGPoint]
        var sizes: [CGSize]
    }
}
