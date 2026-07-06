import SwiftUI

// MARK: - ViewModel

@Observable
final class FacilitiesViewModel {
    var searchTerm = ""
    var facilityType = ""           // "" = all
    var facilities: [Facility] = []
    var types: [String] = []
    var isLoading = false
    var errorMessage: String?

    func load() async {
        isLoading = true; errorMessage = nil
        do {
            var path = "/facilities/?limit=50"
            if !searchTerm.trimmingCharacters(in: .whitespaces).isEmpty {
                let q = searchTerm.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? searchTerm
                path += "&search=\(q)"
            }
            if !facilityType.isEmpty {
                path += "&facility_type=\(facilityType)"
            }
            facilities = try await APIClient.shared.get(path)
            // Derive the type filter list from results on first unfiltered load.
            if types.isEmpty && facilityType.isEmpty {
                types = Array(Set(facilities.map(\.facilityType))).sorted()
            }
        } catch { errorMessage = error.localizedDescription }
        isLoading = false
    }
}

// MARK: - Main View

struct FacilitiesView: View {
    @State private var vm = FacilitiesViewModel()

    var body: some View {
        VStack(spacing: 0) {
            searchBar
            Divider()
            content
        }
        .navigationTitle("Facilities")
        .task { await vm.load() }
    }

    private var searchBar: some View {
        VStack(spacing: 10) {
            HStack {
                Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                TextField("Search facilities…", text: $vm.searchTerm)
                    .textFieldStyle(.plain)
                    .autocapitalization(.none)
                    .onSubmit { Task { await vm.load() } }
            }
            .padding(10)
            .background(Color(.systemGray6))
            .cornerRadius(10)

            if !vm.types.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        typeChip("All", tag: "")
                        ForEach(vm.types, id: \.self) { t in
                            typeChip(t.replacingOccurrences(of: "_", with: " ").capitalized, tag: t)
                        }
                    }
                }
            }
        }
        .padding()
    }

    private func typeChip(_ label: String, tag: String) -> some View {
        Button {
            vm.facilityType = tag
            Task { await vm.load() }
        } label: {
            Text(label)
                .font(.caption.bold())
                .padding(.horizontal, 12).padding(.vertical, 6)
                .background(vm.facilityType == tag ? Color.accentColor : Color(.systemGray5))
                .foregroundStyle(vm.facilityType == tag ? .white : .primary)
                .clipShape(Capsule())
        }
    }

    @ViewBuilder
    private var content: some View {
        if vm.isLoading {
            ProgressView("Loading facilities…")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let error = vm.errorMessage {
            ContentUnavailableView("Error", systemImage: "exclamationmark.triangle", description: Text(error))
        } else if vm.facilities.isEmpty {
            EmptyStateView(icon: "building.2", title: "No Facilities",
                           message: "Try a different search or type filter.")
        } else {
            List(vm.facilities) { f in
                FacilityRow(facility: f)
            }
            .listStyle(.insetGrouped)
        }
    }
}

// MARK: - Row

private struct FacilityRow: View {
    let facility: Facility

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(facility.name).font(.headline)
            Text(facility.facilityType.replacingOccurrences(of: "_", with: " ").capitalized)
                .font(.caption.bold())
                .padding(.horizontal, 8).padding(.vertical, 3)
                .background(Color.teal.opacity(0.15))
                .foregroundStyle(.teal)
                .clipShape(Capsule())

            if let address = addressLine {
                Label(address, systemImage: "mappin")
                    .font(.caption).foregroundStyle(.secondary)
            }
            if let phone = facility.phone, !phone.isEmpty {
                Label(phone, systemImage: "phone")
                    .font(.caption).foregroundStyle(.secondary)
            }
            if let site = facility.website, let url = URL(string: site) {
                Link(destination: url) {
                    Label("Website", systemImage: "arrow.up.right.square").font(.caption.bold())
                }
            }
        }
        .padding(.vertical, 2)
    }

    private var addressLine: String? {
        let parts = [facility.addressLine1, facility.city, facility.stateProvince, facility.country]
            .compactMap { $0 }.filter { !$0.isEmpty }
        return parts.isEmpty ? nil : parts.joined(separator: ", ")
    }
}
