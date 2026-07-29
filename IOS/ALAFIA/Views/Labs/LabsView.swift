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
                    Button { showAdd = true } label: {
                        Image(systemName: "plus")
                    }
                }
            }
            .sheet(isPresented: $showAdd) {
                AddLabSheet(vm: vm)
            }
            .task { await vm.fetchResults() }
    }
}

struct LabRow: View {
    let result: LabResult
    
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(result.testName)
                    .font(.headline)
                Spacer()
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
