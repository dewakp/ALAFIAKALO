import SwiftUI

// MARK: - ViewModel

@Observable
final class FDARecallsViewModel {
    var searchTerm = ""
    var days: Int = 90
    var limit: Int = 10
    var kind: String = "both"        // food | drug | both
    var results: [FDARecallItem] = []
    var totalResults: Int = 0
    var isLoading = false
    var errorMessage: String?
    var hasSearched = false

    func search() async {
        guard !searchTerm.trimmingCharacters(in: .whitespaces).isEmpty else { return }
        isLoading = true; errorMessage = nil; hasSearched = true
        do {
            let encoded = searchTerm.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? searchTerm
            let response: FDARecallResponse = try await APIClient.shared.get(
                "/fda-recalls/?search_term=\(encoded)&days=\(days)&limit=\(limit)&kind=\(kind)"
            )
            results = response.results
            totalResults = response.total
        } catch { errorMessage = error.localizedDescription }
        isLoading = false
    }

    func loadRecent() async {
        isLoading = true; errorMessage = nil; hasSearched = true
        do {
            let response: FDARecallResponse = try await APIClient.shared.get("/fda-recalls/recent?kind=\(kind)")
            results = response.results
            totalResults = response.total
        } catch { errorMessage = error.localizedDescription }
        isLoading = false
    }
}

// MARK: - Main View

struct FDARecallsView: View {
    @State private var vm = FDARecallsViewModel()

    var body: some View {
            VStack(spacing: 0) {
                searchForm
                Divider()
                resultsContent
            }
            .navigationTitle("FDA Recalls")
    }

    // MARK: - Search Form

    private var searchForm: some View {
        VStack(spacing: 12) {
            HStack {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(.secondary)
                TextField("Search food recalls…", text: $vm.searchTerm)
                    .textFieldStyle(.plain)
                    .autocapitalization(.none)
                    .onSubmit { Task { await vm.search() } }
            }
            .padding(10)
            .background(Color(.systemGray6))
            .cornerRadius(10)

            Picker("Type", selection: $vm.kind) {
                Text("Food & Drug").tag("both")
                Text("Food").tag("food")
                Text("Drug").tag("drug")
            }
            .pickerStyle(.segmented)

            HStack {
                Stepper("Days: \(vm.days)", value: $vm.days, in: 1...365)
                    .font(.caption)
            }
            HStack {
                Stepper("Limit: \(vm.limit)", value: $vm.limit, in: 1...100)
                    .font(.caption)
            }

            HStack(spacing: 12) {
                Button {
                    Task { await vm.search() }
                } label: {
                    Label("Search", systemImage: "magnifyingglass")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .disabled(vm.searchTerm.trimmingCharacters(in: .whitespaces).isEmpty || vm.isLoading)

                Button {
                    Task { await vm.loadRecent() }
                } label: {
                    Label("Recent", systemImage: "clock")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .disabled(vm.isLoading)
            }
        }
        .padding()
    }

    // MARK: - Results

    @ViewBuilder
    private var resultsContent: some View {
        if vm.isLoading {
            ProgressView("Searching…")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let error = vm.errorMessage {
            ContentUnavailableView("Error", systemImage: "exclamationmark.triangle", description: Text(error))
        } else if vm.hasSearched && vm.results.isEmpty {
            EmptyStateView(icon: "magnifyingglass", title: "No Results", message: "Try adjusting your search term or increasing the date range.")
        } else if vm.results.isEmpty {
            EmptyStateView(icon: "exclamationmark.shield", title: "FDA Food Recalls", message: "Search for food recalls or view recent alerts.")
        } else {
            resultsList
        }
    }

    private var resultsList: some View {
        List {
            Section {
                Text("\(vm.totalResults) result(s) found")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            ForEach(Array(vm.results.enumerated()), id: \.offset) { _, item in
                FDARecallRow(item: item)
            }
        }
        .listStyle(.insetGrouped)
    }
}

// MARK: - Recall Row

private struct FDARecallRow: View {
    let item: FDARecallItem

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Product description
            Text(item.productDescription ?? "Unknown Product")
                .font(.headline)
                .lineLimit(3)

            // Badges: Food/Drug type, classification, source authority
            HStack(spacing: 6) {
                if let type = item.productType {
                    Text(type.capitalized)
                        .font(.caption.bold())
                        .padding(.horizontal, 8).padding(.vertical, 3)
                        .background((type == "drug" ? Color.purple : Color.green).opacity(0.15))
                        .foregroundStyle(type == "drug" ? Color.purple : Color.green)
                        .clipShape(Capsule())
                }
                if let classification = item.classification {
                    classificationBadge(classification)
                }
                if let source = item.source {
                    Text(source)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }

            // Reason
            if let reason = item.reason, !reason.isEmpty {
                Text(reason)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .lineLimit(4)
            }

            // Details
            VStack(alignment: .leading, spacing: 4) {
                if let firm = item.recallingFirm {
                    detailRow("building.2", firm)
                }
                if let city = item.city, let state = item.state {
                    detailRow("mappin", "\(city), \(state)")
                }
                if let date = item.recallInitiationDate ?? item.reportDate {
                    detailRow("calendar", date)
                }
                if let status = item.status {
                    detailRow("info.circle", status)
                }
                coverageRow
            }
            .font(.caption)

            // Distribution pattern
            if let pattern = item.distribution, !pattern.isEmpty {
                DisclosureGroup {
                    Text(pattern)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } label: {
                    Text("Distribution Pattern")
                        .font(.caption.bold())
                }
            }

            // Official notice link
            if let urlString = item.url, let url = URL(string: urlString) {
                Link(destination: url) {
                    Label("Official notice", systemImage: "arrow.up.right.square")
                        .font(.caption.bold())
                }
            }
        }
        .padding(.vertical, 4)
    }

    /// Geographic coverage: nationwide flag, US states, countries reached.
    ///
    /// The states also get a real map. A comma-separated list of eleven
    /// postal codes is not something anyone can picture — "is this near me?"
    /// is the only question this section exists to answer, and a map answers
    /// it at a glance where "AL, AR, FL, GA, KY, LA, MS, NC, SC, TN, VA" does
    /// not. MapKit is native, already used in PhysiciansView, and needs no key.
    @ViewBuilder
    private var coverageRow: some View {
        if item.nationwide == true {
            detailRow("map", "Coverage: Nationwide (US)")
            RecallCoverageMap(states: [], nationwide: true)
        } else if let states = item.states, !states.isEmpty {
            detailRow("map", "Coverage: \(states.joined(separator: ", "))")
            RecallCoverageMap(states: states, nationwide: false)
        }
        if let countries = item.countries, countries.count > 1 {
            detailRow("globe", "Countries: \(countries.joined(separator: ", "))")
        }
    }

    private func classificationBadge(_ classification: String) -> some View {
        Text(classification)
            .font(.caption.bold())
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(classificationColor(classification).opacity(0.15))
            .foregroundStyle(classificationColor(classification))
            .clipShape(Capsule())
    }

    private func classificationColor(_ classification: String) -> Color {
        let lower = classification.lowercased()
        if lower.contains("class i") && !lower.contains("class ii") {
            return .red
        } else if lower.contains("class ii") && !lower.contains("class iii") {
            return .orange
        } else if lower.contains("class iii") {
            return .blue
        }
        return .gray
    }

    private func detailRow(_ icon: String, _ text: String) -> some View {
        HStack(spacing: 4) {
            Image(systemName: icon)
                .foregroundStyle(.secondary)
                .frame(width: 16)
            Text(text)
                .foregroundStyle(.secondary)
        }
    }
}


// MARK: - Coverage map

import MapKit

/// The states a recall reached, on a real map.
///
/// Geometry is the SAME file the web map draws (`/us-states.geojson`), fetched
/// from the app's own origin rather than bundled: adding a resource here means
/// editing the Xcode project file, and one asset served from one place cannot
/// drift into two versions of the truth.
///
/// It degrades quietly. If the fetch fails there is no map — the text line
/// above it still states the coverage, so nothing is lost but the picture.
/// An empty map frame would be worse than none: it reads as "no coverage".
struct RecallCoverageMap: View {
    let states: [String]
    let nationwide: Bool

    @State private var shapes: [MKPolygon] = []
    @State private var failed = false

    /// Fits the lower 48; Alaska and Hawaii pull the camera far enough that
    /// the covered states become invisible, and this is a thumbnail.
    private static let contiguous = MKCoordinateRegion(
        center: CLLocationCoordinate2D(latitude: 39.5, longitude: -98.0),
        span: MKCoordinateSpan(latitudeDelta: 30, longitudeDelta: 60))

    var body: some View {
        Group {
            if failed || (shapes.isEmpty && !nationwide) {
                EmptyView()
            } else {
                Map(initialPosition: .region(Self.contiguous), interactionModes: []) {
                    ForEach(Array(shapes.enumerated()), id: \.offset) { _, polygon in
                        MapPolygon(polygon)
                            .foregroundStyle(Color.orange.opacity(0.55))
                            .stroke(Color.orange, lineWidth: 0.5)
                    }
                }
                .frame(height: 170)
                .clipShape(RoundedRectangle(cornerRadius: 10))
                .allowsHitTesting(false)
                .accessibilityLabel(nationwide
                    ? "Distributed nationwide"
                    : "Distributed in \(states.count) states")
            }
        }
        .task { await load() }
    }

    private func load() async {
        guard shapes.isEmpty, !failed else { return }
        guard let url = URL(string: "\(AppConfig.webBaseURL)/us-states.geojson") else {
            failed = true
            return
        }
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            let wanted = Set(states.map { $0.uppercased() })
            let features = try MKGeoJSONDecoder().decode(data)
                .compactMap { $0 as? MKGeoJSONFeature }

            var found: [MKPolygon] = []
            for feature in features {
                guard let code = stateCode(of: feature) else { continue }
                guard nationwide || wanted.contains(code) else { continue }
                for geometry in feature.geometry {
                    if let polygon = geometry as? MKPolygon {
                        found.append(polygon)
                    } else if let multi = geometry as? MKMultiPolygon {
                        found.append(contentsOf: multi.polygons)
                    }
                }
            }
            shapes = found
        } catch {
            failed = true
        }
    }

    /// The USPS code is baked into the asset by
    /// `scripts/build_us_states_geojson.py`, so no lookup table lives here.
    private func stateCode(of feature: MKGeoJSONFeature) -> String? {
        guard let data = feature.properties,
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return nil }
        return (object["code"] as? String)?.uppercased()
    }
}
