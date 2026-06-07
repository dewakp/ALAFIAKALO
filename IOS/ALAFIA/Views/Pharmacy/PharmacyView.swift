import SwiftUI

// MARK: - ViewModel

@Observable
final class PharmacyViewModel {
    var prescriptions: [Prescription] = []
    var dispenses: [DispenseRecord] = []
    var adherenceLogs: [AdherenceLog] = []
    var adherenceReport: AdherenceReport?
    var schedules: [MedicationSchedule] = []
    var refills: [RefillRequest] = []
    var impactReport: MedicationImpactReport?
    var isLoading = false
    var errorMessage: String?

    // MARK: Prescriptions
    func fetchPrescriptions() async {
        isLoading = true; errorMessage = nil
        do {
            prescriptions = try await APIClient.shared.get("/pharmacy/prescriptions")
            isLoading = false
        } catch { errorMessage = error.localizedDescription; isLoading = false }
    }

    func createPrescription(_ rx: PrescriptionCreate) async -> Bool {
        do {
            let _: Prescription = try await APIClient.shared.post("/pharmacy/prescriptions", body: rx)
            await fetchPrescriptions(); return true
        } catch { errorMessage = error.localizedDescription; return false }
    }

    func deletePrescription(id: Int) async {
        do {
            try await APIClient.shared.delete("/pharmacy/prescriptions/\(id)")
            prescriptions.removeAll { $0.id == id }
        } catch { errorMessage = error.localizedDescription }
    }

    // MARK: Dispenses
    func fetchDispenses() async {
        do { dispenses = try await APIClient.shared.get("/pharmacy/dispenses") } catch { errorMessage = error.localizedDescription }
    }

    func createDispense(_ d: DispenseCreate) async -> Bool {
        do {
            let _: DispenseRecord = try await APIClient.shared.post("/pharmacy/dispenses", body: d)
            await fetchDispenses(); return true
        } catch { errorMessage = error.localizedDescription; return false }
    }

    // MARK: Adherence
    func fetchAdherenceLogs() async {
        do { adherenceLogs = try await APIClient.shared.get("/pharmacy/adherence") } catch { errorMessage = error.localizedDescription }
    }

    func logDose(_ log: AdherenceLogCreate) async -> Bool {
        do {
            let _: AdherenceLog = try await APIClient.shared.post("/pharmacy/adherence", body: log)
            await fetchAdherenceLogs(); return true
        } catch { errorMessage = error.localizedDescription; return false }
    }

    func fetchAdherenceReport(rxId: Int? = nil) async {
        do {
            let path = rxId != nil ? "/pharmacy/adherence/report?prescription_id=\(rxId!)" : "/pharmacy/adherence/report"
            adherenceReport = try await APIClient.shared.get(path)
        } catch { errorMessage = error.localizedDescription }
    }

    // MARK: Schedules
    func fetchSchedules() async {
        do { schedules = try await APIClient.shared.get("/pharmacy/schedules") } catch { errorMessage = error.localizedDescription }
    }

    func createSchedule(_ s: ScheduleCreate) async -> Bool {
        do {
            let _: MedicationSchedule = try await APIClient.shared.post("/pharmacy/schedules", body: s)
            await fetchSchedules(); return true
        } catch { errorMessage = error.localizedDescription; return false }
    }

    func deleteSchedule(id: Int) async {
        do {
            try await APIClient.shared.delete("/pharmacy/schedules/\(id)")
            schedules.removeAll { $0.id == id }
        } catch { errorMessage = error.localizedDescription }
    }

    // MARK: Refills
    func fetchRefills() async {
        do { refills = try await APIClient.shared.get("/pharmacy/refills") } catch { errorMessage = error.localizedDescription }
    }

    func createRefill(_ r: RefillCreate) async -> Bool {
        do {
            let _: RefillRequest = try await APIClient.shared.post("/pharmacy/refills", body: r)
            await fetchRefills(); return true
        } catch { errorMessage = error.localizedDescription; return false }
    }

    // MARK: Impact
    func fetchImpact(rxId: Int) async {
        do { impactReport = try await APIClient.shared.get("/pharmacy/impact/\(rxId)") } catch { errorMessage = error.localizedDescription }
    }
}

// MARK: - Main View

struct PharmacyView: View {
    @State private var vm = PharmacyViewModel()
    @State private var selectedTab = 0

    var body: some View {
        VStack(spacing: 0) {
            Picker("Section", selection: $selectedTab) {
                Text("Rx").tag(0)
                Text("Dispense").tag(1)
                Text("Adherence").tag(2)
                Text("Schedules").tag(3)
                Text("Refills").tag(4)
                Text("Impact").tag(5)
            }
            .pickerStyle(.segmented)
            .padding(.horizontal)
            .padding(.top, 8)

            switch selectedTab {
            case 0: PrescriptionsTab(vm: vm)
            case 1: DispensesTab(vm: vm)
            case 2: AdherenceTab(vm: vm)
            case 3: SchedulesTab(vm: vm)
            case 4: RefillsTab(vm: vm)
            case 5: ImpactTab(vm: vm)
            default: EmptyView()
            }
        }
        .navigationTitle("Pharmacy")
        .alert("Error", isPresented: .constant(vm.errorMessage != nil)) {
            Button("OK") { vm.errorMessage = nil }
        } message: {
            Text(vm.errorMessage ?? "")
        }
    }
}

// MARK: - Prescriptions Tab

struct PrescriptionsTab: View {
    @Bindable var vm: PharmacyViewModel
    @State private var showAdd = false

    var body: some View {
        Group {
            if vm.isLoading {
                ProgressView()
            } else if vm.prescriptions.isEmpty {
                EmptyStateView(icon: "doc.text.fill", title: "No Prescriptions", message: "Tap + to create a prescription")
            } else {
                List {
                    ForEach(vm.prescriptions) { rx in
                        PrescriptionRow(rx: rx)
                    }
                    .onDelete { indices in
                        Task {
                            for i in indices { await vm.deletePrescription(id: vm.prescriptions[i].id) }
                        }
                    }
                }
            }
        }
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { showAdd = true } label: { Image(systemName: "plus") }
            }
        }
        .sheet(isPresented: $showAdd) { AddPrescriptionSheet(vm: vm) }
        .task { await vm.fetchPrescriptions() }
    }
}

struct PrescriptionRow: View {
    let rx: Prescription

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                VStack(alignment: .leading) {
                    Text(rx.medicationName).font(.headline)
                    Text(rx.dosageDisplay).font(.subheadline).foregroundStyle(.secondary)
                }
                Spacer()
                PharmacyStatusBadge(status: rx.status)
            }
            HStack {
                if let freq = rx.frequency {
                    Label(freq, systemImage: "clock").font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Text("Refills: \(rx.refillsRemaining)/\(rx.refillsAuthorized)")
                    .font(.caption2).foregroundStyle(.tertiary)
            }
        }
        .padding(.vertical, 4)
    }
}

struct AddPrescriptionSheet: View {
    @Bindable var vm: PharmacyViewModel
    @Environment(\.dismiss) var dismiss
    @State private var patientId = ""
    @State private var medicationName = ""
    @State private var dosage = ""
    @State private var dosageUnit = "mg"
    @State private var frequency = "once daily"
    @State private var quantity = ""
    @State private var refills = "0"
    @State private var diagnosis = ""
    @State private var instructions = ""
    @State private var substitution = true
    @State private var saving = false

    let units = ["mg", "mcg", "mL", "units", "tablets"]
    let freqs = ["once daily", "twice daily", "three times daily", "as needed", "weekly"]

    var body: some View {
        NavigationStack {
            Form {
                Section("Patient") {
                    LKTextField(title: "Patient ID", text: $patientId)
                }
                Section("Medication") {
                    LKTextField(title: "Medication name", text: $medicationName)
                    HStack {
                        LKNumberField(title: "Dosage", value: $dosage)
                        Picker("Unit", selection: $dosageUnit) {
                            ForEach(units, id: \.self) { Text($0) }
                        }.pickerStyle(.menu)
                    }
                    Picker("Frequency", selection: $frequency) {
                        ForEach(freqs, id: \.self) { Text($0.capitalized) }
                    }
                    LKNumberField(title: "Quantity", value: $quantity)
                    LKNumberField(title: "Refills authorized", value: $refills)
                    Toggle("Allow substitution", isOn: $substitution)
                }
                Section("Clinical") {
                    LKTextField(title: "Diagnosis", text: $diagnosis)
                    TextField("Instructions", text: $instructions, axis: .vertical).lineLimit(3...6)
                }
            }
            .navigationTitle("New Prescription")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Save") { save() }
                        .disabled(medicationName.isEmpty || patientId.isEmpty || saving)
                        .fontWeight(.semibold)
                }
            }
        }
    }

    private func save() {
        guard let pid = Int(patientId) else { return }
        saving = true
        let rx = PrescriptionCreate(
            patientId: pid,
            medicationName: medicationName,
            dosage: dosage.isEmpty ? nil : dosage,
            dosageUnit: dosageUnit,
            frequency: frequency,
            quantity: Int(quantity),
            refillsAuthorized: Int(refills) ?? 0,
            diagnosis: diagnosis.isEmpty ? nil : diagnosis,
            instructions: instructions.isEmpty ? nil : instructions,
            substitutionAllowed: substitution
        )
        Task {
            if await vm.createPrescription(rx) { dismiss() }
            saving = false
        }
    }
}

// MARK: - Dispenses Tab

struct DispensesTab: View {
    @Bindable var vm: PharmacyViewModel
    @State private var showAdd = false

    var body: some View {
        Group {
            if vm.dispenses.isEmpty {
                EmptyStateView(icon: "shippingbox.fill", title: "No Dispenses", message: "Tap + to dispense a prescription")
            } else {
                List {
                    ForEach(vm.dispenses) { d in
                        DispenseRow(d: d)
                    }
                }
            }
        }
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { showAdd = true } label: { Image(systemName: "plus") }
            }
        }
        .sheet(isPresented: $showAdd) { AddDispenseSheet(vm: vm) }
        .task { await vm.fetchDispenses() }
    }
}

struct DispenseRow: View {
    let d: DispenseRecord

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(d.medicationName ?? "Rx #\(d.prescriptionId)").font(.headline)
                Spacer()
                PharmacyStatusBadge(status: d.status)
            }
            HStack {
                if let qty = d.quantityDispensed { Label("\(qty) units", systemImage: "pills").font(.caption) }
                if d.interactionsChecked { Label("DUR ✓", systemImage: "checkmark.shield").font(.caption).foregroundStyle(.green) }
                if d.allergyChecked { Label("Allergy ✓", systemImage: "checkmark.shield").font(.caption).foregroundStyle(.green) }
            }
            if let name = d.pharmacistName {
                Text("By: \(name)").font(.caption2).foregroundStyle(.tertiary)
            }
        }
        .padding(.vertical, 4)
    }
}

struct AddDispenseSheet: View {
    @Bindable var vm: PharmacyViewModel
    @Environment(\.dismiss) var dismiss
    @State private var rxId = ""
    @State private var qty = ""
    @State private var days = ""
    @State private var ndcCode = ""
    @State private var lotNumber = ""
    @State private var manufacturer = ""
    @State private var isGeneric = false
    @State private var interactionsChecked = false
    @State private var allergyChecked = false
    @State private var counselingProvided = false
    @State private var notes = ""
    @State private var saving = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Prescription") {
                    LKTextField(title: "Prescription ID", text: $rxId)
                }
                Section("Dispense Details") {
                    LKNumberField(title: "Quantity", value: $qty)
                    LKNumberField(title: "Days supply", value: $days)
                    LKTextField(title: "NDC code", text: $ndcCode)
                    LKTextField(title: "Lot number", text: $lotNumber)
                    LKTextField(title: "Manufacturer", text: $manufacturer)
                    Toggle("Generic", isOn: $isGeneric)
                }
                Section("Verification") {
                    Toggle("Interactions checked", isOn: $interactionsChecked)
                    Toggle("Allergy checked", isOn: $allergyChecked)
                    Toggle("Counseling provided", isOn: $counselingProvided)
                }
                Section("Notes") {
                    TextField("Clinical notes", text: $notes, axis: .vertical).lineLimit(3...6)
                }
            }
            .navigationTitle("Dispense")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Dispense") { save() }
                        .disabled(rxId.isEmpty || saving)
                        .fontWeight(.semibold)
                }
            }
        }
    }

    private func save() {
        guard let pid = Int(rxId) else { return }
        saving = true
        let d = DispenseCreate(
            prescriptionId: pid,
            quantityDispensed: Int(qty),
            daysSupply: Int(days),
            ndcCode: ndcCode.isEmpty ? nil : ndcCode,
            lotNumber: lotNumber.isEmpty ? nil : lotNumber,
            manufacturer: manufacturer.isEmpty ? nil : manufacturer,
            isGeneric: isGeneric,
            interactionsChecked: interactionsChecked,
            allergyChecked: allergyChecked,
            counselingProvided: counselingProvided,
            clinicalNotes: notes.isEmpty ? nil : notes
        )
        Task {
            if await vm.createDispense(d) { dismiss() }
            saving = false
        }
    }
}

// MARK: - Adherence Tab

struct AdherenceTab: View {
    @Bindable var vm: PharmacyViewModel
    @State private var showLog = false

    var body: some View {
        List {
            if let report = vm.adherenceReport {
                Section("Summary") {
                    SummaryCard(
                        items: [
                            ("Adherence", String(format: "%.0f%%", report.adherenceRate * 100)),
                            ("Taken", "\(report.totalTaken)"),
                            ("Missed", "\(report.totalMissed)"),
                            ("Late", "\(report.totalLate)"),
                            ("Streak", "\(report.streakCurrent)d"),
                        ]
                    )
                    if !report.commonSideEffects.isEmpty {
                        VStack(alignment: .leading) {
                            Text("Side Effects").font(.caption).foregroundStyle(.secondary)
                            Text(report.commonSideEffects.joined(separator: ", ")).font(.caption2)
                        }
                    }
                }
            }

            Section("Logs") {
                if vm.adherenceLogs.isEmpty {
                    Text("No adherence logs yet").foregroundStyle(.secondary)
                } else {
                    ForEach(vm.adherenceLogs) { log in
                        AdherenceLogRow(log: log)
                    }
                }
            }
        }
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { showLog = true } label: { Image(systemName: "plus") }
            }
        }
        .sheet(isPresented: $showLog) { LogDoseSheet(vm: vm) }
        .task {
            await vm.fetchAdherenceLogs()
            await vm.fetchAdherenceReport()
        }
    }
}

struct AdherenceLogRow: View {
    let log: AdherenceLog

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(log.medicationName ?? "Rx #\(log.prescriptionId)").font(.headline)
                Spacer()
                PharmacyStatusBadge(status: log.status)
            }
            if let dose = log.doseTaken { Text("Dose: \(dose)").font(.caption).foregroundStyle(.secondary) }
            if let side = log.sideEffectsReported { Text("Side effects: \(side)").font(.caption2).foregroundStyle(.orange) }
        }
        .padding(.vertical, 2)
    }
}

struct LogDoseSheet: View {
    @Bindable var vm: PharmacyViewModel
    @Environment(\.dismiss) var dismiss
    @State private var rxId = ""
    @State private var status = "taken"
    @State private var dose = ""
    @State private var sideEffects = ""
    @State private var notes = ""
    @State private var moodBefore = ""
    @State private var moodAfter = ""
    @State private var saving = false

    let statuses = ["taken", "missed", "skipped", "late"]

    var body: some View {
        NavigationStack {
            Form {
                Section("Medication") {
                    LKTextField(title: "Prescription ID", text: $rxId)
                    Picker("Status", selection: $status) {
                        ForEach(statuses, id: \.self) { Text($0.capitalized) }
                    }
                    LKTextField(title: "Dose taken", text: $dose)
                }
                Section("Well-being") {
                    LKNumberField(title: "Mood before (1-10)", value: $moodBefore)
                    LKNumberField(title: "Mood after (1-10)", value: $moodAfter)
                    LKTextField(title: "Side effects", text: $sideEffects)
                }
                Section("Notes") {
                    TextField("Notes", text: $notes, axis: .vertical).lineLimit(3...6)
                }
            }
            .navigationTitle("Log Dose")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Save") { save() }
                        .disabled(rxId.isEmpty || saving)
                        .fontWeight(.semibold)
                }
            }
        }
    }

    private func save() {
        guard let pid = Int(rxId) else { return }
        saving = true
        let log = AdherenceLogCreate(
            prescriptionId: pid,
            scheduledTime: ISO8601DateFormatter().string(from: Date()),
            status: status,
            doseTaken: dose.isEmpty ? nil : dose,
            notes: notes.isEmpty ? nil : notes,
            sideEffectsReported: sideEffects.isEmpty ? nil : sideEffects,
            moodBefore: Int(moodBefore),
            moodAfter: Int(moodAfter)
        )
        Task {
            if await vm.logDose(log) { dismiss() }
            saving = false
        }
    }
}

// MARK: - Schedules Tab

struct SchedulesTab: View {
    @Bindable var vm: PharmacyViewModel
    @State private var showAdd = false

    var body: some View {
        Group {
            if vm.schedules.isEmpty {
                EmptyStateView(icon: "alarm.fill", title: "No Schedules", message: "Tap + to create a medication schedule")
            } else {
                List {
                    ForEach(vm.schedules) { s in
                        ScheduleRow(schedule: s)
                    }
                    .onDelete { indices in
                        Task {
                            for i in indices { await vm.deleteSchedule(id: vm.schedules[i].id) }
                        }
                    }
                }
            }
        }
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { showAdd = true } label: { Image(systemName: "plus") }
            }
        }
        .sheet(isPresented: $showAdd) { AddScheduleSheet(vm: vm) }
        .task { await vm.fetchSchedules() }
    }
}

struct ScheduleRow: View {
    let schedule: MedicationSchedule

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(schedule.medicationName ?? "Rx #\(schedule.prescriptionId)").font(.headline)
                Spacer()
                Text(schedule.isActive ? "Active" : "Inactive")
                    .font(.caption2).fontWeight(.medium)
                    .padding(.horizontal, 8).padding(.vertical, 2)
                    .background(schedule.isActive ? Color.green.opacity(0.15) : Color.gray.opacity(0.15))
                    .foregroundStyle(schedule.isActive ? .green : .gray)
                    .clipShape(Capsule())
            }
            HStack {
                Label(schedule.timeOfDay, systemImage: "clock").font(.caption)
                if let days = schedule.daysOfWeek {
                    Label(days, systemImage: "calendar").font(.caption)
                }
                Spacer()
                Label("\(schedule.reminderMinutesBefore)m before", systemImage: "bell").font(.caption2).foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 2)
    }
}

struct AddScheduleSheet: View {
    @Bindable var vm: PharmacyViewModel
    @Environment(\.dismiss) var dismiss
    @State private var rxId = ""
    @State private var timeOfDay = "08:00"
    @State private var daysOfWeek = ""
    @State private var doseLabel = ""
    @State private var reminder = "15"
    @State private var saving = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Medication") {
                    LKTextField(title: "Prescription ID", text: $rxId)
                }
                Section("Schedule") {
                    LKTextField(title: "Time (HH:MM)", text: $timeOfDay)
                    LKTextField(title: "Days (e.g. Mon,Wed,Fri)", text: $daysOfWeek)
                    LKTextField(title: "Dose label", text: $doseLabel)
                    LKNumberField(title: "Reminder (minutes before)", value: $reminder)
                }
            }
            .navigationTitle("New Schedule")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Save") { save() }
                        .disabled(rxId.isEmpty || saving)
                        .fontWeight(.semibold)
                }
            }
        }
    }

    private func save() {
        guard let pid = Int(rxId) else { return }
        saving = true
        let s = ScheduleCreate(
            prescriptionId: pid,
            timeOfDay: timeOfDay,
            daysOfWeek: daysOfWeek.isEmpty ? nil : daysOfWeek,
            doseLabel: doseLabel.isEmpty ? nil : doseLabel,
            reminderMinutesBefore: Int(reminder) ?? 15
        )
        Task {
            if await vm.createSchedule(s) { dismiss() }
            saving = false
        }
    }
}

// MARK: - Refills Tab

struct RefillsTab: View {
    @Bindable var vm: PharmacyViewModel
    @State private var showAdd = false

    var body: some View {
        Group {
            if vm.refills.isEmpty {
                EmptyStateView(icon: "arrow.clockwise.circle.fill", title: "No Refill Requests", message: "Tap + to request a refill")
            } else {
                List {
                    ForEach(vm.refills) { r in
                        RefillRow(refill: r)
                    }
                }
            }
        }
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { showAdd = true } label: { Image(systemName: "plus") }
            }
        }
        .sheet(isPresented: $showAdd) { AddRefillSheet(vm: vm) }
        .task { await vm.fetchRefills() }
    }
}

struct RefillRow: View {
    let refill: RefillRequest

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(refill.medicationName ?? "Rx #\(refill.prescriptionId)").font(.headline)
                Spacer()
                PharmacyStatusBadge(status: refill.status)
            }
            if let qty = refill.quantityRequested {
                Text("Qty requested: \(qty)").font(.caption).foregroundStyle(.secondary)
            }
            if let reason = refill.denialReason {
                Text("Denied: \(reason)").font(.caption2).foregroundStyle(.red)
            }
        }
        .padding(.vertical, 2)
    }
}

struct AddRefillSheet: View {
    @Bindable var vm: PharmacyViewModel
    @Environment(\.dismiss) var dismiss
    @State private var rxId = ""
    @State private var qty = ""
    @State private var notes = ""
    @State private var saving = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Refill") {
                    LKTextField(title: "Prescription ID", text: $rxId)
                    LKNumberField(title: "Quantity requested", value: $qty)
                }
                Section("Notes") {
                    TextField("Notes", text: $notes, axis: .vertical).lineLimit(3...6)
                }
            }
            .navigationTitle("Request Refill")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Submit") { save() }
                        .disabled(rxId.isEmpty || saving)
                        .fontWeight(.semibold)
                }
            }
        }
    }

    private func save() {
        guard let pid = Int(rxId) else { return }
        saving = true
        let r = RefillCreate(prescriptionId: pid, quantityRequested: Int(qty), notes: notes.isEmpty ? nil : notes)
        Task {
            if await vm.createRefill(r) { dismiss() }
            saving = false
        }
    }
}

// MARK: - Impact Tab

struct ImpactTab: View {
    @Bindable var vm: PharmacyViewModel
    @State private var rxIdText = ""

    var body: some View {
        List {
            Section("Lookup") {
                HStack {
                    TextField("Prescription ID", text: $rxIdText)
                        .keyboardType(.numberPad)
                    Button("Analyze") {
                        guard let id = Int(rxIdText) else { return }
                        Task { await vm.fetchImpact(rxId: id) }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(rxIdText.isEmpty)
                }
            }

            if let report = vm.impactReport {
                Section("Adherence") {
                    SummaryCard(items: [
                        ("Adherence", String(format: "%.0f%%", report.adherenceRate * 100)),
                        ("Taken", "\(report.dosesTaken)"),
                        ("Missed", "\(report.dosesMissed)"),
                        ("Period", "\(report.analysisPeriodDays)d"),
                    ])
                }

                Section("Mood Impact") {
                    HStack {
                        if let before = report.avgMoodBefore {
                            VStack { Text("Before").font(.caption); Text(String(format: "%.1f", before)).font(.title3) }
                            Spacer()
                        }
                        if let after = report.avgMoodAfter {
                            VStack { Text("After").font(.caption); Text(String(format: "%.1f", after)).font(.title3) }
                            Spacer()
                        }
                        if let trend = report.moodTrend {
                            VStack { Text("Trend").font(.caption); Text(trend).font(.title3) }
                        }
                    }
                }

                if !report.reportedSideEffects.isEmpty {
                    Section("Side Effects") {
                        Text(report.reportedSideEffects.joined(separator: ", "))
                    }
                }

                if let eff = report.effectivenessScore {
                    Section("Scores") {
                        HStack {
                            VStack { Text("Effectiveness").font(.caption); Text(String(format: "%.0f%%", eff * 100)).font(.title3) }
                            Spacer()
                            if let tol = report.tolerabilityScore {
                                VStack { Text("Tolerability").font(.caption); Text(String(format: "%.0f%%", tol * 100)).font(.title3) }
                            }
                        }
                    }
                }

                if let summary = report.aiSummary {
                    Section("AI Summary") {
                        Text(summary).font(.body)
                    }
                }
            }
        }
    }
}

// MARK: - Shared Components

struct PharmacyStatusBadge: View {
    let status: String

    private var color: Color {
        switch status.lowercased() {
        case "active", "taken", "approved", "dispensed", "completed": return .green
        case "pending", "pending_review", "in_progress", "late": return .orange
        case "cancelled", "denied", "missed", "expired": return .red
        case "on_hold", "skipped": return .gray
        default: return .blue
        }
    }

    var body: some View {
        Text(status.replacingOccurrences(of: "_", with: " ").capitalized)
            .font(.caption2)
            .fontWeight(.medium)
            .padding(.horizontal, 8)
            .padding(.vertical, 2)
            .background(color.opacity(0.15))
            .foregroundStyle(color)
            .clipShape(Capsule())
    }
}

struct SummaryCard: View {
    let items: [(String, String)]

    var body: some View {
        HStack {
            ForEach(items, id: \.0) { label, value in
                VStack(spacing: 2) {
                    Text(value).font(.title3).fontWeight(.semibold)
                    Text(label).font(.caption2).foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity)
            }
        }
        .padding(.vertical, 4)
    }
}
