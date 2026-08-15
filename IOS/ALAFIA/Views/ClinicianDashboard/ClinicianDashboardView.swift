import SwiftUI

// MARK: - ViewModel

@Observable
final class ClinicianDashboardViewModel {
    var patients: [PatientSummary] = []
    var isLoading = false
    var errorMessage: String?
    var isForbidden = false

    var expandedPatientId: Int?
    var patientDetails: [Int: PatientSummary] = [:]
    var loadingDetails: Set<Int> = []
    
    // Clinical notes per patient
    var patientNotes: [Int: [ClinicalNote]] = [:]
    var loadingNotes: Set<Int> = []
    var newNoteText: String = ""
    var savingNote = false

    func load() async {
        isLoading = true; errorMessage = nil; isForbidden = false
        do {
            let response: ClinicianDashboardResponse = try await APIClient.shared.get("/clinician-dashboard/")
            patients = response.patients
        } catch let error as APIError {
            if case .clientError(let msg) = error, msg.lowercased().contains("not a clinician") || msg.lowercased().contains("403") {
                isForbidden = true
            } else {
                errorMessage = error.localizedDescription
            }
        } catch {
            let desc = error.localizedDescription
            if desc.contains("403") {
                isForbidden = true
            } else {
                errorMessage = desc
            }
        }
        isLoading = false
    }

    func loadPatientDetail(id: Int) async {
        guard patientDetails[id] == nil else { return }
        loadingDetails.insert(id)
        do {
            let detail: PatientSummary = try await APIClient.shared.get("/clinician-dashboard/patient/\(id)")
            patientDetails[id] = detail
        } catch {
            errorMessage = error.localizedDescription
        }
        loadingDetails.remove(id)
        // Also load clinical notes for this patient
        await loadNotes(patientId: id)
    }
    
    func loadNotes(patientId: Int) async {
        loadingNotes.insert(patientId)
        do {
            let notes: [ClinicalNote] = try await APIClient.shared.get("/chronic/therapy-sessions/0/clinical-notes?patient_id=\(patientId)")
            patientNotes[patientId] = notes
        } catch {
            // Notes may not exist yet — that's ok
            patientNotes[patientId] = []
        }
        loadingNotes.remove(patientId)
    }
    
    func addNote(patientId: Int, sessionId: Int = 0) async {
        guard !newNoteText.trimmingCharacters(in: .whitespaces).isEmpty else { return }
        savingNote = true
        do {
            let body = ClinicalNoteCreate(noteType: "clinician", noteText: newNoteText)
            let _: ClinicalNote = try await APIClient.shared.post(
                "/chronic/therapy-sessions/\(sessionId)/clinical-notes",
                body: body
            )
            newNoteText = ""
            await loadNotes(patientId: patientId)
        } catch {
            errorMessage = error.localizedDescription
        }
        savingNote = false
    }

    func toggleExpand(patientId: Int) {
        if expandedPatientId == patientId {
            expandedPatientId = nil
        } else {
            expandedPatientId = patientId
            Task { await loadPatientDetail(id: patientId) }
        }
    }
}

// MARK: - Main View

struct ClinicianDashboardView: View {
    @State private var vm = ClinicianDashboardViewModel()

    var body: some View {
            Group {
                if vm.isLoading {
                    ProgressView("Loading dashboard…")
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if vm.isForbidden {
                    ContentUnavailableView {
                        Label("Access Restricted", systemImage: "lock.shield")
                    } description: {
                        Text("This dashboard is only available to clinician accounts. If you believe this is an error, please contact support.")
                    }
                } else if let error = vm.errorMessage {
                    ContentUnavailableView("Error", systemImage: "exclamationmark.triangle", description: Text(error))
                } else if vm.patients.isEmpty {
                    EmptyStateView(
                        icon: "person.2",
                        title: "No patients yet",
                        message: "Patients appear here as soon as they share their records with you, from Share Records, using your account email."
                    )
                } else {
                    patientGrid
                }
            }
            .navigationTitle("My Patients")
            .task { await vm.load() }
            .refreshable { await vm.load() }
    }

    // MARK: - Patient Grid
    //
    // A grid of cards rather than a list of expanding rows: the first thing a
    // clinician sees is every patient at once, each card carrying enough signal
    // (latest vitals, abnormal-lab count) to decide who to open first.

    private var patientGrid: some View {
        ScrollView {
            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: 160), spacing: 12)],
                spacing: 12
            ) {
                ForEach(vm.patients) { patient in
                    NavigationLink {
                        ClinicianPatientDetailView(vm: vm, patient: patient)
                    } label: {
                        patientCard(patient)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(12)
        }
    }

    private func patientCard(_ patient: PatientSummary) -> some View {
        let abnormal = (patient.latestLabs ?? []).filter { $0.isAbnormal == true }.count

        return VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 10) {
                Text(Self.initials(patient.fullName))
                    .font(.subheadline).fontWeight(.bold)
                    .foregroundStyle(.white)
                    .frame(width: 40, height: 40)
                    .background(Self.tint(for: patient.userId).gradient)
                    .clipShape(Circle())

                VStack(alignment: .leading, spacing: 2) {
                    Text(patient.fullName)
                        .font(.subheadline).fontWeight(.semibold)
                        .lineLimit(1)
                    if let email = patient.email {
                        Text(email).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
                    }
                }
            }

            if let vitals = patient.latestVitals {
                HStack(spacing: 12) {
                    if let bp = vitals.bp { cardMetric("BP", bp) }
                    if let hr = vitals.hr { cardMetric("HR", "\(hr)") }
                }
            }

            HStack(spacing: 10) {
                Text("\((patient.latestLabs ?? []).count) labs")
                Text("\((patient.medications ?? []).count) meds")
                if abnormal > 0 {
                    Label("\(abnormal)", systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(.red)
                }
            }
            .font(.caption2)
            .foregroundStyle(.secondary)

            if let types = patient.permissions, !types.isEmpty {
                HStack(spacing: 4) {
                    ForEach(types.prefix(3), id: \.self) { type in
                        Text(type)
                            .font(.caption2)
                            .padding(.horizontal, 6).padding(.vertical, 2)
                            .background(Color.blue.opacity(0.12))
                            .foregroundStyle(.blue)
                            .cornerRadius(4)
                    }
                    if types.count > 3 {
                        Text("+\(types.count - 3)").font(.caption2).foregroundStyle(.secondary)
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(Color(.secondarySystemGroupedBackground))
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }

    private func cardMetric(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(label).font(.caption2).foregroundStyle(.secondary)
            Text(value).font(.caption).fontWeight(.semibold)
        }
    }

    /// Deterministic tint per patient, so a card keeps its colour between loads.
    static func tint(for id: Int) -> Color {
        [.blue, .purple, .orange, .green, .pink, .indigo][abs(id) % 6]
    }

    static func initials(_ name: String) -> String {
        let parts = name.split(separator: " ").prefix(2)
        let s = parts.compactMap { $0.first }.map(String.init).joined().uppercased()
        return s.isEmpty ? "?" : s
    }

}

// MARK: - Patient Detail
//
// Pushed from a card on the grid. The grid is the clinician's home screen, so
// the detail is a separate destination rather than an inline expansion — a row
// that grows in place pushes every other patient off the screen.

struct ClinicianPatientDetailView: View {
    @Bindable var vm: ClinicianDashboardViewModel
    let patient: PatientSummary

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if vm.loadingDetails.contains(patient.userId) {
                    ProgressView().frame(maxWidth: .infinity)
                } else {
                    patientDetailSection(vm.patientDetails[patient.userId] ?? patient)
                }
            }
            .padding(16)
        }
        .navigationTitle(patient.fullName)
        .navigationBarTitleDisplayMode(.inline)
        .task { await vm.loadPatientDetail(id: patient.userId) }
    }

    // MARK: - Patient Detail

    @ViewBuilder
    private func patientDetailSection(_ detail: PatientSummary) -> some View {
        // Recent Labs
        if let labs = detail.latestLabs, !labs.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                Label("Recent Labs", systemImage: "flask.fill")
                    .font(.caption).fontWeight(.semibold).foregroundStyle(.purple)
                ForEach(labs) { lab in
                    HStack {
                        Text(lab.name ?? "–")
                            .font(.caption)
                        Spacer()
                        Text("\(lab.value ?? "–") \(lab.unit ?? "")")
                            .font(.caption).fontWeight(.medium)
                        if let date = lab.date {
                            Text(date).font(.caption2).foregroundStyle(.secondary)
                        }
                    }
                }
            }
            .padding(.vertical, 4)
        }

        // Vitals
        if let vitals = detail.latestVitals {
            VStack(alignment: .leading, spacing: 6) {
                Label("Vitals", systemImage: "heart.fill")
                    .font(.caption).fontWeight(.semibold).foregroundStyle(.red)
                HStack(spacing: 16) {
                    if let bp = vitals.bp { vitalBadge("BP", value: bp) }
                    if let hr = vitals.hr { vitalBadge("HR", value: "\(hr) bpm") }
                    if let wt = vitals.weightKg { vitalBadge("Wt", value: String(format: "%.1f kg", wt)) }
                }
                if let date = vitals.date {
                    Text("Updated: \(date)").font(.caption2).foregroundStyle(.secondary)
                }
            }
            .padding(.vertical, 4)
        }

        // Mood
        if let mood = detail.latestMood {
            VStack(alignment: .leading, spacing: 6) {
                Label("Mood", systemImage: "face.smiling")
                    .font(.caption).fontWeight(.semibold).foregroundStyle(.green)
                HStack(spacing: 16) {
                    if let score = mood.score { scoreBadge("Score", value: Double(score)) }
                }
                if let date = mood.date {
                    Text("Recorded: \(date)").font(.caption2).foregroundStyle(.secondary)
                }
            }
            .padding(.vertical, 4)
        }

        // Medications
        if let meds = detail.medications, !meds.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                Label("Medications", systemImage: "pills.fill")
                    .font(.caption).fontWeight(.semibold).foregroundStyle(.orange)
                ForEach(meds, id: \.self) { med in
                    Text(med).font(.caption)
                }
            }
            .padding(.vertical, 4)
        }
        
        // Clinical Notes
        clinicalNotesSection(patientId: detail.userId)
    }

    private func vitalBadge(_ label: String, value: String) -> some View {
        VStack(spacing: 2) {
            Text(value).font(.caption).fontWeight(.medium)
            Text(label).font(.caption2).foregroundStyle(.secondary)
        }
    }

    private func scoreBadge(_ label: String, value: Double) -> some View {
        VStack(spacing: 2) {
            Text(String(format: "%.0f", value)).font(.caption).fontWeight(.semibold)
            Text(label).font(.caption2).foregroundStyle(.secondary)
        }
    }
    
    // MARK: - Clinical Notes Section
    
    @ViewBuilder
    private func clinicalNotesSection(patientId: Int) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Clinical Notes", systemImage: "note.text")
                .font(.caption).fontWeight(.semibold).foregroundStyle(.indigo)
            
            if vm.loadingNotes.contains(patientId) {
                ProgressView().frame(maxWidth: .infinity)
            } else if let notes = vm.patientNotes[patientId], !notes.isEmpty {
                ForEach(notes) { note in
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text(note.noteType.capitalized)
                                .font(.caption2)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(Color.indigo.opacity(0.12))
                                .foregroundStyle(.indigo)
                                .cornerRadius(4)
                            Spacer()
                            Text(note.createdAt).font(.caption2).foregroundStyle(.secondary)
                        }
                        Text(note.noteText)
                            .font(.caption)
                    }
                    .padding(8)
                    .background(Color(.tertiarySystemGroupedBackground))
                    .cornerRadius(8)
                }
            } else {
                Text("No clinical notes yet.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            
            // Add note row
            HStack {
                TextField("Add a note…", text: $vm.newNoteText, axis: .vertical)
                    .font(.caption)
                    .lineLimit(1...3)
                    .textFieldStyle(.roundedBorder)
                
                Button {
                    Task { await vm.addNote(patientId: patientId) }
                } label: {
                    if vm.savingNote {
                        ProgressView().controlSize(.small)
                    } else {
                        Image(systemName: "paperplane.fill")
                    }
                }
                .disabled(vm.newNoteText.trimmingCharacters(in: .whitespaces).isEmpty || vm.savingNote)
            }
        }
        .padding(.vertical, 4)
    }
}
