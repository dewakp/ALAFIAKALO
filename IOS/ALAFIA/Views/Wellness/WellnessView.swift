import SwiftUI
import Charts

// MARK: - ViewModel

@Observable
final class WellnessViewModel {
    var score: WellnessScore?
    var trends: HealthTrendResponse?
    var recommendations: [RecommendationItem] = []
    var improvements: HealthImprovementsResponse?
    var isLoading = false
    var errorMessage: String?

    func loadScore() async {
        isLoading = true; errorMessage = nil
        do { score = try await APIClient.shared.get("/wellness/score") }
        catch { errorMessage = error.localizedDescription }
        isLoading = false
    }

    func loadTrends() async {
        isLoading = true; errorMessage = nil
        do { trends = try await APIClient.shared.get("/wellness/trends?days=90") }
        catch { errorMessage = error.localizedDescription }
        isLoading = false
    }

    func loadRecommendations() async {
        isLoading = true; errorMessage = nil
        do {
            let resp: DailyRecommendationsResponse = try await APIClient.shared.get("/wellness/recommendations")
            recommendations = resp.recommendations
        }
        catch { errorMessage = error.localizedDescription }
        isLoading = false
    }

    func loadImprovements() async {
        isLoading = true; errorMessage = nil
        do { improvements = try await APIClient.shared.get("/wellness/improvements") }
        catch { errorMessage = error.localizedDescription }
        isLoading = false
    }

    var omegaData: HEBCSScoreResponse?
    var whatIfResult: WhatIfResponse?

    func loadOmega() async {
        isLoading = true; errorMessage = nil
        do { omegaData = try await APIClient.shared.get("/wellness/omega") }
        catch { errorMessage = error.localizedDescription }
        isLoading = false
    }

    func runWhatIf(_ request: WhatIfRequest) async {
        isLoading = true; errorMessage = nil
        do { whatIfResult = try await APIClient.shared.post("/wellness/whatif", body: request) }
        catch { errorMessage = error.localizedDescription }
        isLoading = false
    }
}

// MARK: - Date Helper

private let trendDateFormatter: DateFormatter = {
    let df = DateFormatter()
    df.dateFormat = "yyyy-MM-dd"
    df.locale = Locale(identifier: "en_US_POSIX")
    return df
}()

// MARK: - Main View

struct WellnessView: View {
    @State private var vm = WellnessViewModel()
    @State private var selectedTab = 0

    var body: some View {
            VStack(spacing: 0) {
                Picker("Section", selection: $selectedTab) {
                    Text("Score").tag(0)
                    Text("Trends").tag(1)
                    Text("HEBCS Ω").tag(2)
                    Text("Recs").tag(3)
                    Text("Improve").tag(4)
                }
                .pickerStyle(.segmented)
                .padding()

                if vm.isLoading {
                    Spacer()
                    ProgressView("Loading…")
                    Spacer()
                } else {
                    switch selectedTab {
                    case 0: ScoreSection(score: vm.score)
                    case 1: TrendsSection(response: vm.trends)
                    case 2: HEBCSSection(vm: vm)
                    case 3: RecommendationsSection(items: vm.recommendations)
                    case 4: ImprovementsSection(data: vm.improvements)
                    default: EmptyView()
                    }
                }
            }
            .navigationTitle("Wellness")
            .task { await loadForTab() }
            .onChange(of: selectedTab) { _, _ in
                Task { await loadForTab() }
            }
            .refreshable { await loadForTab() }
    }

    private func loadForTab() async {
        switch selectedTab {
        case 0: await vm.loadScore()
        case 1: await vm.loadTrends()
        case 2: await vm.loadOmega()
        case 3: await vm.loadRecommendations()
        case 4: await vm.loadImprovements()
        default: break
        }
    }
}

// MARK: - Score Section

private struct ScoreSection: View {
    let score: WellnessScore?

    var body: some View {
        ScrollView {
            if let s = score {
                VStack(spacing: 24) {
                    // Overall Score
                    VStack(spacing: 4) {
                        Text("\(Int(s.overallScore))")
                            .font(.system(size: 72, weight: .black))
                            .foregroundStyle(scoreColor(s.overallScore))
                        Text("Overall Wellness Score")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.top, 12)

                    // Sub-scores
                    VStack(spacing: 14) {
                        SubScoreBar(label: "Nutrition", value: s.nutritionScore, icon: "leaf.fill")
                        SubScoreBar(label: "Fitness", value: s.fitnessScore, icon: "figure.run")
                        SubScoreBar(label: "Sleep", value: s.sleepScore, icon: "moon.fill")
                        SubScoreBar(label: "Mood", value: s.moodScore, icon: "face.smiling.fill")
                        SubScoreBar(label: "Vitals", value: s.vitalsScore, icon: "heart.fill")
                        SubScoreBar(label: "Medication Adherence", value: s.medicationAdherenceScore, icon: "pills.fill")
                    }
                    .padding()
                    .background(Color(.systemBackground))
                    .cornerRadius(16)
                    .shadow(color: .black.opacity(0.04), radius: 8, y: 2)

                    // Explanation
                    if let explanation = s.explanation, !explanation.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Label("Explanation", systemImage: "info.circle.fill")
                                .font(.headline)
                            Text(explanation)
                                .font(.body)
                                .foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding()
                        .background(Color(.systemBackground))
                        .cornerRadius(16)
                        .shadow(color: .black.opacity(0.04), radius: 8, y: 2)
                    }

                    // Recommendations text
                    if let recs = s.recommendations, !recs.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Label("Recommendations", systemImage: "lightbulb.fill")
                                .font(.headline)
                            Text(recs)
                                .font(.body)
                                .foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding()
                        .background(Color(.systemBackground))
                        .cornerRadius(16)
                        .shadow(color: .black.opacity(0.04), radius: 8, y: 2)
                    }
                }
                .padding()
            } else {
                EmptyStateView(icon: "gauge.with.dots.needle.67percent", title: "No Score", message: "Your wellness score will appear here once calculated.")
            }
        }
    }

    private func scoreColor(_ value: Double) -> Color {
        if value > 70 { return .green }
        if value > 40 { return .yellow }
        return .red
    }
}

// MARK: - Sub-Score Bar

private struct SubScoreBar: View {
    let label: String
    let value: Double
    let icon: String

    private var color: Color {
        if value > 70 { return .green }
        if value > 40 { return .orange }
        return .red
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Image(systemName: icon)
                    .foregroundStyle(color)
                    .frame(width: 20)
                Text(label)
                    .font(.subheadline)
                Spacer()
                Text("\(Int(value))")
                    .font(.subheadline.bold())
                    .foregroundStyle(color)
            }
            ProgressView(value: value, total: 100)
                .tint(color)
        }
    }
}

// MARK: - Trends Section

private struct TrendsSection: View {
    let response: HealthTrendResponse?

    var body: some View {
        ScrollView {
            if let resp = response {
                VStack(spacing: 16) {
                    if let summary = resp.overallSummary, !summary.isEmpty {
                        Text(summary)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding()
                            .background(Color(.systemBackground))
                            .cornerRadius(12)
                    }

                    ForEach(resp.streams, id: \.name) { stream in
                        TrendChartCard(stream: stream)
                    }

                    if let suggestions = resp.suggestions, !suggestions.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Label("Suggestions", systemImage: "lightbulb.fill")
                                .font(.headline)
                            ForEach(suggestions, id: \.self) { s in
                                HStack(alignment: .top, spacing: 8) {
                                    Image(systemName: "arrow.right.circle.fill")
                                        .foregroundStyle(.blue)
                                        .font(.caption)
                                        .padding(.top, 2)
                                    Text(s)
                                        .font(.subheadline)
                                }
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding()
                        .background(Color(.systemBackground))
                        .cornerRadius(16)
                        .shadow(color: .black.opacity(0.04), radius: 8, y: 2)
                    }
                }
                .padding()
            } else {
                EmptyStateView(icon: "chart.line.uptrend.xyaxis", title: "No Trends", message: "Health trends will appear here after tracking data for a few days.")
            }
        }
    }
}

// MARK: - Trend Chart Card

private struct TrendChartCard: View {
    let stream: TrendStream

    private var parsedPoints: [(date: Date, value: Double)] {
        stream.data.compactMap { pt in
            guard let d = trendDateFormatter.date(from: String(pt.date.prefix(10))) else { return nil }
            return (d, pt.value)
        }
        .sorted { $0.date < $1.date }
    }

    private var trendBadge: (String, Color) {
        switch stream.trend?.lowercased() {
        case "improving", "up": return ("↑ Improving", .green)
        case "declining", "down": return ("↓ Declining", .red)
        case "stable": return ("→ Stable", .blue)
        default: return ("—", .secondary)
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(stream.name)
                    .font(.headline)
                Spacer()
                Text(trendBadge.0)
                    .font(.caption.bold())
                    .padding(.horizontal, 10)
                    .padding(.vertical, 4)
                    .background(trendBadge.1.opacity(0.15))
                    .foregroundStyle(trendBadge.1)
                    .cornerRadius(8)
            }

            if parsedPoints.isEmpty {
                Text("No data points")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(height: 120)
            } else {
                Chart {
                    ForEach(parsedPoints, id: \.date) { pt in
                        LineMark(
                            x: .value("Date", pt.date),
                            y: .value("Value", pt.value)
                        )
                        .interpolationMethod(.catmullRom)
                        .foregroundStyle(trendBadge.1)

                        AreaMark(
                            x: .value("Date", pt.date),
                            y: .value("Value", pt.value)
                        )
                        .interpolationMethod(.catmullRom)
                        .foregroundStyle(trendBadge.1.opacity(0.1))
                    }
                }
                .frame(height: 160)
                .chartXAxis {
                    AxisMarks(values: .automatic) { value in
                        AxisGridLine()
                        AxisValueLabel {
                            if let d = value.as(Date.self) {
                                Text(d, format: .dateTime.month(.abbreviated).day())
                                    .font(.caption2)
                            }
                        }
                    }
                }
                .chartYAxis {
                    AxisMarks(position: .leading)
                }
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(16)
        .shadow(color: .black.opacity(0.04), radius: 8, y: 2)
    }
}

// MARK: - Recommendations Section

private struct RecommendationsSection: View {
    let items: [RecommendationItem]

    private var grouped: [(String, [RecommendationItem])] {
        Dictionary(grouping: items, by: \.category)
            .sorted { $0.key < $1.key }
    }

    var body: some View {
        ScrollView {
            if items.isEmpty {
                EmptyStateView(icon: "lightbulb", title: "No Recommendations", message: "Personalized health recommendations will appear here.")
            } else {
                LazyVStack(spacing: 16) {
                    ForEach(grouped, id: \.0) { category, recs in
                        VStack(alignment: .leading, spacing: 10) {
                            Text(category.capitalized)
                                .font(.title3.bold())

                            ForEach(recs, id: \.title) { rec in
                                RecommendationCard(item: rec)
                            }
                        }
                    }
                }
                .padding()
            }
        }
    }
}

// MARK: - Recommendation Card

private struct RecommendationCard: View {
    let item: RecommendationItem

    private var priorityBadge: (String, Color) {
        switch item.priority.lowercased() {
        case "high": return ("High", .red)
        case "medium": return ("Medium", .orange)
        case "low": return ("Low", .green)
        default: return (item.priority, .secondary)
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(item.title)
                    .font(.subheadline.bold())
                Spacer()
                Text(priorityBadge.0)
                    .font(.caption2.bold())
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3)
                    .background(priorityBadge.1.opacity(0.15))
                    .foregroundStyle(priorityBadge.1)
                    .cornerRadius(6)
            }

            Text(item.description)
                .font(.caption)
                .foregroundStyle(.secondary)

            if let action = item.action, !action.isEmpty {
                HStack(spacing: 4) {
                    Image(systemName: "arrow.right.circle.fill")
                        .font(.caption)
                    Text(action)
                        .font(.caption.bold())
                }
                .foregroundStyle(.blue)
            }
        }
        .padding()
        .background(Color(.secondarySystemBackground))
        .cornerRadius(12)
    }
}

// MARK: - Improvements Section

private struct ImprovementsSection: View {
    let data: HealthImprovementsResponse?

    var body: some View {
        ScrollView {
            if let d = data {
                VStack(spacing: 16) {
                    if let summary = d.summary, !summary.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Label("Summary", systemImage: "text.alignleft")
                                .font(.headline)
                            Text(summary)
                                .font(.body)
                                .foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding()
                        .background(Color(.systemBackground))
                        .cornerRadius(16)
                        .shadow(color: .black.opacity(0.04), radius: 8, y: 2)
                    }

                    if let ws = d.wellnessScore {
                        HStack {
                            Text("Current Score")
                                .font(.subheadline)
                            Spacer()
                            Text("\(Int(ws))")
                                .font(.title2.bold())
                                .foregroundStyle(ws > 70 ? .green : ws > 40 ? .orange : .red)
                        }
                        .padding()
                        .background(Color(.systemBackground))
                        .cornerRadius(12)
                    }

                    ImprovementList(title: "Nutrition", icon: "leaf.fill", color: .green, items: d.nutritionImprovements)
                    ImprovementList(title: "Fitness", icon: "figure.run", color: .blue, items: d.fitnessImprovements)
                    ImprovementList(title: "Sleep", icon: "moon.fill", color: .indigo, items: d.sleepImprovements)
                    ImprovementList(title: "Mood", icon: "face.smiling.fill", color: .yellow, items: d.moodImprovements)
                    ImprovementList(title: "Medical", icon: "stethoscope", color: .red, items: d.medicalImprovements)
                }
                .padding()
            } else {
                EmptyStateView(icon: "arrow.up.right.circle", title: "No Improvements", message: "Health improvement suggestions will appear here.")
            }
        }
    }
}

// MARK: - Improvement List

private struct ImprovementList: View {
    let title: String
    let icon: String
    let color: Color
    let items: [String]?

    var body: some View {
        if let items, !items.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                Label(title, systemImage: icon)
                    .font(.headline)
                    .foregroundStyle(color)

                ForEach(items, id: \.self) { item in
                    HStack(alignment: .top, spacing: 8) {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundStyle(color)
                            .font(.caption)
                            .padding(.top, 2)
                        Text(item)
                            .font(.subheadline)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding()
            .background(Color(.systemBackground))
            .cornerRadius(16)
            .shadow(color: .black.opacity(0.04), radius: 8, y: 2)
        }
    }
}

// MARK: - HEBCS Ω Section

private let pathwayColors: [String: Color] = [
    "Metabolic": Color(red: 0.06, green: 0.72, blue: 0.51),
    "Hematologic": .red,
    "Bone_Mineral": .orange,
    "Cardiovascular": Color(red: 0.23, green: 0.51, blue: 0.96),
    "Nutritional": Color(red: 0.54, green: 0.36, blue: 0.96),
    "Dialysis_Adequacy": Color(red: 0.02, green: 0.71, blue: 0.80),
    "Inflammatory": .pink,
]

private let whatIfParams: [(field: WritableKeyPath<WhatIfRequest, Double?>, label: String, unit: String, min: Double, max: Double, step: Double)] = [
    (\.Phosphorus,           "Phosphorus",     "mg/dL", 1.5,  9.0,  0.1),
    (\.Potassium,            "Potassium",      "mEq/L", 2.5,  7.0,  0.1),
    (\.Albumin,              "Albumin",        "g/dL",  1.5,  5.5,  0.1),
    (\.Hemoglobin,           "Hemoglobin",     "g/dL",  6.0,  18.0, 0.1),
    (\.Ferritin,             "Ferritin",       "\u{00b5}g/L", 10, 2000, 10),
    (\.KtV_Dialysis_Adequacy,"KtV",            "",      0.5,  2.5,  0.05),
    (\.PTH_Intact,           "PTH",            "pg/mL", 15,   2000, 10),
    (\.Calcium,              "Calcium",        "mg/dL", 6.5,  12.0, 0.1),
]

private struct HEBCSSection: View {
    @Bindable var vm: WellnessViewModel
    @State private var request = WhatIfRequest()
    @State private var enabled: [String: Bool] = [:]
    @State private var showWhatIf = false
    @State private var isRunning = false

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                if let d = vm.omegaData {
                    // Ω Gauge card
                    VStack(spacing: 8) {
                        ZStack {
                            Circle()
                                .stroke(Color.gray.opacity(0.15), lineWidth: 14)
                            Circle()
                                .trim(from: 0, to: d.omega)
                                .stroke(omegaColor(d.omega), style: StrokeStyle(lineWidth: 14, lineCap: .round))
                                .rotationEffect(.degrees(-90))
                                .animation(.easeInOut(duration: 0.8), value: d.omega)
                        }
                        .frame(width: 160, height: 160)
                        .overlay {
                            VStack(spacing: 2) {
                                Text(String(format: "Ω %.3f", d.omega))
                                    .font(.system(size: 26, weight: .black))
                                    .foregroundStyle(omegaColor(d.omega))
                                Text(omegaLabel(d.omega))
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }

                        HStack(spacing: 24) {
                            VStack {
                                Text(String(format: "%.0f%%", d.omegaPct))
                                    .font(.title2).bold().foregroundStyle(.blue)
                                Text("Score 0–100")
                                    .font(.caption2).foregroundStyle(.secondary)
                            }
                            VStack {
                                Text(String(format: "%.0f%%", d.dataCoverage * 100))
                                    .font(.title2).bold()
                                    .foregroundStyle(d.dataCoverage >= 0.6 ? .green : .orange)
                                Text("Data coverage")
                                    .font(.caption2).foregroundStyle(.secondary)
                            }
                        }

                        if let lab = d.labDateUsed {
                            Text("Latest labs: \(lab)")
                                .font(.caption2).foregroundStyle(.tertiary)
                        }
                    }
                    .padding()
                    .background(Color(.systemBackground))
                    .cornerRadius(20)
                    .shadow(color: .black.opacity(0.05), radius: 8, y: 2)

                    // Interpretation
                    if let interp = d.interpretation {
                        HStack {
                            Image(systemName: "checkmark.seal.fill").foregroundStyle(.green)
                            Text(interp).font(.callout).foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding()
                        .background(Color.green.opacity(0.07))
                        .cornerRadius(12)
                    }

                    // Pathway breakdown
                    VStack(alignment: .leading, spacing: 12) {
                        Label("Pathway Breakdown", systemImage: "waveform.path.ecg")
                            .font(.headline)
                        ForEach(Array(d.pathways.keys.sorted()), id: \.self) { name in
                            if let pw = d.pathways[name] {
                                PathwayBarRow(name: name, score: pw.score, weight: pw.weight)
                            }
                        }
                    }
                    .padding()
                    .background(Color(.systemBackground))
                    .cornerRadius(16)
                    .shadow(color: .black.opacity(0.04), radius: 6, y: 2)

                    // What-If simulator
                    VStack(alignment: .leading, spacing: 12) {
                        Button {
                            withAnimation { showWhatIf.toggle() }
                        } label: {
                            HStack {
                                Label("What-If Simulator", systemImage: "slider.horizontal.3")
                                    .font(.headline)
                                Spacer()
                                Image(systemName: showWhatIf ? "chevron.up" : "chevron.down")
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .buttonStyle(.plain)

                        if showWhatIf {
                            Text("Enable sliders to override biomarkers, then run simulation.")
                                .font(.caption).foregroundStyle(.secondary)

                            ForEach(whatIfParams.indices, id: \.self) { i in
                                let p = whatIfParams[i]
                                let key = p.label
                                let isOn = enabled[key] ?? false
                                let currentVal = request[keyPath: p.field] ?? (p.min + p.max) / 2

                                VStack(alignment: .leading, spacing: 4) {
                                    HStack {
                                        Toggle("", isOn: Binding(
                                            get: { enabled[key] ?? false },
                                            set: { enabled[key] = $0 }
                                        ))
                                        .labelsHidden()
                                        .scaleEffect(0.85)
                                        Text("\(p.label) \(p.unit)")
                                            .font(.subheadline)
                                            .foregroundStyle(isOn ? .primary : .secondary)
                                        Spacer()
                                        if isOn {
                                            Text(String(format: p.step < 1 ? "%.1f" : "%.0f", currentVal))
                                                .font(.subheadline).bold()
                                                .foregroundStyle(pathwayColors.values.randomElement() ?? .blue)
                                        }
                                    }
                                    if isOn {
                                        Slider(
                                            value: Binding(
                                                get: { request[keyPath: p.field] ?? (p.min + p.max) / 2 },
                                                set: { request[keyPath: p.field] = $0 }
                                            ),
                                            in: p.min...p.max,
                                            step: p.step
                                        )
                                    }
                                }
                                .opacity(isOn ? 1 : 0.5)
                            }

                            let activeCount = enabled.values.filter { $0 }.count
                            Button {
                                Task {
                                    isRunning = true
                                    var req = request
                                    // zero out disabled fields
                                    for p in whatIfParams {
                                        if !(enabled[p.label] ?? false) {
                                            req[keyPath: p.field] = nil
                                        }
                                    }
                                    await vm.runWhatIf(req)
                                    isRunning = false
                                }
                            } label: {
                                HStack {
                                    if isRunning {
                                        ProgressView().scaleEffect(0.8)
                                    } else {
                                        Image(systemName: "play.circle.fill")
                                    }
                                    Text(isRunning ? "Simulating…" : "Run What-If" + (activeCount > 0 ? " (\(activeCount))": ""))
                                }
                                .frame(maxWidth: .infinity)
                            }
                            .buttonStyle(.borderedProminent)
                            .disabled(activeCount == 0 || isRunning)

                            // What-If result
                            if let res = vm.whatIfResult {
                                WhatIfResultView(result: res)
                            }
                        }
                    }
                    .padding()
                    .background(Color(.systemBackground))
                    .cornerRadius(16)
                    .shadow(color: .black.opacity(0.04), radius: 6, y: 2)

                } else {
                    Text(vm.errorMessage ?? "Loading HEBCS Ω…")
                        .foregroundStyle(.secondary)
                        .padding(.top, 40)
                }
            }
            .padding()
        }
    }

    private func omegaColor(_ v: Double) -> Color {
        v >= 0.65 ? .green : v >= 0.45 ? .orange : .red
    }
    private func omegaLabel(_ v: Double) -> String {
        v >= 0.65 ? "Good" : v >= 0.45 ? "Moderate" : "Critical"
    }
}

private struct PathwayBarRow: View {
    let name: String
    let score: Double?
    let weight: Double

    private var pct: Double { (score ?? 0) * 100 }
    private var color: Color { pathwayColors[name] ?? .gray }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(name.replacingOccurrences(of: "_", with: " "))
                    .font(.subheadline).fontWeight(.medium)
                Text("w=\(weight, format: .number.precision(.fractionLength(2)))")
                    .font(.caption2).foregroundStyle(.secondary)
                Spacer()
                Text(score != nil ? String(format: "%.0f%%", pct) : "N/A")
                    .font(.subheadline).bold().foregroundStyle(score != nil ? color : .secondary)
            }
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 4).fill(Color.gray.opacity(0.12)).frame(height: 8)
                    if score != nil {
                        RoundedRectangle(cornerRadius: 4)
                            .fill(color)
                            .frame(width: geo.size.width * CGFloat(pct / 100), height: 8)
                            .animation(.easeInOut(duration: 0.6), value: pct)
                    }
                }
            }
            .frame(height: 8)
        }
    }
}

private struct WhatIfResultView: View {
    let result: WhatIfResponse

    private var deltaColor: Color {
        result.deltaOmega > 0.001 ? .green : result.deltaOmega < -0.001 ? .red : .secondary
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 0) {
                ResultMetric(label: "Baseline Ω", value: String(format: "%.3f", result.baselineOmega), color: .secondary)
                Spacer()
                ResultMetric(label: "Scenario Ω", value: String(format: "%.3f", result.scenarioOmega), color: deltaColor)
                Spacer()
                ResultMetric(
                    label: "Change",
                    value: String(format: "%+.1fpp", result.deltaPct),
                    color: deltaColor
                )
            }
            .padding()
            .background(Color(.secondarySystemBackground))
            .cornerRadius(12)

            ForEach(Array(result.pathwayDeltas.keys.sorted()), id: \.self) { name in
                if let d = result.pathwayDeltas[name], let delta = d.delta {
                    PathwayDeltaRow(name: name, delta: delta, baseline: d.baselineScore, scenario: d.scenarioScore)
                }
            }

            Text(result.interpretation)
                .font(.callout).italic().foregroundStyle(.secondary)
        }
        .padding()
        .background(Color(.secondarySystemBackground))
        .cornerRadius(12)
    }
}

private struct ResultMetric: View {
    let label: String; let value: String; let color: Color
    var body: some View {
        VStack(spacing: 2) {
            Text(value).font(.title3).bold().foregroundStyle(color)
            Text(label).font(.caption2).foregroundStyle(.secondary)
        }
    }
}

private struct PathwayDeltaRow: View {
    let name: String; let delta: Double; let baseline: Double?; let scenario: Double?
    private var color: Color { delta > 0.005 ? .green : delta < -0.005 ? .red : .secondary }
    var body: some View {
        HStack {
            Circle().fill(pathwayColors[name] ?? .gray).frame(width: 10, height: 10)
            Text(name.replacingOccurrences(of: "_", with: " ")).font(.caption).frame(maxWidth: .infinity, alignment: .leading)
            if let b = baseline { Text(String(format: "%.0f%%", b * 100)).font(.caption2).foregroundStyle(.secondary) }
            Image(systemName: delta > 0.005 ? "arrow.up.right" : delta < -0.005 ? "arrow.down.right" : "minus")
                .font(.caption2).foregroundStyle(color)
            if let s = scenario { Text(String(format: "%.0f%%", s * 100)).font(.caption2).foregroundStyle(.secondary) }
            Text(String(format: "%+.1fpp", delta * 100)).font(.caption).bold().foregroundStyle(color).frame(minWidth: 48, alignment: .trailing)
        }
        .padding(.horizontal, 8).padding(.vertical, 4)
        .background(Color(.secondarySystemBackground)).cornerRadius(8)
    }
}

#Preview {
    WellnessView()
}
