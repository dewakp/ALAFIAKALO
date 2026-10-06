// Copyright © 2026 Wole Akpose / 6igma Health Inc.
// All rights reserved. ALAFIA — proprietary and confidential.

import SwiftUI

// Hospital stays and surgical procedures.
//
// Lasting effects lead the screen, before any list of admissions, because that
// is the half a patient and a clinician act on: a parathyroidectomy explains a
// calcium requirement no guideline default can express, and it stays true
// decades after the admission is history.
//
// Stays and procedures are drawn as SEPARATE sections on purpose. A procedure
// may have no admission at all — day-case surgery, or anything recorded years
// later — so a screen that only walked stays and their nested procedures would
// silently omit exactly those operations.

struct HospitalHistoryView: View {
    @StateObject private var viewModel = HospitalHistoryViewModel()

    // Both flags are READ by a `.sheet(isPresented:)` below. §3ar: setting an
    // unobserved Bool compiles perfectly and produces a dead button — the
    // Camera button on the food screen did exactly that, and
    // tests/test_ios_presentation_flags.py now fails the build on it.
    @State private var showStayForm = false
    @State private var showProcedureForm = false

    var body: some View {
        List {
            if let error = viewModel.loadError {
                Section {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Your hospital history could not be loaded")
                            .font(.subheadline.weight(.semibold))
                        Text(error).font(.caption).foregroundStyle(.secondary)
                        Button("Try again") { Task { await viewModel.load() } }
                            .font(.caption)
                    }
                }
            }

            if !viewModel.lastingEffects.isEmpty {
                Section("What past surgery still means for you") {
                    ForEach(viewModel.lastingEffects, id: \.self) { effect in
                        Text(effect).font(.callout)
                    }
                    Text("Only effects recorded with the operation are listed. Nothing here is guessed from the name of an operation.")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }

            Section {
                Button("Add a hospital stay") { showStayForm = true }
                Button("Add an operation") { showProcedureForm = true }
            }

            Section("Hospital stays") {
                if viewModel.stays.isEmpty && viewModel.loadError == nil && !viewModel.loading {
                    Text("No hospital stays recorded yet.")
                        .foregroundStyle(.secondary)
                }
                ForEach(viewModel.stays) { stay in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(stayHeadline(stay)).font(.subheadline.weight(.semibold))
                        if let facility = stay.facility {
                            Text(facility).font(.caption)
                        }
                        if let reason = stay.reason {
                            Text(reason).font(.caption).foregroundStyle(.secondary)
                        }
                        if let diagnosis = stay.diagnosis {
                            Text(diagnosis).font(.caption).foregroundStyle(.secondary)
                        }
                        ForEach(stay.procedures) { procedure in
                            Text("• \(procedure.name)\(procedure.performed.map { " · \($0)" } ?? "")")
                                .font(.caption)
                        }
                    }
                }
            }

            Section {
                if viewModel.procedures.isEmpty && viewModel.loadError == nil && !viewModel.loading {
                    Text("No operations recorded yet.").foregroundStyle(.secondary)
                }
                ForEach(viewModel.procedures) { procedure in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(procedure.name).font(.subheadline.weight(.semibold))
                        if let detail = procedureDetail(procedure) {
                            Text(detail).font(.caption).foregroundStyle(.secondary)
                        }
                        if let code = procedure.code {
                            // The code is meaningless without its vocabulary.
                            Text("\(code)\(procedure.codeSystem.map { " (\($0))" } ?? "")")
                                .font(.caption2).foregroundStyle(.secondary)
                        }
                        Text(procedure.admission.map { "During \($0)" } ?? "No hospital stay recorded")
                            .font(.caption2).foregroundStyle(.secondary)
                        if let effect = procedure.ongoingEffects {
                            Text(effect).font(.caption).foregroundStyle(.indigo)
                        }
                    }
                }
            } header: {
                Text("All operations")
            } footer: {
                Text("Every operation on your record, including those with no hospital stay attached.")
            }
        }
        .navigationTitle("Hospital & Surgery")
        .overlay {
            if viewModel.loading && viewModel.stays.isEmpty && viewModel.procedures.isEmpty {
                ProgressView()
            }
        }
        .task { await viewModel.load() }
        .sheet(isPresented: $showStayForm) {
            HospitalStayForm(viewModel: viewModel)
        }
        .sheet(isPresented: $showProcedureForm) {
            SurgicalProcedureForm(viewModel: viewModel)
        }
    }

    private func stayHeadline(_ stay: HospitalizationView) -> String {
        var parts = [stay.admitted]
        if let discharged = stay.discharged { parts.append("→ \(discharged)") }
        // `nights` is absent while the patient is still an inpatient — never a
        // length measured against today.
        if let nights = stay.nights { parts.append("· \(nights) nights") }
        return parts.joined(separator: " ")
    }

    private func procedureDetail(_ procedure: ProcedureView) -> String? {
        let parts = [procedure.performed, procedure.bodySite, procedure.outcome].compactMap { $0 }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }
}

// MARK: - Forms

private struct HospitalStayForm: View {
    @ObservedObject var viewModel: HospitalHistoryViewModel
    @Environment(\.dismiss) private var dismiss

    @State private var admitted = Date()
    @State private var hasDischarge = false
    @State private var discharged = Date()
    @State private var facility = ""
    @State private var reason = ""
    @State private var admissionType = ""
    @State private var status = ""

    var body: some View {
        NavigationStack {
            Form {
                DatePicker("Admitted", selection: $admitted)
                Toggle("Discharged", isOn: $hasDischarge)
                if hasDischarge {
                    DatePicker("Discharge date", selection: $discharged)
                }
                TextField("Hospital", text: $facility)
                TextField("Reason for admission", text: $reason)
                Picker("Type of admission", selection: $admissionType) {
                    Text("Not stated").tag("")
                    ForEach(HospitalVocabulary.admissionTypes, id: \.self) { value in
                        Text(HospitalLabels.text(for: value)).tag(value)
                    }
                }
                Picker("Status", selection: $status) {
                    Text("Not stated").tag("")
                    ForEach(HospitalVocabulary.statuses, id: \.self) { value in
                        Text(HospitalLabels.text(for: value)).tag(value)
                    }
                }
                if let error = viewModel.saveError {
                    Text(error).font(.caption).foregroundStyle(.red)
                }
            }
            .navigationTitle("Add a hospital stay")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        Task {
                            let saved = await viewModel.createStay(
                                admitted: admitted,
                                discharged: hasDischarge ? discharged : nil,
                                facility: facility, reason: reason,
                                admissionType: admissionType, status: status)
                            if saved { dismiss() }
                        }
                    }
                }
            }
        }
    }
}

private struct SurgicalProcedureForm: View {
    @ObservedObject var viewModel: HospitalHistoryViewModel
    @Environment(\.dismiss) private var dismiss

    @State private var name = ""
    @State private var hasDate = true
    @State private var performed = Date()
    @State private var code = ""
    @State private var codeSystem = ""
    @State private var bodySite = ""
    @State private var outcome = ""
    @State private var ongoingEffects = ""
    @State private var stayId: Int?

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Operation", text: $name)
                    Toggle("I know the date", isOn: $hasDate)
                    if hasDate { DatePicker("Date of operation", selection: $performed) }
                } footer: {
                    Text("An operation does not need a hospital stay. Day-case surgery, and anything you are recording years later, can be added on its own.")
                }

                Section {
                    Picker("During which stay?", selection: $stayId) {
                        Text("No hospital stay").tag(Int?.none)
                        ForEach(viewModel.stayRows) { row in
                            Text(row.facilityName.map { "\(String(row.admittedAt.prefix(10))) — \($0)" }
                                 ?? String(row.admittedAt.prefix(10)))
                                .tag(Int?.some(row.id))
                        }
                    }
                }

                Section {
                    TextField("Procedure code", text: $code)
                    TextField("Coding system", text: $codeSystem)
                    TextField("Part of the body", text: $bodySite)
                    Picker("Outcome", selection: $outcome) {
                        Text("Not stated").tag("")
                        ForEach(HospitalVocabulary.outcomes, id: \.self) { value in
                            Text(HospitalLabels.text(for: value)).tag(value)
                        }
                    }
                } footer: {
                    Text("A code needs the system that issued it — ICD-10-PCS, CPT and SNOMED are different systems.")
                }

                Section {
                    TextField("What this still means for you", text: $ongoingEffects, axis: .vertical)
                } footer: {
                    Text("For example, an organ or gland removed, or something you have had to take ever since.")
                }

                if let error = viewModel.saveError {
                    Text(error).font(.caption).foregroundStyle(.red)
                }
            }
            .navigationTitle("Add an operation")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        Task {
                            let saved = await viewModel.createProcedure(
                                name: name,
                                performed: hasDate ? performed : nil,
                                code: code, codeSystem: codeSystem,
                                bodySite: bodySite, outcome: outcome,
                                ongoingEffects: ongoingEffects, stayId: stayId)
                            if saved { dismiss() }
                        }
                    }
                }
            }
        }
    }
}

/// Patient-facing wording for an API value. The VALUE is what travels; this
/// only decides what is drawn (§3aw).
enum HospitalLabels {
    static func text(for value: String) -> String {
        switch value {
        case "emergency": return "Emergency"
        case "elective", "planned": return "Planned"
        case "urgent": return "Urgent"
        case "observation": return "Observation"
        case "day_case": return "Day case"
        case "maternity": return "Maternity"
        case "rehabilitation": return "Rehabilitation"
        case "in_progress": return "Still in hospital"
        case "discharged": return "Discharged"
        case "transferred": return "Transferred"
        case "cancelled": return "Cancelled"
        case "successful": return "Successful"
        case "partially_successful": return "Partly successful"
        case "unsuccessful": return "Unsuccessful"
        case "complicated": return "Complicated"
        case "abandoned": return "Abandoned"
        case "unknown": return "Not known"
        default: return "Other"
        }
    }
}

// MARK: - View model

@MainActor
final class HospitalHistoryViewModel: ObservableObject {
    @Published var stays: [HospitalizationView] = []
    @Published var procedures: [ProcedureView] = []
    @Published var lastingEffects: [String] = []
    @Published var stayRows: [HospitalizationRow] = []
    @Published var loading = false
    /// Kept apart from the data: a failed fetch must never render as "no
    /// hospital history recorded" (§3aa — an error is not an empty state).
    @Published var loadError: String?
    @Published var saveError: String?

    private static let wire: DateFormatter = {
        let formatter = DateFormatter()
        // The API columns are naive; sending an offset would be a different
        // instant than the one the patient typed.
        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        return formatter
    }()

    func load() async {
        loading = true
        do {
            let history: HospitalHistoryResponse =
                try await APIClient.shared.get("/hospital/history")
            let rows: [HospitalizationRow] =
                try await APIClient.shared.get("/hospital/stays")
            stays = history.stays
            procedures = history.procedures
            lastingEffects = history.lastingEffects
            stayRows = rows
            loadError = nil
        } catch {
            loadError = error.localizedDescription
        }
        loading = false
    }

    func createStay(admitted: Date, discharged: Date?, facility: String,
                    reason: String, admissionType: String, status: String) async -> Bool {
        saveError = nil
        var body: [String: String] = ["admitted_at": Self.wire.string(from: admitted)]
        if let discharged { body["discharged_at"] = Self.wire.string(from: discharged) }
        // Blanks are dropped, never sent: the enums reject "" and the server
        // would answer 422 for a field the patient simply left alone.
        if !facility.isEmpty { body["facility_name"] = facility }
        if !reason.isEmpty { body["reason"] = reason }
        if !admissionType.isEmpty { body["admission_type"] = admissionType }
        if !status.isEmpty { body["status"] = status }
        do {
            let _: HospitalizationRow =
                try await APIClient.shared.post("/hospital/stays", body: body)
            await load()
            return true
        } catch {
            saveError = error.localizedDescription
            return false
        }
    }

    func createProcedure(name: String, performed: Date?, code: String,
                         codeSystem: String, bodySite: String, outcome: String,
                         ongoingEffects: String, stayId: Int?) async -> Bool {
        saveError = nil
        guard !name.trimmingCharacters(in: .whitespaces).isEmpty else {
            saveError = "An operation needs a name."
            return false
        }
        var payload = SurgicalProcedureCreate(name: name)
        if let performed { payload.performedAt = Self.wire.string(from: performed) }
        if !code.isEmpty { payload.code = code }
        if !codeSystem.isEmpty { payload.codeSystem = codeSystem }
        if !bodySite.isEmpty { payload.bodySite = bodySite }
        if !outcome.isEmpty { payload.outcome = outcome }
        if !ongoingEffects.isEmpty { payload.ongoingEffects = ongoingEffects }
        payload.hospitalizationId = stayId
        do {
            let _: SurgicalProcedureRow =
                try await APIClient.shared.post("/hospital/procedures", body: payload)
            await load()
            return true
        } catch {
            saveError = error.localizedDescription
            return false
        }
    }

    func deleteStay(_ id: Int) async {
        saveError = nil
        do {
            try await APIClient.shared.delete("/hospital/stays/\(id)")
            await load()
        } catch {
            saveError = error.localizedDescription
        }
    }
}
