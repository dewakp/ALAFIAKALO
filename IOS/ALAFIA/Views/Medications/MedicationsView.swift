import SwiftUI
import PhotosUI

@Observable
final class MedicationsViewModel {
    var medications: [Medication] = []
    var doseLogs: [MedicationDoseLog] = []
    var isLoading = false
    var loadingLogs = false
    var errorMessage: String?

    /// Intake history for a single day (YYYY-MM-DD), newest first.
    func fetchDoseLogs(date: String) async {
        loadingLogs = true
        defer { loadingLogs = false }
        do {
            doseLogs = try await APIClient.shared.get("/medications/dose-logs?log_date=\(date)")
        } catch {
            errorMessage = error.localizedDescription
            doseLogs = []
        }
    }

    func deleteDoseLog(id: Int) async {
        do {
            try await APIClient.shared.delete("/medications/dose-logs/\(id)")
            doseLogs.removeAll { $0.id == id }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func fetchMedications() async {
        isLoading = true
        errorMessage = nil
        do {
            medications = try await APIClient.shared.get("/medications/")
            isLoading = false
        } catch {
            errorMessage = error.localizedDescription
            isLoading = false
        }
    }
    
    func addMedication(_ med: MedicationCreate) async -> Bool {
        do {
            let _: Medication = try await APIClient.shared.post("/medications/", body: med)
            await fetchMedications()
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }
    
    func deleteMedication(id: Int) async {
        do {
            try await APIClient.shared.delete("/medications/\(id)")
            medications.removeAll { $0.id == id }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    /// Records a "taken" dose event. Returns true on success.
    func logDose(_ dose: MedicationDoseLogCreate) async -> Bool {
        do {
            let _: MedicationDoseLog = try await APIClient.shared.post("/medications/dose-logs", body: dose)
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    /// Scan a bottle/label photo → AI reads name/dosage/instructions to prefill the form.
    func scanLabel(imageData: Data) async -> MedicationFromImageResponse? {
        struct Body: Encodable { let image_base64: String }
        do {
            let body = Body(image_base64: "data:image/jpeg;base64," + imageData.base64EncodedString())
            let res: MedicationFromImageResponse = try await APIClient.shared.post(
                "/image-ai/medication-from-image", body: body, timeout: 180)
            return res
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }
}

struct MedicationsView: View {
    enum MedTab: String, CaseIterable, Identifiable {
        case meds = "Medications", log = "Intake Log"
        var id: String { rawValue }
    }

    @State private var vm = MedicationsViewModel()
    @State private var tab: MedTab = .meds
    @State private var logDate = Date()
    @State private var showLogSheet = false
    @State private var showAdd = false
    @State private var doseTarget: Medication?
    @State private var scanItem: PhotosPickerItem?
    @State private var scanning = false
    @State private var scanPrefill: MedicationFromImageResponse?
    @State private var showScanForm = false

    private var logDateISO: String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX"); f.timeZone = .current
        f.dateFormat = "yyyy-MM-dd"
        return f.string(from: logDate)
    }

    var body: some View {
        VStack(spacing: 0) {
            Picker("", selection: $tab) {
                ForEach(MedTab.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)
            .padding(.horizontal)
            .padding(.top, 8)

            switch tab {
            case .meds: medicationsList
            case .log:  intakeLog
            }
        }
        .navigationTitle("Medications")
        .toolbar {
            ToolbarItemGroup(placement: .topBarTrailing) {
                PhotosPicker(selection: $scanItem, matching: .images) {
                    if scanning { ProgressView() } else { Image(systemName: "camera.viewfinder") }
                }
                .disabled(scanning)
                Button { showAdd = true } label: {
                    Image(systemName: "plus")
                }
            }
        }
        .onChange(of: scanItem) { _, item in
            guard let item else { return }
            Task {
                scanning = true
                defer { scanning = false }
                guard let data = try? await item.loadTransferable(type: Data.self) else { return }
                if let res = await vm.scanLabel(imageData: data) {
                    let name = res.medicationName ?? ""
                    if name.isEmpty || name.caseInsensitiveCompare("Unknown Medication") == .orderedSame {
                        vm.errorMessage = res.notes ?? "Couldn't read the label — try a clearer, well-lit photo."
                    } else {
                        scanPrefill = res
                        showScanForm = true
                    }
                }
                scanItem = nil
            }
        }
        .sheet(isPresented: $showAdd) {
            AddMedicationSheet(vm: vm)
        }
        .sheet(isPresented: $showScanForm, onDismiss: { scanPrefill = nil }) {
            AddMedicationSheet(vm: vm, prefill: scanPrefill)
        }
        .sheet(item: $doseTarget, onDismiss: refreshLogsIfNeeded) { med in
            MedicationDoseSheet(medication: med, vm: vm, defaultDate: logDate)
        }
        .sheet(isPresented: $showLogSheet, onDismiss: refreshLogsIfNeeded) {
            MedicationDoseSheet(medication: nil, vm: vm, defaultDate: logDate)
        }
        .task { await vm.fetchMedications() }
    }

    private func refreshLogsIfNeeded() {
        if tab == .log { Task { await vm.fetchDoseLogs(date: logDateISO) } }
    }

    // MARK: - Medications registry tab

    @ViewBuilder private var medicationsList: some View {
        if vm.isLoading {
            ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if vm.medications.isEmpty {
            EmptyStateView(icon: "pills.fill", title: "No Medications", message: "Tap + to add a medication")
        } else {
            List {
                ForEach(vm.medications) { med in
                    MedicationRow(med: med)
                        .swipeActions(edge: .leading, allowsFullSwipe: true) {
                            Button { doseTarget = med } label: {
                                Label("Log Dose", systemImage: "checkmark.circle.fill")
                            }
                            .tint(.green)
                        }
                }
                .onDelete { indexSet in
                    Task { for index in indexSet { await vm.deleteMedication(id: vm.medications[index].id) } }
                }
            }
        }
    }

    // MARK: - Intake-log tab (date + per-day history with pre-med vitals)

    @ViewBuilder private var intakeLog: some View {
        List {
            Section {
                DatePicker("Date", selection: $logDate, displayedComponents: .date)
                Button { showLogSheet = true } label: {
                    Label("Log New Intake", systemImage: "plus.circle.fill")
                }
            }
            Section("Logged intake") {
                if vm.loadingLogs {
                    HStack { Spacer(); ProgressView(); Spacer() }
                } else if vm.doseLogs.isEmpty {
                    Text("No intake logged for this date.")
                        .font(.subheadline).foregroundStyle(.secondary)
                } else {
                    ForEach(vm.doseLogs) { log in DoseLogRow(log: log) }
                        .onDelete { idx in
                            Task { for i in idx { await vm.deleteDoseLog(id: vm.doseLogs[i].id) } }
                        }
                }
            }
        }
        .task(id: logDateISO) { await vm.fetchDoseLogs(date: logDateISO) }
    }
}

/// One intake entry: medication, time, dose, and any pre-medication vitals.
struct DoseLogRow: View {
    let log: MedicationDoseLog

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(log.medicationName).font(.subheadline).fontWeight(.semibold)
                Spacer()
                if let t = log.timeDisplay {
                    Text(t).font(.caption).foregroundStyle(.secondary)
                }
            }
            Text("\(doseText) \(log.doseUnit)")
                .font(.caption).foregroundStyle(.secondary)
            if log.hasVitals {
                Text(vitalsSummary)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            if let notes = log.notes, !notes.isEmpty {
                Text(notes).font(.caption2).foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 2)
    }

    private var doseText: String {
        let a = log.doseAmount
        return a == a.rounded() ? String(Int(a)) : String(a)
    }

    private var vitalsSummary: String {
        var parts: [String] = []
        if log.preSystolicBp != nil || log.preDiastolicBp != nil {
            parts.append("BP \(log.preSystolicBp.map(String.init) ?? "–")/\(log.preDiastolicBp.map(String.init) ?? "–")")
        }
        if let hr = log.preHeartRate { parts.append("HR \(hr)") }
        if let c = log.preTemperatureC { parts.append(TempConvert.fahrenheitString(fromCelsius: c)) }
        return "Pre: " + parts.joined(separator: ", ")
    }
}

struct MedicationRow: View {
    let med: Medication
    
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(med.name)
                        .font(.headline)
                    if let src = med.source {
                        Text("⤵ Imported · \(src)")
                            .font(.caption2).fontWeight(.medium)
                            .padding(.horizontal, 6).padding(.vertical, 1)
                            .background(Color.orange.opacity(0.15))
                            .foregroundStyle(.orange)
                            .clipShape(Capsule())
                    }
                    Text(med.dosageDisplay)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                if med.isActive {
                    Text("Active")
                        .font(.caption2)
                        .fontWeight(.medium)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 2)
                        .background(Color.green.opacity(0.15))
                        .foregroundStyle(.green)
                        .clipShape(Capsule())
                }
            }
            
            HStack {
                if let freq = med.frequency {
                    Label(freq, systemImage: "clock")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                if let rxnorm = med.rxnormCode {
                    Spacer()
                    Text("RxNorm: \(rxnorm)")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
            }
        }
        .padding(.vertical, 4)
    }
}

struct AddMedicationSheet: View {
    @Bindable var vm: MedicationsViewModel
    var prefill: MedicationFromImageResponse? = nil
    @Environment(\.dismiss) var dismiss

    @State private var medicationName = ""
    @State private var dosage = ""
    @State private var dosageUnit = "mg"
    @State private var frequency = "once daily"
    @State private var rxnormCode = ""
    @State private var prescribedBy = ""
    @State private var active = true
    @State private var notes = ""
    @State private var saving = false

    let dosageUnits = ["mg", "mcg", "mL", "units", "tablets"]
    let frequencies = ["once daily", "twice daily", "three times daily", "as needed", "weekly"]

    private func applyPrefill() {
        guard let p = prefill, medicationName.isEmpty else { return }
        medicationName = p.medicationName ?? ""
        if let d = p.dosage, d.caseInsensitiveCompare("See label") != .orderedSame {
            dosage = d.filter { "0123456789.".contains($0) }
            let unit = d.filter { $0.isLetter }
            if !unit.isEmpty, dosageUnits.contains(unit) { dosageUnit = unit }
        }
        notes = [p.instructions, p.notes].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: "\n")
    }
    
    var body: some View {
        NavigationStack {
            Form {
                Section("Medication") {
                    LKTextField(title: "Medication name", text: $medicationName)
                    LKTextField(title: "RxNorm code (optional)", text: $rxnormCode)
                    Toggle("Active", isOn: $active)
                }
                Section("Dosage") {
                    HStack {
                        LKNumberField(title: "Amount", value: $dosage)
                        Picker("Unit", selection: $dosageUnit) {
                            ForEach(dosageUnits, id: \.self) { Text($0) }
                        }
                        .pickerStyle(.menu)
                    }
                    Picker("Frequency", selection: $frequency) {
                        ForEach(frequencies, id: \.self) { Text($0.capitalized) }
                    }
                }
                Section("Provider") {
                    LKTextField(title: "Prescribed by (optional)", text: $prescribedBy)
                }
                Section("Notes") {
                    TextField("Notes (optional)", text: $notes, axis: .vertical)
                        .lineLimit(3...6)
                }
            }
            .navigationTitle(prefill != nil ? "Add Scanned Medication" : "Add Medication")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Save") { save() }
                        .disabled(medicationName.isEmpty || saving)
                        .fontWeight(.semibold)
                }
            }
            .onAppear { applyPrefill() }
        }
    }
    
    private func save() {
        saving = true
        let med = MedicationCreate(
            name: medicationName,
            dosage: dosage.isEmpty ? nil : dosage,
            dosageUnit: dosageUnit,
            frequency: frequency,
            startDate: .todayISO(),
            prescribingDoctor: prescribedBy.isEmpty ? nil : prescribedBy,
            isActive: active
        )
        Task {
            if await vm.addMedication(med) { dismiss() }
            saving = false
        }
    }
}

struct MedicationDoseSheet: View {
    /// Preselected medication (from a registry row), or nil to log any medication
    /// by name (matches the web "Select from profile or add new").
    let medication: Medication?
    @Bindable var vm: MedicationsViewModel
    var defaultDate: Date = Date()
    @Environment(\.dismiss) var dismiss

    @State private var medName = ""
    @State private var amount = ""
    @State private var unit = "mg"
    @State private var date = Date()
    @State private var time = Date()
    @State private var notes = ""
    // Pre-medication vitals (optional) — parity with the web intake form.
    @State private var systolic = ""
    @State private var diastolic = ""
    @State private var heartRate = ""
    @State private var tempF = ""
    @State private var saving = false
    @State private var errorText: String?

    private var resolvedName: String {
        (medication?.name ?? medName).trimmingCharacters(in: .whitespaces)
    }
    private var units: [String] {
        var base = ["mg", "mcg", "mL", "units", "tablets", "IU", "g"]
        if let u = medication?.dosageUnit, !u.isEmpty, !base.contains(u) {
            base.insert(u, at: 0)
        }
        return base
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Medication") {
                    if let medication {
                        Text(medication.name).font(.headline)
                        if let freq = medication.frequency {
                            Text(freq).font(.caption).foregroundStyle(.secondary)
                        }
                    } else {
                        TextField("Medication name", text: $medName)
                        if !vm.medications.isEmpty {
                            Menu("Choose from your medications") {
                                ForEach(vm.medications) { m in
                                    Button(m.name) {
                                        medName = m.name
                                        if let u = m.dosageUnit, !u.isEmpty { unit = u }
                                    }
                                }
                            }
                            .font(.caption)
                        }
                    }
                }
                Section("When") {
                    DatePicker("Date", selection: $date, displayedComponents: .date)
                    DatePicker("Time", selection: $time, displayedComponents: .hourAndMinute)
                }
                Section("Dose taken") {
                    HStack {
                        LKNumberField(title: "Amount", value: $amount)
                        Picker("Unit", selection: $unit) {
                            ForEach(units, id: \.self) { Text($0) }
                        }
                        .pickerStyle(.menu)
                    }
                }
                Section("Pre-Medication Vitals (optional)") {
                    LKNumberField(title: "Systolic BP", value: $systolic)
                    LKNumberField(title: "Diastolic BP", value: $diastolic)
                    LKNumberField(title: "Heart Rate", value: $heartRate)
                    LKNumberField(title: "Temp (°F)", value: $tempF)
                }
                Section("Notes") {
                    TextField("Notes (optional)", text: $notes, axis: .vertical)
                        .lineLimit(2...4)
                }
                if let errorText {
                    Text(errorText).font(.caption).foregroundStyle(.red)
                }
            }
            .navigationTitle("Log Intake")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Log") { save() }
                        .disabled(Double(amount) == nil || resolvedName.isEmpty || saving)
                        .fontWeight(.semibold)
                }
            }
            .onAppear {
                date = defaultDate
                if amount.isEmpty {
                    amount = (medication?.dosage ?? "").filter { "0123456789.".contains($0) }
                }
                if let u = medication?.dosageUnit, !u.isEmpty { unit = u }
            }
        }
    }

    private func save() {
        guard let value = Double(amount), !resolvedName.isEmpty else { return }
        saving = true
        errorText = nil
        let dateF = DateFormatter()
        dateF.locale = Locale(identifier: "en_US_POSIX"); dateF.timeZone = .current
        dateF.dateFormat = "yyyy-MM-dd"
        let timeF = DateFormatter()
        timeF.locale = Locale(identifier: "en_US_POSIX"); timeF.timeZone = .current
        timeF.dateFormat = "HH:mm:ss"

        let dose = MedicationDoseLogCreate(
            medicationName: resolvedName,
            logDate: dateF.string(from: date),
            doseAmount: value,
            doseUnit: unit,
            logTime: timeF.string(from: time),
            medicationId: medication?.id,
            preSystolicBp: Int(systolic),
            preDiastolicBp: Int(diastolic),
            preHeartRate: Int(heartRate),
            preTemperatureC: Double(tempF).map(TempConvert.toCelsius),
            notes: notes.isEmpty ? nil : notes
        )
        Task {
            let ok = await vm.logDose(dose)
            saving = false
            if ok {
                dismiss()
            } else {
                errorText = vm.errorMessage ?? "Failed to log dose"
            }
        }
    }
}
