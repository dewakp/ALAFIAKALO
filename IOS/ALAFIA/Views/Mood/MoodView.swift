import SwiftUI

@Observable
final class MoodViewModel {
    var entries: [MoodEntry] = []
    var isLoading = false
    var errorMessage: String?
    
    func fetchEntries() async {
        isLoading = true
        errorMessage = nil
        do {
            entries = try await APIClient.shared.get("/mood/")
            isLoading = false
        } catch {
            errorMessage = error.localizedDescription
            isLoading = false
        }
    }
    
    func addEntry(_ entry: MoodEntryCreate) async -> Bool {
        do {
            let _: MoodEntry = try await APIClient.shared.post("/mood/", body: entry)
            await fetchEntries()
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }
    
    func deleteEntry(id: Int) async {
        do {
            try await APIClient.shared.delete("/mood/\(id)")
            entries.removeAll { $0.id == id }
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct MoodView: View {
    @State private var vm = MoodViewModel()
    @State private var showAdd = false
    
    var body: some View {
        Group {
            if vm.isLoading {
                ProgressView()
            } else if vm.entries.isEmpty {
                EmptyStateView(icon: "brain", title: "No Mood Entries", message: "Tap + to log how you feel")
            } else {
                List {
                    ForEach(vm.entries) { entry in
                        MoodRow(entry: entry)
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
        .navigationTitle("Mood")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { showAdd = true } label: {
                    Image(systemName: "plus")
                }
            }
        }
        .sheet(isPresented: $showAdd) {
            AddMoodSheet(vm: vm)
        }
        .task { await vm.fetchEntries() }
    }
}

struct MoodRow: View {
    let entry: MoodEntry
    
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(entry.moodEmoji)
                    .font(.largeTitle)
                VStack(alignment: .leading) {
                    Text("Mood: \(entry.moodScore)/10")
                        .font(.headline)
                    if let anx = entry.anxietyLevel {
                        Text("Anxiety: \(anx)/10")
                            .font(.caption)
                            .foregroundStyle(.orange)
                    }
                }
                Spacer()
                if let sleep = entry.sleepQuality {
                    VStack {
                        Image(systemName: "moon.zzz.fill")
                            .foregroundStyle(.indigo)
                        Text("\(sleep)/10")
                            .font(.caption2)
                    }
                }
            }
            
            if let notes = entry.notes, !notes.isEmpty {
                Text(notes)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
        .padding(.vertical, 4)
    }
}

struct AddMoodSheet: View {
    @Bindable var vm: MoodViewModel
    @Environment(\.dismiss) var dismiss
    
    @State private var moodScore: Double = 5
    @State private var anxietyLevel: Double = 3
    @State private var stressLevel: Double = 3
    @State private var sleepQuality: Double = 5
    @State private var sleepHours = ""
    @State private var energyLevel: Double = 5
    @State private var notes = ""
    @State private var emotions = ""
    @State private var triggers = ""
    @State private var copingStrategies = ""
    @State private var saving = false
    @State private var moodRationale: String?
    @State private var scoringMood = false
    
    var moodEmoji: String {
        let s = Int(moodScore)
        switch s {
        case 0...2: return "😢"
        case 3...4: return "😟"
        case 5...6: return "😐"
        case 7...8: return "😊"
        default: return "🤩"
        }
    }
    
    var body: some View {
        NavigationStack {
            Form {
                Section {
                    VStack(spacing: 8) {
                        Text(moodEmoji)
                            .font(.system(size: 64))
                        Text("How are you feeling?")
                            .font(.headline)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 8)
                }
                
                Section("Mood, Anxiety & Stress") {
                    VStack(alignment: .leading) {
                        Text("Mood: \(Int(moodScore))/10")
                        Slider(value: $moodScore, in: 0...10, step: 1)
                            .tint(.green)
                            .onChange(of: moodScore) { _, _ in moodRationale = nil }
                        // Provenance: say where the number came from, always.
                        if let moodRationale {
                            Text(moodRationale)
                                .font(.caption2).foregroundStyle(.secondary)
                        }
                    }
                    VStack(alignment: .leading) {
                        Text("Anxiety: \(Int(anxietyLevel))/10")
                        Slider(value: $anxietyLevel, in: 0...10, step: 1)
                            .tint(.orange)
                    }
                    VStack(alignment: .leading) {
                        Text("Stress: \(Int(stressLevel))/10")
                        Slider(value: $stressLevel, in: 0...10, step: 1)
                            .tint(.red)
                    }
                }
                
                Section("Sleep & Energy") {
                    VStack(alignment: .leading) {
                        Text("Sleep Quality: \(Int(sleepQuality))/10")
                        Slider(value: $sleepQuality, in: 0...10, step: 1)
                            .tint(.indigo)
                    }
                    LKNumberField(title: "Sleep hours", value: $sleepHours)
                    VStack(alignment: .leading) {
                        Text("Energy: \(Int(energyLevel))/10")
                        Slider(value: $energyLevel, in: 0...10, step: 1)
                            .tint(.yellow)
                    }
                }
                
                Section("Journal") {
                    TextField("How's your day going?", text: $notes, axis: .vertical)
                        .lineLimit(4...8)
                    // Reads the entry and PROPOSES a score: it lands on the
                    // slider with its reason beside it and the user still
                    // presses Save, so a wrong read is visible, not silent
                    // (canon 3aj — inference proposes, it never writes).
                    if !notes.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        Button {
                            Task { await scoreFromNotes() }
                        } label: {
                            Text(scoringMood ? "Reading your entry…"
                                             : "Score this from what I wrote")
                                .font(.caption)
                        }
                        .disabled(scoringMood)
                    }
                }
                
                Section("Emotions & Coping") {
                    TextField("What emotions are you feeling?", text: $emotions, axis: .vertical)
                        .lineLimit(2...4)
                    TextField("Any triggers today?", text: $triggers, axis: .vertical)
                        .lineLimit(2...4)
                    TextField("Coping strategies used", text: $copingStrategies, axis: .vertical)
                        .lineLimit(2...4)
                }
            }
            .navigationTitle("Check In")
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
    
    /// Ask the backend to read the entry and propose a score for it.
    ///
    /// `available == false` means the model could not be reached or answered
    /// unusably. The slider then goes back to the user — an unreachable scorer
    /// must never become a number.
    private func scoreFromNotes() async {
        let text = notes.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !scoringMood else { return }
        scoringMood = true
        defer { scoringMood = false }
        do {
            let s: MoodScoreSuggestion = try await APIClient.shared.post(
                "/mood/suggest-score", body: MoodScoreRequest(notes: text))
            if s.available, let score = s.moodScore {
                moodScore = Double(score)
                if let energy = s.energyLevel { energyLevel = Double(energy) }
                moodRationale = "Read from what you wrote: \(score)/10"
                    + (s.rationale.isEmpty ? "" : " — \(s.rationale)")
            } else {
                moodRationale = s.rationale.isEmpty
                    ? "Scoring is unavailable — set the slider yourself."
                    : s.rationale
            }
        } catch {
            moodRationale = "Scoring is unavailable — set the slider yourself."
        }
    }

    private func save() {
        saving = true
        let entry = MoodEntryCreate(
            entryDate: .todayISO(),
            moodScore: Int(moodScore),
            energyLevel: Int(energyLevel),
            stressLevel: Int(stressLevel),
            anxietyLevel: Int(anxietyLevel),
            sleepQuality: Int(sleepQuality),
            sleepHours: Double(sleepHours),
            emotions: emotions.isEmpty ? nil : emotions,
            triggers: triggers.isEmpty ? nil : triggers,
            copingStrategies: copingStrategies.isEmpty ? nil : copingStrategies,
            journalEntry: notes.isEmpty ? nil : notes
        )
        Task {
            if await vm.addEntry(entry) { dismiss() }
            saving = false
        }
    }
}
