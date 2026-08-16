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
                    onSave: { condition in
                        if let existing = selectedCondition {
                            viewModel.updateCondition(id: existing.id, condition: condition)
                        } else {
                            viewModel.createCondition(condition)
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

struct ConditionFormView: View {
    let condition: ChronicCondition?
    let onSave: (ChronicConditionCreate) -> Void
    
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
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") {
                        dismiss()
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Save") {
                        onSave(formData)
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
    let severity: String
    let diagnosisDate: Date?
    let diagnosedBy: String?
    let diagnosingFacility: String?
    let isActive: Bool
    let remissionDate: Date?
    let stage: String?
    let grade: String?
    let currentTreatmentPlan: String?
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
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct ChronicConditionCreate: Codable {
    var conditionName: String
    var category: String
    var icd10Code: String?
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
         icd10Code: String? = nil, diagnosisDate: Date? = nil, diagnosedBy: String? = nil,
         diagnosingFacility: String? = nil, remissionDate: Date? = nil, stage: String? = nil,
         grade: String? = nil, currentTreatmentPlan: String? = nil, primaryPhysician: String? = nil,
         specialistPhysician: String? = nil, monitoringFrequency: String? = nil,
         nextAppointment: Date? = nil, notes: String? = nil, symptoms: String? = nil,
         complications: String? = nil) {
        self.conditionName = conditionName
        self.category = category
        self.icd10Code = icd10Code
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
                errorMessage = "Failed to load conditions: \(error.localizedDescription)"
                showError = true
                isLoading = false
            }
        }
    }
    
    func createCondition(_ condition: ChronicConditionCreate) {
        Task {
            do {
                let _: ChronicCondition = try await APIClient.shared.post("/chronic/conditions", body: condition)
                loadConditions()
            } catch {
                errorMessage = "Failed to create condition: \(error.localizedDescription)"
                showError = true
            }
        }
    }
    
    func updateCondition(id: Int, condition: ChronicConditionCreate) {
        Task {
            do {
                let _: ChronicCondition = try await APIClient.shared.put("/chronic/conditions/\(id)", body: condition)
                loadConditions()
            } catch {
                errorMessage = "Failed to update condition: \(error.localizedDescription)"
                showError = true
            }
        }
    }
    
    func deleteCondition(id: Int) {
        Task {
            do {
                try await APIClient.shared.delete("/chronic/conditions/\(id)")
                loadConditions()
            } catch {
                errorMessage = "Failed to delete condition: \(error.localizedDescription)"
                showError = true
            }
        }
    }
}
