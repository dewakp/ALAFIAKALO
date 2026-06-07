import SwiftUI
import MapKit
import CoreLocation

// MARK: - ViewModel

@Observable
final class PhysiciansViewModel {
    var physicians: [Physician] = []
    var savedPhysicians: [SavedPhysician] = []
    var specialtyCategories: [String: [String]] = [:]
    var reviews: [Int: [PhysicianReview]] = [:]
    var isLoading = false
    var errorMessage: String?

    // Search / filter
    var searchQuery = ""
    var selectedSpecialty = ""
    var selectedCategory = ""
    var filterCity = ""

    // Map
    var mapRegion = MKCoordinateRegion(
        center: CLLocationCoordinate2D(latitude: 29.76, longitude: -95.37),
        span: MKCoordinateSpan(latitudeDelta: 0.5, longitudeDelta: 0.5)
    )

    var savedIds: Set<Int> {
        Set(savedPhysicians.map(\.physicianId))
    }

    var allSpecialties: [String] {
        if !selectedCategory.isEmpty, let specs = specialtyCategories[selectedCategory] {
            return specs
        }
        return specialtyCategories.values.flatMap { $0 }.sorted()
    }

    // MARK: - Fetch

    func loadAll() async {
        isLoading = true; errorMessage = nil
        do {
            async let p: [Physician] = APIClient.shared.get("/physicians/")
            async let s: [SavedPhysician] = APIClient.shared.get("/physicians/saved/")
            async let c: SpecialtyCategoriesResponse = APIClient.shared.get("/physicians/specialties")
            let (pRes, sRes, cRes) = try await (p, s, c)
            physicians = pRes; savedPhysicians = sRes; specialtyCategories = cRes.categories
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }

    func searchPhysicians() async {
        isLoading = true
        var params: [String] = []
        if !searchQuery.isEmpty { params.append("q=\(searchQuery)") }
        if !selectedSpecialty.isEmpty { params.append("specialty=\(selectedSpecialty)") }
        if !selectedCategory.isEmpty { params.append("specialty_category=\(selectedCategory)") }
        if !filterCity.isEmpty { params.append("city=\(filterCity)") }
        let query = params.isEmpty ? "" : "?\(params.joined(separator: "&"))"
        do {
            physicians = try await APIClient.shared.get("/physicians/\(query)")
        } catch { errorMessage = error.localizedDescription }
        isLoading = false
    }

    // MARK: - CRUD

    func addPhysician(_ create: PhysicianCreate) async -> Bool {
        do {
            let _: Physician = try await APIClient.shared.post("/physicians/", body: create)
            await loadAll()
            return true
        } catch {
            errorMessage = error.localizedDescription; return false
        }
    }

    func deletePhysician(id: Int) async {
        do {
            try await APIClient.shared.delete("/physicians/\(id)")
            physicians.removeAll { $0.id == id }
        } catch { errorMessage = error.localizedDescription }
    }

    // MARK: - Save / Unsave

    func savePhysician(_ req: SavePhysicianRequest) async {
        do {
            let _: SavedPhysician = try await APIClient.shared.post("/physicians/saved/", body: req)
            savedPhysicians = try await APIClient.shared.get("/physicians/saved/")
        } catch { errorMessage = error.localizedDescription }
    }

    func unsavePhysician(savedId: Int) async {
        do {
            try await APIClient.shared.delete("/physicians/saved/\(savedId)")
            savedPhysicians.removeAll { $0.id == savedId }
        } catch { errorMessage = error.localizedDescription }
    }

    // MARK: - Reviews

    func loadReviews(for physicianId: Int) async {
        do {
            let r: [PhysicianReview] = try await APIClient.shared.get("/physicians/\(physicianId)/reviews")
            reviews[physicianId] = r
        } catch { errorMessage = error.localizedDescription }
    }

    func submitReview(physicianId: Int, review: ReviewCreate) async -> Bool {
        do {
            let _: PhysicianReview = try await APIClient.shared.post("/physicians/\(physicianId)/reviews", body: review)
            await loadReviews(for: physicianId)
            await loadAll()
            return true
        } catch { errorMessage = error.localizedDescription; return false }
    }
}

// MARK: - Main View

struct PhysicianDirectoryView: View {
    @State private var vm = PhysiciansViewModel()
    @State private var showAdd = false
    @State private var showFilters = false
    @State private var selectedTab = 0 // 0=directory 1=saved 2=map
    @State private var selectedPhysician: Physician?

    var body: some View {
        VStack(spacing: 0) {
            Picker("", selection: $selectedTab) {
                Text("Directory").tag(0)
                Text("Saved (\(vm.savedPhysicians.count))").tag(1)
                Text("Map").tag(2)
            }
            .pickerStyle(.segmented)
            .padding()

            switch selectedTab {
            case 0: directoryTab
            case 1: savedTab
            case 2: mapTab
            default: EmptyView()
            }
        }
        .navigationTitle("Physician Directory")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { showAdd = true } label: { Image(systemName: "plus") }
            }
        }
        .sheet(isPresented: $showAdd) { AddPhysicianSheet(vm: vm) }
        .sheet(item: $selectedPhysician) { p in PhysicianDetailSheet(physician: p, vm: vm) }
        .task { await vm.loadAll() }
    }

    // MARK: – Directory

    @ViewBuilder
    private var directoryTab: some View {
        VStack(spacing: 8) {
            HStack {
                HStack {
                    Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                    TextField("Search physicians…", text: $vm.searchQuery)
                        .textInputAutocapitalization(.never)
                        .onSubmit { Task { await vm.searchPhysicians() } }
                }
                .padding(8).background(.fill).cornerRadius(10)

                Button { showFilters.toggle() } label: {
                    Image(systemName: showFilters ? "line.3.horizontal.decrease.circle.fill" : "line.3.horizontal.decrease.circle")
                }
            }
            .padding(.horizontal)

            if showFilters {
                VStack(spacing: 8) {
                    Picker("Category", selection: $vm.selectedCategory) {
                        Text("All Categories").tag("")
                        ForEach(vm.specialtyCategories.keys.sorted(), id: \.self) { Text($0).tag($0) }
                    }
                    Picker("Specialty", selection: $vm.selectedSpecialty) {
                        Text("All Specialties").tag("")
                        ForEach(vm.allSpecialties, id: \.self) { Text($0).tag($0) }
                    }
                    HStack {
                        TextField("City", text: $vm.filterCity)
                            .textFieldStyle(.roundedBorder)
                        Button("Clear") {
                            vm.searchQuery = ""; vm.selectedSpecialty = ""; vm.selectedCategory = ""; vm.filterCity = ""
                            Task { await vm.loadAll() }
                        }
                        .buttonStyle(.bordered)
                    }
                }
                .padding(.horizontal)
                .transition(.move(edge: .top).combined(with: .opacity))
            }
        }

        if vm.isLoading {
            Spacer(); ProgressView(); Spacer()
        } else if vm.physicians.isEmpty {
            Spacer()
            EmptyStateView(icon: "stethoscope", title: "No Physicians", message: "Tap + to add one")
            Spacer()
        } else {
            List {
                ForEach(vm.physicians) { p in
                    PhysicianRow(physician: p, isSaved: vm.savedIds.contains(p.id))
                        .contentShape(Rectangle())
                        .onTapGesture { selectedPhysician = p }
                }
                .onDelete { indexSet in
                    Task {
                        for i in indexSet { await vm.deletePhysician(id: vm.physicians[i].id) }
                    }
                }
            }
            .listStyle(.plain)
        }
    }

    // MARK: – Saved

    @ViewBuilder
    private var savedTab: some View {
        if vm.savedPhysicians.isEmpty {
            Spacer()
            VStack(spacing: 12) {
                Image(systemName: "heart.slash").font(.system(size: 48)).foregroundStyle(.secondary)
                Text("No Saved Physicians").font(.headline)
                Text("Bookmark physicians from the directory").font(.subheadline).foregroundStyle(.secondary)
            }
            Spacer()
        } else {
            List {
                ForEach(vm.savedPhysicians) { s in
                    SavedPhysicianRow(saved: s)
                        .contentShape(Rectangle())
                        .onTapGesture { if let p = s.physician { selectedPhysician = p } }
                }
                .onDelete { indexSet in
                    Task {
                        for i in indexSet { await vm.unsavePhysician(savedId: vm.savedPhysicians[i].id) }
                    }
                }
            }
            .listStyle(.plain)
        }
    }

    // MARK: – Map

    @ViewBuilder
    private var mapTab: some View {
        Map(coordinateRegion: .constant(vm.mapRegion), annotationItems: vm.physicians.filter { $0.latitude != nil && $0.longitude != nil }) { p in
            MapAnnotation(coordinate: CLLocationCoordinate2D(latitude: p.latitude!, longitude: p.longitude!)) {
                VStack(spacing: 2) {
                    Image(systemName: "stethoscope.circle.fill")
                        .font(.title)
                        .foregroundStyle(.indigo)
                        .background(Circle().fill(.white).frame(width: 28, height: 28))
                    Text(p.fullName)
                        .font(.caption2)
                        .fontWeight(.medium)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 1)
                        .background(.ultraThinMaterial)
                        .cornerRadius(4)
                }
                .onTapGesture { selectedPhysician = p }
            }
        }
        .ignoresSafeArea(edges: .bottom)
    }
}

// MARK: - Physician Row

struct PhysicianRow: View {
    let physician: Physician
    let isSaved: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text(physician.fullName).font(.headline)
                        if let cred = physician.credentials {
                            Text(cred).font(.caption).foregroundStyle(.secondary)
                        }
                        if physician.isVerified {
                            Image(systemName: "checkmark.seal.fill").font(.caption).foregroundStyle(.green)
                        }
                    }
                    Text(physician.specialty)
                        .font(.subheadline).foregroundStyle(.indigo).fontWeight(.medium)
                }
                Spacer()
                if isSaved {
                    Image(systemName: "heart.fill").foregroundStyle(.red).font(.caption)
                }
            }

            HStack(spacing: 12) {
                if let facility = physician.facilityName {
                    Label(facility, systemImage: "building.2").font(.caption).foregroundStyle(.secondary)
                }
                if !physician.locationDisplay.isEmpty {
                    Label(physician.locationDisplay, systemImage: "mappin").font(.caption).foregroundStyle(.secondary)
                }
            }

            if physician.reviewCount > 0 {
                HStack(spacing: 4) {
                    ForEach(0..<5) { i in
                        Image(systemName: i < Int(physician.averageRating ?? 0) ? "star.fill" : "star")
                            .font(.caption2).foregroundStyle(.orange)
                    }
                    Text("(\(physician.reviewCount))").font(.caption2).foregroundStyle(.secondary)
                }
            }

            HStack(spacing: 8) {
                if physician.acceptingNewPatients {
                    Text("Accepting patients").font(.caption2).fontWeight(.medium)
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(Color.green.opacity(0.12)).foregroundStyle(.green)
                        .clipShape(Capsule())
                }
                if physician.telehealthAvailable {
                    Label("Telehealth", systemImage: "video.fill").font(.caption2)
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(Color.cyan.opacity(0.12)).foregroundStyle(.cyan)
                        .clipShape(Capsule())
                }
            }
        }
        .padding(.vertical, 4)
    }
}

// MARK: – Saved Row

struct SavedPhysicianRow: View {
    let saved: SavedPhysician

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                VStack(alignment: .leading) {
                    Text(saved.physician?.fullName ?? "Unknown").font(.headline)
                    Text(saved.physician?.specialty ?? "").font(.subheadline).foregroundStyle(.indigo)
                }
                Spacer()
                if saved.isPrimaryCare {
                    Text("PCP").font(.caption2).fontWeight(.bold)
                        .padding(.horizontal, 8).padding(.vertical, 2)
                        .background(Color.green.opacity(0.15)).foregroundStyle(.green).clipShape(Capsule())
                }
                if let rel = saved.relationshipType {
                    Text(rel).font(.caption2)
                        .padding(.horizontal, 8).padding(.vertical, 2)
                        .background(Color.indigo.opacity(0.12)).foregroundStyle(.indigo).clipShape(Capsule())
                }
            }
            if let nick = saved.nickname { Text("\u{201C}\(nick)\u{201D}").font(.caption).foregroundStyle(.secondary) }
            if let notes = saved.notes { Text(notes).font(.caption).foregroundStyle(.secondary).italic() }
        }
        .padding(.vertical, 4)
    }
}

// MARK: - Detail Sheet

struct PhysicianDetailSheet: View {
    let physician: Physician
    @Bindable var vm: PhysiciansViewModel
    @Environment(\.dismiss) var dismiss
    @State private var showReviewSheet = false
    @State private var showSaveSheet = false

    var body: some View {
        NavigationStack {
            List {
                // Identity
                Section {
                    HStack {
                        Image(systemName: "stethoscope.circle.fill")
                            .font(.system(size: 44)).foregroundStyle(.indigo)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(physician.fullName).font(.title2).fontWeight(.bold)
                            Text(physician.specialty).font(.subheadline).foregroundStyle(.indigo)
                            if let cred = physician.credentials {
                                Text(cred).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                }

                // Contact
                Section("Contact") {
                    if let phone = physician.phone { Label(phone, systemImage: "phone") }
                    if let email = physician.email { Label(email, systemImage: "envelope") }
                    if let web = physician.website { Label(web, systemImage: "globe") }
                    if let fac = physician.facilityName { Label(fac, systemImage: "building.2") }
                    if !physician.locationDisplay.isEmpty {
                        Label(physician.locationDisplay, systemImage: "mappin.circle")
                    }
                    if let hours = physician.operatingHours { Label(hours, systemImage: "clock") }
                    if let langs = physician.languagesSpoken { Label(langs, systemImage: "globe.americas") }
                    if let ins = physician.insuranceAccepted { Label(ins, systemImage: "shield") }
                }

                // Rating
                if physician.reviewCount > 0 {
                    Section("Rating") {
                        HStack {
                            ForEach(0..<5) { i in
                                Image(systemName: i < Int(physician.averageRating ?? 0) ? "star.fill" : "star")
                                    .foregroundStyle(.orange)
                            }
                            Text(String(format: "%.1f", physician.averageRating ?? 0))
                                .fontWeight(.semibold)
                            Text("(\(physician.reviewCount) reviews)").foregroundStyle(.secondary)
                        }
                    }
                }

                // Reviews
                Section("Reviews") {
                    let revs = vm.reviews[physician.id] ?? []
                    if revs.isEmpty {
                        Text("No reviews yet").foregroundStyle(.secondary)
                    } else {
                        ForEach(revs) { r in
                            VStack(alignment: .leading, spacing: 4) {
                                HStack {
                                    ForEach(0..<5) { i in
                                        Image(systemName: i < r.rating ? "star.fill" : "star")
                                            .font(.caption2).foregroundStyle(.orange)
                                    }
                                    Text(r.reviewerName ?? "Anonymous").font(.caption).foregroundStyle(.secondary)
                                }
                                if let t = r.title { Text(t).font(.subheadline).fontWeight(.medium) }
                                if let txt = r.reviewText { Text(txt).font(.caption) }
                            }
                            .padding(.vertical, 2)
                        }
                    }

                    Button { showReviewSheet = true } label: {
                        Label("Write a Review", systemImage: "pencil.tip")
                    }
                }

                // Map
                if let lat = physician.latitude, let lon = physician.longitude {
                    Section("Location") {
                        Map(coordinateRegion: .constant(MKCoordinateRegion(
                            center: CLLocationCoordinate2D(latitude: lat, longitude: lon),
                            span: MKCoordinateSpan(latitudeDelta: 0.01, longitudeDelta: 0.01)
                        )), annotationItems: [physician]) { p in
                            MapMarker(coordinate: CLLocationCoordinate2D(latitude: lat, longitude: lon), tint: .indigo)
                        }
                        .frame(height: 200)
                        .cornerRadius(12)
                    }
                }

                // Actions
                Section {
                    if vm.savedIds.contains(physician.id) {
                        Button(role: .destructive) {
                            if let s = vm.savedPhysicians.first(where: { $0.physicianId == physician.id }) {
                                Task { await vm.unsavePhysician(savedId: s.id) }
                            }
                        } label: {
                            Label("Remove from Saved", systemImage: "heart.slash")
                        }
                    } else {
                        Button { showSaveSheet = true } label: {
                            Label("Save Physician", systemImage: "heart")
                        }
                    }
                }
            }
            .navigationTitle("Details")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Done") { dismiss() } } }
            .sheet(isPresented: $showReviewSheet) { WriteReviewSheet(physicianId: physician.id, vm: vm) }
            .sheet(isPresented: $showSaveSheet) { SavePhysicianSheet(physicianId: physician.id, vm: vm) }
            .task { await vm.loadReviews(for: physician.id) }
        }
    }
}

// MARK: - Add Physician Sheet

struct AddPhysicianSheet: View {
    @Bindable var vm: PhysiciansViewModel
    @Environment(\.dismiss) var dismiss

    @State private var fullName = ""
    @State private var specialty = ""
    @State private var credentials = ""
    @State private var facilityName = ""
    @State private var phone = ""
    @State private var email = ""
    @State private var city = ""
    @State private var stateProvince = ""
    @State private var country = ""
    @State private var acceptingNew = true
    @State private var telehealth = false
    @State private var languages = ""
    @State private var saving = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Physician") {
                    LKTextField(title: "Full Name", text: $fullName)
                    Picker("Specialty", selection: $specialty) {
                        Text("Select…").tag("")
                        ForEach(vm.specialtyCategories.keys.sorted(), id: \.self) { cat in
                            Section(cat) {
                                ForEach(vm.specialtyCategories[cat] ?? [], id: \.self) { s in
                                    Text(s).tag(s)
                                }
                            }
                        }
                    }
                    LKTextField(title: "Credentials (e.g. MD, DO)", text: $credentials)
                }
                Section("Practice") {
                    LKTextField(title: "Facility Name", text: $facilityName)
                    Toggle("Accepting New Patients", isOn: $acceptingNew)
                    Toggle("Telehealth Available", isOn: $telehealth)
                }
                Section("Contact") {
                    LKTextField(title: "Phone", text: $phone)
                    LKTextField(title: "Email", text: $email)
                }
                Section("Location") {
                    LKTextField(title: "City", text: $city)
                    LKTextField(title: "State / Province", text: $stateProvince)
                    LKTextField(title: "Country", text: $country)
                }
                Section("Other") {
                    LKTextField(title: "Languages", text: $languages)
                }
            }
            .navigationTitle("Add Physician")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Save") { save() }.disabled(fullName.isEmpty || specialty.isEmpty || saving).fontWeight(.semibold)
                }
            }
        }
    }

    private func save() {
        saving = true
        let create = PhysicianCreate(
            fullName: fullName, specialty: specialty,
            credentials: credentials.isEmpty ? nil : credentials,
            facilityName: facilityName.isEmpty ? nil : facilityName,
            city: city.isEmpty ? nil : city,
            stateProvince: stateProvince.isEmpty ? nil : stateProvince,
            country: country.isEmpty ? nil : country,
            phone: phone.isEmpty ? nil : phone,
            email: email.isEmpty ? nil : email,
            acceptingNewPatients: acceptingNew,
            telehealthAvailable: telehealth,
            languagesSpoken: languages.isEmpty ? nil : languages
        )
        Task {
            if await vm.addPhysician(create) { dismiss() }
            saving = false
        }
    }
}

// MARK: - Save Physician Sheet

struct SavePhysicianSheet: View {
    let physicianId: Int
    @Bindable var vm: PhysiciansViewModel
    @Environment(\.dismiss) var dismiss

    @State private var nickname = ""
    @State private var notes = ""
    @State private var isPrimary = false
    @State private var relationship = ""

    let relationships = ["PCP", "Specialist", "Dentist", "Therapist", "Surgeon", "Pharmacist", "Other"]

    var body: some View {
        NavigationStack {
            Form {
                LKTextField(title: "Nickname (optional)", text: $nickname)
                Picker("Relationship", selection: $relationship) {
                    Text("Select…").tag("")
                    ForEach(relationships, id: \.self) { Text($0).tag($0) }
                }
                TextField("Notes", text: $notes, axis: .vertical).lineLimit(3...6)
                Toggle("Primary Care Provider", isOn: $isPrimary)
            }
            .navigationTitle("Save Physician")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Save") {
                        let req = SavePhysicianRequest(
                            physicianId: physicianId,
                            nickname: nickname.isEmpty ? nil : nickname,
                            notes: notes.isEmpty ? nil : notes,
                            isPrimaryCare: isPrimary,
                            relationshipType: relationship.isEmpty ? nil : relationship
                        )
                        Task { await vm.savePhysician(req); dismiss() }
                    }.fontWeight(.semibold)
                }
            }
        }
    }
}

// MARK: - Write Review Sheet

struct WriteReviewSheet: View {
    let physicianId: Int
    @Bindable var vm: PhysiciansViewModel
    @Environment(\.dismiss) var dismiss

    @State private var rating = 5
    @State private var title = ""
    @State private var reviewText = ""
    @State private var anonymous = false
    @State private var saving = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Rating") {
                    HStack {
                        ForEach(1...5, id: \.self) { i in
                            Image(systemName: i <= rating ? "star.fill" : "star")
                                .font(.title2).foregroundStyle(.orange)
                                .onTapGesture { rating = i }
                        }
                    }
                }
                Section("Review") {
                    LKTextField(title: "Title (optional)", text: $title)
                    TextField("Review text", text: $reviewText, axis: .vertical).lineLimit(4...8)
                }
                Section { Toggle("Post anonymously", isOn: $anonymous) }
            }
            .navigationTitle("Write Review")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Submit") {
                        saving = true
                        let review = ReviewCreate(
                            rating: rating,
                            title: title.isEmpty ? nil : title,
                            reviewText: reviewText.isEmpty ? nil : reviewText,
                            isAnonymous: anonymous
                        )
                        Task {
                            if await vm.submitReview(physicianId: physicianId, review: review) { dismiss() }
                            saving = false
                        }
                    }
                    .disabled(saving).fontWeight(.semibold)
                }
            }
        }
    }
}
