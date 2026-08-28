import SwiftUI
import PhotosUI

/// What came back from an attempt to record a dose.
///
/// `logDose` used to return `Bool` and flatten the guard's refusal into
/// `errorMessage`, which discarded the findings and the override. A refusal is
/// not the same event as a network failure: one has a reason and a way through,
/// the other does not.
enum DoseLogOutcome {
    case saved
    case refused(DoseGuardRefusal.Detail)
    case failed(String)
}

@Observable
final class MedicationsViewModel {
    var medications: [Medication] = []
    var doseLogs: [MedicationDoseLog] = []
    /// What this patient actually takes, from their own dose logs.
    var frequent: [FrequentMedication] = []
    var isLoading = false
    var loadingLogs = false
    var errorMessage: String?

    /// Prescriptions first (the strongest statement of what they take), then
    /// their own logging history, de-duplicated case-insensitively — the same
    /// drug arrives as both "Calcium Carbonate" and "Calcium carbonate".
    var pickerOptions: [MedicationSuggestion] {
        var seen = Set<String>()
        var out: [MedicationSuggestion] = []
        for m in medications where m.isActive {
            let key = m.name.lowercased()
            if key.isEmpty || seen.contains(key) { continue }
            seen.insert(key)
            out.append(MedicationSuggestion(name: m.name, timesLogged: nil, lastTaken: nil))
        }
        for h in frequent {
            let key = h.name.lowercased()
            if seen.contains(key) { continue }
            seen.insert(key)
            out.append(MedicationSuggestion(name: h.name, timesLogged: h.timesLogged, lastTaken: h.lastTaken))
        }
        return out
    }

    /// Drugs logged often enough to be a real regimen but absent from the
    /// prescription list. Thresholded at 3, matching the backend: a drug logged
    /// ONCE (the mistyped "Calcium Calcitriol" on this record) must never become
    /// a clinical statement.
    var unlistedRegulars: [FrequentMedication] {
        frequent.filter { h in
            h.timesLogged >= 3
                && !medications.contains { $0.name.lowercased() == h.name.lowercased() }
        }
    }

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
    /// Read free text into a dose proposal. Writes nothing — see the model.
    func readIntake(_ text: String) async -> MedicationIntakeProposal? {
        try? await APIClient.shared.post(
            "/medications/intake-intent", body: MedicationIntakeRequest(text: text)
        )
    }

    /// The patient's own dose-log history, for the intake picker.
    /// A failure leaves the list empty rather than blocking the form — they can
    /// still type a name.
    func fetchFrequent() async {
        frequent = (try? await APIClient.shared.get("/medications/frequent")) ?? []
    }

    /// Turn regularly-logged drugs into prescription rows. Explicit on purpose:
    /// a prescription is a clinical statement, so the patient asks for it.
    @discardableResult
    func promoteLogged() async -> Bool {
        struct Empty: Encodable {}
        struct Result: Decodable { let created: [Created]
                                   struct Created: Decodable { let name: String } }
        do {
            let _: Result = try await APIClient.shared.post("/medications/promote-logged", body: Empty())
            await fetchMedications()
            await fetchFrequent()
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    func logDose(_ dose: MedicationDoseLogCreate) async -> DoseLogOutcome {
        do {
            let _: MedicationDoseLog = try await APIClient.shared.post("/medications/dose-logs", body: dose)
            return .saved
        } catch {
            // A refusal carries WHY and a way through. Both used to be dropped:
            // iOS showed "Request failed (422)" on a dose the guard had already
            // diagnosed down to the corrected spelling.
            if let refusal = DoseGuardRefusal.from(error) {
                return .refused(refusal.detail)
            }
            errorMessage = error.localizedDescription
            return .failed(error.localizedDescription)
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
    @State private var scanning = false
    @State private var scanPrefill: MedicationFromImageResponse?
    @State private var showScanForm = false
    @State private var intakeText = ""
    @State private var intakeBusy = false
    @State private var intakeError: String?
    @State private var intakeProposal: MedicationIntakeProposal?
    @State private var intakePrefill: MedicationIntakeProposal?
    @State private var promoting = false

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
                // A medication label is in the patient's hand when they tap
                // this. Opening the photo library was the wrong default.
                PhotoCaptureButton { data in
                    Task { await scanLabel(data) }
                } label: {
                    if scanning { ProgressView() } else { Image(systemName: "camera.viewfinder") }
                }
                .disabled(scanning)
                Button { showAdd = true } label: {
                    Image(systemName: "plus")
                }
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
            MedicationDoseSheet(medication: nil, vm: vm, defaultDate: logDate,
                                prefill: intakePrefill)
        }
        .task {
            await vm.fetchMedications()
            await vm.fetchFrequent()
        }
    }

    /// Read a label photo. Takes Data so the CAMERA and the library are the
    /// same path — the source is the caller's choice, not this function's
    /// concern.
    private func scanLabel(_ data: Data) async {
        scanning = true
        defer { scanning = false }
        guard let res = await vm.scanLabel(imageData: data) else { return }
        let name = res.medicationName ?? ""
        if name.isEmpty || name.caseInsensitiveCompare("Unknown Medication") == .orderedSame {
            vm.errorMessage = res.notes ?? "Couldn't read the label — try a clearer, well-lit photo."
        } else {
            scanPrefill = res
            showScanForm = true
        }
    }

    private func refreshLogsIfNeeded() {
        if tab == .log { Task { await vm.fetchDoseLogs(date: logDateISO) } }
    }

    // MARK: - Medications registry tab

    @ViewBuilder private var medicationsList: some View {
        if vm.isLoading {
            ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if vm.medications.isEmpty && vm.unlistedRegulars.isEmpty {
            EmptyStateView(icon: "pills.fill", title: "No Medications", message: "Tap + to add a medication")
        } else {
            List {
                // "No medications" was a lie on the production record: zero
                // prescriptions, 943 dose logs. The patient's own history is a
                // statement of what they take — offer to make it one on file
                // rather than showing an empty screen (canon §3aa).
                if !vm.unlistedRegulars.isEmpty {
                    Section {
                        promoteLoggedPrompt
                    }
                }
                if !vm.medications.isEmpty {
                    Section {
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
                    } header: {
                        // Prescribed and taken are different facts; label which
                        // one this list is, rather than implying it is both.
                        Text(vm.medications.contains { $0.isActive }
                             ? "Prescriptions" : "Prescriptions (all stopped)")
                    }
                }
            }
        }
    }

    @ViewBuilder private var promoteLoggedPrompt: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("You regularly log \(vm.unlistedRegulars.count) medication\(vm.unlistedRegulars.count == 1 ? "" : "s") that aren’t on this list")
                .font(.subheadline.weight(.semibold))
            ForEach(vm.unlistedRegulars) { m in
                Text("• \(m.name) — taken \(m.timesLogged)×\(m.lastTaken.map { ", last \($0)" } ?? "")")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Button {
                Task { promoting = true; await vm.promoteLogged(); promoting = false }
            } label: {
                if promoting { ProgressView() } else { Text("Add these to my medications") }
            }
            .font(.subheadline.weight(.semibold))
            .disabled(promoting)
        }
        .padding(.vertical, 4)
    }

    // MARK: - Intake-log tab (date + per-day history with pre-med vitals)

    /// 0.5 stays 0.5; 2.0 prints as 2. Doses are read at a glance.
    static func doseText(_ value: Double) -> String {
        value == value.rounded() && abs(value) < 1e9
            ? String(Int(value)) : String(format: "%g", value)
    }

    private func runIntake() async {
        let text = intakeText.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return }
        intakeBusy = true; intakeProposal = nil; intakeError = nil
        defer { intakeBusy = false }
        guard let proposal = await vm.readIntake(text) else {
            intakeError = "Couldn’t read that."; return
        }
        if proposal.medicationName.isEmpty {
            intakeError = proposal.provenance ?? "No medication recognised."
        } else {
            intakeProposal = proposal
        }
    }

    /// Hand the proposal to the sheet the user already knows, rather than
    /// logging it behind their back.
    private func acceptProposal(_ p: MedicationIntakeProposal) {
        intakePrefill = p
        intakeProposal = nil
        intakeText = ""
        showLogSheet = true
    }

    @ViewBuilder private var intakeLog: some View {
        List {
            Section("Say it in words") {
                HStack {
                    TextField("e.g. “I take Calcitriol”", text: $intakeText)
                        .textInputAutocapitalization(.never)
                        .onSubmit { Task { await runIntake() } }
                    if intakeBusy { ProgressView() }
                    else {
                        Button("Read") { Task { await runIntake() } }
                            .disabled(intakeText.trimmingCharacters(in: .whitespaces).isEmpty)
                    }
                }
                if let p = intakeProposal, !p.medicationName.isEmpty {
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text(p.medicationName).bold()
                            if let amount = p.doseAmount {
                                Text("— \(Self.doseText(amount)) \(p.doseUnit ?? "")")
                            }
                        }
                        // Provenance is always shown. An inferred dose that does
                        // not say where it came from cannot be told apart from
                        // one the app invented.
                        if let why = p.provenance {
                            Text(why).font(.caption).foregroundStyle(.secondary)
                        }
                        ForEach(p.blocking) { f in
                            Text(f.message).font(.caption).foregroundStyle(.red)
                        }
                        Button(p.hasDose ? "Use this" : "Fill the name") { acceptProposal(p) }
                            .buttonStyle(.borderedProminent).controlSize(.small)
                    }
                } else if let err = intakeError {
                    Text(err).font(.caption).foregroundStyle(.red)
                }
            }
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
    /// A proposal read from free text ("I take Calcitriol"), pre-filled here so
    /// the user confirms in the form they already know instead of the app
    /// writing a dose on their behalf.
    var prefill: MedicationIntakeProposal? = nil
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
    /// What the dose guard refused, kept apart from `errorText`: a refusal has a
    /// reason and a way through, a network failure has neither.
    @State private var refusal: DoseGuardRefusal.Detail?

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
                // FIRST, deliberately. "Log" is in the top toolbar, so a refusal
                // rendered after the Notes section sits below the fold: the user
                // taps Log, nothing appears to happen, and the explanation is
                // off-screen — the very failure this panel exists to fix. Only
                // running the app showed it; the build and unit tests were green.
                if let refusal {
                    Section {
                        DoseGuardFindingsView(
                            detail: refusal,
                            onUseSuggestion: { suggestion in
                                medName = suggestion
                                self.refusal = nil
                            },
                            onAcknowledge: { save(acknowledgeUnusual: true) }
                        )
                    }
                }
                Section("Medication") {
                    if let medication {
                        Text(medication.name).font(.headline)
                        if let freq = medication.frequency {
                            Text(freq).font(.caption).foregroundStyle(.secondary)
                        }
                    } else {
                        // Offers prescriptions AND this patient's own dose-log
                        // history. The menu it replaces read `/medications/`
                        // only, which on this record is empty (canon §3aa).
                        MedicationPickerField(
                            name: $medName,
                            options: vm.pickerOptions,
                            onSelect: { option in
                                if let m = vm.medications.first(where: {
                                    $0.name.lowercased() == option.name.lowercased()
                                }), let u = m.dosageUnit, !u.isEmpty {
                                    unit = u
                                }
                            }
                        )
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
            .task { await vm.fetchFrequent() }
            .onAppear {
                date = defaultDate
                // A proposal read from free text wins over the registry default:
                // it is what the user just asked for, and it already carries the
                // dose their own history says they take.
                if let p = prefill, !p.medicationName.isEmpty {
                    medName = p.medicationName
                    if let value = p.doseAmount { amount = MedicationsView.doseText(value) }
                    if let u = p.doseUnit, !u.isEmpty { unit = u }
                }
                if amount.isEmpty {
                    amount = (medication?.dosage ?? "").filter { "0123456789.".contains($0) }
                }
                if let u = medication?.dosageUnit, !u.isEmpty { unit = u }
            }
        }
    }

    private func save(acknowledgeUnusual: Bool = false) {
        guard let value = Double(amount), !resolvedName.isEmpty else { return }
        saving = true
        errorText = nil
        if !acknowledgeUnusual { refusal = nil }
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
            notes: notes.isEmpty ? nil : notes,
            acknowledgeUnusual: acknowledgeUnusual
        )
        Task {
            let outcome = await vm.logDose(dose)
            saving = false
            switch outcome {
            case .saved:
                dismiss()
            case .refused(let detail):
                // Not an error the user can only stare at: it names what is
                // wrong and offers both the correction and a way past.
                refusal = detail
            case .failed(let message):
                errorText = message
            }
        }
    }
}
