import SwiftUI

// MARK: - ViewModel

@Observable
final class SurveillanceViewModel {
    var diseases: [SurveillanceDisease] = []
    var selectedDisease = "influenza"
    var days = 90
    var data: SurveillanceGlobal?
    var isLoading = false
    var errorMessage: String?

    func loadDiseases() async {
        do {
            diseases = try await APIClient.shared.get("/surveillance/diseases")
            if let first = diseases.first, !diseases.contains(where: { $0.id == selectedDisease }) {
                selectedDisease = first.id
            }
        } catch { errorMessage = error.localizedDescription }
    }

    func loadGlobal() async {
        isLoading = true; errorMessage = nil
        do {
            data = try await APIClient.shared.get(
                "/surveillance/global?disease=\(selectedDisease)&days=\(days)&view=both"
            )
        } catch { errorMessage = error.localizedDescription }
        isLoading = false
    }

    /// Countries ranked by combined signal: outward indicator first, inward as tiebreaker.
    var rankedCountries: [SurveillanceCountry] {
        (data?.countries ?? []).sorted {
            let a = ($0.outward ?? 0) + Double($0.inward)
            let b = ($1.outward ?? 0) + Double($1.inward)
            return a > b
        }
    }
}

// MARK: - Main View

struct SurveillanceView: View {
    @State private var vm = SurveillanceViewModel()

    var body: some View {
        VStack(spacing: 0) {
            controls
            Divider()
            content
        }
        .navigationTitle("Disease Surveillance")
        .task {
            await vm.loadDiseases()
            await vm.loadGlobal()
        }
    }

    private var controls: some View {
        VStack(spacing: 10) {
            if !vm.diseases.isEmpty {
                Picker("Disease", selection: $vm.selectedDisease) {
                    ForEach(vm.diseases) { d in
                        Text("\(d.icon) \(d.label)").tag(d.id)
                    }
                }
                .pickerStyle(.menu)
                .onChange(of: vm.selectedDisease) { Task { await vm.loadGlobal() } }
            }
            if let d = vm.data {
                HStack {
                    Text("\(d.countries.count) countries · \(d.inwardTotal) ALAFIA symptom signals")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Spacer()
                }
            }
        }
        .padding()
    }

    @ViewBuilder
    private var content: some View {
        if vm.isLoading {
            ProgressView("Loading surveillance data…")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let error = vm.errorMessage {
            ContentUnavailableView("Error", systemImage: "exclamationmark.triangle", description: Text(error))
        } else if vm.rankedCountries.isEmpty {
            EmptyStateView(icon: "globe", title: "No Data",
                           message: "No surveillance signal for this disease yet.")
        } else {
            List {
                Section("Ranked by signal (WHO/CDC outward + ALAFIA inward)") {
                    ForEach(vm.rankedCountries.prefix(60)) { c in
                        CountrySignalRow(country: c)
                    }
                }
            }
            .listStyle(.insetGrouped)
        }
    }
}

// MARK: - Row

private struct CountrySignalRow: View {
    let country: SurveillanceCountry

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 3) {
                Text(country.name).font(.subheadline.bold())
                if let region = country.region {
                    Text(region).font(.caption2).foregroundStyle(.secondary)
                }
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 3) {
                if let outward = country.outward {
                    Text(formatted(outward))
                        .font(.subheadline.monospacedDigit())
                    if let year = country.outwardYear {
                        Text("WHO \(String(year))").font(.caption2).foregroundStyle(.secondary)
                    }
                }
                if country.inward > 0 {
                    Text("\(country.inward) local signals")
                        .font(.caption2)
                        .foregroundStyle(.orange)
                }
            }
        }
        .padding(.vertical, 2)
    }

    private func formatted(_ v: Double) -> String {
        v >= 1000 ? String(format: "%,.0f", v) : String(format: "%g", v)
    }
}
