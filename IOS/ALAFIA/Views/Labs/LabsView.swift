import SwiftUI

@Observable
final class LabsViewModel {
    var results: [LabResult] = []
    var isLoading = false
    var errorMessage: String?
    
    func fetchResults() async {
        isLoading = true
        errorMessage = nil
        do {
            results = try await APIClient.shared.get("/labs/")
            isLoading = false
        } catch {
            errorMessage = error.localizedDescription
            isLoading = false
        }
    }
    
    func addResult(_ result: LabResultCreate) async -> Bool {
        do {
            let _: LabResult = try await APIClient.shared.post("/labs/", body: result)
            await fetchResults()
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }
    
    func deleteResult(id: Int) async {
        do {
            try await APIClient.shared.delete("/labs/\(id)")
            results.removeAll { $0.id == id }
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct LabsView: View {
    @State private var vm = LabsViewModel()
    @State private var showAdd = false
    /// Document import, on its Import tab. A report is parsed and staged for
    /// review there; nothing reaches the results until the patient confirms.
    @State private var showUpload = false

    var body: some View {
            Group {
                if vm.isLoading {
                    ProgressView()
                } else if vm.results.isEmpty {
                    EmptyStateView(icon: "flask.fill", title: "No Lab Results", message: "Tap + to add a lab result")
                } else {
                    List {
                        ForEach(vm.results) { result in
                            LabRow(result: result)
                        }
                        .onDelete { indexSet in
                            Task {
                                for index in indexSet {
                                    await vm.deleteResult(id: vm.results[index].id)
                                }
                            }
                        }
                    }
                }
            }
            .navigationTitle("Labs / EHR")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Button { showAdd = true } label: {
                            Label("Enter a result", systemImage: "square.and.pencil")
                        }
                        Button { showUpload = true } label: {
                            Label("Upload lab report (PDF)", systemImage: "doc.badge.arrow.up")
                        }
                    } label: {
                        Image(systemName: "plus")
                    }
                    .accessibilityLabel("Add lab result")
                }
            }
            .sheet(isPresented: $showAdd) {
                AddLabSheet(vm: vm)
            }
            .navigationDestination(isPresented: $showUpload) {
                PdfToolsView()
            }
            .task { await vm.fetchResults() }
    }
}

struct LabRow: View {
    let result: LabResult
    
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(result.shownName)
                        .font(.headline)
                    // The report's own wording under the analyte's name ("ALP" under
                    // Alkaline Phosphatase), so the row can still be found on the document.
                    if let reported = result.reportedAs {
                        Text(reported)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                Spacer()
                AbnormalBadge(isAbnormal: result.isAbnormal)
                StatusBadge(status: result.status)
            }
            
            Text(result.displayValue)
                .font(.title3)
                .fontWeight(.semibold)
                .foregroundStyle(.purple)
            
            HStack {
                if let ref = result.referenceRange {
                    Text("Ref: \(ref)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                if let loinc = result.loincCode {
                    Text("LOINC: \(loinc)")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
            }
        }
        .padding(.vertical, 4)
    }
}

/// Whether the result is in range — a THREE-state fact, never a boolean.
///
/// `is_abnormal` is null when nothing ever compared the value to a reference
/// range: 9,417 of 9,745 stored results on this database. Web collapsed that to
/// a boolean and printed "✅ Normal" beside a potassium of 6.7 (range 3.5–5.5).
/// This screen showed nothing at all — it drew `status` ("Final"), which says
/// the lab finished the test, not that the number is safe.
struct AbnormalBadge: View {
    let isAbnormal: Bool?

    private var label: LocalizedStringKey {
        switch isAbnormal {
        case .some(true):  return "Abnormal"
        case .some(false): return "In range"
        case .none:        return "Not assessed"
        }
    }

    private var tint: Color {
        switch isAbnormal {
        case .some(true):  return .red
        case .some(false): return .green
        // Deliberately NOT green. An unchecked result is not a reassuring one.
        case .none:        return .secondary
        }
    }

    var body: some View {
        Text(label)
            .font(.caption2)
            .fontWeight(.medium)
            .padding(.horizontal, 8)
            .padding(.vertical, 2)
            .background(tint.opacity(0.15))
            .foregroundStyle(tint)
            .clipShape(Capsule())
    }
}

struct StatusBadge: View {
    let status: String
    
    var color: Color {
        switch status.lowercased() {
        case "final": return .green
        case "preliminary": return .orange
        case "cancelled": return .red
        default: return .gray
        }
    }
    
    var body: some View {
        Text(status.capitalized)
            .font(.caption2)
            .fontWeight(.medium)
            .padding(.horizontal, 8)
            .padding(.vertical, 2)
            .background(color.opacity(0.15))
            .foregroundStyle(color)
            .clipShape(Capsule())
    }
}

struct AddLabSheet: View {
    @Bindable var vm: LabsViewModel
    @Environment(\.dismiss) var dismiss
    
    @State private var testName = ""
    @State private var loincCode = ""
    @State private var value = ""
    @State private var unit = ""
    @State private var refMin = ""
    @State private var refMax = ""
    @State private var status = "final"
    @State private var notes = ""
    @State private var saving = false
    
    let statuses = ["preliminary", "final", "cancelled"]
    
    var body: some View {
        NavigationStack {
            Form {
                Section("Test Info") {
                    LKTextField(title: "Test name (e.g. Glucose)", text: $testName)
                    LKTextField(title: "LOINC code (optional)", text: $loincCode)
                    Picker("Status", selection: $status) {
                        ForEach(statuses, id: \.self) { Text($0.capitalized) }
                    }
                }
                Section("Result") {
                    LKNumberField(title: "Value", value: $value)
                    LKTextField(title: "Unit (e.g. mg/dL)", text: $unit)
                }
                Section("Reference Range") {
                    LKNumberField(title: "Min", value: $refMin)
                    LKNumberField(title: "Max", value: $refMax)
                }
                Section("Notes") {
                    TextField("Notes (optional)", text: $notes, axis: .vertical)
                        .lineLimit(3...6)
                }
            }
            .navigationTitle("Add Lab Result")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Save") { save() }
                        .disabled(testName.isEmpty || value.isEmpty || saving)
                        .fontWeight(.semibold)
                }
            }
        }
    }
    
    private func save() {
        saving = true
        let result = LabResultCreate(
            testDate: .todayISO(),
            testName: testName,
            loincCode: loincCode.isEmpty ? nil : loincCode,
            value: Double(value) ?? 0,
            unit: unit.isEmpty ? nil : unit,
            referenceRangeLow: Double(refMin),
            referenceRangeHigh: Double(refMax),
            notes: notes.isEmpty ? nil : notes
        )
        Task {
            if await vm.addResult(result) { dismiss() }
            saving = false
        }
    }
}
