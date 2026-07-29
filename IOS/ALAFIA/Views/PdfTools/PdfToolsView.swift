import SwiftUI
import UniformTypeIdentifiers

// MARK: - ViewModel

@Observable
final class PdfToolsViewModel {
    enum Tab: String, CaseIterable { case parse = "Parse Report"; case flowsheet = "Flowsheet" }

    var selectedTab: Tab = .parse

    // Parse
    var showDocPicker = false
    var selectedFileName: String?
    var selectedFileData: Data?
    var parseResult: LabReportParseResponse?
    var isParsing = false
    var showRawText = false

    // Flowsheet
    var sessionType = "hemodialysis"
    var flowsheetDays: Int = 7
    var flowsheetResult: FlowsheetResponse?
    var isGenerating = false

    var errorMessage: String?

    static let sessionTypes = ["hemodialysis", "peritoneal_dialysis"]

    // MARK: - Parse Upload

    func parseLabReport() async {
        guard let data = selectedFileData, let name = selectedFileName else { return }
        isParsing = true; errorMessage = nil
        do {
            parseResult = try await uploadFile(data, fileName: name, to: "/pdf/parse-lab-report")
        } catch { errorMessage = error.localizedDescription }
        isParsing = false
    }

    // MARK: - Generate Flowsheet

    func generateFlowsheet() async {
        isGenerating = true; errorMessage = nil
        do {
            let body: [String: Any] = ["session_type": sessionType, "days": flowsheetDays]
            let jsonData = try JSONSerialization.data(withJSONObject: body)
            let url = URL(string: "\(AppConfig.baseURL)/pdf/generate-flowsheet")!
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            if let token = KeychainHelper.get(key: AppConfig.tokenKey) {
                request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
            }
            request.httpBody = jsonData
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse, (200...299).contains(httpResponse.statusCode) else {
                if let detail = try? JSONDecoder().decode(ErrorDetail.self, from: data) {
                    throw APIError.clientError(detail.detail)
                }
                throw APIError.invalidResponse
            }
            flowsheetResult = try JSONDecoder().decode(FlowsheetResponse.self, from: data)
        } catch { errorMessage = error.localizedDescription }
        isGenerating = false
    }

    // MARK: - Multipart File Upload

    private func uploadFile<T: Decodable>(_ fileData: Data, fileName: String, to path: String) async throws -> T {
        let boundary = UUID().uuidString
        let url = URL(string: "\(AppConfig.baseURL)\(path)")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        if let token = KeychainHelper.get(key: AppConfig.tokenKey) {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        let mimeType = fileName.hasSuffix(".pdf") ? "application/pdf" : "text/plain"
        var body = Data()
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"\(fileName)\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: \(mimeType)\r\n\r\n".data(using: .utf8)!)
        body.append(fileData)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
        request.httpBody = body

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, (200...299).contains(httpResponse.statusCode) else {
            if let detail = try? JSONDecoder().decode(ErrorDetail.self, from: data) {
                throw APIError.clientError(detail.detail)
            }
            throw APIError.invalidResponse
        }
        return try JSONDecoder().decode(T.self, from: data)
    }
}

// MARK: - Document Picker Coordinator

struct DocumentPicker: UIViewControllerRepresentable {
    let types: [UTType]
    let onPick: (URL) -> Void

    func makeUIViewController(context: Context) -> UIDocumentPickerViewController {
        let picker = UIDocumentPickerViewController(forOpeningContentTypes: types)
        picker.delegate = context.coordinator
        picker.allowsMultipleSelection = false
        return picker
    }

    func updateUIViewController(_ uiViewController: UIDocumentPickerViewController, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator(onPick: onPick) }

    class Coordinator: NSObject, UIDocumentPickerDelegate {
        let onPick: (URL) -> Void
        init(onPick: @escaping (URL) -> Void) { self.onPick = onPick }

        func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
            guard let url = urls.first else { return }
            onPick(url)
        }
    }
}

// MARK: - Main View

struct PdfToolsView: View {
    @State private var vm = PdfToolsViewModel()

    var body: some View {
            VStack(spacing: 0) {
                Picker("Tab", selection: $vm.selectedTab) {
                    ForEach(PdfToolsViewModel.Tab.allCases, id: \.self) { tab in
                        Text(tab.rawValue).tag(tab)
                    }
                }
                .pickerStyle(.segmented)
                .padding()

                Divider()

                ScrollView {
                    switch vm.selectedTab {
                    case .parse:     parseTab
                    case .flowsheet: flowsheetTab
                    }
                }
            }
            .navigationTitle("PDF Tools")
            .sheet(isPresented: $vm.showDocPicker) {
                DocumentPicker(types: [.pdf, .plainText]) { url in
                    guard url.startAccessingSecurityScopedResource() else { return }
                    defer { url.stopAccessingSecurityScopedResource() }
                    if let data = try? Data(contentsOf: url) {
                        vm.selectedFileData = data
                        vm.selectedFileName = url.lastPathComponent
                    }
                }
            }
            .alert("Error", isPresented: .constant(vm.errorMessage != nil)) {
                Button("OK") { vm.errorMessage = nil }
            } message: {
                Text(vm.errorMessage ?? "")
            }
    }

    // MARK: - Parse Tab

    private var parseTab: some View {
        VStack(spacing: 16) {
            Button {
                vm.showDocPicker = true
            } label: {
                Label(vm.selectedFileName ?? "Select PDF or Text File", systemImage: "doc.badge.plus")
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 12)
                    .background(Color.brown.opacity(0.12))
                    .foregroundStyle(.brown)
                    .cornerRadius(10)
            }

            LKButton(title: "Parse Lab Report", isLoading: vm.isParsing) {
                Task { await vm.parseLabReport() }
            }
            .disabled(vm.selectedFileData == nil)

            if let result = vm.parseResult {
                parseResultCard(result)
            }
        }
        .padding()
    }

    private func parseResultCard(_ result: LabReportParseResponse) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Parsed Results").font(.headline)

            // Patient info
            Group {
                if let name = result.patientName { infoRow("Patient", value: name) }
                if let date = result.reportDate { infoRow("Date", value: date) }
                if let lab = result.labName { infoRow("Lab", value: lab) }
                if let doc = result.orderingPhysician { infoRow("Physician", value: doc) }
            }

            if let items = result.items, !items.isEmpty {
                Divider()
                Text("Lab Results").font(.subheadline).fontWeight(.semibold)

                ForEach(items.indices, id: \.self) { idx in
                    let item = items[idx]
                    HStack {
                        VStack(alignment: .leading) {
                            Text(item.testName ?? "Unknown")
                                .font(.subheadline)
                                .fontWeight(.medium)
                                .foregroundStyle(item.isAbnormal == true ? .red : .primary)
                            if let ref = item.referenceRange {
                                Text("Ref: \(ref)")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        Spacer()
                        VStack(alignment: .trailing) {
                            Text("\(item.value ?? "–") \(item.unit ?? "")")
                                .font(.subheadline)
                                .fontWeight(.semibold)
                                .foregroundStyle(item.isAbnormal == true ? .red : .primary)
                        }
                    }
                    .padding(.vertical, 2)
                    if idx < items.count - 1 { Divider() }
                }
            }

            // Raw text toggle
            if let raw = result.rawTextPreview, !raw.isEmpty {
                Divider()
                DisclosureGroup(isExpanded: $vm.showRawText) {
                    Text(raw)
                        .font(.system(.caption, design: .monospaced))
                        .padding(8)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color(.systemGray6))
                        .cornerRadius(8)
                } label: {
                    Text("Raw Text Preview")
                        .font(.subheadline).fontWeight(.medium)
                }
            }
        }
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(12)
    }

    private func infoRow(_ label: String, value: String) -> some View {
        HStack {
            Text(label).font(.caption).foregroundStyle(.secondary)
            Spacer()
            Text(value).font(.subheadline).fontWeight(.medium)
        }
    }

    // MARK: - Flowsheet Tab

    private var flowsheetTab: some View {
        VStack(spacing: 16) {
            VStack(alignment: .leading, spacing: 8) {
                Text("Session Type").font(.caption).foregroundStyle(.secondary)
                Picker("Session Type", selection: $vm.sessionType) {
                    ForEach(PdfToolsViewModel.sessionTypes, id: \.self) { type in
                        Text(type.replacingOccurrences(of: "_", with: " ").capitalized).tag(type)
                    }
                }
                .pickerStyle(.segmented)
            }

            Stepper("Days: \(vm.flowsheetDays)", value: $vm.flowsheetDays, in: 1...90)

            LKButton(title: "Generate Flowsheet", isLoading: vm.isGenerating) {
                Task { await vm.generateFlowsheet() }
            }

            if let result = vm.flowsheetResult {
                flowsheetResultCard(result)
            }
        }
        .padding()
    }

    private func flowsheetResultCard(_ result: FlowsheetResponse) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading) {
                    if let title = result.title {
                        Text(title).font(.headline)
                    }
                    if let date = result.generatedAt {
                        Text("Generated: \(date)").font(.caption).foregroundStyle(.secondary)
                    }
                    if let count = result.sessionCount {
                        Text("\(count) sessions").font(.caption).foregroundStyle(.secondary)
                    }
                }
                Spacer()
                if let content = result.content {
                    ShareLink(item: content) {
                        Image(systemName: "square.and.arrow.up")
                    }
                }
            }

            if let content = result.content {
                ScrollView(.horizontal, showsIndicators: true) {
                    Text(content)
                        .font(.system(.caption, design: .monospaced))
                        .padding(8)
                }
                .frame(maxHeight: 400)
                .background(Color(.systemGray6))
                .cornerRadius(8)
            }
        }
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(12)
    }
}
