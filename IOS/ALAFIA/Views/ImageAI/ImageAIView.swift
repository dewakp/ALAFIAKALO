import SwiftUI
import PhotosUI

// MARK: - ViewModel

@Observable
final class ImageAIViewModel {
    enum Tab: String, CaseIterable { case nutrition = "Nutrition"; case medication = "Medication"; case dosage = "Dosage" }

    var selectedTab: Tab = .nutrition

    // Nutrition
    var nutritionPhotoItem: PhotosPickerItem?
    var nutritionImageData: Data?
    var nutritionResult: NutritionFromImageResponse?
    var isUploadingNutrition = false
    var correction = ""            // "Teach ALAFIA" ground-truth foods
    var isTeaching = false

    // Medication
    var medicationPhotoItem: PhotosPickerItem?
    var medicationImageData: Data?
    var medicationResult: MedicationFromImageResponse?
    var isUploadingMedication = false

    // Dosage
    var dosageMedName = ""
    var dosagePrescribed = ""
    var dosageFrequency = ""
    var dosageResult: DosageVerificationResponse?
    var isVerifyingDosage = false

    var errorMessage: String?

    // MARK: - Nutrition Upload

    func loadNutritionPhoto() async {
        guard let item = nutritionPhotoItem,
              let data = try? await item.loadTransferable(type: Data.self) else { return }
        nutritionImageData = data
    }

    func analyzeNutrition() async {
        guard let data = nutritionImageData else { return }
        isUploadingNutrition = true; errorMessage = nil
        do {
            nutritionResult = try await uploadImage(data, to: "/image-ai/nutrition-from-image")
            correction = (nutritionResult?.foodItems ?? []).map(\.name).joined(separator: "; ")
        } catch { errorMessage = error.localizedDescription }
        isUploadingNutrition = false
    }

    /// Teach ALAFIA: store the ground-truth foods for this photo (visual
    /// memory) — the same meal is recognized instantly in future photos.
    func teachNutrition() async {
        guard let data = nutritionImageData,
              !correction.trimmingCharacters(in: .whitespaces).isEmpty else { return }
        isTeaching = true; errorMessage = nil
        struct LabelBody: Encodable {
            let image_base64: String
            let foods: String
        }
        do {
            let body = LabelBody(image_base64: data.base64EncodedString(),
                                 foods: correction.trimmingCharacters(in: .whitespaces))
            nutritionResult = try await APIClient.shared.post("/image-ai/label", body: body)
        } catch { errorMessage = error.localizedDescription }
        isTeaching = false
    }

    // MARK: - Medication Upload

    func loadMedicationPhoto() async {
        guard let item = medicationPhotoItem,
              let data = try? await item.loadTransferable(type: Data.self) else { return }
        medicationImageData = data
    }

    func analyzeMedication() async {
        guard let data = medicationImageData else { return }
        isUploadingMedication = true; errorMessage = nil
        do {
            medicationResult = try await uploadImage(data, to: "/image-ai/medication-from-image")
        } catch { errorMessage = error.localizedDescription }
        isUploadingMedication = false
    }

    // MARK: - Dosage Verification

    func verifyDosage() async {
        guard !dosageMedName.isEmpty, !dosagePrescribed.isEmpty else { return }
        isVerifyingDosage = true; errorMessage = nil
        do {
            let request = DosageVerificationRequest(
                medicationName: dosageMedName,
                dosage: dosagePrescribed,
                frequency: dosageFrequency.isEmpty ? nil : dosageFrequency
            )
            dosageResult = try await APIClient.shared.post("/image-ai/verify-dosage", body: request)
        } catch { errorMessage = error.localizedDescription }
        isVerifyingDosage = false
    }

    // MARK: - Multipart Upload Helper

    private func uploadImage<T: Decodable>(_ imageData: Data, to path: String) async throws -> T {
        let boundary = UUID().uuidString
        let url = URL(string: "\(AppConfig.baseURL)\(path)")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        if let token = KeychainHelper.get(key: AppConfig.tokenKey) {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        var body = Data()
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"image.jpg\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: image/jpeg\r\n\r\n".data(using: .utf8)!)
        body.append(imageData)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
        request.httpBody = body

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, (200...299).contains(httpResponse.statusCode) else {
            if let httpResponse = response as? HTTPURLResponse {
                if let detail = try? JSONDecoder().decode(ErrorDetail.self, from: data) {
                    throw APIError.clientError(detail.detail)
                }
                throw APIError.unknown(httpResponse.statusCode)
            }
            throw APIError.invalidResponse
        }
        return try JSONDecoder().decode(T.self, from: data)
    }
}

// MARK: - Main View

struct ImageAIView: View {
    @State private var vm = ImageAIViewModel()

    var body: some View {
            VStack(spacing: 0) {
                Picker("Tab", selection: $vm.selectedTab) {
                    ForEach(ImageAIViewModel.Tab.allCases, id: \.self) { tab in
                        Text(tab.rawValue).tag(tab)
                    }
                }
                .pickerStyle(.segmented)
                .padding()

                Divider()

                ScrollView {
                    switch vm.selectedTab {
                    case .nutrition:  nutritionTab
                    case .medication: medicationTab
                    case .dosage:     dosageTab
                    }
                }
            }
            .navigationTitle("Image AI")
            .alert("Error", isPresented: .constant(vm.errorMessage != nil)) {
                Button("OK") { vm.errorMessage = nil }
            } message: {
                Text(vm.errorMessage ?? "")
            }
    }

    // MARK: - Nutrition Tab

    private var nutritionTab: some View {
        VStack(spacing: 16) {
            if let data = vm.nutritionImageData, let uiImage = UIImage(data: data) {
                Image(uiImage: uiImage)
                    .resizable()
                    .scaledToFit()
                    .frame(maxHeight: 200)
                    .cornerRadius(12)
            }

            PhotosPicker(selection: $vm.nutritionPhotoItem, matching: .images) {
                Label("Select Food Photo", systemImage: "photo.on.rectangle.angled")
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 12)
                    .background(Color.green.opacity(0.15))
                    .foregroundStyle(.green)
                    .cornerRadius(10)
            }
            .onChange(of: vm.nutritionPhotoItem) { _, _ in
                Task { await vm.loadNutritionPhoto() }
            }

            LKButton(title: "Analyze Nutrition", isLoading: vm.isUploadingNutrition) {
                Task { await vm.analyzeNutrition() }
            }
            .disabled(vm.nutritionImageData == nil)

            if let result = vm.nutritionResult {
                nutritionResultCard(result)
            }
        }
        .padding()
    }

    private func nutritionResultCard(_ result: NutritionFromImageResponse) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Detected Foods")
                .font(.headline)

            if result.foodItems.isEmpty {
                Text("No food items detected.")
                    .foregroundStyle(.secondary)
            } else {
                ForEach(result.foodItems, id: \.name) { item in
                    HStack {
                        VStack(alignment: .leading) {
                            Text(item.name).font(.subheadline).fontWeight(.medium)
                            if let serving = item.servingSize {
                                Text(serving).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                        Spacer()
                        if let cal = item.calories {
                            Text("\(cal) cal").font(.subheadline).foregroundStyle(.orange)
                        }
                    }
                    .padding(.vertical, 4)
                    Divider()
                }
            }

            HStack(spacing: 16) {
                totalBadge("Calories", value: result.totalCalories.map { "\($0)" } ?? "–", color: .orange)
                totalBadge("Protein", value: result.totalProteinG.map { String(format: "%.1fg", $0) } ?? "–", color: .red)
                totalBadge("Carbs", value: result.totalCarbsG.map { String(format: "%.1fg", $0) } ?? "–", color: .blue)
                totalBadge("Fat", value: result.totalFatG.map { String(format: "%.1fg", $0) } ?? "–", color: .yellow)
            }

            if let note = result.confidenceNote {
                Text(note).font(.caption).foregroundStyle(.secondary)
            }

            // Teach ALAFIA: correct the food list → learned for future photos
            Divider()
            Text("Not right? Teach ALAFIA what this actually is")
                .font(.caption).fontWeight(.semibold)
            HStack(spacing: 8) {
                TextField("e.g. beans in palm oil; grilled chicken", text: $vm.correction)
                    .textFieldStyle(.roundedBorder)
                    .font(.caption)
                Button {
                    Task { await vm.teachNutrition() }
                } label: {
                    if vm.isTeaching { ProgressView().controlSize(.small) }
                    else { Text("Teach").font(.caption).fontWeight(.semibold) }
                }
                .buttonStyle(.bordered)
                .disabled(vm.isTeaching || vm.correction.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            Text("Separate foods with semicolons — ALAFIA will recognize this meal in future photos.")
                .font(.caption2).foregroundStyle(.secondary)
        }
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(12)
    }

    private func totalBadge(_ label: String, value: String, color: Color) -> some View {
        VStack(spacing: 2) {
            Text(value).font(.subheadline).fontWeight(.semibold).foregroundStyle(color)
            Text(label).font(.caption2).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: - Medication Tab

    private var medicationTab: some View {
        VStack(spacing: 16) {
            if let data = vm.medicationImageData, let uiImage = UIImage(data: data) {
                Image(uiImage: uiImage)
                    .resizable()
                    .scaledToFit()
                    .frame(maxHeight: 200)
                    .cornerRadius(12)
            }

            PhotosPicker(selection: $vm.medicationPhotoItem, matching: .images) {
                Label("Select Medication Photo", systemImage: "pills.fill")
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 12)
                    .background(Color.purple.opacity(0.15))
                    .foregroundStyle(.purple)
                    .cornerRadius(10)
            }
            .onChange(of: vm.medicationPhotoItem) { _, _ in
                Task { await vm.loadMedicationPhoto() }
            }

            LKButton(title: "Identify Medication", isLoading: vm.isUploadingMedication) {
                Task { await vm.analyzeMedication() }
            }
            .disabled(vm.medicationImageData == nil)

            if let result = vm.medicationResult {
                medicationResultCard(result)
            }
        }
        .padding()
    }

    private func medicationResultCard(_ result: MedicationFromImageResponse) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            if let name = result.medicationName {
                HStack {
                    Text(name).font(.title3).fontWeight(.bold)
                    Spacer()
                }
            }
            if let dosage = result.dosage {
                Label(dosage, systemImage: "scalemass")
                    .font(.subheadline).foregroundStyle(.green)
            }
            if let instructions = result.instructions {
                Label(instructions, systemImage: "list.bullet.rectangle")
                    .font(.subheadline)
            }
            if let ndc = result.ndcCode {
                Label("NDC \(ndc)", systemImage: "barcode")
                    .font(.subheadline).foregroundStyle(.secondary)
            }
            if let mfr = result.manufacturer {
                Label(mfr, systemImage: "building.2")
                    .font(.subheadline).foregroundStyle(.secondary)
            }
            ForEach(Array(result.fields.enumerated()), id: \.offset) { _, f in
                if let label = f.label, let value = f.value, !label.isEmpty, !value.isEmpty {
                    Label("\(label): \(value)", systemImage: "info.circle")
                        .font(.subheadline).foregroundStyle(.blue)
                }
            }
            if let note = result.notes {
                Text(note).font(.caption).foregroundStyle(.secondary).padding(.top, 4)
            }
        }
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(12)
    }

    private func sectionList(_ title: String, items: [String], icon: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Label(title, systemImage: icon)
                .font(.subheadline).fontWeight(.semibold).foregroundStyle(color)
            ForEach(items, id: \.self) { item in
                Text("• \(item)").font(.caption)
            }
        }
        .padding(.top, 6)
    }

    // MARK: - Dosage Tab

    private var dosageTab: some View {
        VStack(spacing: 16) {
            LKTextField(title: "Medication Name", text: $vm.dosageMedName)
            LKTextField(title: "Dosage", text: $vm.dosagePrescribed)
            LKTextField(title: "Frequency — optional", text: $vm.dosageFrequency)

            LKButton(title: "Verify Dosage", isLoading: vm.isVerifyingDosage) {
                Task { await vm.verifyDosage() }
            }
            .disabled(vm.dosageMedName.isEmpty || vm.dosagePrescribed.isEmpty)

            if let result = vm.dosageResult {
                dosageResultCard(result)
            }
        }
        .padding()
    }

    private func dosageResultCard(_ result: DosageVerificationResponse) -> some View {
        let typical = result.isTypical ?? true
        return VStack(alignment: .leading, spacing: 10) {
            HStack {
                Image(systemName: typical ? "checkmark.seal.fill" : "exclamationmark.triangle.fill")
                    .foregroundStyle(typical ? .green : .red)
                    .font(.title2)
                Text(typical ? "Typical Dosage" : "Atypical — please verify")
                    .font(.headline)
                    .foregroundStyle(typical ? .green : .red)
            }

            if let medName = result.medicationName {
                Label(medName, systemImage: "pills").font(.subheadline)
            }
            if let dosage = result.dosage {
                Label("Dosage: \(dosage)", systemImage: "scalemass").font(.subheadline)
            }
            if let range = result.typicalRange {
                Label("Typical: \(range)", systemImage: "ruler").font(.subheadline).foregroundStyle(.secondary)
            }
            if let feedback = result.feedback {
                Text(feedback).font(.subheadline).padding(.top, 4)
            }
            if !result.precautions.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Label("Precautions", systemImage: "exclamationmark.triangle")
                        .font(.subheadline).fontWeight(.semibold).foregroundStyle(.red)
                    ForEach(result.precautions, id: \.self) { p in
                        Text("• \(p)").font(.caption)
                    }
                }
                .padding(.top, 6)
            }
        }
        .padding()
        .background((typical ? Color.green : Color.red).opacity(0.08))
        .cornerRadius(12)
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(typical ? Color.green : Color.red, lineWidth: 1)
        )
    }
}
