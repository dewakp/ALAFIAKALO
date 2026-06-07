import SwiftUI

// MARK: - ViewModel

@Observable
final class AdvancedDirectivesViewModel {
    var directive: AdvancedDirective?
    var isLoading = false
    var isEditing = false
    var errorMessage: String?
    var isSaving = false

    // Primary Agent
    var primaryAgentName = ""
    var primaryAgentRelationship = ""
    var primaryAgentPhone = ""
    var primaryAgentEmail = ""
    var primaryAgentAddress = ""

    // Alternate Agent
    var alternateAgentName = ""
    var alternateAgentRelationship = ""
    var alternateAgentPhone = ""
    var alternateAgentEmail = ""
    var alternateAgentAddress = ""

    // Organ Donation
    var organDonation = "none"
    var organDonationPreferences = ""

    // Life-Sustaining Treatment
    var lifeSupport = "let_agent_decide"
    var cpr = "let_agent_decide"
    var ventilator = "let_agent_decide"
    var feedingTube = "let_agent_decide"
    var dialysisDirective = "let_agent_decide"
    var bloodTransfusion = "let_agent_decide"

    // Document Info
    var documentSigned = false
    var documentDate = Date()
    var witnessName = ""
    var notarized = false
    var documentLocation = ""

    // Additional
    var additionalInstructions = ""

    private let treatmentOptions = ["yes", "no", "let_agent_decide"]
    private let organOptions = ["all", "heart", "kidneys", "liver", "lungs", "none"]

    func load() async {
        isLoading = true; errorMessage = nil
        do {
            let result: AdvancedDirective = try await APIClient.shared.get("/advanced-directives/")
            directive = result
            populateForm(from: result)
        } catch {
            // 404 means no directive exists yet — that's OK
            if !error.localizedDescription.contains("404") {
                errorMessage = error.localizedDescription
            }
            directive = nil
        }
        isLoading = false
    }

    func save() async {
        isSaving = true; errorMessage = nil
        let dateStr = Self.dateFormatter.string(from: documentDate)
        let body = AdvancedDirective(
            id: directive?.id,
            userId: nil,
            primaryAgentName: primaryAgentName.isEmpty ? nil : primaryAgentName,
            primaryAgentRelationship: primaryAgentRelationship.isEmpty ? nil : primaryAgentRelationship,
            primaryAgentPhone: primaryAgentPhone.isEmpty ? nil : primaryAgentPhone,
            primaryAgentEmail: primaryAgentEmail.isEmpty ? nil : primaryAgentEmail,
            primaryAgentAddress: primaryAgentAddress.isEmpty ? nil : primaryAgentAddress,
            alternateAgentName: alternateAgentName.isEmpty ? nil : alternateAgentName,
            alternateAgentRelationship: alternateAgentRelationship.isEmpty ? nil : alternateAgentRelationship,
            alternateAgentPhone: alternateAgentPhone.isEmpty ? nil : alternateAgentPhone,
            alternateAgentEmail: alternateAgentEmail.isEmpty ? nil : alternateAgentEmail,
            alternateAgentAddress: alternateAgentAddress.isEmpty ? nil : alternateAgentAddress,
            organDonation: organDonation,
            organDonationPreferences: organDonationPreferences.isEmpty ? nil : organDonationPreferences,
            lifeSupport: lifeSupport,
            cpr: cpr,
            ventilator: ventilator,
            feedingTube: feedingTube,
            dialysisDirective: dialysisDirective,
            bloodTransfusion: bloodTransfusion,
            documentSigned: documentSigned,
            documentDate: documentSigned ? dateStr : nil,
            witnessName: witnessName.isEmpty ? nil : witnessName,
            notarized: notarized,
            documentLocation: documentLocation.isEmpty ? nil : documentLocation,
            additionalInstructions: additionalInstructions.isEmpty ? nil : additionalInstructions,
            createdAt: nil
        )
        do {
            if directive != nil {
                let updated: AdvancedDirective = try await APIClient.shared.put("/advanced-directives/", body: body)
                directive = updated
            } else {
                let created: AdvancedDirective = try await APIClient.shared.post("/advanced-directives/", body: body)
                directive = created
            }
            isEditing = false
        } catch { errorMessage = error.localizedDescription }
        isSaving = false
    }

    func deleteDirective() async {
        guard let d = directive, let id = d.id else { return }
        do {
            try await APIClient.shared.delete("/advanced-directives/\(id)")
            directive = nil
            resetForm()
            isEditing = false
        } catch { errorMessage = error.localizedDescription }
    }

    func beginEditing() {
        if let d = directive { populateForm(from: d) }
        isEditing = true
    }

    // MARK: - Helpers

    private func populateForm(from d: AdvancedDirective) {
        primaryAgentName = d.primaryAgentName ?? ""
        primaryAgentRelationship = d.primaryAgentRelationship ?? ""
        primaryAgentPhone = d.primaryAgentPhone ?? ""
        primaryAgentEmail = d.primaryAgentEmail ?? ""
        primaryAgentAddress = d.primaryAgentAddress ?? ""
        alternateAgentName = d.alternateAgentName ?? ""
        alternateAgentRelationship = d.alternateAgentRelationship ?? ""
        alternateAgentPhone = d.alternateAgentPhone ?? ""
        alternateAgentEmail = d.alternateAgentEmail ?? ""
        alternateAgentAddress = d.alternateAgentAddress ?? ""
        organDonation = d.organDonation ?? "none"
        organDonationPreferences = d.organDonationPreferences ?? ""
        lifeSupport = d.lifeSupport ?? "let_agent_decide"
        cpr = d.cpr ?? "let_agent_decide"
        ventilator = d.ventilator ?? "let_agent_decide"
        feedingTube = d.feedingTube ?? "let_agent_decide"
        dialysisDirective = d.dialysisDirective ?? "let_agent_decide"
        bloodTransfusion = d.bloodTransfusion ?? "let_agent_decide"
        documentSigned = d.documentSigned ?? false
        if let ds = d.documentDate, let parsed = Self.dateFormatter.date(from: String(ds.prefix(10))) {
            documentDate = parsed
        }
        witnessName = d.witnessName ?? ""
        notarized = d.notarized ?? false
        documentLocation = d.documentLocation ?? ""
        additionalInstructions = d.additionalInstructions ?? ""
    }

    private func resetForm() {
        primaryAgentName = ""
        primaryAgentRelationship = ""
        primaryAgentPhone = ""
        primaryAgentEmail = ""
        primaryAgentAddress = ""
        alternateAgentName = ""
        alternateAgentRelationship = ""
        alternateAgentPhone = ""
        alternateAgentEmail = ""
        alternateAgentAddress = ""
        organDonation = "none"
        organDonationPreferences = ""
        lifeSupport = "let_agent_decide"
        cpr = "let_agent_decide"
        ventilator = "let_agent_decide"
        feedingTube = "let_agent_decide"
        dialysisDirective = "let_agent_decide"
        bloodTransfusion = "let_agent_decide"
        documentSigned = false
        documentDate = Date()
        witnessName = ""
        notarized = false
        documentLocation = ""
        additionalInstructions = ""
    }

    static let dateFormatter: DateFormatter = {
        let df = DateFormatter()
        df.dateFormat = "yyyy-MM-dd"
        df.locale = Locale(identifier: "en_US_POSIX")
        return df
    }()
}

// MARK: - Main View

struct AdvancedDirectivesView: View {
    @State private var vm = AdvancedDirectivesViewModel()
    @State private var showDeleteConfirmation = false

    var body: some View {
            Group {
                if vm.isLoading {
                    ProgressView("Loading…")
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if vm.isEditing {
                    editForm
                } else if let d = vm.directive {
                    displayView(d)
                } else {
                    EmptyStateView(icon: "doc.text", title: "No Advanced Directive", message: "Tap Edit to create your advanced directive.")
                }
            }
            .navigationTitle("Advanced Directives")
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    if vm.isEditing {
                        Button("Save") { Task { await vm.save() } }
                            .disabled(vm.isSaving)
                    } else {
                        Button("Edit") { vm.beginEditing() }
                    }
                }
                if vm.isEditing {
                    ToolbarItem(placement: .cancellationAction) {
                        Button("Cancel") { vm.isEditing = false }
                    }
                }
            }
            .alert("Delete Directive?", isPresented: $showDeleteConfirmation) {
                Button("Delete", role: .destructive) { Task { await vm.deleteDirective() } }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("This action cannot be undone.")
            }
            .task { await vm.load() }
            .refreshable { await vm.load() }
    }

    // MARK: - Display Mode

    private func displayView(_ d: AdvancedDirective) -> some View {
        List {
            Section("Primary Healthcare Agent") {
                infoRow("Name", d.primaryAgentName)
                infoRow("Relationship", d.primaryAgentRelationship)
                infoRow("Phone", d.primaryAgentPhone)
                infoRow("Email", d.primaryAgentEmail)
                infoRow("Address", d.primaryAgentAddress)
            }
            Section("Alternate Healthcare Agent") {
                infoRow("Name", d.alternateAgentName)
                infoRow("Relationship", d.alternateAgentRelationship)
                infoRow("Phone", d.alternateAgentPhone)
                infoRow("Email", d.alternateAgentEmail)
                infoRow("Address", d.alternateAgentAddress)
            }
            Section("Organ Donation") {
                infoRow("Donation", d.organDonation)
                infoRow("Preferences", d.organDonationPreferences)
            }
            Section("Life-Sustaining Treatment") {
                infoRow("Life Support", displayTreatment(d.lifeSupport))
                infoRow("CPR", displayTreatment(d.cpr))
                infoRow("Ventilator", displayTreatment(d.ventilator))
                infoRow("Feeding Tube", displayTreatment(d.feedingTube))
                infoRow("Dialysis", displayTreatment(d.dialysisDirective))
                infoRow("Blood Transfusion", displayTreatment(d.bloodTransfusion))
            }
            Section("Document Info") {
                infoRow("Signed", d.documentSigned == true ? "Yes" : "No")
                infoRow("Date", d.documentDate)
                infoRow("Witness", d.witnessName)
                infoRow("Notarized", d.notarized == true ? "Yes" : "No")
                infoRow("Location", d.documentLocation)
            }
            if let instructions = d.additionalInstructions, !instructions.isEmpty {
                Section("Additional Instructions") {
                    Text(instructions)
                        .font(.body)
                }
            }
            Section {
                Button("Delete Directive", role: .destructive) {
                    showDeleteConfirmation = true
                }
            }
        }
        .listStyle(.insetGrouped)
    }

    @ViewBuilder
    private func infoRow(_ label: String, _ value: String?) -> some View {
        LabeledContent(label, value: value ?? "—")
    }

    private func displayTreatment(_ value: String?) -> String {
        switch value {
        case "yes": return "Yes"
        case "no": return "No"
        case "let_agent_decide": return "Let Agent Decide"
        default: return value ?? "—"
        }
    }

    // MARK: - Edit Form

    private var editForm: some View {
        Form {
            primaryAgentSection
            alternateAgentSection
            organDonationSection
            treatmentSection
            documentSection
            additionalSection
        }
    }

    private var primaryAgentSection: some View {
        Section("Primary Healthcare Agent") {
            TextField("Name", text: $vm.primaryAgentName)
            TextField("Relationship", text: $vm.primaryAgentRelationship)
            TextField("Phone", text: $vm.primaryAgentPhone)
                .keyboardType(.phonePad)
            TextField("Email", text: $vm.primaryAgentEmail)
                .keyboardType(.emailAddress)
                .textContentType(.emailAddress)
                .autocapitalization(.none)
            TextField("Address", text: $vm.primaryAgentAddress)
        }
    }

    private var alternateAgentSection: some View {
        Section("Alternate Healthcare Agent") {
            TextField("Name", text: $vm.alternateAgentName)
            TextField("Relationship", text: $vm.alternateAgentRelationship)
            TextField("Phone", text: $vm.alternateAgentPhone)
                .keyboardType(.phonePad)
            TextField("Email", text: $vm.alternateAgentEmail)
                .keyboardType(.emailAddress)
                .textContentType(.emailAddress)
                .autocapitalization(.none)
            TextField("Address", text: $vm.alternateAgentAddress)
        }
    }

    private var organDonationSection: some View {
        Section("Organ Donation") {
            Picker("Donation", selection: $vm.organDonation) {
                ForEach(["all", "heart", "kidneys", "liver", "lungs", "none"], id: \.self) {
                    Text($0.capitalized).tag($0)
                }
            }
            TextField("Preferences", text: $vm.organDonationPreferences, axis: .vertical)
                .lineLimit(2...4)
        }
    }

    private var treatmentSection: some View {
        Section("Life-Sustaining Treatment") {
            treatmentPicker("Life Support", selection: $vm.lifeSupport)
            treatmentPicker("CPR", selection: $vm.cpr)
            treatmentPicker("Ventilator", selection: $vm.ventilator)
            treatmentPicker("Feeding Tube", selection: $vm.feedingTube)
            treatmentPicker("Dialysis", selection: $vm.dialysisDirective)
            treatmentPicker("Blood Transfusion", selection: $vm.bloodTransfusion)
        }
    }

    private func treatmentPicker(_ label: String, selection: Binding<String>) -> some View {
        Picker(label, selection: selection) {
            Text("Yes").tag("yes")
            Text("No").tag("no")
            Text("Let Agent Decide").tag("let_agent_decide")
        }
    }

    private var documentSection: some View {
        Section("Document Info") {
            Toggle("Signed", isOn: $vm.documentSigned)
            if vm.documentSigned {
                DatePicker("Date", selection: $vm.documentDate, displayedComponents: .date)
            }
            TextField("Witness Name", text: $vm.witnessName)
            Toggle("Notarized", isOn: $vm.notarized)
            TextField("Document Location", text: $vm.documentLocation)
        }
    }

    private var additionalSection: some View {
        Section("Additional Instructions") {
            TextField("Instructions…", text: $vm.additionalInstructions, axis: .vertical)
                .lineLimit(3...8)
        }
    }
}
