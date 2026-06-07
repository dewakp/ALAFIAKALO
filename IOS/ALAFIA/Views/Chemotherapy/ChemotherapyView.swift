import SwiftUI

// MARK: - ViewModel

@Observable
final class ChemotherapyViewModel {
    var sessions: [TherapySession] = []
    var isLoading = false
    var errorMessage: String?
    var showAddSheet = false
    var isSaving = false

    // Form state
    var scheduledDate = Date()
    var status = "completed"
    var therapyName = ""
    var sessionNumber = ""
    var totalSessionsPlanned = ""
    var durationMinutes = ""
    var startTime = ""
    var endTime = ""
    // Drugs
    var drugsAdministered = ""
    var dosage = ""
    var routeOfAdministration = "IV Infusion"
    // Vitals
    var preSystolicBp = ""
    var preDiastolicBp = ""
    var preHeartRate = ""
    var preTemperature = ""
    var postSystolicBp = ""
    var postDiastolicBp = ""
    var postHeartRate = ""
    var postTemperature = ""
    var oxygenSaturation = ""
    // Outcomes
    var sideEffects = ""
    var adverseReactions = ""
    var patientTolerance = ""
    var facilityName = ""
    var attendingPhysician = ""
    var attendingNurse = ""
    var clinicalNotes = ""
    var patientNotes = ""

    static let routes = ["IV Push", "IV Drip", "IV Infusion", "Oral", "Subcutaneous", "Intramuscular", "Intrathecal"]
    static let statusOptions = ["scheduled", "in_progress", "completed", "cancelled", "missed"]
    static let toleranceOptions = ["Well Tolerated", "Moderate", "Poor", "Severe Reaction"]
    static let commonSideEffects = [
        "Nausea", "Vomiting", "Fatigue", "Hair Loss", "Mouth Sores", "Neuropathy",
        "Low WBC", "Low Platelets", "Anemia", "Diarrhea", "Constipation",
        "Loss of Appetite", "Skin Changes", "Fever", "Chills"
    ]

    func load() async {
        isLoading = true; errorMessage = nil
        do {
            sessions = try await APIClient.shared.get("/chronic/therapy-sessions?therapy_type=chemotherapy")
        } catch { errorMessage = error.localizedDescription }
        isLoading = false
    }

    func deleteSession(id: Int) async {
        do {
            try await APIClient.shared.delete("/chronic/therapy-sessions/\(id)")
            sessions.removeAll { $0.id == id }
        } catch { errorMessage = error.localizedDescription }
    }

    func resetForm() {
        scheduledDate = Date(); status = "completed"; therapyName = ""; sessionNumber = ""; totalSessionsPlanned = ""
        durationMinutes = ""; startTime = ""; endTime = ""
        drugsAdministered = ""; dosage = ""; routeOfAdministration = "IV Infusion"
        preSystolicBp = ""; preDiastolicBp = ""; preHeartRate = ""; preTemperature = ""
        postSystolicBp = ""; postDiastolicBp = ""; postHeartRate = ""; postTemperature = ""
        oxygenSaturation = ""; sideEffects = ""; adverseReactions = ""; patientTolerance = ""
        facilityName = ""; attendingPhysician = ""; attendingNurse = ""
        clinicalNotes = ""; patientNotes = ""; isSaving = false
    }

    func submit() async {
        isSaving = true
        let df = DateFormatter(); df.dateFormat = "yyyy-MM-dd"

        let body = TherapySessionCreate(
            therapyType: "CHEMOTHERAPY",
            scheduledDate: df.string(from: scheduledDate),
            status: status,
            therapyName: therapyName.isEmpty ? nil : therapyName,
            sessionNumber: Int(sessionNumber),
            totalSessionsPlanned: Int(totalSessionsPlanned),
            durationMinutes: Int(durationMinutes),
            actualStartTime: startTime.isEmpty ? nil : startTime,
            actualEndTime: endTime.isEmpty ? nil : endTime,
            facilityName: facilityName.isEmpty ? nil : facilityName,
            attendingPhysician: attendingPhysician.isEmpty ? nil : attendingPhysician,
            attendingNurse: attendingNurse.isEmpty ? nil : attendingNurse,
            dialysisAccessType: nil,
            dryWeightKg: nil,
            preDialysisWeightKg: nil,
            postDialysisWeightKg: nil,
            fluidRemovedMl: nil,
            bloodFlowRate: nil,
            dialysateFlowRate: nil,
            drugsAdministered: drugsAdministered.isEmpty ? nil : drugsAdministered,
            dosage: dosage.isEmpty ? nil : dosage,
            routeOfAdministration: routeOfAdministration,
            preSystolicBp: Int(preSystolicBp),
            preDiastolicBp: Int(preDiastolicBp),
            postSystolicBp: Int(postSystolicBp),
            postDiastolicBp: Int(postDiastolicBp),
            preHeartRate: Int(preHeartRate),
            postHeartRate: Int(postHeartRate),
            preTemperature: Double(preTemperature),
            postTemperature: Double(postTemperature),
            oxygenSaturation: Int(oxygenSaturation),
            sideEffects: sideEffects.isEmpty ? nil : sideEffects,
            adverseReactions: adverseReactions.isEmpty ? nil : adverseReactions,
            patientTolerance: patientTolerance.isEmpty ? nil : patientTolerance,
            clinicalNotes: clinicalNotes.isEmpty ? nil : clinicalNotes,
            patientNotes: patientNotes.isEmpty ? nil : patientNotes
        )

        do {
            let _: TherapySession = try await APIClient.shared.post("/chronic/therapy-sessions", body: body)
            resetForm()
            showAddSheet = false
            await load()
        } catch { errorMessage = error.localizedDescription }
        isSaving = false
    }
}

// MARK: - View

struct ChemotherapyView: View {
    @State private var vm = ChemotherapyViewModel()
    @State private var selectedEffects: Set<String> = []

    var body: some View {
        Group {
            if vm.isLoading {
                ProgressView("Loading…")
            } else if vm.sessions.isEmpty {
                ContentUnavailableView(
                    "No Chemotherapy Sessions",
                    systemImage: "cross.vial",
                    description: Text("Tap + to log a chemotherapy session.")
                )
            } else {
                sessionList
            }
        }
        .navigationTitle("Chemotherapy")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button { vm.resetForm(); selectedEffects = []; vm.showAddSheet = true } label: {
                    Image(systemName: "plus")
                }
            }
        }
        .task { await vm.load() }
        .refreshable { await vm.load() }
        .sheet(isPresented: $vm.showAddSheet) { addSessionSheet }
        .alert("Error", isPresented: .constant(vm.errorMessage != nil)) {
            Button("OK") { vm.errorMessage = nil }
        } message: { Text(vm.errorMessage ?? "") }
    }

    // MARK: - Session List

    private var sessionList: some View {
        List {
            // Summary
            Section {
                HStack {
                    ChemoStatCard(title: "Total", value: "\(vm.sessions.count)", color: .purple)
                    ChemoStatCard(title: "Completed", value: "\(vm.sessions.filter { $0.status == "completed" }.count)", color: .green)
                    ChemoStatCard(title: "Scheduled", value: "\(vm.sessions.filter { $0.status == "scheduled" }.count)", color: .orange)
                }
            }

            ForEach(vm.sessions) { session in
                sessionCard(session)
            }
            .onDelete { indexSet in
                Task { for i in indexSet { await vm.deleteSession(id: vm.sessions[i].id) } }
            }
        }
    }

    private func sessionCard(_ s: TherapySession) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                VStack(alignment: .leading) {
                    Text(s.therapyName ?? "Chemotherapy")
                        .font(.headline)
                    HStack(spacing: 4) {
                        if let num = s.sessionNumber {
                            Text("Session #\(num)")
                            if let total = s.totalSessionsPlanned { Text("/ \(total)").foregroundStyle(.secondary) }
                        }
                        Text("·").foregroundStyle(.secondary)
                        Text(formatDate(s.scheduledDate)).foregroundStyle(.secondary)
                    }
                    .font(.caption)
                }
                Spacer()
                Text(s.status.replacingOccurrences(of: "_", with: " ").capitalized)
                    .font(.caption).bold()
                    .padding(.horizontal, 10).padding(.vertical, 3)
                    .background(statusColor(s.status).opacity(0.15))
                    .foregroundStyle(statusColor(s.status))
                    .clipShape(Capsule())
            }

            Divider()

            // Drugs
            if let drugs = s.drugsAdministered, !drugs.isEmpty {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Drugs").font(.system(size: 10)).foregroundStyle(.secondary)
                    Text(drugs).font(.callout)
                }
            }

            HStack(spacing: 16) {
                if let d = s.dosage, !d.isEmpty { ChemoInfoPill(label: "Dosage", value: d) }
                if let r = s.routeOfAdministration, !r.isEmpty { ChemoInfoPill(label: "Route", value: r) }
                if let dur = s.durationMinutes { ChemoInfoPill(label: "Duration", value: "\(dur) min") }
            }

            // Vitals
            if s.preSystolicBp != nil || s.postSystolicBp != nil {
                HStack(spacing: 16) {
                    ChemoInfoPill(label: "Pre BP", value: fmtBP(s.preSystolicBp, s.preDiastolicBp))
                    ChemoInfoPill(label: "Post BP", value: fmtBP(s.postSystolicBp, s.postDiastolicBp))
                    if let o2 = s.oxygenSaturation { ChemoInfoPill(label: "SpO₂", value: "\(o2)%") }
                }
            }

            // Tolerance & Side Effects
            if let tol = s.patientTolerance, !tol.isEmpty {
                HStack {
                    Text("Tolerance:").font(.caption).bold()
                    Text(tol).font(.caption)
                        .foregroundStyle(tol.contains("Severe") ? .red : tol.contains("Poor") ? .orange : .green)
                }
            }
            if let se = s.sideEffects, !se.isEmpty {
                Text("Side Effects: \(se)").font(.caption).foregroundStyle(.secondary).lineLimit(2)
            }
            if let ar = s.adverseReactions, !ar.isEmpty {
                Text("⚠️ \(ar)").font(.caption).foregroundStyle(.red)
            }

            if let fac = s.facilityName, !fac.isEmpty {
                Text("📍 \(fac)").font(.caption2).foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
    }

    // MARK: - Add Session Sheet

    private var addSessionSheet: some View {
        NavigationStack {
            Form {
                Section("Regimen & Scheduling") {
                    TextField("Protocol (e.g., FOLFOX, R-CHOP)", text: $vm.therapyName)
                    DatePicker("Date", selection: $vm.scheduledDate, displayedComponents: .date)
                    Picker("Status", selection: $vm.status) {
                        ForEach(ChemotherapyViewModel.statusOptions, id: \.self) { Text($0.replacingOccurrences(of: "_", with: " ").capitalized) }
                    }
                    HStack {
                        VStack(alignment: .leading) { Text("Session #").font(.caption); TextField("#", text: $vm.sessionNumber).keyboardType(.numberPad) }
                        VStack(alignment: .leading) { Text("Total Planned").font(.caption); TextField("#", text: $vm.totalSessionsPlanned).keyboardType(.numberPad) }
                    }
                    VStack(alignment: .leading) { Text("Duration (min)").font(.caption); TextField("120", text: $vm.durationMinutes).keyboardType(.numberPad) }
                }

                Section("Drugs & Administration") {
                    TextField("Drugs (e.g., Cisplatin 75mg/m²)", text: $vm.drugsAdministered)
                    TextField("Dosage (e.g., 75mg/m²)", text: $vm.dosage)
                    Picker("Route", selection: $vm.routeOfAdministration) {
                        ForEach(ChemotherapyViewModel.routes, id: \.self) { Text($0) }
                    }
                }

                Section("Pre-Treatment Vitals") {
                    HStack {
                        VStack(alignment: .leading) { Text("Systolic").font(.caption); TextField("mmHg", text: $vm.preSystolicBp).keyboardType(.numberPad) }
                        VStack(alignment: .leading) { Text("Diastolic").font(.caption); TextField("mmHg", text: $vm.preDiastolicBp).keyboardType(.numberPad) }
                    }
                    HStack {
                        VStack(alignment: .leading) { Text("Heart Rate").font(.caption); TextField("bpm", text: $vm.preHeartRate).keyboardType(.numberPad) }
                        VStack(alignment: .leading) { Text("Temp (°F)").font(.caption); TextField("°F", text: $vm.preTemperature).keyboardType(.decimalPad) }
                    }
                }

                Section("Post-Treatment Vitals") {
                    HStack {
                        VStack(alignment: .leading) { Text("Systolic").font(.caption); TextField("mmHg", text: $vm.postSystolicBp).keyboardType(.numberPad) }
                        VStack(alignment: .leading) { Text("Diastolic").font(.caption); TextField("mmHg", text: $vm.postDiastolicBp).keyboardType(.numberPad) }
                    }
                    HStack {
                        VStack(alignment: .leading) { Text("Heart Rate").font(.caption); TextField("bpm", text: $vm.postHeartRate).keyboardType(.numberPad) }
                        VStack(alignment: .leading) { Text("Temp (°F)").font(.caption); TextField("°F", text: $vm.postTemperature).keyboardType(.decimalPad) }
                    }
                    VStack(alignment: .leading) { Text("SpO₂ (%)").font(.caption); TextField("%", text: $vm.oxygenSaturation).keyboardType(.numberPad) }
                }

                Section("Side Effects") {
                    Text("Tap to toggle").font(.caption).foregroundStyle(.secondary)
                    FlowLayout(spacing: 6) {
                        ForEach(ChemotherapyViewModel.commonSideEffects, id: \.self) { effect in
                            Button {
                                if selectedEffects.contains(effect) {
                                    selectedEffects.remove(effect)
                                } else {
                                    selectedEffects.insert(effect)
                                }
                                vm.sideEffects = selectedEffects.sorted().joined(separator: ", ")
                            } label: {
                                Text(effect)
                                    .font(.caption)
                                    .padding(.horizontal, 10).padding(.vertical, 5)
                                    .background(selectedEffects.contains(effect) ? Color.purple : Color(.systemGray5))
                                    .foregroundStyle(selectedEffects.contains(effect) ? .white : .primary)
                                    .clipShape(Capsule())
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    Picker("Patient Tolerance", selection: $vm.patientTolerance) {
                        Text("Select…").tag("")
                        ForEach(ChemotherapyViewModel.toleranceOptions, id: \.self) { Text($0).tag($0) }
                    }
                    TextField("Adverse Reactions", text: $vm.adverseReactions)
                }

                Section("Facility & Staff") {
                    TextField("Facility", text: $vm.facilityName)
                    TextField("Physician", text: $vm.attendingPhysician)
                    TextField("Nurse", text: $vm.attendingNurse)
                }

                Section("Notes") {
                    TextField("Clinical Notes", text: $vm.clinicalNotes, axis: .vertical).lineLimit(2...4)
                    TextField("Patient Notes", text: $vm.patientNotes, axis: .vertical).lineLimit(2...4)
                }
            }
            .navigationTitle("New Chemo Session")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { vm.showAddSheet = false } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { Task { await vm.submit() } }.disabled(vm.isSaving)
                }
            }
        }
    }

    // MARK: - Helpers

    private func formatDate(_ s: String) -> String {
        let df = DateFormatter(); df.dateFormat = "yyyy-MM-dd"
        guard let date = df.date(from: String(s.prefix(10))) else { return s }
        df.dateStyle = .medium; return df.string(from: date)
    }

    private func fmtBP(_ s: Int?, _ d: Int?) -> String {
        guard let s, let d else { return "—" }; return "\(s)/\(d)"
    }

    private func statusColor(_ s: String) -> Color {
        switch s {
        case "completed": return .green; case "in_progress": return .blue
        case "scheduled": return .orange; case "cancelled": return .red
        case "missed": return .gray; default: return .secondary
        }
    }
}

// MARK: - Reusable subviews

private struct ChemoStatCard: View {
    let title: String; let value: String; let color: Color
    var body: some View {
        VStack {
            Text(value).font(.title2).bold().foregroundStyle(color)
            Text(title).font(.caption).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity).padding()
        .background(color.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}

private struct ChemoInfoPill: View {
    let label: String; let value: String
    var body: some View {
        VStack(spacing: 2) {
            Text(label).font(.system(size: 10)).foregroundStyle(.secondary)
            Text(value).font(.caption).bold()
        }
    }
}


