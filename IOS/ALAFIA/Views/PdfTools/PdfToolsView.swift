import SwiftUI
import UniformTypeIdentifiers

// MARK: - ViewModel

@Observable
final class PdfToolsViewModel {
    enum Tab: String, CaseIterable { case parse = "Import"; case flowsheet = "Flowsheet" }

    var selectedTab: Tab = .parse

    // Import
    var showDocPicker = false
    var selectedFileName: String?
    var selectedFileData: Data?
    var parseResult: LabReportParseResponse?
    var isParsing = false
    var showRawText = false
    /// Item ids the patient has chosen to import.
    var selectedItemIds: Set<Int> = []
    var isImporting = false
    var importMessage: String?

    // Flowsheet
    var sessionType = "hemodialysis"
    var flowsheetDays: Int = 7
    var flowsheetResult: FlowsheetResponse?
    var isGenerating = false
    var isDownloading = false
    var sharePdfURL: URL?

    var errorMessage: String?

    static let sessionTypes = ["hemodialysis", "peritoneal_dialysis"]

    // MARK: - Parse Upload

    /// Reads the document and stages what it found. Writes nothing — the
    /// clinical tables are only touched by `confirmImport`.
    func parseLabReport() async {
        guard let data = selectedFileData, let name = selectedFileName else { return }
        isParsing = true; errorMessage = nil; importMessage = nil
        do {
            let result: LabReportParseResponse = try await uploadFile(
                data, fileName: name, to: "/pdf/parse-document"
            )
            parseResult = result
            // Pre-tick what the server judged safe; duplicates stay off so
            // confirming never silently writes a second copy of a reading.
            selectedItemIds = Set((result.items ?? []).compactMap { $0.accepted == true ? $0.itemId : nil })
        } catch { errorMessage = error.localizedDescription }
        isParsing = false
    }

    func toggle(_ itemId: Int) {
        if selectedItemIds.contains(itemId) { selectedItemIds.remove(itemId) }
        else { selectedItemIds.insert(itemId) }
    }

    func confirmImport() async {
        guard let importId = parseResult?.importId, !selectedItemIds.isEmpty else { return }
        isImporting = true; errorMessage = nil
        do {
            let body: [String: Any] = ["accepted_item_ids": Array(selectedItemIds).sorted()]
            let response: ConfirmImportResponse = try await postJSON(
                body, to: "/pdf/imports/\(importId)/confirm"
            )
            importMessage = response.message
        } catch { errorMessage = error.localizedDescription }
        isImporting = false
    }

    func discardImport() async {
        guard let importId = parseResult?.importId else { return }
        _ = try? await postJSON([:], to: "/pdf/imports/\(importId)/reject") as ConfirmImportResponse
        parseResult = nil
        selectedItemIds = []
        importMessage = nil
        selectedFileData = nil
        selectedFileName = nil
    }

    // MARK: - PDF download

    /// Fetches the report as a PDF and writes it to a temporary file so it can
    /// go through the share sheet.
    func downloadFlowsheetPdf() async {
        isDownloading = true; errorMessage = nil
        do {
            var components = URLComponents(string: "\(AppConfig.baseURL)/pdf/reports/flowsheet.pdf")!
            components.queryItems = [
                URLQueryItem(name: "session_type", value: sessionType),
                URLQueryItem(name: "days", value: String(flowsheetDays)),
            ]
            var request = URLRequest(url: components.url!)
            if let token = KeychainHelper.get(key: AppConfig.tokenKey) {
                request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
            }
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
                throw APIError.invalidResponse
            }
            let name = "flowsheet_\(sessionType)_\(Int(Date().timeIntervalSince1970)).pdf"
            let url = FileManager.default.temporaryDirectory.appendingPathComponent(name)
            try data.write(to: url)
            sharePdfURL = url
        } catch { errorMessage = error.localizedDescription }
        isDownloading = false
    }

    // MARK: - JSON POST

    private func postJSON<T: Decodable>(_ body: [String: Any], to path: String) async throws -> T {
        let url = URL(string: "\(AppConfig.baseURL)\(path)")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token = KeychainHelper.get(key: AppConfig.tokenKey) {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            if let detail = try? JSONDecoder().decode(ErrorDetail.self, from: data) {
                throw APIError.clientError(detail.detail)
            }
            throw APIError.invalidResponse
        }
        return try JSONDecoder().decode(T.self, from: data)
    }

    // MARK: - Generate Flowsheet

    func generateFlowsheet() async {
        isGenerating = true; errorMessage = nil
        // Drop any PDF from a previous run — it was built for different
        // parameters and sharing it would hand over the wrong report.
        sharePdfURL = nil
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
            Text("Upload a lab report, medication list or flowsheet. Nothing is added to your records until you review it and choose Import.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)

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

            LKButton(title: "Read Document", isLoading: vm.isParsing) {
                Task { await vm.parseLabReport() }
            }
            .disabled(vm.selectedFileData == nil)

            if let message = vm.importMessage {
                banner(message, systemImage: "checkmark.circle.fill", tint: .green)
            }

            if let result = vm.parseResult {
                // A document that could not be read must say so. An empty list
                // here would read as "the document contained no results".
                if let error = result.error {
                    banner(error, systemImage: "exclamationmark.triangle.fill", tint: .orange)
                }
                if result.alreadyImported == true {
                    banner("You have uploaded this file before — showing what was read then.",
                           systemImage: "info.circle.fill", tint: .blue)
                }
                parseResultCard(result)
            }
        }
        .padding()
    }

    private func banner(_ text: String, systemImage: String, tint: Color) -> some View {
        Label(text, systemImage: systemImage)
            .font(.caption)
            .foregroundStyle(tint)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(10)
            .background(tint.opacity(0.12))
            .cornerRadius(8)
    }

    private func parseResultCard(_ result: LabReportParseResponse) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(docTypeLabel(result.docType)).font(.headline)

            Group {
                if let name = result.patientName { infoRow("Patient", value: name) }
                if let date = result.reportDate { infoRow("Date", value: date) }
                if let lab = result.labName { infoRow("Lab", value: lab) }
                if let doc = result.orderingPhysician { infoRow("Physician", value: doc) }
                if let confidence = result.confidence {
                    infoRow("Confidence", value: "\(Int(confidence * 100))%")
                }
            }

            if let notes = result.parsingNotes, !notes.isEmpty {
                ForEach(notes, id: \.self) { note in
                    Text("• \(note)").font(.caption2).foregroundStyle(.secondary)
                }
            }

            if let items = result.items, !items.isEmpty {
                Divider()
                HStack {
                    Text("\(items.count) reading\(items.count == 1 ? "" : "s") found")
                        .font(.subheadline).fontWeight(.semibold)
                    Spacer()
                    if result.canImport && vm.importMessage == nil {
                        Text("\(vm.selectedItemIds.count) selected")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }

                ForEach(items) { item in
                    itemRow(item, selectable: result.canImport && vm.importMessage == nil)
                    Divider()
                }

                if result.canImport && vm.importMessage == nil {
                    HStack(spacing: 10) {
                        LKButton(title: "Import \(vm.selectedItemIds.count) selected",
                                 isLoading: vm.isImporting) {
                            Task { await vm.confirmImport() }
                        }
                        .disabled(vm.selectedItemIds.isEmpty)

                        Button("Discard") { Task { await vm.discardImport() } }
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.top, 4)
                } else if !result.canImport {
                    Text("This document type can be read but not imported yet — the values above are shown for reference only.")
                        .font(.caption2).foregroundStyle(.secondary)
                }
            }

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
                    Text("Extracted text").font(.subheadline).fontWeight(.medium)
                }
            }
        }
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(12)
    }

    private func itemRow(_ item: LabReportItem, selectable: Bool) -> some View {
        HStack(alignment: .top, spacing: 10) {
            if selectable, let id = item.itemId {
                Button {
                    vm.toggle(id)
                } label: {
                    Image(systemName: vm.selectedItemIds.contains(id) ? "checkmark.square.fill" : "square")
                        .foregroundStyle(vm.selectedItemIds.contains(id) ? Color.accentColor : .secondary)
                }
                .buttonStyle(.plain)
            }

            VStack(alignment: .leading, spacing: 2) {
                Text(item.testName ?? "Unknown")
                    .font(.subheadline).fontWeight(.medium)
                    .foregroundStyle(item.isAbnormal == true ? .red : .primary)
                if let ref = item.referenceRange {
                    Text("Ref: \(ref)").font(.caption2).foregroundStyle(.secondary)
                }
                if let label = item.sourceLabel, label != item.testName {
                    Text("document: “\(label)”").font(.caption2).foregroundStyle(.tertiary)
                }
                if let note = item.note {
                    Text(note).font(.caption2).foregroundStyle(.orange)
                }
                if item.isDuplicate {
                    Text("Already recorded").font(.caption2).foregroundStyle(.secondary)
                } else if item.isConflict {
                    Text("Differs from existing").font(.caption2).foregroundStyle(.orange)
                }
            }

            Spacer()

            Text("\(item.value ?? "–") \(item.unit ?? "")")
                .font(.subheadline).fontWeight(.semibold)
                .foregroundStyle(item.isAbnormal == true ? .red : .primary)
        }
        .padding(.vertical, 3)
    }

    private func docTypeLabel(_ type: String?) -> String {
        switch type {
        case "lab_report":         return "Lab report"
        case "medication_list":    return "Medication list"
        case "discharge_summary":  return "Discharge summary"
        case "dialysis_flowsheet": return "Dialysis flowsheet"
        case "imaging_report":     return "Imaging report"
        default:                   return "Document"
        }
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
                // The real PDF, not the text preview — the same ReportSpec on
                // the server renders both, so they cannot disagree.
                if let url = vm.sharePdfURL {
                    ShareLink(item: url) {
                        Label("Share PDF", systemImage: "square.and.arrow.up").font(.caption)
                    }
                } else {
                    Button {
                        Task { await vm.downloadFlowsheetPdf() }
                    } label: {
                        if vm.isDownloading {
                            ProgressView()
                        } else {
                            Label("PDF", systemImage: "arrow.down.doc").font(.caption)
                        }
                    }
                    .disabled(vm.isDownloading)
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
