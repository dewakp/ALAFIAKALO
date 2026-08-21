import SwiftUI

// MARK: - Catalog Models

/// One ICD-11 MMS entity, as returned by `GET /chronic/icd11/search`.
///
/// The catalog lives on the backend (the full WHO linearization ships in the
/// image), so the app never carries a code list of its own and cannot drift
/// from what the server will accept.
struct ICD11Code: Identifiable, Codable, Hashable {
    let code: String
    let title: String
    let chapter: String
    let chapterTitle: String
    let isLeaf: Bool
    let isResidual: Bool

    var id: String { code }

    enum CodingKeys: String, CodingKey {
        case code, title, chapter
        case chapterTitle = "chapter_title"
        case isLeaf = "is_leaf"
        case isResidual = "is_residual"
    }
}

struct ICD11SearchResponse: Codable {
    let query: String
    let results: [ICD11Code]
    let total: Int
    let catalogVersion: String

    enum CodingKeys: String, CodingKey {
        case query, results, total
        case catalogVersion = "catalog_version"
    }
}

// MARK: - Form Row

/// The row that sits in the condition form. Shows the selected code, or opens
/// a search sheet when there is none.
struct ICD11PickerField: View {
    @Binding var code: String?
    @Binding var title: String?

    @State private var showingSearch = false

    var body: some View {
        Button {
            showingSearch = true
        } label: {
            HStack(alignment: .firstTextBaseline) {
                Text("ICD-11 Code")
                    .foregroundStyle(.primary)
                Spacer()
                if let code, !code.isEmpty {
                    VStack(alignment: .trailing, spacing: 2) {
                        Text(code)
                            .font(.system(.body, design: .monospaced))
                            .foregroundStyle(.primary)
                        if let title, !title.isEmpty {
                            Text(title)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .multilineTextAlignment(.trailing)
                                .lineLimit(2)
                        }
                    }
                } else {
                    Text("Search")
                        .foregroundStyle(.secondary)
                }
                Image(systemName: "chevron.right")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }
        }
        .buttonStyle(.plain)
        .swipeActions {
            if code?.isEmpty == false {
                Button(role: .destructive) {
                    code = nil
                    title = nil
                } label: {
                    Label("Clear", systemImage: "xmark")
                }
            }
        }
        .sheet(isPresented: $showingSearch) {
            ICD11SearchSheet(selectedCode: $code, selectedTitle: $title)
        }
    }
}

// MARK: - Search Sheet

struct ICD11SearchSheet: View {
    @Binding var selectedCode: String?
    @Binding var selectedTitle: String?

    @Environment(\.dismiss) private var dismiss

    @State private var query = ""
    @State private var results: [ICD11Code] = []
    @State private var isSearching = false
    /// Kept apart from `results` on purpose. A failed lookup rendered as an
    /// empty list tells the patient their condition is not in the catalog —
    /// the recurring failure of this app's clinical surfaces (CLAUDE.md §3aa).
    @State private var loadError: String?
    @State private var searchTask: Task<Void, Never>?

    var body: some View {
        NavigationStack {
            List {
                if let loadError {
                    Section {
                        VStack(alignment: .leading, spacing: 8) {
                            Label(loadError, systemImage: "exclamationmark.triangle.fill")
                                .foregroundStyle(.red)
                                .font(.subheadline)
                            Button("Retry") { runSearch(query, immediately: true) }
                                .font(.subheadline)
                        }
                        .padding(.vertical, 4)
                    }
                } else if isSearching {
                    Section {
                        HStack(spacing: 10) {
                            ProgressView()
                            Text("Searching…").foregroundStyle(.secondary)
                        }
                    }
                } else if results.isEmpty && !query.trimmingCharacters(in: .whitespaces).isEmpty {
                    Section {
                        Text("No ICD-11 match for “\(query)”. You can still save the condition by name.")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                }

                ForEach(results) { entry in
                    Button {
                        selectedCode = entry.code
                        selectedTitle = entry.title
                        dismiss()
                    } label: {
                        VStack(alignment: .leading, spacing: 3) {
                            HStack(alignment: .firstTextBaseline, spacing: 8) {
                                Text(entry.code)
                                    .font(.system(.subheadline, design: .monospaced))
                                    .fontWeight(.bold)
                                Text(entry.title)
                                    .font(.subheadline)
                                    .foregroundStyle(.primary)
                            }
                            Text(entry.chapterTitle)
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                    .buttonStyle(.plain)
                }

                if query.trimmingCharacters(in: .whitespaces).isEmpty && loadError == nil {
                    Section {
                        Text("Search by name, abbreviation or code — try “kidney”, “ESRD”, “sickle cell” or “GB61.5”.")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle("ICD-11 Code")
            .navigationBarTitleDisplayMode(.inline)
            .searchable(text: $query, prompt: "Condition, abbreviation or code")
            .onChange(of: query) { _, newValue in runSearch(newValue) }
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                if selectedCode?.isEmpty == false {
                    ToolbarItem(placement: .destructiveAction) {
                        Button("Clear") {
                            selectedCode = nil
                            selectedTitle = nil
                            dismiss()
                        }
                    }
                }
            }
        }
    }

    /// Debounced so a type-ahead does not fire a request per keystroke.
    /// Cancelling the previous task also stops a slow earlier response from
    /// landing after a newer one.
    private func runSearch(_ text: String, immediately: Bool = false) {
        searchTask?.cancel()
        let term = text.trimmingCharacters(in: .whitespaces)
        guard !term.isEmpty else {
            results = []
            loadError = nil
            isSearching = false
            return
        }

        isSearching = true
        searchTask = Task {
            if !immediately {
                try? await Task.sleep(nanoseconds: 250_000_000)
                if Task.isCancelled { return }
            }
            do {
                guard let encoded = term.addingPercentEncoding(
                    withAllowedCharacters: .urlQueryAllowed
                ) else { return }
                let response: ICD11SearchResponse = try await APIClient.shared.get(
                    "/chronic/icd11/search?q=\(encoded)&limit=25"
                )
                if Task.isCancelled { return }
                results = response.results
                loadError = nil
            } catch {
                if Task.isCancelled { return }
                results = []
                loadError = "Could not reach the ICD-11 catalog. Your condition may still be there."
            }
            isSearching = false
        }
    }
}
