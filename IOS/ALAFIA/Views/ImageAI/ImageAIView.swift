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

    // Medication
    var medicationPhotoItem: PhotosPickerItem?
    var medicationImageData: Data?
    var medicationResult: MedicationFromImageResponse?
    var isUploadingMedication = false

    // Dosage
    var dosageMedName = ""
    var dosagePrescribed = ""
    var dosageWeight = ""
    var dosageAge = ""
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
        } catch { errorMessage = error.localizedDescription }
        isUploadingNutrition = false
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
                prescribedDosage: dosagePrescribed,
                patientWeightKg: Double(dosageWeight),
                patientAge: Int(dosageAge)
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
            if let generic = result.genericName {
                Label(generic, systemImage: "textformat")
                    .font(.subheadline).foregroundStyle(.secondary)
            }
            if let drugClass = result.drugClass {
                Label(drugClass, systemImage: "tag")
                    .font(.subheadline).foregroundStyle(.blue)
            }
            if let dosages = result.commonDosages {
                Label(dosages, systemImage: "scalemass")
                    .font(.subheadline).foregroundStyle(.green)
            }

            if let effects = result.sideEffects, !effects.isEmpty {
                sectionList("Side Effects", items: effects, icon: "exclamationmark.circle", color: .orange)
            }
            if let interactions = result.interactions, !interactions.isEmpty {
                sectionList("Interactions", items: interactions, icon: "arrow.triangle.2.circlepath", color: .red)
            }
            if let warnings = result.warnings, !warnings.isEmpty {
                sectionList("Warnings", items: warnings, icon: "exclamationmark.triangle", color: .red)
            }
            if let note = result.confidenceNote {
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
            LKTextField(title: "Prescribed Dosage", text: $vm.dosagePrescribed)
            LKTextField(title: "Patient Weight (kg) — optional", text: $vm.dosageWeight, keyboardType: .decimalPad)
            LKTextField(title: "Patient Age — optional", text: $vm.dosageAge, keyboardType: .numberPad)

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
        let inRange = result.isWithinRange ?? true
        return VStack(alignment: .leading, spacing: 10) {
            HStack {
                Image(systemName: inRange ? "checkmark.seal.fill" : "xmark.seal.fill")
                    .foregroundStyle(inRange ? .green : .red)
                    .font(.title2)
                Text(inRange ? "Within Standard Range" : "Outside Standard Range")
                    .font(.headline)
                    .foregroundStyle(inRange ? .green : .red)
            }

            if let medName = result.medicationName {
                Label(medName, systemImage: "pills").font(.subheadline)
            }
            if let prescribed = result.prescribedDosage {
                Label("Prescribed: \(prescribed)", systemImage: "scalemass").font(.subheadline)
            }
            if let range = result.standardRange {
                Label("Standard: \(range)", systemImage: "ruler").font(.subheadline).foregroundStyle(.secondary)
            }
            if let rec = result.recommendation {
                Text(rec).font(.subheadline).padding(.top, 4)
            }
            if let warnings = result.warnings, !warnings.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Label("Warnings", systemImage: "exclamationmark.triangle")
                        .font(.subheadline).fontWeight(.semibold).foregroundStyle(.red)
                    ForEach(warnings, id: \.self) { w in
                        Text("• \(w)").font(.caption)
                    }
                }
                .padding(.top, 6)
            }
        }
        .padding()
        .background((inRange ? Color.green : Color.red).opacity(0.08))
        .cornerRadius(12)
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(inRange ? Color.green : Color.red, lineWidth: 1)
        )
    }
}
