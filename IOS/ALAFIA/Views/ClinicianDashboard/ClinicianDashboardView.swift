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
                    EmptyStateView(icon: "list.clipboard", title: "No Patients", message: "No patients are currently sharing data with you.")
                } else {
                    patientList
                }
            }
            .navigationTitle("Clinician Dashboard")
            .task { await vm.load() }
            .refreshable { await vm.load() }
    }

    // MARK: - Patient List

    private var patientList: some View {
        List {
            ForEach(vm.patients) { patient in
                Section {
                    Button {
                        vm.toggleExpand(patientId: patient.userId)
                    } label: {
                        patientRow(patient)
                    }
                    .buttonStyle(.plain)

                    if vm.expandedPatientId == patient.userId {
                        if vm.loadingDetails.contains(patient.userId) {
                            HStack {
                                Spacer()
                                ProgressView()
                                Spacer()
                            }
                            .padding(.vertical, 8)
                        } else if let detail = vm.patientDetails[patient.userId] {
                            patientDetailSection(detail)
                        }
                    }
                }
            }
        }
        .listStyle(.insetGrouped)
    }

    private func patientRow(_ patient: PatientSummary) -> some View {
        HStack(spacing: 12) {
            // Avatar initial
            let initial = String(patient.fullName.prefix(1)).uppercased()
            Text(initial)
                .font(.headline)
                .foregroundStyle(.white)
                .frame(width: 40, height: 40)
                .background(Color.blue.gradient)
                .clipShape(Circle())

            VStack(alignment: .leading, spacing: 4) {
                Text(patient.fullName)
                    .font(.subheadline)
                    .fontWeight(.semibold)

                if let types = patient.permissions, !types.isEmpty {
                    HStack(spacing: 4) {
                        ForEach(types.prefix(4), id: \.self) { type in
                            Text(type)
                                .font(.caption2)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(Color.blue.opacity(0.12))
                                .foregroundStyle(.blue)
                                .cornerRadius(4)
                        }
                        if types.count > 4 {
                            Text("+\(types.count - 4)")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }

            Spacer()

            Image(systemName: vm.expandedPatientId == patient.userId ? "chevron.up" : "chevron.down")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
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
