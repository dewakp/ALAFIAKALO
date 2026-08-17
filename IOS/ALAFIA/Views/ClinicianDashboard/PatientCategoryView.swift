import Charts
import SwiftUI

/// Trends and full records for one shared category.
///
/// Series that share a unit share a plot; different units get their own. There
/// is never a second y-axis — two scales on one plot let the chart say whatever
/// the axis ranges were set to. Above six series (labs, typically dozens) each
/// measure gets its own small multiple and the clinician picks which to show:
/// a seventh series would have to reuse a hue, and identity by colour would be
/// gone.
struct PatientCategoryView: View {
    let patientId: Int
    let categoryKey: String
    let categoryLabel: String

    @State private var data: PatientCategoryResponse?
    @State private var error: String?
    @State private var days = 90
    @State private var picked: Set<String> = []

    private static let maxSeriesPerChart = 6
    /// Mirrors the patient's own period control. "All" was 1825 days, which on
    /// the reference record returned 1048 of 2005 sessions — history starts
    /// 2013-05-21 — so "All" showed half the chart and said nothing.
    private static let windows: [(Int, String)] = [(30, "30 days"), (90, "90 days"),
                                                   (180, "180 days"), (365, "1 year"),
                                                   (36500, "All")]

    /// Validated categorical palette — the same six slots, in the same fixed
    /// order, as the web charts. Assigned by index and never cycled.
    private static let palette: [Color] = [
        Color(red: 0.16, green: 0.47, blue: 0.84),   // #2a78d6
        Color(red: 0.92, green: 0.41, blue: 0.20),   // #eb6834
        Color(red: 0.11, green: 0.69, blue: 0.48),   // #1baf7a
        Color(red: 0.93, green: 0.63, blue: 0.00),   // #eda100
        Color(red: 0.91, green: 0.48, blue: 0.64),   // #e87ba4
        Color(red: 0.00, green: 0.51, blue: 0.00),   // #008300
    ]

    private var manySeries: Bool { (data?.series.count ?? 0) > Self.maxSeriesPerChart }

    /// Series grouped into plots: by unit normally, one-per-plot when there are
    /// too many to colour apart.
    private var groups: [(unit: String, series: [TrendSeries])] {
        guard let series = data?.series, !series.isEmpty else { return [] }
        if manySeries {
            return series.filter { picked.contains($0.label) }
                .map { (unit: $0.unit ?? "", series: [$0]) }
        }
        var order: [String] = []
        var byUnit: [String: [TrendSeries]] = [:]
        for s in series {
            let u = s.unit ?? ""
            if byUnit[u] == nil { order.append(u) }
            byUnit[u, default: []].append(s)
        }
        return order.flatMap { u -> [(unit: String, series: [TrendSeries])] in
            stride(from: 0, to: byUnit[u]!.count, by: Self.maxSeriesPerChart).map {
                (unit: u, series: Array(byUnit[u]![$0..<min($0 + Self.maxSeriesPerChart,
                                                            byUnit[u]!.count)]))
            }
        }
    }

    var body: some View {
        Group {
            if let error {
                ContentUnavailableView("Unavailable", systemImage: "lock.shield",
                                       description: Text(error))
            } else if let data {
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        windowPicker
                        if manySeries { seriesPicker(data) }
                        // Cards above the plots: the finding first, the line as
                        // its evidence.
                        ForEach(data.cards ?? []) { detailCard($0) }
                        ForEach(Array(groups.enumerated()), id: \.offset) { _, g in
                            chartCard(g)
                        }
                        if groups.isEmpty {
                            Text("No trend to plot for this period — the records are below.")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        // A dialysis session is a document a clinician opens,
                        // reads a curve from and signs — not a table row.
                        if categoryKey == "dialysis" {
                            TherapyReportView(patientId: patientId, rows: data.rows, days: days)
                        } else {
                            recordsTable(data)
                        }
                    }
                    .padding(12)
                }
            } else {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .navigationTitle(categoryLabel)
        .navigationBarTitleDisplayMode(.inline)
        .task(id: days) { await load() }
    }

    private func detailCard(_ card: BoardDetailCard) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(card.label).font(.subheadline.bold())
            ForEach(Array(card.items.enumerated()), id: \.offset) { _, item in
                HStack(alignment: .firstTextBaseline) {
                    Text(item.label).font(.caption).foregroundStyle(.secondary)
                    Spacer(minLength: 8)
                    Text((item.danger == true ? "⚠ " : "") + item.valueWithUnit)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(item.danger == true ? .red : .primary)
                }
                if let note = item.note, !note.isEmpty {
                    Text(note).font(.caption2).foregroundStyle(.secondary)
                }
            }
            if let note = card.note, !note.isEmpty {
                Text(note).font(.caption2).foregroundStyle(.secondary)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemGroupedBackground))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private var windowPicker: some View {
        Picker("Period", selection: $days) {
            ForEach(Self.windows, id: \.0) { Text($0.1).tag($0.0) }
        }
        .pickerStyle(.segmented)
    }

    private func seriesPicker(_ data: PatientCategoryResponse) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("\(data.series.count) measures have enough history to trend — pick the ones to plot:")
                .font(.caption2).foregroundStyle(.secondary)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    ForEach(data.series) { s in
                        let on = picked.contains(s.label)
                        Button {
                            if on { picked.remove(s.label) } else { picked.insert(s.label) }
                        } label: {
                            Text(s.label)
                                .font(.caption2)
                                .padding(.horizontal, 10).padding(.vertical, 4)
                                .background(on ? Color.accentColor : Color(.tertiarySystemFill))
                                .foregroundStyle(on ? .white : .secondary)
                                .clipShape(Capsule())
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
    }

    /// The y-range for a plot.
    ///
    /// Swift Charts includes zero by default, which is right for a count or a
    /// volume and wrong for a bounded measure: pre/post dialysis weights of
    /// 71.8-75.2 kg were drawn on a 0-80 axis, squashed into the top 5% of the
    /// plot and reading as flat — when the ~2.5 kg interdialytic gain is exactly
    /// what the chart exists to show.
    ///
    /// A group shares a unit, so if ANY member needs a fitted axis the whole
    /// plot gets one; mixing the two on one axis misrepresents whichever lost.
    private static func yDomain(for series: [TrendSeries]) -> ClosedRange<Double> {
        let values = series.flatMap { $0.points.compactMap(\.value) }
        guard let lo = values.min(), let hi = values.max() else { return 0...1 }
        let zeroBased = series.allSatisfy { $0.zeroBaseline ?? true }
        if zeroBased { return 0...(hi > 0 ? hi * 1.05 : 1) }
        // A flat series still needs a visible band, or it collapses to a line
        // on the axis and the reader cannot tell stable from missing.
        let span = hi - lo
        let pad = span > 0 ? span * 0.15 : max(abs(hi) * 0.05, 1)
        return (lo - pad)...(hi + pad)
    }

    private func chartCard(_ g: (unit: String, series: [TrendSeries])) -> some View {
        let single = g.series.count == 1
        let unitSuffix = g.unit.isEmpty ? "" : " (\(g.unit))"
        let title = single
            ? "\(g.series[0].label)\(unitSuffix)"
            : g.series.map(\.label).joined(separator: " · ") + unitSuffix

        return VStack(alignment: .leading, spacing: 8) {
            // The title names the measure, so a single series needs no legend.
            Text(title).font(.footnote).fontWeight(.semibold)
            Chart {
                ForEach(Array(g.series.enumerated()), id: \.element.id) { idx, s in
                    ForEach(s.points, id: \.date) { p in
                        if let v = p.value, let d = Self.parse(p.date) {
                            LineMark(x: .value("Date", d), y: .value(s.label, v))
                                .foregroundStyle(by: .value("Series", s.label))
                                .lineStyle(StrokeStyle(lineWidth: 2))
                            PointMark(x: .value("Date", d), y: .value(s.label, v))
                                .foregroundStyle(by: .value("Series", s.label))
                                .symbolSize(60)
                        }
                    }
                    .foregroundStyle(Self.palette[idx % Self.palette.count])
                }
            }
            .chartForegroundStyleScale(range: Array(Self.palette.prefix(max(g.series.count, 1))))
            .chartLegend(single ? .hidden : .visible)
            .chartYScale(domain: Self.yDomain(for: g.series))
            .frame(height: 200)
        }
        .padding(12)
        .background(Color(.secondarySystemGroupedBackground))
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }

    private func recordsTable(_ data: PatientCategoryResponse) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            if data.rows.isEmpty {
                Text("No \(data.label.lowercased()) records in this period.")
                    .font(.caption).foregroundStyle(.secondary).padding(12)
            } else {
                ForEach(Array(data.rows.enumerated()), id: \.offset) { _, row in
                    let danger = row["danger"]?.flag == true
                    VStack(alignment: .leading, spacing: 3) {
                        ForEach(data.columns) { col in
                            if let v = row[col.key]?.display, !v.isEmpty {
                                HStack(alignment: .firstTextBaseline) {
                                    Text(col.label).font(.caption2).foregroundStyle(.secondary)
                                    Spacer(minLength: 8)
                                    Text(v).font(.caption).multilineTextAlignment(.trailing)
                                }
                            }
                        }
                    }
                    .foregroundStyle(danger ? Color.red : Color.primary)
                    .padding(.vertical, 8).padding(.horizontal, 12)
                    Divider()
                }
            }
        }
        .background(Color(.secondarySystemGroupedBackground))
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }

    private static func parse(_ s: String) -> Date? {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        f.timeZone = TimeZone(identifier: "UTC")
        return f.date(from: String(s.prefix(10)))
    }

    private func load() async {
        do {
            let r: PatientCategoryResponse = try await APIClient.shared.get(
                "/clinician-dashboard/patient/\(patientId)/category/\(categoryKey)?days=\(days)")
            data = r
            if r.series.count > Self.maxSeriesPerChart, picked.isEmpty {
                // Backend sorts by point count, so this defaults to the measures
                // with the most history — the ones that actually trend.
                picked = Set(r.series.prefix(4).map(\.label))
            }
        } catch {
            self.error = error.localizedDescription.contains("403")
                ? "This patient has not shared \(categoryLabel.lowercased())."
                : "Could not load this category."
        }
    }
}
