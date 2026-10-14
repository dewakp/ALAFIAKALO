// Copyright © 2026 Wole Akpose / 6igma Health Inc.
// All rights reserved. ALAFIA — proprietary and confidential.

import SwiftUI

struct ChronicConditionsView: View {
    @StateObject private var viewModel = ChronicConditionsViewModel()
    @State private var showingAddCondition = false
    @State private var selectedCondition: ChronicCondition?
    
    var body: some View {
        NavigationStack {
            ZStack {
                if viewModel.isLoading {
                    ProgressView("Loading...")
                } else if viewModel.conditions.isEmpty {
                    VStack(spacing: 20) {
                        Image(systemName: "heart.text.square")
                            .font(.system(size: 60))
                            .foregroundColor(.gray)
                        Text("No Chronic Conditions")
                            .font(.title2)
                            .foregroundColor(.secondary)
                        Text("Tap + to add a condition")
                            .foregroundColor(.secondary)
                    }
                } else {
                    List {
                        ForEach(viewModel.conditions) { condition in
                            ConditionRow(condition: condition)
                                .onTapGesture {
                                    selectedCondition = condition
                                    showingAddCondition = true
                                }
                        }
                        .onDelete(perform: deleteCondition)
                    }
                }
            }
            .navigationTitle("Chronic Conditions")
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: {
                        selectedCondition = nil
                        showingAddCondition = true
                    }) {
                        Image(systemName: "plus")
                    }
                }
            }
            .sheet(isPresented: $showingAddCondition) {
                ConditionFormView(
                    condition: selectedCondition,
                    onSave: { condition, therapies in
                        if let existing = selectedCondition {
                            viewModel.updateCondition(id: existing.id, condition: condition,
                                                      therapies: therapies)
                        } else {
                            viewModel.createCondition(condition, therapies: therapies)
                        }
                        showingAddCondition = false
                    }
                )
            }
            .onAppear {
                viewModel.loadConditions()
            }
            .alert("Error", isPresented: $viewModel.showError) {
                Button("OK", role: .cancel) { }
            } message: {
                Text(viewModel.errorMessage)
            }
        }
    }
    
    private func deleteCondition(at offsets: IndexSet) {
        offsets.forEach { index in
            let condition = viewModel.conditions[index]
            viewModel.deleteCondition(id: condition.id)
        }
    }
}

struct ConditionRow: View {
    let condition: ChronicCondition
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(condition.conditionName)
                    .font(.headline)
                Spacer()
                ChronicSeverityBadge(severity: condition.severity)
                if !condition.isActive {
                    Text("INACTIVE")
                        .font(.caption)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Color.gray)
                        .foregroundColor(.white)
                        .cornerRadius(8)
                }
            }
            
            HStack {
                Text(condition.category.capitalized.replacingOccurrences(of: "_", with: " "))
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                
                if let icd11 = condition.icd11Code {
                    Text("• ICD-11: \(icd11)")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }

                if let icd10 = condition.icd10Code {
                    Text("• ICD-10: \(icd10)")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            
            if let diagnosisDate = condition.diagnosisDate {
                Text("Diagnosed: \(diagnosisDate, style: .date)")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            
            if let physician = condition.primaryPhysician {
                Text("Physician: \(physician)")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
        .padding(.vertical, 4)
    }
}

struct ChronicSeverityBadge: View {
    let severity: String
    
    var color: Color {
        switch severity {
        case "mild": return .green
        case "moderate": return .orange
        case "severe": return .red
        case "critical": return Color(red: 0.82, green: 0.18, blue: 0.18)
        case "remission": return .blue
        default: return .gray
        }
    }
    
    var body: some View {
        Text(severity.uppercased())
            .font(.caption)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(color)
            .foregroundColor(.white)
            .cornerRadius(8)
    }
}

/// One therapy a patient can declare — an ICD-11 code with WHO's own title.
///
/// `group`/`groupTitle` are the SERVER's grouping. This file must never split
/// a code on its dot to decide which branch it belongs to: that is the client
/// deciding what a code means, which is the §3ad rule the hand-typed enum broke.
struct TherapyOption: Codable, Identifiable {
    let code: String
    let title: String
    let surface: String
    let group: String?
    let groupTitle: String?
    var id: String { code }

    enum CodingKeys: String, CodingKey {
        case code, title, surface, group
        case groupTitle = "group_title"
    }
}

struct TherapyOptionsResponse: Codable {
    let options: [TherapyOption]
}

/// One STATEMENT about one therapy.
///
/// Operator, 2026-10-14: *"a comprehensive list with items zeroed out (no
/// impact) when not present (like a switch)"*.
///
/// `receiving` is NOT optional and has no default. A row exists only because
/// somebody answered, so the three states are:
///
///     no row            nobody asked          -> unknown, nothing inferred
///     receiving false   explicitly not on it  -> a measured ZERO
///     receiving true    undergoing it         -> opens its screen
///
/// A checkbox could only ever express the third (§3at).
struct ConditionTherapyRow: Codable, Identifiable {
    let therapyCode: String
    let receiving: Bool
    var regimen: String?
    var id: String { therapyCode }

    enum CodingKeys: String, CodingKey {
        case receiving, regimen
        case therapyCode = "therapy_code"
    }
}

struct ConditionTherapiesResponse: Codable {
    let therapies: [ConditionTherapyRow]
}

struct ConditionTherapiesUpdate: Codable {
    let therapies: [ConditionTherapyRow]
}

struct ConditionFormView: View {
    /// Fetched from the server, which reads it out of the bundled WHO ICD-11
    /// catalog. This file used to hold its OWN copy of the list — one of four,
    /// alongside the backend, web and Android — while WHO already codes every
    /// entry (QB94.1 "Care involving extracorporeal dialysis", QB94.2 "Care
    /// involving peritoneal dialysis", …). §3ad: the catalog is the authority
    /// and a code is never typed from memory.
    ///
    /// Empty until it loads, and empty if the request fails: the field simply
    /// does not render, which is correct — a guessed list is worse than none.
    @State private var therapyOptions: [TherapyOption] = []

    /// Each therapy's STATEMENT, keyed by code. A code ABSENT from this
    /// dictionary was never answered — a different fact from `false`, and
    /// keeping them apart is the whole reason this replaced a set of ticks.
    @State private var therapySwitches: [String: Bool] = [:]
    @State private var therapyRegimens: [String: String] = [:]
    /// §3aa: an unreadable list must not render as a screen full of zeros.
    @State private var therapyLoadFailed = false

    /// The branches, in the order the server sent them.
    private var therapyGroups: [(code: String, title: String?, options: [TherapyOption])] {
        var order: [String] = []
        var byGroup: [String: [TherapyOption]] = [:]
        var titles: [String: String?] = [:]
        for option in therapyOptions {
            let key = option.group ?? option.code
            if byGroup[key] == nil {
                order.append(key)
                titles[key] = option.groupTitle
            }
            byGroup[key, default: []].append(option)
        }
        return order.map { (code: $0, title: titles[$0] ?? nil, options: byGroup[$0] ?? []) }
    }

    private func loadTherapyOptions() async {
        if let r: TherapyOptionsResponse =
            try? await APIClient.shared.get("/chronic/therapy-options") {
            therapyOptions = r.options
        }
        // The stored statements, read back before the form is touched. A
        // control that never loads its stored value shows its default, which
        // reads as NEVER RECORDED, and the next save overwrites what was
        // there — §3av, measured on `machine_total_time_minutes`.
        guard let existing = condition else { return }
        do {
            let r: ConditionTherapiesResponse = try await APIClient.shared
                .get("/chronic/conditions/\(existing.id)/therapies")
            var states: [String: Bool] = [:]
            var labels: [String: String] = [:]
            for row in r.therapies {
                states[row.therapyCode] = row.receiving
                if let regimen = row.regimen { labels[row.therapyCode] = regimen }
            }
            therapySwitches = states
            therapyRegimens = labels
            therapyLoadFailed = false
        } catch {
            // Never guess. Every therapy stays UNANSWERED, so the save sends
            // nothing for those codes and what is stored survives.
            therapyLoadFailed = true
        }
    }

    /// One therapy's three-state control.
    ///
    /// Extracted into its own function on purpose: the inline version of this
    /// row made the compiler answer *"unable to type-check this expression in
    /// reasonable time"*, which is how this file's Ω card was written too.
    @ViewBuilder
    private func therapyRow(_ option: TherapyOption) -> some View {
        let state: Bool? = therapySwitches[option.code]
        VStack(alignment: .leading, spacing: 6) {
            // WHO's own title; nothing is relabelled here.
            Text(option.title).font(.subheadline)
            Picker("", selection: Binding<Int>(
                get: { state == nil ? 2 : (state == true ? 0 : 1) },
                set: { choice in
                    switch choice {
                    case 0: therapySwitches[option.code] = true
                    case 1: therapySwitches[option.code] = false
                    default:
                        // Back to unanswered. REMOVING the key is the point: a
                        // client cannot express "unknown" by sending false, so
                        // it stops sending the entry at all.
                        therapySwitches.removeValue(forKey: option.code)
                        therapyRegimens.removeValue(forKey: option.code)
                    }
                }
            )) {
                Text("On this").tag(0)
                Text("Not on this").tag(1)
                Text("Not answered").tag(2)
            }
            .pickerStyle(.segmented)
            // Compounding: therapies given as ONE treatment share a label. It
            // records what is given together and claims nothing about effect.
            if state == true {
                TextField("Given together as (optional)", text: Binding(
                    get: { therapyRegimens[option.code] ?? "" },
                    set: { therapyRegimens[option.code] = $0 }
                ))
                .font(.caption)
            }
        }
        .padding(.vertical, 2)
    }

    /// What the save sends: only the codes somebody answered for.
    private var declaredTherapies: [ConditionTherapyRow] {
        therapySwitches.keys.sorted().map { code in
            ConditionTherapyRow(therapyCode: code,
                                receiving: therapySwitches[code] ?? false,
                                regimen: therapyRegimens[code]?.isEmpty == false
                                    ? therapyRegimens[code] : nil)
        }
    }

    let condition: ChronicCondition?
    /// The condition AND its therapy statements. They travel together because
    /// a switch belongs to a condition that must exist first, and the view
    /// model is where the id comes back.
    let onSave: (ChronicConditionCreate, [ConditionTherapyRow]) -> Void
    
    @Environment(\.dismiss) var dismiss
    @State private var formData = ChronicConditionCreate.empty()
    
    let categories = [
        "cancer", "renal", "diabetes", "blood_disorder", 
        "cardiovascular", "respiratory", "autoimmune",
        "neurological", "endocrine", "other"
    ]
    
    let severities = ["mild", "moderate", "severe", "critical", "remission"]
    
    var body: some View {
        NavigationStack {
            Form {
                Section("Basic Information") {
                    TextField("Condition Name", text: $formData.conditionName)
                    
                    Picker("Category", selection: $formData.category) {
                        ForEach(categories, id: \.self) { category in
                            Text(category.capitalized.replacingOccurrences(of: "_", with: " "))
                                .tag(category)
                        }
                    }
                    
                    ICD11PickerField(
                        code: $formData.icd11Code,
                        title: $formData.icd11Title
                    )

                    TextField("ICD-10 Code", text: Binding(
                        get: { formData.icd10Code ?? "" },
                        set: { formData.icd10Code = $0.isEmpty ? nil : $0 }
                    ))
                    
                    Picker("Severity", selection: $formData.severity) {
                        ForEach(severities, id: \.self) { severity in
                            Text(severity.capitalized).tag(severity)
                        }
                    }
                    
                    Toggle("Currently Active", isOn: $formData.isActive)
                }
                
                Section("Diagnosis") {
                    DatePicker("Diagnosis Date", selection: Binding(
                        get: { formData.diagnosisDate ?? Date() },
                        set: { formData.diagnosisDate = $0 }
                    ), displayedComponents: .date)
                    
                    TextField("Diagnosed By", text: Binding(
                        get: { formData.diagnosedBy ?? "" },
                        set: { formData.diagnosedBy = $0.isEmpty ? nil : $0 }
                    ))
                    
                    TextField("Diagnosing Facility", text: Binding(
                        get: { formData.diagnosingFacility ?? "" },
                        set: { formData.diagnosingFacility = $0.isEmpty ? nil : $0 }
                    ))
                }
                
                Section("Classification") {
                    TextField("Stage", text: Binding(
                        get: { formData.stage ?? "" },
                        set: { formData.stage = $0.isEmpty ? nil : $0 }
                    ))
                    
                    TextField("Grade", text: Binding(
                        get: { formData.grade ?? "" },
                        set: { formData.grade = $0.isEmpty ? nil : $0 }
                    ))
                }
                
                Section("Healthcare Providers") {
                    TextField("Primary Physician", text: Binding(
                        get: { formData.primaryPhysician ?? "" },
                        set: { formData.primaryPhysician = $0.isEmpty ? nil : $0 }
                    ))
                    
                    TextField("Specialist Physician", text: Binding(
                        get: { formData.specialistPhysician ?? "" },
                        set: { formData.specialistPhysician = $0.isEmpty ? nil : $0 }
                    ))
                }
                
                Section("Monitoring") {
                    TextField("Monitoring Frequency", text: Binding(
                        get: { formData.monitoringFrequency ?? "" },
                        set: { formData.monitoringFrequency = $0.isEmpty ? nil : $0 }
                    ))
                    
                    DatePicker("Next Appointment", selection: Binding(
                        get: { formData.nextAppointment ?? Date() },
                        set: { formData.nextAppointment = $0 }
                    ), displayedComponents: .date)
                }
                
                // Therapies this condition is treated with — a SWITCH over
                // WHO's whole therapy branch, not a set of ticked items.
                //
                // This was a checkbox per therapy, and a checkbox cannot
                // record three states (§3at). Unticked meant BOTH "not on this
                // therapy" and "nobody asked"; the first retires a screen and
                // the second must leave it alone.
                Section {
                    Text("For each therapy, say whether you are on it, not on it, or leave it unanswered. Saying you are not on one is an answer too.")
                        .font(.caption).foregroundStyle(.secondary)
                    if therapyLoadFailed {
                        Text("Could not load your therapy answers. Nothing has been changed.")
                            .font(.caption).foregroundStyle(.orange)
                    }
                    ForEach(therapyGroups, id: \.code) { group in
                        // WHO's own heading, or the shared prefix of its
                        // members where the branch root carries no title.
                        DisclosureGroup(group.title ?? group.code) {
                            ForEach(group.options) { option in
                                therapyRow(option)
                            }
                        }
                    }
                } header: {
                    Text("Therapies")
                }

                Section("Treatment & Notes") {
                    TextEditor(text: Binding(
                        get: { formData.currentTreatmentPlan ?? "" },
                        set: { formData.currentTreatmentPlan = $0.isEmpty ? nil : $0 }
                    ))
                    .frame(height: 100)
                    .overlay(
                        Text("Current Treatment Plan")
                            .foregroundColor(.secondary)
                            .opacity((formData.currentTreatmentPlan ?? "").isEmpty ? 0.5 : 0),
                        alignment: .topLeading
                    )
                    
                    TextEditor(text: Binding(
                        get: { formData.symptoms ?? "" },
                        set: { formData.symptoms = $0.isEmpty ? nil : $0 }
                    ))
                    .frame(height: 80)
                    .overlay(
                        Text("Symptoms")
                            .foregroundColor(.secondary)
                            .opacity((formData.symptoms ?? "").isEmpty ? 0.5 : 0),
                        alignment: .topLeading
                    )
                    
                    TextEditor(text: Binding(
                        get: { formData.notes ?? "" },
                        set: { formData.notes = $0.isEmpty ? nil : $0 }
                    ))
                    .frame(height: 80)
                    .overlay(
                        Text("Additional Notes")
                            .foregroundColor(.secondary)
                            .opacity((formData.notes ?? "").isEmpty ? 0.5 : 0),
                        alignment: .topLeading
                    )
                }
            }
            .navigationTitle(condition == nil ? "New Condition" : "Edit Condition")
            .task { await loadTherapyOptions() }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") {
                        dismiss()
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Save") {
                        onSave(formData, declaredTherapies)
                        dismiss()
                    }
                    .disabled(formData.conditionName.isEmpty)
                }
            }
            .onAppear {
                if let condition = condition {
                    formData = ChronicConditionCreate(from: condition)
                }
            }
        }
    }
}

// MARK: - Data Models

struct ChronicCondition: Identifiable, Codable {
    let id: Int
    let userId: Int
    let conditionName: String
    let category: String
    let icd10Code: String?
    // Two coding systems, deliberately: ICD-10 arrives with an imported
    // record, ICD-11 is what the patient picks. See CLAUDE.md §3aa.
    let icd11Code: String?
    let icd11Title: String?
    let severity: String
    let diagnosisDate: Date?
    let diagnosedBy: String?
    let diagnosingFacility: String?
    let isActive: Bool
    let remissionDate: Date?
    let stage: String?
    let grade: String?
    let currentTreatmentPlan: String?
    /// Therapies this condition is treated with. DECLARED by the patient, and
    /// what decides whether the app offers the matching treatment screens —
    /// the backend used to guess it by substring-matching the condition's
    /// wording, so "ESKD" matched nothing and "history of dialysis" matched
    /// everything.
    let therapyTypes: [String]?
    let primaryPhysician: String?
    let specialistPhysician: String?
    let monitoringFrequency: String?
    let nextAppointment: Date?
    let notes: String?
    let symptoms: String?
    let complications: String?
    let createdAt: Date
    let updatedAt: Date
    
    enum CodingKeys: String, CodingKey {
        case id, category, severity, stage, grade, notes, symptoms, complications
        case userId = "user_id"
        case conditionName = "condition_name"
        case icd10Code = "icd10_code"
        case icd11Code = "icd11_code"
        case icd11Title = "icd11_title"
        case diagnosisDate = "diagnosis_date"
        case diagnosedBy = "diagnosed_by"
        case diagnosingFacility = "diagnosing_facility"
        case isActive = "is_active"
        case remissionDate = "remission_date"
        case currentTreatmentPlan = "current_treatment_plan"
        case therapyTypes = "therapy_types"
        case primaryPhysician = "primary_physician"
        case specialistPhysician = "specialist_physician"
        case monitoringFrequency = "monitoring_frequency"
        case nextAppointment = "next_appointment"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct ChronicConditionCreate: Codable {
    var conditionName: String
    var category: String
    var icd10Code: String?
    var icd11Code: String?
    var icd11Title: String?
    var severity: String
    var diagnosisDate: Date?
    var diagnosedBy: String?
    var diagnosingFacility: String?
    var isActive: Bool
    var remissionDate: Date?
    var stage: String?
    var grade: String?
    var currentTreatmentPlan: String?
    var primaryPhysician: String?
    var specialistPhysician: String?
    var monitoringFrequency: String?
    var nextAppointment: Date?
    var notes: String?
    var symptoms: String?
    var complications: String?
    
    enum CodingKeys: String, CodingKey {
        case category, severity, stage, grade, notes, symptoms, complications
        case conditionName = "condition_name"
        case icd10Code = "icd10_code"
        case icd11Code = "icd11_code"
        case icd11Title = "icd11_title"
        case diagnosisDate = "diagnosis_date"
        case diagnosedBy = "diagnosed_by"
        case diagnosingFacility = "diagnosing_facility"
        case isActive = "is_active"
        case remissionDate = "remission_date"
        case currentTreatmentPlan = "current_treatment_plan"
        case primaryPhysician = "primary_physician"
        case specialistPhysician = "specialist_physician"
        case monitoringFrequency = "monitoring_frequency"
        case nextAppointment = "next_appointment"
    }
    
    static func empty() -> ChronicConditionCreate {
        ChronicConditionCreate(
            conditionName: "",
            category: "other",
            severity: "moderate",
            isActive: true
        )
    }
    
    init(from condition: ChronicCondition) {
        self.conditionName = condition.conditionName
        self.category = condition.category
        self.icd10Code = condition.icd10Code
        self.icd11Code = condition.icd11Code
        self.icd11Title = condition.icd11Title
        self.severity = condition.severity
        self.diagnosisDate = condition.diagnosisDate
        self.diagnosedBy = condition.diagnosedBy
        self.diagnosingFacility = condition.diagnosingFacility
        self.isActive = condition.isActive
        self.remissionDate = condition.remissionDate
        self.stage = condition.stage
        self.grade = condition.grade
        self.currentTreatmentPlan = condition.currentTreatmentPlan
        self.primaryPhysician = condition.primaryPhysician
        self.specialistPhysician = condition.specialistPhysician
        self.monitoringFrequency = condition.monitoringFrequency
        self.nextAppointment = condition.nextAppointment
        self.notes = condition.notes
        self.symptoms = condition.symptoms
        self.complications = condition.complications
    }
    
    init(conditionName: String, category: String, severity: String, isActive: Bool,
         icd10Code: String? = nil, icd11Code: String? = nil, icd11Title: String? = nil,
         diagnosisDate: Date? = nil, diagnosedBy: String? = nil,
         diagnosingFacility: String? = nil, remissionDate: Date? = nil, stage: String? = nil,
         grade: String? = nil, currentTreatmentPlan: String? = nil, primaryPhysician: String? = nil,
         specialistPhysician: String? = nil, monitoringFrequency: String? = nil,
         nextAppointment: Date? = nil, notes: String? = nil, symptoms: String? = nil,
         complications: String? = nil) {
        self.conditionName = conditionName
        self.category = category
        self.icd10Code = icd10Code
        self.icd11Code = icd11Code
        self.icd11Title = icd11Title
        self.severity = severity
        self.diagnosisDate = diagnosisDate
        self.diagnosedBy = diagnosedBy
        self.diagnosingFacility = diagnosingFacility
        self.isActive = isActive
        self.remissionDate = remissionDate
        self.stage = stage
        self.grade = grade
        self.currentTreatmentPlan = currentTreatmentPlan
        self.primaryPhysician = primaryPhysician
        self.specialistPhysician = specialistPhysician
        self.monitoringFrequency = monitoringFrequency
        self.nextAppointment = nextAppointment
        self.notes = notes
        self.symptoms = symptoms
        self.complications = complications
    }
}

// MARK: - ViewModel

@MainActor
class ChronicConditionsViewModel: ObservableObject {
    @Published var conditions: [ChronicCondition] = []
    @Published var isLoading = false
    @Published var showError = false
    @Published var errorMessage = ""
    
    func loadConditions() {
        isLoading = true
        Task {
            do {
                conditions = try await APIClient.shared.get("/chronic/conditions")
                isLoading = false
            } catch {
                errorMessage = AppLanguage.text("Failed to load conditions: \(error.localizedDescription)")
                showError = true
                isLoading = false
            }
        }
    }
    
    func createCondition(_ condition: ChronicConditionCreate,
                         therapies: [ConditionTherapyRow] = []) {
        Task {
            do {
                let created: ChronicCondition = try await APIClient.shared.post("/chronic/conditions", body: condition)
                await saveTherapies(conditionId: created.id, therapies: therapies)
                loadConditions()
            } catch {
                errorMessage = AppLanguage.text("Failed to create condition: \(error.localizedDescription)")
                showError = true
            }
        }
    }
    
    func updateCondition(id: Int, condition: ChronicConditionCreate,
                         therapies: [ConditionTherapyRow] = []) {
        Task {
            do {
                let _: ChronicCondition = try await APIClient.shared.put("/chronic/conditions/\(id)", body: condition)
                await saveTherapies(conditionId: id, therapies: therapies)
                loadConditions()
            } catch {
                errorMessage = AppLanguage.text("Failed to update condition: \(error.localizedDescription)")
                showError = true
            }
        }
    }
    
    /// The therapy switches, written AFTER the condition exists.
    ///
    /// Deliberately a second request and deliberately not fatal to the first:
    /// losing a therapy answer is bad, losing the condition the patient just
    /// typed because a therapy write failed is worse (§3c's argument for
    /// saving the meal before estimating it). The failure is REPORTED —
    /// silence would leave the patient believing they declared a treatment the
    /// navigation will not reflect (§3aa).
    private func saveTherapies(conditionId: Int,
                               therapies: [ConditionTherapyRow]) async {
        guard !therapies.isEmpty else { return }
        do {
            let _: ConditionTherapiesResponse = try await APIClient.shared.put(
                "/chronic/conditions/\(conditionId)/therapies",
                body: ConditionTherapiesUpdate(therapies: therapies))
        } catch {
            errorMessage = AppLanguage.text(
                "Your condition was saved, but your therapy answers were not: \(error.localizedDescription)")
            showError = true
        }
    }

    func deleteCondition(id: Int) {
        Task {
            do {
                try await APIClient.shared.delete("/chronic/conditions/\(id)")
                loadConditions()
            } catch {
                errorMessage = AppLanguage.text("Failed to delete condition: \(error.localizedDescription)")
                showError = true
            }
        }
    }
}
