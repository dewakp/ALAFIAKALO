import SwiftUI
import Charts

// MARK: - ViewModel

@Observable
final class LabChartsViewModel {
    var groups: [LabChartGroup] = []
    var isLoading = false
    var errorMessage: String?

    func load() async {
        isLoading = true; errorMessage = nil
        do {
            groups = try await APIClient.shared.get("/lab-charts/groups")
        } catch { errorMessage = error.localizedDescription }
        isLoading = false
    }
}

// MARK: - Helpers

private let isoDateFormatter: DateFormatter = {
    let df = DateFormatter()
    df.dateFormat = "yyyy-MM-dd"
    df.locale = Locale(identifier: "en_US_POSIX")
    return df
}()

private let shortDateFormatter: DateFormatter = {
    let df = DateFormatter()
    df.dateFormat = "MMM d"
    return df
}()

// MARK: - Main View

struct LabChartsView: View {
    @State private var vm = LabChartsViewModel()

    var body: some View {
            Group {
                if vm.isLoading {
                    ProgressView("Loading lab charts…")
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if let error = vm.errorMessage {
                    ContentUnavailableView("Error", systemImage: "exclamationmark.triangle", description: Text(error))
                } else if vm.groups.isEmpty {
                    EmptyStateView(icon: "chart.xyaxis.line", title: "No Lab Charts", message: "Your lab results will appear here as charts once data is available.")
                } else {
                    chartsList
                }
            }
            .navigationTitle("Lab Charts")
            .task { await vm.load() }
            .refreshable { await vm.load() }
    }

    private var chartsList: some View {
        ScrollView {
            LazyVStack(spacing: 24) {
                ForEach(vm.groups, id: \.name) { group in
                    LabChartGroupSection(group: group)
                }
            }
            .padding()
        }
    }
}

// MARK: - Group Section

private struct LabChartGroupSection: View {
    let group: LabChartGroup

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(group.name)
                .font(.title3.bold())

            ForEach(group.series, id: \.testName) { series in
                LabChartCard(series: series)
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(16)
        .shadow(color: .black.opacity(0.04), radius: 8, y: 2)
    }
}

// MARK: - Chart Card

private struct LabChartCard: View {
    let series: LabChartSeries

    private var parsedPoints: [(date: Date, value: Double, refLow: Double?, refHigh: Double?)] {
        series.data.compactMap { point in
            guard let d = isoDateFormatter.date(from: String(point.date.prefix(10))) else { return nil }
            return (d, point.value, point.referenceLow, point.referenceHigh)
        }
        .sorted { $0.date < $1.date }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(series.testName)
                    .font(.headline)
                if let unit = series.unit, !unit.isEmpty {
                    Text("(\(unit))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            if parsedPoints.isEmpty {
                Text("No data points")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(height: 140, alignment: .center)
            } else {
                Chart {
                    // Reference range band
                    if let low = parsedPoints.first?.refLow, let high = parsedPoints.first?.refHigh {
                        RuleMark(y: .value("Ref Low", low))
                            .lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 4]))
                            .foregroundStyle(.green.opacity(0.5))
                            .annotation(position: .leading, alignment: .leading) {
                                Text("Low")
                                    .font(.system(size: 9))
                                    .foregroundStyle(.green)
                            }
                        RuleMark(y: .value("Ref High", high))
                            .lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 4]))
                            .foregroundStyle(.red.opacity(0.5))
                            .annotation(position: .leading, alignment: .leading) {
                                Text("High")
                                    .font(.system(size: 9))
                                    .foregroundStyle(.red)
                            }
                        RectangleMark(
                            yStart: .value("Ref Low", low),
                            yEnd: .value("Ref High", high)
                        )
                        .foregroundStyle(.green.opacity(0.06))
                    }

                    // Data line
                    ForEach(parsedPoints, id: \.date) { point in
                        LineMark(
                            x: .value("Date", point.date),
                            y: .value("Value", point.value)
                        )
                        .foregroundStyle(by: .value("Test", series.testName))
                        .interpolationMethod(.catmullRom)

                        PointMark(
                            x: .value("Date", point.date),
                            y: .value("Value", point.value)
                        )
                        .foregroundStyle(by: .value("Test", series.testName))
                    }
                }
                .chartXAxis {
                    AxisMarks(values: .automatic) { value in
                        AxisGridLine()
                        AxisValueLabel {
                            if let d = value.as(Date.self) {
                                Text(shortDateFormatter.string(from: d))
                                    .font(.caption2)
                            }
                        }
                    }
                }
                .chartYAxis {
                    AxisMarks(position: .leading)
                }
                .frame(height: 200)
            }
        }
        .padding(.vertical, 4)
    }
}

#Preview {
    LabChartsView()
}
