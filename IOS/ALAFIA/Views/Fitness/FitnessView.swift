import SwiftUI

@Observable
final class FitnessViewModel {
    var logs: [FitnessLog] = []
    var isLoading = false
    var errorMessage: String?
    
    func fetchLogs() async {
        isLoading = true
        errorMessage = nil
        do {
            logs = try await APIClient.shared.get("/fitness/")
            isLoading = false
        } catch {
            errorMessage = error.localizedDescription
            isLoading = false
        }
    }
    
    func addLog(_ log: FitnessLogCreate) async -> Bool {
        do {
            let _: FitnessLog = try await APIClient.shared.post("/fitness/", body: log)
            await fetchLogs()
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }
    
    func deleteLog(id: Int) async {
        do {
            try await APIClient.shared.delete("/fitness/\(id)")
            logs.removeAll { $0.id == id }
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct FitnessView: View {
    @State private var vm = FitnessViewModel()
    @State private var showAdd = false
    
    var body: some View {
        NavigationStack {
            Group {
                if vm.isLoading {
                    ProgressView()
                } else if vm.logs.isEmpty {
                    EmptyStateView(icon: "figure.run", title: "No Fitness Logs", message: "Tap + to log a workout")
                } else {
                    List {
                        ForEach(vm.logs) { log in
                            FitnessRow(log: log)
                        }
                        .onDelete { indexSet in
                            Task {
                                for index in indexSet {
                                    await vm.deleteLog(id: vm.logs[index].id)
                                }
                            }
                        }
                    }
                }
            }
            .navigationTitle("Fitness")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showAdd = true } label: {
                        Image(systemName: "plus")
                    }
                }
            }
            .sheet(isPresented: $showAdd) {
                AddFitnessSheet(vm: vm)
            }
            .task { await vm.fetchLogs() }
        }
    }
}

struct FitnessRow: View {
    let log: FitnessLog
    
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Image(systemName: iconForActivity(log.activityType))
                    .foregroundStyle(.blue)
                Text(log.activityType.capitalized)
                    .font(.headline)
                Spacer()
                if let cal = log.caloriesBurned {
                    Text("\(Int(cal)) kcal")
                        .font(.subheadline)
                        .foregroundStyle(.orange)
                        .fontWeight(.semibold)
                }
            }
            HStack(spacing: 16) {
                if let dur = log.durationMinutes {
                    Label("\(dur) min", systemImage: "clock")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                if let dist = log.distanceKm {
                    Label(String(format: "%.1f km", dist), systemImage: "map")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(.vertical, 4)
    }
    
    private func iconForActivity(_ type: String) -> String {
        switch type.lowercased() {
        case "running": return "figure.run"
        case "cycling": return "figure.outdoor.cycle"
        case "swimming": return "figure.pool.swim"
        case "yoga": return "figure.yoga"
        case "strength", "weights": return "dumbbell.fill"
        case "walking": return "figure.walk"
        default: return "figure.mixed.cardio"
        }
    }
}

struct AddFitnessSheet: View {
    @Bindable var vm: FitnessViewModel
    @Environment(\.dismiss) var dismiss
    
    @State private var activityType = "running"
    @State private var durationMinutes = ""
    @State private var caloriesBurned = ""
    @State private var distanceKm = ""
    @State private var notes = ""
    @State private var saving = false
    
    let activities = ["running", "walking", "cycling", "swimming", "yoga", "strength", "cardio"]
    
    var body: some View {
        NavigationStack {
            Form {
                Section("Activity") {
                    Picker("Type", selection: $activityType) {
                        ForEach(activities, id: \.self) { Text($0.capitalized) }
                    }
                    .pickerStyle(.menu)
                }
                Section("Details") {
                    LKNumberField(title: "Duration (min)", value: $durationMinutes)
                    LKNumberField(title: "Calories burned", value: $caloriesBurned)
                    LKNumberField(title: "Distance (km)", value: $distanceKm)
                }
                Section("Notes") {
                    TextField("Notes (optional)", text: $notes, axis: .vertical)
                        .lineLimit(3...6)
                }
            }
            .navigationTitle("Log Workout")
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
        let log = FitnessLogCreate(
            logDate: .todayISO(),
            activityType: activityType,
            durationMinutes: Int(durationMinutes),
            caloriesBurned: Double(caloriesBurned),
            notes: notes.isEmpty ? nil : notes
        )
        Task {
            if await vm.addLog(log) { dismiss() }
            saving = false
        }
    }
}
