import SwiftUI

@Observable
final class InsuranceViewModel {
    var plans: [Insurance] = []
    var regions: [String: [InsuranceCountry]] = [:]
    var providers: [InsuranceProvider] = []
    var isLoading = false
    var errorMessage: String?

    static let regionLabels: [(code: String, name: String, icon: String)] = [
        ("north_america", "North America", "globe.americas.fill"),
        ("europe", "Europe", "globe.europe.africa.fill"),
        ("south_asia", "South Asia", "globe.asia.australia.fill"),
        ("africa", "Africa", "globe.europe.africa.fill"),
        ("middle_east", "Middle East", "globe.europe.africa.fill"),
    ]

    func fetchPlans() async {
        isLoading = true
        errorMessage = nil
        do {
            plans = try await APIClient.shared.get("/insurance/")
            isLoading = false
        } catch {
            errorMessage = error.localizedDescription
            isLoading = false
        }
    }

    func fetchRegions() async {
        do {
            regions = try await APIClient.shared.get("/insurance/regions")
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func fetchProviders(for countryCode: String) async {
        do {
            providers = try await APIClient.shared.get("/insurance/providers/\(countryCode)")
        } catch {
            providers = []
        }
    }

    func addPlan(_ plan: InsuranceCreate) async -> Bool {
        do {
            let _: Insurance = try await APIClient.shared.post("/insurance/", body: plan)
            await fetchPlans()
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    func deletePlan(id: Int) async {
        do {
            try await APIClient.shared.delete("/insurance/\(id)")
            plans.removeAll { $0.id == id }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func setPrimary(id: Int) async {
        do {
            let _: Insurance = try await APIClient.shared.post("/insurance/\(id)/set-primary", body: EmptyBody())
            await fetchPlans()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct InsuranceView: View {
    @State private var vm = InsuranceViewModel()
    @State private var showAdd = false

    var activePlans: [Insurance] { vm.plans.filter { $0.isActive } }
    var inactivePlans: [Insurance] { vm.plans.filter { !$0.isActive } }

    var body: some View {
        Group {
            if vm.isLoading {
                ProgressView()
            } else if vm.plans.isEmpty {
                EmptyStateView(icon: "shield.lefthalf.filled", title: "No Insurance Plans", message: "Tap + to add insurance plans from any supported country")
            } else {
                List {
                    if !activePlans.isEmpty {
                        Section("Active Plans") {
                            ForEach(activePlans) { plan in
                                InsurancePlanRow(plan: plan, vm: vm)
                            }
                            .onDelete { indexSet in
                                Task {
                                    for index in indexSet {
                                        await vm.deletePlan(id: activePlans[index].id)
                                    }
                                }
                            }
                        }
                    }
                    if !inactivePlans.isEmpty {
                        Section("Inactive Plans") {
                            ForEach(inactivePlans) { plan in
                                InsurancePlanRow(plan: plan, vm: vm)
                            }
                        }
                    }
                }
            }
        }
        .navigationTitle("Insurance Plans")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { showAdd = true } label: {
                    Image(systemName: "plus")
                }
            }
        }
        .sheet(isPresented: $showAdd) {
            AddInsuranceSheet(vm: vm)
        }
        .task {
            await vm.fetchRegions()
            await vm.fetchPlans()
        }
    }
}

struct InsurancePlanRow: View {
    let plan: Insurance
    let vm: InsuranceViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(plan.providerName)
                        .font(.headline)
                    Text(plan.countryName)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                Spacer()

                if plan.isPrimary {
                    Label("Primary", systemImage: "star.fill")
                        .font(.caption2)
                        .fontWeight(.bold)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(Color.yellow.opacity(0.2))
                        .foregroundStyle(.orange)
                        .clipShape(Capsule())
                }
            }

            HStack(spacing: 12) {
                if let planName = plan.planName {
                    Label(planName, systemImage: "doc.text")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                if let planType = plan.planType {
                    Text(planType)
                        .font(.caption2)
                        .fontWeight(.medium)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.blue.opacity(0.1))
                        .foregroundStyle(.blue)
                        .clipShape(Capsule())
                }
                if let policy = plan.policyNumber {
                    Text("# \(policy)")
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                }
            }
        }
        .padding(.vertical, 4)
        .swipeActions(edge: .trailing) {
            Button(role: .destructive) {
                Task { await vm.deletePlan(id: plan.id) }
            } label: {
                Image(systemName: "trash")
            }
        }
        .swipeActions(edge: .leading) {
            if !plan.isPrimary {
                Button {
                    Task { await vm.setPrimary(id: plan.id) }
                } label: {
                    Label("Primary", systemImage: "star.fill")
                }
                .tint(.orange)
            }
        }
    }
}

struct AddInsuranceSheet: View {
    @Bindable var vm: InsuranceViewModel
    @Environment(\.dismiss) var dismiss

    @State private var selectedRegion = ""
    @State private var selectedCountryCode = ""
    @State private var selectedCountryName = ""
    @State private var selectedProviderCode = ""
    @State private var selectedProviderName = ""
    @State private var policyNumber = ""
    @State private var groupNumber = ""
    @State private var memberId = ""
    @State private var planName = ""
    @State private var planType = ""
    @State private var coverageStart = ""
    @State private var coverageEnd = ""
    @State private var isPrimary = false
    @State private var subscriberName = ""
    @State private var subscriberRelationship = "self"
    @State private var insurancePhone = ""
    @State private var notes = ""
    @State private var saving = false

    let planTypes = ["HMO", "PPO", "EPO", "POS", "HDHP", "Indemnity", "Government", "Universal", "Other"]
    let relationships = ["self", "spouse", "child", "parent", "other"]

    var countries: [InsuranceCountry] { vm.regions[selectedRegion] ?? [] }

    var body: some View {
        NavigationStack {
            Form {
                Section("Location") {
                    Picker("Region", selection: $selectedRegion) {
                        Text("Select Region").tag("")
                        ForEach(InsuranceViewModel.regionLabels, id: \.code) { r in
                            Label(r.name, systemImage: r.icon).tag(r.code)
                        }
                    }
                    .onChange(of: selectedRegion) { _, _ in
                        selectedCountryCode = ""
                        selectedCountryName = ""
                        selectedProviderCode = ""
                        selectedProviderName = ""
                        vm.providers = []
                    }

                    Picker("Country", selection: $selectedCountryCode) {
                        Text("Select Country").tag("")
                        ForEach(countries) { c in
                            Text(c.name).tag(c.code)
                        }
                    }
                    .disabled(selectedRegion.isEmpty)
                    .onChange(of: selectedCountryCode) { _, newCode in
                        if let c = countries.first(where: { $0.code == newCode }) {
                            selectedCountryName = c.name
                        }
                        selectedProviderCode = ""
                        selectedProviderName = ""
                        if !newCode.isEmpty {
                            Task { await vm.fetchProviders(for: newCode) }
                        }
                    }
                }

                Section("Insurance Provider") {
                    Picker("Provider", selection: $selectedProviderCode) {
                        Text("Select Provider").tag("")
                        ForEach(vm.providers) { p in
                            Text(p.name).tag(p.code)
                        }
                    }
                    .disabled(selectedCountryCode.isEmpty)
                    .onChange(of: selectedProviderCode) { _, newCode in
                        if let p = vm.providers.first(where: { $0.code == newCode }) {
                            selectedProviderName = p.name
                        }
                    }
                }

                Section("Policy Details") {
                    LKTextField(title: "Policy / ID Number", text: $policyNumber)
                    LKTextField(title: "Group Number", text: $groupNumber)
                    LKTextField(title: "Member ID", text: $memberId)
                    LKTextField(title: "Plan Name", text: $planName)
                    Picker("Plan Type", selection: $planType) {
                        Text("Select").tag("")
                        ForEach(planTypes, id: \.self) { Text($0).tag($0) }
                    }
                }

                Section("Coverage Period") {
                    LKTextField(title: "Start Date (YYYY-MM-DD)", text: $coverageStart)
                    LKTextField(title: "End Date (YYYY-MM-DD)", text: $coverageEnd)
                }

                Section("Subscriber") {
                    LKTextField(title: "Subscriber Name", text: $subscriberName)
                    Picker("Relationship", selection: $subscriberRelationship) {
                        ForEach(relationships, id: \.self) { Text($0.capitalized).tag($0) }
                    }
                    LKTextField(title: "Insurance Phone", text: $insurancePhone)
                }

                Section {
                    Toggle("Set as Primary", isOn: $isPrimary)
                }

                Section("Notes") {
                    TextField("Additional notes", text: $notes, axis: .vertical)
                        .lineLimit(3...6)
                }
            }
            .navigationTitle("Add Insurance")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Save") { save() }
                        .disabled(selectedRegion.isEmpty || selectedCountryCode.isEmpty || selectedProviderCode.isEmpty || saving)
                        .fontWeight(.semibold)
                }
            }
        }
    }

    private func save() {
        saving = true
        let plan = InsuranceCreate(
            region: selectedRegion,
            countryCode: selectedCountryCode,
            countryName: selectedCountryName,
            providerCode: selectedProviderCode,
            providerName: selectedProviderName,
            policyNumber: policyNumber.isEmpty ? nil : policyNumber,
            groupNumber: groupNumber.isEmpty ? nil : groupNumber,
            memberId: memberId.isEmpty ? nil : memberId,
            planName: planName.isEmpty ? nil : planName,
            planType: planType.isEmpty ? nil : planType,
            coverageStart: coverageStart.isEmpty ? nil : coverageStart,
            coverageEnd: coverageEnd.isEmpty ? nil : coverageEnd,
            isPrimary: isPrimary,
            subscriberName: subscriberName.isEmpty ? nil : subscriberName,
            subscriberRelationship: subscriberRelationship,
            insurancePhone: insurancePhone.isEmpty ? nil : insurancePhone,
            notes: notes.isEmpty ? nil : notes
        )
        Task {
            if await vm.addPlan(plan) { dismiss() }
            saving = false
        }
    }
}
