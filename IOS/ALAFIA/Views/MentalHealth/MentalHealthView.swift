import SwiftUI

// MARK: - ViewModel

@Observable
final class MentalHealthViewModel {
    var stats: MentalHealthStats?
    var exercises: [BreathingExerciseInfo] = []
    var gratitudes: [GratitudeEntry] = []
    var assessments: [MentalHealthAssessment] = []
    var isLoading = false
    var errorMessage: String?

    func loadAll() async {
        isLoading = true; errorMessage = nil
        do {
            async let s: MentalHealthStats = APIClient.shared.get("/mental-health/stats")
            async let e: [BreathingExerciseInfo] = APIClient.shared.get("/mental-health/breathing/exercises")
            async let g: [GratitudeEntry] = APIClient.shared.get("/mental-health/gratitude")
            async let a: [MentalHealthAssessment] = APIClient.shared.get("/mental-health/assessments")
            stats = try await s; exercises = try await e; gratitudes = try await g; assessments = try await a
        } catch { errorMessage = error.localizedDescription }
        isLoading = false
    }

    func submitAssessment(_ create: AssessmentCreate) async -> Bool {
        do {
            let _: MentalHealthAssessment = try await APIClient.shared.post("/mental-health/assessments", body: create)
            await loadAll(); return true
        } catch { errorMessage = error.localizedDescription; return false }
    }

    func saveBreathingSession(_ create: BreathingSessionCreate) async -> Bool {
        do {
            let _: BreathingSession = try await APIClient.shared.post("/mental-health/breathing/sessions", body: create)
            await loadAll(); return true
        } catch { errorMessage = error.localizedDescription; return false }
    }

    func saveGratitude(_ create: GratitudeCreate) async -> Bool {
        do {
            let _: GratitudeEntry = try await APIClient.shared.post("/mental-health/gratitude", body: create)
            await loadAll(); return true
        } catch { errorMessage = error.localizedDescription; return false }
    }

    func deleteAssessment(id: Int) async {
        do { try await APIClient.shared.delete("/mental-health/assessments/\(id)"); assessments.removeAll { $0.id == id } }
        catch { errorMessage = error.localizedDescription }
    }

    func deleteGratitude(id: Int) async {
        do { try await APIClient.shared.delete("/mental-health/gratitude/\(id)"); gratitudes.removeAll { $0.id == id } }
        catch { errorMessage = error.localizedDescription }
    }
}

// MARK: - Main View

struct MentalHealthView: View {
    @State private var vm = MentalHealthViewModel()
    @State private var selectedTab = 0

    var body: some View {
            VStack(spacing: 0) {
                Picker("Section", selection: $selectedTab) {
                    Text("Dashboard").tag(0)
                    Text("Breathing").tag(1)
                    Text("Gratitude").tag(2)
                    Text("Assessments").tag(3)
                }
                .pickerStyle(.segmented)
                .padding()

                if vm.isLoading {
                    Spacer()
                    ProgressView("Loading...")
                    Spacer()
                } else {
                    switch selectedTab {
                    case 0: DashboardSection(stats: vm.stats)
                    case 1: BreathingSection(exercises: vm.exercises, vm: vm)
                    case 2: GratitudeSection(entries: vm.gratitudes, vm: vm)
                    case 3: AssessmentSection(assessments: vm.assessments, vm: vm)
                    default: EmptyView()
                    }
                }
            }
            .navigationTitle("Mental Health")
            .task { await vm.loadAll() }
            .refreshable { await vm.loadAll() }
    }
}

// MARK: - Dashboard

struct DashboardSection: View {
    let stats: MentalHealthStats?

    var body: some View {
        ScrollView {
            if let s = stats {
                VStack(spacing: 20) {
                    // Wellness Score
                    VStack(spacing: 4) {
                        Text("\(s.wellnessScore ?? 0)")
                            .font(.system(size: 56, weight: .black))
                            .foregroundColor(wellnessColor(s.wellnessScore ?? 0))
                        Text("Wellness Score")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    .padding()

                    // Stats grid
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                        StatTile(label: "Mood (7d)", value: s.avgMood7d.map { String(format: "%.1f", $0) } ?? "—", icon: "face.smiling")
                        StatTile(label: "Trend", value: trendEmoji(s.moodTrend), icon: "chart.line.uptrend.xyaxis")
                        StatTile(label: "Streak", value: "\(s.streakDays)d 🔥", icon: "flame")
                        StatTile(label: "Stress", value: s.avgStress7d.map { String(format: "%.1f", $0) } ?? "—", icon: "bolt.heart")
                        StatTile(label: "Anxiety", value: s.avgAnxiety7d.map { String(format: "%.1f", $0) } ?? "—", icon: "waveform.path.ecg")
                        StatTile(label: "Sleep", value: s.avgSleepHours7d.map { String(format: "%.1fh", $0) } ?? "—", icon: "moon.zzz")
                        StatTile(label: "Entries (30d)", value: "\(s.totalEntries30d)", icon: "pencil.and.list.clipboard")
                        StatTile(label: "Breathing", value: "\(s.totalBreathingMinutes30d)m", icon: "lungs")
                        StatTile(label: "Sleep Quality", value: s.avgSleepQuality7d.map { String(format: "%.1f", $0) } ?? "—", icon: "bed.double")
                    }
                    .padding(.horizontal)

                    // Clinical Summary
                    if s.latestPhq9Score != nil || s.latestGad7Score != nil || s.latestWho5Score != nil {
                        VStack(alignment: .leading, spacing: 8) {
                            Label("Clinical Assessments", systemImage: "clipboard")
                                .font(.headline)
                            if let phq = s.latestPhq9Score {
                                HStack {
                                    Text("PHQ-9 (Depression):")
                                    Spacer()
                                    Text("\(phq)/27")
                                    SeverityBadge(severity: s.latestPhq9Severity)
                                }
                            }
                            if let gad = s.latestGad7Score {
                                HStack {
                                    Text("GAD-7 (Anxiety):")
                                    Spacer()
                                    Text("\(gad)/21")
                                    SeverityBadge(severity: s.latestGad7Severity)
                                }
                            }
                            if let who = s.latestWho5Score {
                                HStack {
                                    Text("WHO-5 Well-Being:")
                                    Spacer()
                                    Text("\(who)%")
                                }
                            }
                        }
                        .padding()
                        .background(RoundedRectangle(cornerRadius: 12).fill(.ultraThinMaterial))
                        .padding(.horizontal)
                    }
                }
                .padding(.bottom, 40)
            } else {
                ContentUnavailableView("No Data Yet", systemImage: "brain.head.profile",
                    description: Text("Start by logging your mood or trying a breathing exercise"))
            }
        }
    }

    func wellnessColor(_ score: Int) -> Color {
        score >= 70 ? .green : score >= 40 ? .orange : .red
    }

    func trendEmoji(_ trend: String?) -> String {
        switch trend {
        case "improving": return "📈"
        case "declining": return "📉"
        default: return "➡️"
        }
    }
}

struct StatTile: View {
    let label: String
    let value: String
    let icon: String

    var body: some View {
        VStack(spacing: 4) {
            Image(systemName: icon)
                .foregroundStyle(.green)
            Text(value)
                .font(.headline)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity)
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 10).fill(.ultraThinMaterial))
    }
}

struct SeverityBadge: View {
    let severity: String?

    var body: some View {
        if let s = severity {
            Text(s.replacingOccurrences(of: "_", with: " ").capitalized)
                .font(.caption2)
                .fontWeight(.semibold)
                .padding(.horizontal, 8)
                .padding(.vertical, 2)
                .background(Capsule().fill(severityColor(s)))
                .foregroundStyle(.white)
        }
    }

    func severityColor(_ s: String) -> Color {
        switch s {
        case "minimal": return .green
        case "mild": return .yellow
        case "moderate": return .orange
        case "moderately_severe", "severe": return .red
        case "good": return .green
        case "low", "very_low": return .red
        default: return .gray
        }
    }
}

// MARK: - Breathing Exercises

struct BreathingSection: View {
    let exercises: [BreathingExerciseInfo]
    let vm: MentalHealthViewModel
    @State private var activeExercise: BreathingExerciseInfo?

    var body: some View {
        ScrollView {
            LazyVStack(spacing: 16) {
                ForEach(exercises) { ex in
                    VStack(alignment: .leading, spacing: 8) {
                        Text(ex.name).font(.headline)
                        Text(ex.description).font(.caption).foregroundStyle(.secondary)
                        HStack {
                            Text("\(ex.inhaleSeconds)s in → \(ex.holdSeconds)s hold → \(ex.exhaleSeconds)s out")
                                .font(.caption2).foregroundStyle(.secondary)
                            if ex.holdAfterExhaleSeconds > 0 {
                                Text("→ \(ex.holdAfterExhaleSeconds)s hold")
                                    .font(.caption2).foregroundStyle(.secondary)
                            }
                        }
                        FlowLayout(spacing: 4) {
                            ForEach(ex.benefits, id: \.self) { b in
                                Text(b)
                                    .font(.caption2)
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 2)
                                    .background(Capsule().fill(.green.opacity(0.15)))
                                    .foregroundStyle(.green)
                            }
                        }
                        Button("Start Exercise") { activeExercise = ex }
                            .buttonStyle(.borderedProminent)
                            .tint(.green)
                    }
                    .padding()
                    .background(RoundedRectangle(cornerRadius: 12).fill(.ultraThinMaterial))
                }
            }
            .padding()
        }
        .sheet(item: $activeExercise) { ex in
            BreathingTimerSheet(exercise: ex, vm: vm)
        }
    }
}

// Simple flow layout for benefit tags
struct FlowLayout: Layout {
    var spacing: CGFloat = 4

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? 300
        var currentX: CGFloat = 0; var currentY: CGFloat = 0; var maxHeight: CGFloat = 0

        for sv in subviews {
            let size = sv.sizeThatFits(.unspecified)
            if currentX + size.width > width {
                currentX = 0; currentY += maxHeight + spacing; maxHeight = 0
            }
            currentX += size.width + spacing
            maxHeight = max(maxHeight, size.height)
        }
        return CGSize(width: width, height: currentY + maxHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var currentX = bounds.minX; var currentY = bounds.minY; var maxHeight: CGFloat = 0

        for sv in subviews {
            let size = sv.sizeThatFits(.unspecified)
            if currentX + size.width > bounds.maxX {
                currentX = bounds.minX; currentY += maxHeight + spacing; maxHeight = 0
            }
            sv.place(at: CGPoint(x: currentX, y: currentY), proposal: ProposedViewSize(size))
            currentX += size.width + spacing
            maxHeight = max(maxHeight, size.height)
        }
    }
}

struct BreathingTimerSheet: View {
    let exercise: BreathingExerciseInfo
    let vm: MentalHealthViewModel
    @Environment(\.dismiss) var dismiss
    @State private var phase = "inhale"
    @State private var timer = 0
    @State private var cycle = 1
    @State private var running = false
    @State private var done = false
    @State private var moodBefore = 5.0
    @State private var moodAfter = 5.0
    @State private var startDate = Date()

    let phaseColors: [String: Color] = ["inhale": .green, "hold": .blue, "exhale": .orange, "hold2": .purple]
    let phaseLabels: [String: String] = ["inhale": "Breathe In", "hold": "Hold", "exhale": "Breathe Out", "hold2": "Hold"]

    var body: some View {
        NavigationStack {
            VStack(spacing: 24) {
                if done {
                    doneView
                } else if running {
                    timerView
                } else {
                    startView
                }
            }
            .padding()
            .navigationTitle(exercise.name)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Close") { dismiss() } } }
        }
    }

    var startView: some View {
        VStack(spacing: 20) {
            Image(systemName: "lungs.fill")
                .font(.system(size: 60))
                .foregroundStyle(.green)
            Text("Rate your mood before starting")
                .font(.headline)
            HStack {
                Text("😢")
                Slider(value: $moodBefore, in: 1...10, step: 1)
                Text("😄")
            }
            Text("\(Int(moodBefore))/10").font(.title2).fontWeight(.bold)
            Button("Begin") {
                running = true; startDate = Date(); timer = exercise.inhaleSeconds; phase = "inhale"; cycle = 1
            }
            .buttonStyle(.borderedProminent).tint(.green).controlSize(.large)
        }
    }

    var timerView: some View {
        VStack(spacing: 24) {
            Text(phaseLabels[phase] ?? phase)
                .font(.title).fontWeight(.semibold)
            Text("\(timer)")
                .font(.system(size: 80, weight: .black, design: .rounded))
                .foregroundColor(phaseColors[phase] ?? .primary)
                .contentTransition(.numericText())
                .animation(.default, value: timer)
            Text("Cycle \(cycle) of \(exercise.recommendedCycles)")
                .foregroundStyle(.secondary)
            Button("Stop") { running = false }
                .buttonStyle(.bordered)
        }
        .onAppear { startTimer() }
    }

    var doneView: some View {
        VStack(spacing: 20) {
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 60))
                .foregroundStyle(.green)
            Text("Session Complete!").font(.title2).fontWeight(.bold)
            Text("How do you feel now?").font(.headline)
            HStack {
                Text("😢")
                Slider(value: $moodAfter, in: 1...10, step: 1)
                Text("😄")
            }
            Text("\(Int(moodAfter))/10").font(.title2).fontWeight(.bold)
            Button("Save Session") {
                Task {
                    let duration = Int(Date().timeIntervalSince(startDate))
                    let df = DateFormatter(); df.dateFormat = "yyyy-MM-dd"
                    let create = BreathingSessionCreate(
                        sessionDate: df.string(from: Date()),
                        exerciseType: exercise.id,
                        durationSeconds: duration,
                        moodBefore: Int(moodBefore),
                        moodAfter: Int(moodAfter)
                    )
                    _ = await vm.saveBreathingSession(create)
                    dismiss()
                }
            }
            .buttonStyle(.borderedProminent).tint(.green).controlSize(.large)
        }
    }

    func startTimer() {
        Task {
            while running {
                try? await Task.sleep(for: .seconds(1))
                guard running else { break }
                timer -= 1
                if timer <= 0 { advancePhase() }
            }
        }
    }

    func advancePhase() {
        switch phase {
        case "inhale":
            if exercise.holdSeconds > 0 { phase = "hold"; timer = exercise.holdSeconds }
            else { phase = "exhale"; timer = exercise.exhaleSeconds }
        case "hold":
            phase = "exhale"; timer = exercise.exhaleSeconds
        case "exhale":
            if exercise.holdAfterExhaleSeconds > 0 { phase = "hold2"; timer = exercise.holdAfterExhaleSeconds }
            else { nextCycle() }
        case "hold2":
            nextCycle()
        default: break
        }
    }

    func nextCycle() {
        if cycle >= exercise.recommendedCycles { running = false; done = true }
        else { cycle += 1; phase = "inhale"; timer = exercise.inhaleSeconds }
    }
}

// MARK: - Gratitude Journal

struct GratitudeSection: View {
    let entries: [GratitudeEntry]
    let vm: MentalHealthViewModel
    @State private var showAdd = false

    var body: some View {
        Group {
            if entries.isEmpty {
                ContentUnavailableView("No Gratitude Entries", systemImage: "heart.text.clipboard",
                    description: Text("Tap + to write what you're grateful for"))
            } else {
                List {
                    ForEach(entries) { e in
                        VStack(alignment: .leading, spacing: 6) {
                            Text(e.entryDate).font(.caption).foregroundStyle(.secondary)
                            Text("1. \(e.item1)")
                            if let i2 = e.item2, !i2.isEmpty { Text("2. \(i2)") }
                            if let i3 = e.item3, !i3.isEmpty { Text("3. \(i3)") }
                            if let r = e.reflection, !r.isEmpty {
                                Text(r).font(.caption).italic().foregroundStyle(.secondary)
                            }
                        }
                        .padding(.vertical, 4)
                    }
                    .onDelete { indexSet in
                        Task { for i in indexSet { await vm.deleteGratitude(id: entries[i].id) } }
                    }
                }
            }
        }
        .toolbar { ToolbarItem(placement: .primaryAction) { Button { showAdd = true } label: { Image(systemName: "plus") } } }
        .sheet(isPresented: $showAdd) { AddGratitudeSheet(vm: vm, isPresented: $showAdd) }
    }
}

struct AddGratitudeSheet: View {
    let vm: MentalHealthViewModel
    @Binding var isPresented: Bool
    @State private var item1 = ""
    @State private var item2 = ""
    @State private var item3 = ""
    @State private var reflection = ""
    @State private var saving = false

    var body: some View {
        NavigationStack {
            Form {
                Section("What are you grateful for today?") {
                    TextField("1. I'm grateful for...", text: $item1)
                    TextField("2. I'm grateful for...", text: $item2)
                    TextField("3. I'm grateful for...", text: $item3)
                }
                Section("Reflection (optional)") {
                    TextEditor(text: $reflection)
                        .frame(height: 80)
                }
            }
            .navigationTitle("Gratitude Entry")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { isPresented = false } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        saving = true
                        Task {
                            let df = DateFormatter(); df.dateFormat = "yyyy-MM-dd"
                            let create = GratitudeCreate(
                                entryDate: df.string(from: Date()),
                                item1: item1,
                                item2: item2.isEmpty ? nil : item2,
                                item3: item3.isEmpty ? nil : item3,
                                reflection: reflection.isEmpty ? nil : reflection
                            )
                            if await vm.saveGratitude(create) { isPresented = false }
                            saving = false
                        }
                    }
                    .disabled(item1.isEmpty || saving)
                }
            }
        }
    }
}

// MARK: - Assessments

struct AssessmentSection: View {
    let assessments: [MentalHealthAssessment]
    let vm: MentalHealthViewModel
    @State private var showAdd = false

    var body: some View {
        Group {
            if assessments.isEmpty {
                ContentUnavailableView("No Assessments", systemImage: "clipboard",
                    description: Text("Tap + to take a PHQ-9, GAD-7, or WHO-5 assessment"))
            } else {
                List {
                    ForEach(assessments) { a in
                        HStack {
                            VStack(alignment: .leading) {
                                Text(a.assessmentType.uppercased()).font(.headline)
                                Text(a.assessmentDate).font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                            if let score = a.totalScore { Text("\(score)").font(.title2).fontWeight(.bold) }
                            SeverityBadge(severity: a.severity)
                        }
                    }
                    .onDelete { indexSet in
                        Task { for i in indexSet { await vm.deleteAssessment(id: assessments[i].id) } }
                    }
                }
            }
        }
        .toolbar { ToolbarItem(placement: .primaryAction) { Button { showAdd = true } label: { Image(systemName: "plus") } } }
        .sheet(isPresented: $showAdd) { AddAssessmentSheet(vm: vm, isPresented: $showAdd) }
    }
}

struct AddAssessmentSheet: View {
    let vm: MentalHealthViewModel
    @Binding var isPresented: Bool
    @State private var type = "phq9"
    @State private var answers: [String: Int] = [:]
    @State private var saving = false

    struct Question: Identifiable {
        let id: String // key
        let text: String
    }

    let phq9 = [
        Question(id: "phq_interest", text: "Little interest or pleasure in doing things"),
        Question(id: "phq_feeling_down", text: "Feeling down, depressed, or hopeless"),
        Question(id: "phq_sleep", text: "Trouble falling/staying asleep, or sleeping too much"),
        Question(id: "phq_energy", text: "Feeling tired or having little energy"),
        Question(id: "phq_appetite", text: "Poor appetite or overeating"),
        Question(id: "phq_self_esteem", text: "Feeling bad about yourself"),
        Question(id: "phq_concentration", text: "Trouble concentrating"),
        Question(id: "phq_psychomotor", text: "Moving or speaking slowly / being fidgety"),
        Question(id: "phq_suicidal_ideation", text: "Thoughts of self-harm"),
    ]
    let gad7 = [
        Question(id: "gad_nervous", text: "Feeling nervous, anxious, or on edge"),
        Question(id: "gad_uncontrollable_worry", text: "Not being able to stop worrying"),
        Question(id: "gad_excessive_worry", text: "Worrying too much about different things"),
        Question(id: "gad_trouble_relaxing", text: "Trouble relaxing"),
        Question(id: "gad_restless", text: "Being so restless it's hard to sit still"),
        Question(id: "gad_irritable", text: "Becoming easily annoyed or irritable"),
        Question(id: "gad_afraid", text: "Feeling afraid something awful might happen"),
    ]
    let who5 = [
        Question(id: "who5_cheerful", text: "I have felt cheerful and in good spirits"),
        Question(id: "who5_calm", text: "I have felt calm and relaxed"),
        Question(id: "who5_active", text: "I have felt active and vigorous"),
        Question(id: "who5_rested", text: "I woke up feeling fresh and rested"),
        Question(id: "who5_interesting", text: "My daily life has been filled with things that interest me"),
    ]

    var questions: [Question] {
        switch type {
        case "phq9": return phq9
        case "gad7": return gad7
        case "who5": return who5
        default: return []
        }
    }

    var maxVal: Int { type == "who5" ? 5 : 3 }
    var labels03: [String] { ["Not at all", "Several days", "More than half", "Nearly every day"] }
    var labels05: [String] { ["At no time", "Some of the time", "Less than half", "More than half", "Most of the time", "All of the time"] }
    var labels: [String] { type == "who5" ? labels05 : labels03 }

    var body: some View {
        NavigationStack {
            Form {
                Section("Assessment Type") {
                    Picker("Type", selection: $type) {
                        Text("PHQ-9 (Depression)").tag("phq9")
                        Text("GAD-7 (Anxiety)").tag("gad7")
                        Text("WHO-5 (Well-Being)").tag("who5")
                    }
                    .pickerStyle(.segmented)
                    .onChange(of: type) { _, _ in answers = [:] }
                }

                Section("Over the last 2 weeks…") {
                    ForEach(Array(questions.enumerated()), id: \.element.id) { i, q in
                        VStack(alignment: .leading, spacing: 8) {
                            Text("\(i + 1). \(q.text)").font(.subheadline)
                            ForEach(0...maxVal, id: \.self) { v in
                                Button {
                                    answers[q.id] = v
                                } label: {
                                    HStack {
                                        Image(systemName: answers[q.id] == v ? "largecircle.fill.circle" : "circle")
                                        Text("\(labels[v]) (\(v))")
                                            .font(.caption)
                                    }
                                    .foregroundStyle(answers[q.id] == v ? .green : .primary)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                        .padding(.vertical, 4)
                    }
                }
            }
            .navigationTitle("Assessment")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { isPresented = false } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Submit") {
                        saving = true
                        Task {
                            let df = DateFormatter(); df.dateFormat = "yyyy-MM-dd"
                            var create = AssessmentCreate(assessmentDate: df.string(from: Date()), assessmentType: type)
                            // Map answers to create fields
                            create.phqInterest = answers["phq_interest"]
                            create.phqFeelingDown = answers["phq_feeling_down"]
                            create.phqSleep = answers["phq_sleep"]
                            create.phqEnergy = answers["phq_energy"]
                            create.phqAppetite = answers["phq_appetite"]
                            create.phqSelfEsteem = answers["phq_self_esteem"]
                            create.phqConcentration = answers["phq_concentration"]
                            create.phqPsychomotor = answers["phq_psychomotor"]
                            create.phqSuicidalIdeation = answers["phq_suicidal_ideation"]
                            create.gadNervous = answers["gad_nervous"]
                            create.gadUncontrollableWorry = answers["gad_uncontrollable_worry"]
                            create.gadExcessiveWorry = answers["gad_excessive_worry"]
                            create.gadTroubleRelaxing = answers["gad_trouble_relaxing"]
                            create.gadRestless = answers["gad_restless"]
                            create.gadIrritable = answers["gad_irritable"]
                            create.gadAfraid = answers["gad_afraid"]
                            create.who5Cheerful = answers["who5_cheerful"]
                            create.who5Calm = answers["who5_calm"]
                            create.who5Active = answers["who5_active"]
                            create.who5Rested = answers["who5_rested"]
                            create.who5Interesting = answers["who5_interesting"]
                            if await vm.submitAssessment(create) { isPresented = false }
                            saving = false
                        }
                    }
                    .disabled(saving || answers.count < questions.count)
                }
            }
        }
    }
}
