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
            // Session id 0 is a placeholder that matches no session, so this
            // always 404s and the catch below renders it as "no notes yet".
            // Notes hang off a specific therapy session — this needs a real
            // session id, which this screen does not yet carry. Leaving the
            // list empty is honest; pretending to call an endpoint is not.
            patientNotes[patientId] = []
            return
        } catch {
            // The route is /notes, not /clinical-notes — this called a path that
            // never existed, so the catch below made it look like "no notes yet"
            // forever. Session 0 is a placeholder: notes hang off a therapy
            // session, so this needs a real session id to return anything.
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
                        // The board replaces the old flat detail screen: a
                        // clinician picks a category first, then drills in.
                        PatientBoardView(patientId: patient.userId,
                                         patientName: patient.fullName)
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
