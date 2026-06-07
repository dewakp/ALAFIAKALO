import SwiftUI

// MARK: - ViewModel

@Observable
final class FDARecallsViewModel {
    var searchTerm = ""
    var days: Int = 30
    var limit: Int = 10
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
                "/fda-recalls/?search_term=\(encoded)&days=\(days)&limit=\(limit)"
            )
            results = response.results
            totalResults = response.total
        } catch { errorMessage = error.localizedDescription }
        isLoading = false
    }

    func loadRecent() async {
        isLoading = true; errorMessage = nil; hasSearched = true
        do {
            let response: FDARecallResponse = try await APIClient.shared.get("/fda-recalls/recent")
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

            // Classification badge
            if let classification = item.classification {
                classificationBadge(classification)
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
                if let date = item.recallDate {
                    detailRow("calendar", date)
                }
                if let status = item.status {
                    detailRow("info.circle", status)
                }
            }
            .font(.caption)

            // Distribution pattern
            if let pattern = item.distributionPattern, !pattern.isEmpty {
                DisclosureGroup {
                    Text(pattern)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } label: {
                    Text("Distribution Pattern")
                        .font(.caption.bold())
                }
            }
        }
        .padding(.vertical, 4)
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
