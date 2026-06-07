import SwiftUI

@Observable
final class LifestyleViewModel {
    var entries: [LifestyleEntry] = []
    var isLoading = false
    var errorMessage: String?
    
    func fetchEntries() async {
        isLoading = true
        errorMessage = nil
        do {
            entries = try await APIClient.shared.get("/lifestyle/")
            isLoading = false
        } catch {
            errorMessage = error.localizedDescription
            isLoading = false
        }
    }
    
    func addEntry(_ entry: LifestyleEntryCreate) async -> Bool {
        do {
            let _: LifestyleEntry = try await APIClient.shared.post("/lifestyle/", body: entry)
            await fetchEntries()
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }
    
    func deleteEntry(id: Int) async {
        do {
            try await APIClient.shared.delete("/lifestyle/\(id)")
            entries.removeAll { $0.id == id }
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct LifestyleView: View {
    @State private var vm = LifestyleViewModel()
    @State private var showAdd = false
    
    var body: some View {
        Group {
            if vm.isLoading {
                ProgressView()
            } else if vm.entries.isEmpty {
                EmptyStateView(icon: "heart.fill", title: "No Lifestyle Entries", message: "Tap + to log vitals & habits")
            } else {
                List {
                    ForEach(vm.entries) { entry in
                        LifestyleRow(entry: entry)
                    }
                    .onDelete { indexSet in
                        Task {
                            for index in indexSet {
                                await vm.deleteEntry(id: vm.entries[index].id)
                            }
                        }
                    }
                }
            }
        }
        .navigationTitle("Lifestyle")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { showAdd = true } label: {
                    Image(systemName: "plus")
                }
            }
        }
        .sheet(isPresented: $showAdd) {
            AddLifestyleSheet(vm: vm)
        }
        .task { await vm.fetchEntries() }
    }
}

struct LifestyleRow: View {
    let entry: LifestyleEntry
    
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                if let bp = entry.bloodPressure {
                    VitalPill(icon: "heart.fill", value: bp, color: .red)
                }
                if let hr = entry.restingHeartRate {
                    VitalPill(icon: "waveform.path.ecg", value: "\(hr) bpm", color: .pink)
                }
                if let wt = entry.weightKg {
                    VitalPill(icon: "scalemass.fill", value: String(format: "%.1f kg", wt), color: .blue)
                }
            }
            
            HStack(spacing: 12) {
                if let smoke = entry.smokingStatus {
                    Label(smoke, systemImage: "smoke.fill")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                if let alc = entry.alcoholDrinks {
                    Label("\(alc) drinks", systemImage: "wineglass.fill")
                        .font(.caption)
                        .foregroundStyle(.orange)
                }
            }
        }
        .padding(.vertical, 4)
    }
}

struct VitalPill: View {
    let icon: String
    let value: String
    let color: Color
    
    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: icon)
                .font(.caption2)
            Text(value)
                .font(.caption)
                .fontWeight(.medium)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(color.opacity(0.12))
        .foregroundStyle(color)
        .clipShape(Capsule())
    }
}

struct AddLifestyleSheet: View {
    @Bindable var vm: LifestyleViewModel
    @Environment(\.dismiss) var dismiss
    
    @State private var systolic = ""
    @State private var diastolic = ""
    @State private var heartRate = ""
    @State private var weightKg = ""
    @State private var waterMl = ""
    @State private var steps = ""
    @State private var smokingStatus = "never"
    @State private var alcoholUnits = ""
    @State private var notes = ""
    @State private var saving = false
    
    let smokingOptions = ["never", "former", "current", "occasional"]
    
    var body: some View {
        NavigationStack {
            Form {
                Section("Blood Pressure") {
                    HStack {
                        LKNumberField(title: "Systolic", value: $systolic)
                        Text("/")
                        LKNumberField(title: "Diastolic", value: $diastolic)
                    }
                }
                Section("Vitals") {
                    LKNumberField(title: "Heart rate (bpm)", value: $heartRate)
                    LKNumberField(title: "Weight (kg)", value: $weightKg)
                }
                Section("Daily Habits") {
                    LKNumberField(title: "Water intake (mL)", value: $waterMl)
                    LKNumberField(title: "Steps", value: $steps)
                }
                Section("Substances") {
                    Picker("Smoking", selection: $smokingStatus) {
                        ForEach(smokingOptions, id: \.self) { Text($0.capitalized) }
                    }
                    LKNumberField(title: "Alcohol units", value: $alcoholUnits)
                }
                Section("Notes") {
                    TextField("Notes (optional)", text: $notes, axis: .vertical)
                        .lineLimit(3...6)
                }
            }
            .navigationTitle("Log Vitals")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Save") { save() }
                        .disabled(saving)
                        .fontWeight(.semibold)
                }
            }
        }
    }
    
    private func save() {
        saving = true
        let entry = LifestyleEntryCreate(
            entryDate: .todayISO(),
            weightKg: Double(weightKg),
            bloodPressureSystolic: Int(systolic),
            bloodPressureDiastolic: Int(diastolic),
            restingHeartRate: Int(heartRate),
            notes: notes.isEmpty ? nil : notes
        )
        Task {
            if await vm.addEntry(entry) { dismiss() }
            saving = false
        }
    }
}
