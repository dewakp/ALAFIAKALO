import SwiftUI
import Charts

// MARK: - Models

struct ChartDatasetInfo: Codable, Identifiable {
    var id: String { key }
    let key: String
    let label: String
    let unit: String
}

struct ChartDataPoint: Codable {
    let date: String
    let value: Double?
    let min: Double?
    let max: Double?
    let count: Int?
}

struct ChartDataSeries: Codable {
    let label: String
    let unit: String
    let domain: String
    let points: [ChartDataPoint]
}

struct ChartSummary: Codable {
    let key: String
    let label: String
    let unit: String
    let days: Int
    let avg: Double?
    let min: Double?
    let max: Double?
    let count: Int
    let stddev: Double?
    let trend: String
}

struct CorrelateAxis: Codable {
    let key: String
    let label: String
    let unit: String
}

struct CorrelatePoint: Codable {
    let date: String
    let x: Double
    let y: Double
}

struct CorrelateResponse: Codable {
    let x: CorrelateAxis
    let y: CorrelateAxis
    let points: [CorrelatePoint]
}

// MARK: - ViewModel

@Observable
final class ChartDashboardViewModel {
    var datasetsByDomain: [String: [ChartDatasetInfo]] = [:]
    var selectedKeys: [String] = []
    var chartData: [String: ChartDataSeries] = [:]
    var summaries: [String: ChartSummary] = [:]
    var correlateData: CorrelateResponse?
    var chartType: ChartType = .line
    var aggregation = "daily"
    var days = 90
    var isLoading = false
    var errorMessage: String?
    var showPicker = false

    enum ChartType: String, CaseIterable {
        case line, bar, area, point
        var label: String { rawValue.capitalized }
        var icon: String {
            switch self {
            case .line: return "chart.xyaxis.line"
            case .bar: return "chart.bar.fill"
            case .area: return "chart.line.uptrend.xyaxis.circle.fill"
            case .point: return "chart.dots.scatter"
            }
        }
    }

    func loadDatasets() async {
        do {
            let raw: [String: [ChartDatasetInfo]] = try await APIClient.shared.get("/chart-dashboard/datasets")
            datasetsByDomain = raw
        } catch { /* ignore */ }
    }

    func loadChartData() async {
        guard !selectedKeys.isEmpty else {
            chartData = [:]
            summaries = [:]
            correlateData = nil
            return
        }
        isLoading = true
        errorMessage = nil
        let keys = selectedKeys.joined(separator: ",")
        do {
            let data: [String: ChartDataSeries] = try await APIClient.shared.get(
                "/chart-dashboard/data?datasets=\(keys)&days=\(days)&aggregation=\(aggregation)"
            )
            chartData = data
        } catch {
            errorMessage = error.localizedDescription
        }

        // Load summaries
        for key in selectedKeys {
            do {
                let s: ChartSummary = try await APIClient.shared.get(
                    "/chart-dashboard/summary?dataset=\(key)&days=\(days)"
                )
                summaries[key] = s
            } catch { /* skip */ }
        }

        // Correlate if exactly 2
        if selectedKeys.count == 2 {
            do {
                let c: CorrelateResponse = try await APIClient.shared.get(
                    "/chart-dashboard/correlate?dataset_a=\(selectedKeys[0])&dataset_b=\(selectedKeys[1])&days=\(days)"
                )
                correlateData = c
            } catch { correlateData = nil }
        } else {
            correlateData = nil
        }

        isLoading = false
    }

    func toggle(_ key: String) {
        if selectedKeys.contains(key) {
            selectedKeys.removeAll { $0 == key }
        } else {
            selectedKeys.append(key)
        }
    }
}

// MARK: - Parsed Point

private struct ParsedPoint: Identifiable {
    let id = UUID()
    let date: Date
    let value: Double
    let series: String
}

private let isoFmt: DateFormatter = {
    let f = DateFormatter()
    f.dateFormat = "yyyy-MM-dd"
    f.locale = Locale(identifier: "en_US_POSIX")
    return f
}()

private let shortFmt: DateFormatter = {
    let f = DateFormatter()
    f.dateFormat = "MMM d"
    return f
}()

private let colors: [Color] = [.green, .blue, .orange, .red, .purple, .pink, .teal, .cyan, .mint, .indigo]

// MARK: - Main View

struct ChartDashboardView: View {
    @State private var vm = ChartDashboardViewModel()

    var body: some View {
            Group {
                if vm.isLoading {
                    ProgressView("Loading chart data…")
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if let err = vm.errorMessage {
                    ContentUnavailableView("Error", systemImage: "exclamationmark.triangle", description: Text(err))
                } else {
                    mainContent
                }
            }
            .navigationTitle("Chart Dashboard")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { vm.showPicker.toggle() } label: {
                        Image(systemName: "plus.circle")
                    }
                }
            }
            .sheet(isPresented: $vm.showPicker) {
                DatasetPickerSheet(vm: vm)
            }
            .task { await vm.loadDatasets() }
    }

    private var mainContent: some View {
        ScrollView {
            VStack(spacing: 16) {
                controlBar
                selectedTags
                if vm.selectedKeys.isEmpty {
                    emptyState
                } else {
                    chartCard
                    summaryCards
                }
            }
            .padding()
        }
    }

    // MARK: Controls

    private var controlBar: some View {
        VStack(spacing: 10) {
            // Chart type picker
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(ChartDashboardViewModel.ChartType.allCases, id: \.self) { ct in
                        Button {
                            vm.chartType = ct
                            Task { await vm.loadChartData() }
                        } label: {
                            Label(ct.label, systemImage: ct.icon)
                                .font(.caption.bold())
                                .padding(.horizontal, 12)
                                .padding(.vertical, 6)
                                .background(vm.chartType == ct ? Color.accentColor : Color(.systemGray5))
                                .foregroundStyle(vm.chartType == ct ? .white : .primary)
                                .clipShape(Capsule())
                        }
                    }
                }
            }

            HStack {
                // Aggregation
                Picker("Aggregation", selection: $vm.aggregation) {
                    Text("Daily").tag("daily")
                    Text("Weekly").tag("weekly")
                    Text("Monthly").tag("monthly")
                }
                .pickerStyle(.segmented)
                .onChange(of: vm.aggregation) { Task { await vm.loadChartData() } }

                // Days
                Picker("Range", selection: $vm.days) {
                    Text("30d").tag(30)
                    Text("90d").tag(90)
                    Text("6m").tag(180)
                    Text("1y").tag(365)
                }
                .pickerStyle(.segmented)
                .onChange(of: vm.days) { Task { await vm.loadChartData() } }
            }
        }
    }

    // MARK: Tags

    private var selectedTags: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(Array(vm.selectedKeys.enumerated()), id: \.element) { idx, key in
                    HStack(spacing: 4) {
                        Circle()
                            .fill(colors[idx % colors.count])
                            .frame(width: 8, height: 8)
                        Text(vm.chartData[key]?.label ?? key)
                            .font(.caption.bold())
                        Button {
                            vm.toggle(key)
                            Task { await vm.loadChartData() }
                        } label: {
                            Image(systemName: "xmark.circle.fill")
                                .font(.caption2)
                        }
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 4)
                    .background(colors[idx % colors.count].opacity(0.15))
                    .clipShape(Capsule())
                }
            }
        }
    }

    // MARK: Empty

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "chart.bar.xaxis")
                .font(.system(size: 48))
                .foregroundStyle(.secondary.opacity(0.4))
            Text("Select Datasets to Chart")
                .font(.headline)
            Text("Tap the + button to pick from Nutrition, Fitness, Mood, Vitals, and Lifestyle metrics.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding(40)
    }

    // MARK: Chart

    private var chartCard: some View {
        VStack(alignment: .leading) {
            let parsed = parsedPoints()
            if parsed.isEmpty {
                Text("No data for selected range")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(height: 250, alignment: .center)
            } else {
                chartView(for: parsed)
                    .frame(height: 280)
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(16)
        .shadow(color: .black.opacity(0.04), radius: 8, y: 2)
    }

    @ViewBuilder
    private func chartView(for points: [ParsedPoint]) -> some View {
        Chart {
            ForEach(points) { pt in
                switch vm.chartType {
                case .line:
                    LineMark(x: .value("Date", pt.date), y: .value("Value", pt.value))
                        .foregroundStyle(by: .value("Metric", pt.series))
                        .interpolationMethod(.catmullRom)
                case .bar:
                    BarMark(x: .value("Date", pt.date), y: .value("Value", pt.value))
                        .foregroundStyle(by: .value("Metric", pt.series))
                case .area:
                    AreaMark(x: .value("Date", pt.date), y: .value("Value", pt.value))
                        .foregroundStyle(by: .value("Metric", pt.series))
                        .interpolationMethod(.catmullRom)
                        .opacity(0.3)
                    LineMark(x: .value("Date", pt.date), y: .value("Value", pt.value))
                        .foregroundStyle(by: .value("Metric", pt.series))
                        .interpolationMethod(.catmullRom)
                case .point:
                    PointMark(x: .value("Date", pt.date), y: .value("Value", pt.value))
                        .foregroundStyle(by: .value("Metric", pt.series))
                }
            }
        }
        .chartForegroundStyleScale(range: vm.selectedKeys.enumerated().map { colors[$0.offset % colors.count] })
        .chartXAxis {
            AxisMarks(values: .automatic) { value in
                AxisGridLine()
                AxisValueLabel {
                    if let d = value.as(Date.self) {
                        Text(shortFmt.string(from: d)).font(.caption2)
                    }
                }
            }
        }
        .chartYAxis { AxisMarks(position: .leading) }
    }

    // MARK: Summary

    private var summaryCards: some View {
        ForEach(Array(vm.selectedKeys.enumerated()), id: \.element) { idx, key in
            if let s = vm.summaries[key] {
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Circle().fill(colors[idx % colors.count]).frame(width: 10, height: 10)
                        Text(s.label).font(.headline)
                        Text(s.unit).font(.caption).foregroundStyle(.secondary)
                        Spacer()
                        trendBadge(s.trend)
                    }
                    LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 3), spacing: 8) {
                        statCell("Avg", s.avg)
                        statCell("Min", s.min)
                        statCell("Max", s.max)
                        statCell("Std", s.stddev)
                        statCell("Count", Double(s.count))
                    }
                }
                .padding()
                .background(Color(.systemBackground))
                .cornerRadius(16)
                .shadow(color: .black.opacity(0.04), radius: 8, y: 2)
            }
        }
    }

    private func statCell(_ label: String, _ val: Double?) -> some View {
        VStack(spacing: 2) {
            Text(label).font(.caption2).foregroundStyle(.secondary)
            Text(val != nil ? String(format: "%.1f", val!) : "–")
                .font(.subheadline.bold())
        }
    }

    private func trendBadge(_ trend: String) -> some View {
        HStack(spacing: 2) {
            Image(systemName: trend == "increasing" ? "arrow.up.right" : trend == "decreasing" ? "arrow.down.right" : "minus")
                .font(.caption2)
            Text(trend.capitalized).font(.caption2)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 2)
        .background(trend == "increasing" ? Color.green.opacity(0.15) : trend == "decreasing" ? Color.red.opacity(0.15) : Color.gray.opacity(0.15))
        .foregroundStyle(trend == "increasing" ? .green : trend == "decreasing" ? .red : .gray)
        .clipShape(Capsule())
    }

    // MARK: Data Parsing

    private func parsedPoints() -> [ParsedPoint] {
        var result: [ParsedPoint] = []
        for key in vm.selectedKeys {
            guard let series = vm.chartData[key] else { continue }
            for pt in series.points {
                guard let v = pt.value,
                      let d = isoFmt.date(from: String(pt.date.prefix(10))) else { continue }
                result.append(ParsedPoint(date: d, value: v, series: series.label))
            }
        }
        return result.sorted { $0.date < $1.date }
    }
}

// MARK: - Dataset Picker Sheet

private struct DatasetPickerSheet: View {
    @Bindable var vm: ChartDashboardViewModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                ForEach(vm.datasetsByDomain.keys.sorted(), id: \.self) { domain in
                    Section(domain.capitalized) {
                        ForEach(vm.datasetsByDomain[domain] ?? [], id: \.key) { ds in
                            let active = vm.selectedKeys.contains(ds.key)
                            Button {
                                vm.toggle(ds.key)
                            } label: {
                                HStack {
                                    Text(ds.label)
                                    if !ds.unit.isEmpty {
                                        Text("(\(ds.unit))").font(.caption).foregroundStyle(.secondary)
                                    }
                                    Spacer()
                                    if active {
                                        Image(systemName: "checkmark.circle.fill")
                                            .foregroundStyle(.blue)
                                    }
                                }
                            }
                            .foregroundStyle(.primary)
                        }
                    }
                }
            }
            .navigationTitle("Select Datasets")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") {
                        dismiss()
                        Task { await vm.loadChartData() }
                    }
                }
            }
        }
    }
}

#Preview {
    ChartDashboardView()
}
