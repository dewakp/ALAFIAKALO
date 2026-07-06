import SwiftUI
import Charts

// MARK: - ViewModel

@Observable
final class WeightTrendViewModel {
    var days = 90
    var data: WeightSeriesResponse?
    var isLoading = false
    var errorMessage: String?

    func load() async {
        isLoading = true; errorMessage = nil
        do {
            data = try await APIClient.shared.get(
                "/chart-dashboard/weight-series?days=\(days)&aggregation=daily"
            )
        } catch { errorMessage = error.localizedDescription }
        isLoading = false
    }
}

// MARK: - Main View

/// Composite weight trend — unifies weight recorded anywhere in the app
/// (vitals, meals, elimination, dialysis therapy, labs, lifestyle, fitness)
/// with a 7-day rolling average and the profile target-weight goal line.
struct WeightTrendView: View {
    @State private var vm = WeightTrendViewModel()

    private static let dayOptions = [30, 90, 180, 365]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Picker("Range", selection: $vm.days) {
                    ForEach(Self.dayOptions, id: \.self) { d in
                        Text(d >= 365 ? "1 year" : "\(d) days").tag(d)
                    }
                }
                .pickerStyle(.segmented)
                .onChange(of: vm.days) { Task { await vm.load() } }

                if vm.isLoading {
                    ProgressView("Loading weight data…")
                        .frame(maxWidth: .infinity, minHeight: 200)
                } else if let error = vm.errorMessage {
                    ContentUnavailableView("Error", systemImage: "exclamationmark.triangle",
                                           description: Text(error))
                } else if let data = vm.data, !data.points.isEmpty {
                    chart(data)
                    summaryCard(data.summary)
                    sourcesCard(data.summary)
                } else {
                    EmptyStateView(icon: "scalemass", title: "No Weight Data",
                                   message: "Log weight in Vitals, Meals, Elimination or Therapy to see the trend.")
                }
            }
            .padding()
        }
        .navigationTitle("Weight Trend")
        .task { await vm.load() }
    }

    // MARK: Chart

    private func chart(_ data: WeightSeriesResponse) -> some View {
        let target = data.summary.profileTargetWeightKg
        let values = data.points.map(\.value) + [target].compactMap { $0 }
        let lower = Swift.min(40, (values.min() ?? 45) - 5)
        let upper = (values.max() ?? 100) * 1.03

        return Chart {
            ForEach(data.points) { p in
                LineMark(
                    x: .value("Date", p.date),
                    y: .value("Weight", p.value),
                    series: .value("Series", "Daily mean")
                )
                .foregroundStyle(.green)
                .interpolationMethod(.monotone)

                LineMark(
                    x: .value("Date", p.date),
                    y: .value("Weight", p.rolling7d),
                    series: .value("Series", "7-day average")
                )
                .foregroundStyle(.blue)
                .interpolationMethod(.monotone)
            }
            if let target {
                RuleMark(y: .value("Target", target))
                    .foregroundStyle(.red)
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [6, 3]))
                    .annotation(position: .top, alignment: .leading) {
                        Text("Target \(target, specifier: "%.1f") kg")
                            .font(.caption2).foregroundStyle(.red)
                    }
            }
        }
        .chartYScale(domain: lower...upper)
        .chartXAxis {
            AxisMarks(values: .automatic(desiredCount: 5)) { _ in
                AxisGridLine(); AxisValueLabel()
            }
        }
        .frame(height: 280)
    }

    // MARK: Summary

    private func summaryCard(_ s: WeightSeriesSummary) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Statistics").font(.headline)
            Grid(alignment: .leading, horizontalSpacing: 24, verticalSpacing: 6) {
                GridRow {
                    stat("Average", s.avg, "kg")
                    stat("Std Dev", s.stddev, "kg")
                }
                GridRow {
                    stat("Min", s.min, "kg")
                    stat("Max", s.max, "kg")
                }
                GridRow {
                    VStack(alignment: .leading) {
                        Text("Points").font(.caption).foregroundStyle(.secondary)
                        Text("\(s.count)").font(.subheadline.bold())
                    }
                    VStack(alignment: .leading) {
                        Text("Trend").font(.caption).foregroundStyle(.secondary)
                        Text(s.trend.capitalized).font(.subheadline.bold())
                    }
                }
                if let dry = s.dryWeightKg {
                    GridRow {
                        stat("Dry Weight", dry, "kg")
                        stat("Target", s.profileTargetWeightKg, "kg")
                    }
                }
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.systemGray6))
        .cornerRadius(12)
    }

    private func stat(_ label: String, _ value: Double?, _ unit: String) -> some View {
        VStack(alignment: .leading) {
            Text(label).font(.caption).foregroundStyle(.secondary)
            Text(value.map { String(format: "%.1f %@", $0, unit) } ?? "–")
                .font(.subheadline.bold())
        }
    }

    private func sourcesCard(_ s: WeightSeriesSummary) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Data Sources").font(.headline)
            ForEach(s.sources.sorted { $0.value > $1.value }, id: \.key) { source, count in
                HStack {
                    Text(source.capitalized).font(.subheadline)
                    Spacer()
                    Text("\(count)").font(.subheadline.monospacedDigit()).foregroundStyle(.secondary)
                }
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.systemGray6))
        .cornerRadius(12)
    }
}
