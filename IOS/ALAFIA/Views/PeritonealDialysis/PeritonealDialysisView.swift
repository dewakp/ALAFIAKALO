import SwiftUI

// MARK: - ViewModel

@Observable
final class PeritonealDialysisViewModel {
    var sessions: [PDSession] = []
    var isLoading = false
    var errorMessage: String?
    var expandedSessionId: Int?

    // Add-session form state
    var showAddSheet = false
    var sessionDate = Date()
    var modality = "capd"
    var exitSiteStatus = "normal"
    var preWeightKg: String = ""
    var postWeightKg: String = ""
    var preBpSystolic: String = ""
    var preBpDiastolic: String = ""
    var postBpSystolic: String = ""
    var postBpDiastolic: String = ""
    var notes: String = ""

    // APD fields
    var machineType: String = ""
    var totalVolumeMl: String = ""
    var fillVolumeMl: String = ""
    var cycles: String = ""
    var therapyTimeMinutes: String = ""

    // Exchanges
    var formExchanges: [FormExchange] = []
    var isSaving = false

    struct FormExchange: Identifiable {
        let id = UUID()
        var solutionType: String = "1.5% Dextrose"
        var inflowVolumeMl: String = ""
        var outflowVolumeMl: String = ""
        var effluentClarity: String = "clear"
    }

    func load() async {
        isLoading = true; errorMessage = nil
        do {
            sessions = try await APIClient.shared.get("/pd/sessions")
        } catch { errorMessage = error.localizedDescription }
        isLoading = false
    }

    func deleteSession(id: Int) async {
        do {
            try await APIClient.shared.delete("/pd/sessions/\(id)")
            sessions.removeAll { $0.id == id }
        } catch { errorMessage = error.localizedDescription }
    }

    func resetForm() {
        sessionDate = Date()
        modality = "capd"
        exitSiteStatus = "normal"
        preWeightKg = ""
        postWeightKg = ""
        preBpSystolic = ""
        preBpDiastolic = ""
        postBpSystolic = ""
        postBpDiastolic = ""
        notes = ""
        machineType = ""
        totalVolumeMl = ""
        fillVolumeMl = ""
        cycles = ""
        therapyTimeMinutes = ""
        formExchanges = []
        isSaving = false
    }

    func submit() async {
        isSaving = true
        let dateStr = Self.dateFormatter.string(from: sessionDate)
        let exchanges: [PDExchange] = formExchanges.enumerated().map { idx, ex in
            PDExchange(
                id: nil,
                exchangeNumber: idx + 1,
                startTime: nil,
                drainStartTime: nil,
                drainEndTime: nil,
                fillEndTime: nil,
                solutionType: ex.solutionType,
                inflowVolumeMl: Int(ex.inflowVolumeMl),
                outflowVolumeMl: Int(ex.outflowVolumeMl),
                ufMl: nil,
                dwellTimeMinutes: nil,
                effluentClarity: ex.effluentClarity,
                effluentColor: nil
            )
        }
        let body = PDSessionCreate(
            conditionId: nil,
            sessionDate: dateStr,
            modality: modality,
            preWeightKg: Double(preWeightKg),
            postWeightKg: Double(postWeightKg),
            preBpSystolic: Int(preBpSystolic),
            preBpDiastolic: Int(preBpDiastolic),
            postBpSystolic: Int(postBpSystolic),
            postBpDiastolic: Int(postBpDiastolic),
            temperatureC: nil,
            exitSiteStatus: exitSiteStatus,
            machineType: modality != "capd" ? machineType : nil,
            totalVolumeMl: Int(totalVolumeMl),
            fillVolumeMl: Int(fillVolumeMl),
            cycles: Int(cycles),
            therapyTimeMinutes: Int(therapyTimeMinutes),
            lastFillMl: nil,
            complications: nil,
            notes: notes.isEmpty ? nil : notes,
            exchanges: exchanges.isEmpty ? nil : exchanges
        )
        do {
            let created: PDSession = try await APIClient.shared.post("/pd/sessions", body: body)
            sessions.insert(created, at: 0)
            showAddSheet = false
            resetForm()
        } catch { errorMessage = error.localizedDescription }
        isSaving = false
    }

    static let dateFormatter: DateFormatter = {
        let df = DateFormatter()
        df.dateFormat = "yyyy-MM-dd"
        df.locale = Locale(identifier: "en_US_POSIX")
        return df
    }()
}

// MARK: - Main View

struct PeritonealDialysisView: View {
    @State private var vm = PeritonealDialysisViewModel()

    var body: some View {
            Group {
                if vm.isLoading {
                    ProgressView("Loading sessions…")
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if let error = vm.errorMessage {
                    ContentUnavailableView("Error", systemImage: "exclamationmark.triangle", description: Text(error))
                } else if vm.sessions.isEmpty {
                    EmptyStateView(icon: "drop.circle", title: "No PD Sessions", message: "Tap + to record your first peritoneal dialysis session.")
                } else {
                    sessionsList
                }
            }
            .navigationTitle("PD Sessions")
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button { vm.showAddSheet = true } label: {
                        Image(systemName: "plus")
                    }
                }
            }
            .sheet(isPresented: $vm.showAddSheet) {
                AddPDSessionSheet(vm: vm)
            }
            .task { await vm.load() }
            .refreshable { await vm.load() }
    }

    private var sessionsList: some View {
        List {
            ForEach(vm.sessions) { session in
                PDSessionRow(session: session, isExpanded: vm.expandedSessionId == session.id)
                    .contentShape(Rectangle())
                    .onTapGesture {
                        withAnimation {
                            vm.expandedSessionId = vm.expandedSessionId == session.id ? nil : session.id
                        }
                    }
                    .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                        Button(role: .destructive) {
                            Task { await vm.deleteSession(id: session.id) }
                        } label: {
                            Label("Delete", systemImage: "trash")
                        }
                    }
            }
        }
        .listStyle(.insetGrouped)
    }
}

// MARK: - Session Row

private struct PDSessionRow: View {
    let session: PDSession
    let isExpanded: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(session.sessionDate)
                        .font(.headline)
                    if let uf = session.totalUfMl {
                        Text("Total UF: \(uf) mL")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                }
                Spacer()
                modalityBadge(session.modality)
                Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                    .foregroundStyle(.secondary)
                    .font(.caption)
            }

            if isExpanded {
                expandedDetails
            }
        }
        .padding(.vertical, 4)
    }

    @ViewBuilder
    private var expandedDetails: some View {
        VStack(alignment: .leading, spacing: 10) {
            Divider()

            if let preW = session.preWeightKg, let postW = session.postWeightKg {
                LabeledContent("Weight", value: String(format: "%.1f → %.1f kg", preW, postW))
            }
            if let sys = session.preBpSystolic, let dia = session.preBpDiastolic {
                LabeledContent("Pre-BP", value: "\(sys)/\(dia)")
            }
            if let sys = session.postBpSystolic, let dia = session.postBpDiastolic {
                LabeledContent("Post-BP", value: "\(sys)/\(dia)")
            }
            if let status = session.exitSiteStatus {
                LabeledContent("Exit Site", value: status.capitalized)
            }

            if let exchanges = session.exchanges, !exchanges.isEmpty {
                Text("Exchanges")
                    .font(.subheadline.bold())
                    .padding(.top, 4)
                ForEach(exchanges) { ex in
                    HStack {
                        Text("#\(ex.exchangeNumber)")
                            .font(.caption.bold())
                            .frame(width: 30, alignment: .leading)
                        Text(ex.solutionType ?? "—")
                            .font(.caption)
                        Spacer()
                        if let inf = ex.inflowVolumeMl {
                            Text("In: \(inf)")
                                .font(.caption2)
                        }
                        if let out = ex.outflowVolumeMl {
                            Text("Out: \(out)")
                                .font(.caption2)
                        }
                        clarityBadge(ex.effluentClarity)
                    }
                }
            }

            if let notes = session.notes, !notes.isEmpty {
                LabeledContent("Notes", value: notes)
                    .font(.caption)
            }
        }
    }

    private func modalityBadge(_ modality: String) -> some View {
        Text(modality.uppercased())
            .font(.caption.bold())
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(modalityColor(modality).opacity(0.15))
            .foregroundStyle(modalityColor(modality))
            .clipShape(Capsule())
    }

    private func modalityColor(_ modality: String) -> Color {
        switch modality.lowercased() {
        case "capd": return .blue
        case "apd": return .purple
        case "ccpd": return .indigo
        default: return .gray
        }
    }

    private func clarityBadge(_ clarity: String?) -> some View {
        Text(clarity?.capitalized ?? "—")
            .font(.caption2)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(Color.secondary.opacity(0.1))
            .clipShape(Capsule())
    }
}

// MARK: - Add Session Sheet

private struct AddPDSessionSheet: View {
    @Bindable var vm: PeritonealDialysisViewModel
    @Environment(\.dismiss) private var dismiss

    private let modalities = ["capd", "apd", "ccpd"]
    private let exitStatuses = ["normal", "redness", "drainage", "swelling", "other"]
    private let solutionTypes = ["1.5% Dextrose", "2.5% Dextrose", "4.25% Dextrose", "Icodextrin", "Other"]
    private let clarityOptions = ["clear", "slightly cloudy", "cloudy", "bloody"]

    var body: some View {
        NavigationStack {
            Form {
                sessionInfoSection
                weightBPSection
                exchangesSection

                if vm.modality != "capd" {
                    apdSettingsSection
                }

                notesSection
            }
            .navigationTitle("Add PD Session")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss(); vm.resetForm() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { Task { await vm.submit() } }
                        .disabled(vm.isSaving)
                }
            }
        }
    }

    private var sessionInfoSection: some View {
        Section("Session Info") {
            DatePicker("Date", selection: $vm.sessionDate, displayedComponents: .date)
            Picker("Modality", selection: $vm.modality) {
                ForEach(modalities, id: \.self) { Text($0.uppercased()).tag($0) }
            }
            Picker("Exit Site", selection: $vm.exitSiteStatus) {
                ForEach(exitStatuses, id: \.self) { Text($0.capitalized).tag($0) }
            }
        }
    }

    private var weightBPSection: some View {
        Section("Weight & Blood Pressure") {
            HStack {
                TextField("Pre Weight (kg)", text: $vm.preWeightKg)
                    .keyboardType(.decimalPad)
                TextField("Post Weight (kg)", text: $vm.postWeightKg)
                    .keyboardType(.decimalPad)
            }
            HStack {
                TextField("Pre Sys", text: $vm.preBpSystolic)
                    .keyboardType(.numberPad)
                TextField("Pre Dia", text: $vm.preBpDiastolic)
                    .keyboardType(.numberPad)
            }
            HStack {
                TextField("Post Sys", text: $vm.postBpSystolic)
                    .keyboardType(.numberPad)
                TextField("Post Dia", text: $vm.postBpDiastolic)
                    .keyboardType(.numberPad)
            }
        }
    }

    private var exchangesSection: some View {
        Section {
            ForEach($vm.formExchanges) { $exchange in
                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        Text("Exchange \(exchangeIndex(exchange) + 1)")
                            .font(.subheadline.bold())
                        Spacer()
                        Button(role: .destructive) {
                            vm.formExchanges.removeAll { $0.id == exchange.id }
                        } label: {
                            Image(systemName: "minus.circle.fill")
                                .foregroundStyle(.red)
                        }
                        .buttonStyle(.plain)
                    }
                    Picker("Solution", selection: $exchange.solutionType) {
                        ForEach(solutionTypes, id: \.self) { Text($0).tag($0) }
                    }
                    HStack {
                        TextField("Inflow (mL)", text: $exchange.inflowVolumeMl)
                            .keyboardType(.numberPad)
                        TextField("Outflow (mL)", text: $exchange.outflowVolumeMl)
                            .keyboardType(.numberPad)
                    }
                    Picker("Effluent Clarity", selection: $exchange.effluentClarity) {
                        ForEach(clarityOptions, id: \.self) { Text($0.capitalized).tag($0) }
                    }
                }
                .padding(.vertical, 4)
            }

            Button {
                vm.formExchanges.append(.init())
            } label: {
                Label("Add Exchange", systemImage: "plus.circle")
            }
        } header: {
            Text("Exchanges")
        }
    }

    private var apdSettingsSection: some View {
        Section("APD Settings") {
            TextField("Machine Type", text: $vm.machineType)
            TextField("Total Volume (mL)", text: $vm.totalVolumeMl)
                .keyboardType(.numberPad)
            TextField("Fill Volume (mL)", text: $vm.fillVolumeMl)
                .keyboardType(.numberPad)
            TextField("Cycles", text: $vm.cycles)
                .keyboardType(.numberPad)
            TextField("Therapy Time (min)", text: $vm.therapyTimeMinutes)
                .keyboardType(.numberPad)
        }
    }

    private var notesSection: some View {
        Section("Notes") {
            TextField("Additional notes…", text: $vm.notes, axis: .vertical)
                .lineLimit(3...6)
        }
    }

    private func exchangeIndex(_ exchange: PeritonealDialysisViewModel.FormExchange) -> Int {
        vm.formExchanges.firstIndex(where: { $0.id == exchange.id }) ?? 0
    }
}
