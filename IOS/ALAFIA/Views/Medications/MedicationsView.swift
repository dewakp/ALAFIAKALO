import SwiftUI
import PhotosUI

@Observable
final class MedicationsViewModel {
    var medications: [Medication] = []
    var isLoading = false
    var errorMessage: String?
    
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
    @State private var vm = MedicationsViewModel()
    @State private var showAdd = false
    @State private var doseTarget: Medication?
    @State private var scanItem: PhotosPickerItem?
    @State private var scanning = false
    @State private var scanPrefill: MedicationFromImageResponse?
    @State private var showScanForm = false

    var body: some View {
        Group {
            if vm.isLoading {
                ProgressView()
            } else if vm.medications.isEmpty {
                EmptyStateView(icon: "pills.fill", title: "No Medications", message: "Tap + to add a medication")
            } else {
                List {
                    ForEach(vm.medications) { med in
                        MedicationRow(med: med)
                            .swipeActions(edge: .leading, allowsFullSwipe: true) {
                                Button {
                                    doseTarget = med
                                } label: {
                                    Label("Log Dose", systemImage: "checkmark.circle.fill")
                                }
                                .tint(.green)
                            }
                    }
                    .onDelete { indexSet in
                        Task {
                            for index in indexSet {
                                await vm.deleteMedication(id: vm.medications[index].id)
                            }
                        }
                    }
                }
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
        .sheet(item: $doseTarget) { med in
            MedicationDoseSheet(medication: med, vm: vm)
        }
        .task { await vm.fetchMedications() }
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
    let medication: Medication
    @Bindable var vm: MedicationsViewModel
    @Environment(\.dismiss) var dismiss

    @State private var amount = ""
    @State private var unit = "mg"
    @State private var notes = ""
    @State private var saving = false
    @State private var errorText: String?

    private var units: [String] {
        var base = ["mg", "mcg", "mL", "units", "tablets", "IU", "g"]
        if let u = medication.dosageUnit, !u.isEmpty, !base.contains(u) {
            base.insert(u, at: 0)
        }
        return base
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Medication") {
                    Text(medication.name).font(.headline)
                    if let freq = medication.frequency {
                        Text(freq).font(.caption).foregroundStyle(.secondary)
                    }
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
                Section("Notes") {
                    TextField("Notes (optional)", text: $notes, axis: .vertical)
                        .lineLimit(2...4)
                }
                if let errorText {
                    Text(errorText).font(.caption).foregroundStyle(.red)
                }
            }
            .navigationTitle("Log Dose")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Log") { save() }
                        .disabled(Double(amount) == nil || saving)
                        .fontWeight(.semibold)
                }
            }
            .onAppear {
                if amount.isEmpty {
                    amount = (medication.dosage ?? "").filter { "0123456789.".contains($0) }
                }
                if let u = medication.dosageUnit, !u.isEmpty { unit = u }
            }
        }
    }

    private func save() {
        guard let value = Double(amount) else { return }
        saving = true
        errorText = nil
        let dose = MedicationDoseLogCreate(
            medicationName: medication.name,
            logDate: .todayISO(),
            doseAmount: value,
            doseUnit: unit,
            medicationId: medication.id,
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
