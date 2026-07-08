import SwiftUI

// MARK: - ViewModel

@Observable
final class NutritionViewModel {
    var logs: [NutritionLog] = []
    var isLoading = false
    var errorMessage: String?

    // USDA search
    var searchResults: [USDAFoodResult] = []
    var isSearching = false
    var foodDetail: USDAFoodDetail?
    var isLoadingDetail = false

    // Daily summary
    var summary: DailySummary?
    var isLoadingSummary = false

    // Personalized daily nutrient goals
    var goals: GoalProgressResponse?

    func fetchLogs() async {
        isLoading = true
        errorMessage = nil
        do {
            logs = try await APIClient.shared.get("/nutrition/")
            isLoading = false
        } catch {
            errorMessage = error.localizedDescription
            isLoading = false
        }
    }

    func addLog(_ log: NutritionLogCreate) async -> Bool {
        do {
            let _: NutritionLog = try await APIClient.shared.post("/nutrition/", body: log)
            await fetchLogs()
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    func deleteLog(id: Int) async {
        do {
            try await APIClient.shared.delete("/nutrition/\(id)")
            logs.removeAll { $0.id == id }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func searchFoods(query: String) async {
        guard query.count >= 2 else { searchResults = []; return }
        isSearching = true
        do {
            let encoded = query.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? query
            searchResults = try await APIClient.shared.get("/nutrition/food-search?q=\(encoded)&page_size=15")
        } catch {
            searchResults = []
        }
        isSearching = false
    }

    func fetchFoodDetail(fdcId: Int) async {
        isLoadingDetail = true
        do {
            foodDetail = try await APIClient.shared.get("/nutrition/food/\(fdcId)")
        } catch {
            foodDetail = nil
        }
        isLoadingDetail = false
    }

    func fetchSummary(date: String) async {
        isLoadingSummary = true
        do {
            summary = try await APIClient.shared.get("/nutrition/daily-summary?date=\(date)")
        } catch {
            summary = nil
        }
        isLoadingSummary = false
    }

    func fetchGoals(date: String) async {
        do {
            goals = try await APIClient.shared.get("/nutrition/goal-progress?date=\(date)")
        } catch {
            goals = nil
        }
    }

    /// Analyze a recipe link: parse the page's structured recipe, price the
    /// ingredients, return per-serving nutrition. Published nutrition is learned
    /// server-side under the dish name.
    func analyzeRecipe(url: String) async -> RecipeAnalyzeResponse? {
        do {
            return try await APIClient.shared.post(
                "/nutrition/recipe-analyze",
                body: RecipeAnalyzeRequest(url: url, servings: nil),
                timeout: 120
            )
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }
}

// MARK: - Main View

struct NutritionView: View {
    @State private var vm = NutritionViewModel()
    @State private var showAdd = false
    @State private var selectedTab = 0  // 0=log, 1=summary
    @State private var summaryDate = Date()
    @State private var detailFdcId: Int?

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                Picker("View", selection: $selectedTab) {
                    Text("Food Log").tag(0)
                    Text("Daily Summary").tag(1)
                }
                .pickerStyle(.segmented)
                .padding(.horizontal)
                .padding(.top, 8)

                if selectedTab == 0 {
                    foodLogView
                } else {
                    dailySummaryView
                }
            }
            .navigationTitle("Nutrition")
            .toolbar {
                if selectedTab == 0 {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button { showAdd = true } label: { Image(systemName: "plus") }
                    }
                }
            }
            .sheet(isPresented: $showAdd) {
                AddNutritionSheet(vm: vm)
            }
            .sheet(item: $detailFdcId) { fdcId in
                FoodDetailSheet(vm: vm, fdcId: fdcId)
            }
            .task { await vm.fetchLogs() }
        }
    }

    // MARK: Food Log

    private var foodLogView: some View {
        Group {
            if vm.isLoading {
                ProgressView().frame(maxHeight: .infinity)
            } else if vm.logs.isEmpty {
                EmptyStateView(icon: "leaf.fill", title: "No Nutrition Logs", message: "Tap + to log your first meal")
            } else {
                List {
                    ForEach(vm.logs) { log in
                        NutritionRow(log: log) {
                            if let fdc = log.fdcId { detailFdcId = fdc }
                        }
                    }
                    .onDelete { indexSet in
                        Task {
                            for index in indexSet { await vm.deleteLog(id: vm.logs[index].id) }
                        }
                    }
                }
            }
        }
    }

    // MARK: Daily Summary

    private var dailySummaryView: some View {
        ScrollView {
            VStack(spacing: 16) {
                DatePicker("Date", selection: $summaryDate, displayedComponents: .date)
                    .datePickerStyle(.compact)
                    .padding(.horizontal)
                    .onChange(of: summaryDate) { _, newVal in
                        Task {
                            await vm.fetchSummary(date: isoDate(newVal))
                            await vm.fetchGoals(date: isoDate(newVal))
                        }
                    }

                // Personalized daily nutrient goals / limits
                if let g = vm.goals {
                    DailyTargetsCard(data: g).padding(.horizontal)
                }

                if vm.isLoadingSummary {
                    ProgressView().padding(.top, 40)
                } else if let s = vm.summary, s.mealCount > 0 {
                    // Macro cards
                    HStack(spacing: 12) {
                        MacroCard(label: "Calories", value: s.totalCalories, unit: "kcal", rda: 2000, color: .orange)
                        MacroCard(label: "Protein", value: s.totalProteinG, unit: "g", rda: 50, color: .blue)
                        MacroCard(label: "Carbs", value: s.totalCarbsG, unit: "g", rda: 275, color: .purple)
                        MacroCard(label: "Fat", value: s.totalFatG, unit: "g", rda: 78, color: .red)
                    }
                    .padding(.horizontal)

                    Text("\(s.mealCount) meal\(s.mealCount == 1 ? "" : "s") logged")
                        .font(.caption).foregroundStyle(.secondary)

                    // Nutrient breakdown
                    NutrientBreakdownView(nutrients: s.nutrients)
                        .padding(.horizontal)
                } else {
                    VStack(spacing: 8) {
                        Image(systemName: "chart.bar.xaxis")
                            .font(.largeTitle).foregroundStyle(.tertiary)
                        Text("No meals logged for this date")
                            .font(.subheadline).foregroundStyle(.secondary)
                    }
                    .padding(.top, 60)
                }
            }
            .padding(.vertical)
        }
        .task {
            await vm.fetchSummary(date: isoDate(summaryDate))
            await vm.fetchGoals(date: isoDate(summaryDate))
        }
    }

    private func isoDate(_ d: Date) -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        return f.string(from: d)
    }
}

// MARK: - Int Identifiable

extension Int: @retroactive Identifiable {
    public var id: Int { self }
}

// MARK: - Daily Nutrient Targets

struct DailyTargetsCard: View {
    let data: GoalProgressResponse

    private let condLabels: [String: String] = [
        "ckd": "CKD", "dialysis": "Dialysis", "diabetes": "Diabetes",
        "hypertension": "Hypertension", "cardiovascular": "Cardiac", "heart_failure": "Heart failure",
    ]

    private func color(_ status: String) -> Color {
        switch status {
        case "ok": return .green
        case "over": return .red
        default: return .orange   // low / warning
        }
    }

    private func fmt(_ v: Double) -> String {
        v < 10 ? String(format: "%.1f", v) : String(Int(v.rounded()))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Daily Targets").font(.headline)

            if !data.conditions.isEmpty {
                HStack(spacing: 6) {
                    ForEach(data.conditions, id: \.self) { c in
                        Text(condLabels[c] ?? c)
                            .font(.caption2).fontWeight(.semibold)
                            .padding(.horizontal, 8).padding(.vertical, 3)
                            .background(Color.red.opacity(0.15))
                            .foregroundStyle(.red)
                            .clipShape(Capsule())
                    }
                }
            }

            if !data.profileComplete {
                Text("Add your age, height & weight in Profile for goals tailored to you.")
                    .font(.caption).foregroundStyle(.secondary)
            }

            ForEach(data.goals) { g in
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 6) {
                        Image(systemName: g.kind == "limit" ? "arrow.down" : "arrow.up")
                            .font(.caption2).foregroundStyle(color(g.status))
                        Text(g.name).font(.subheadline).fontWeight(.medium)
                        Spacer()
                        Text("\(fmt(g.current))/\(fmt(g.goal)) \(g.unit)")
                            .font(.caption).monospaced().foregroundStyle(.secondary)
                    }
                    GeometryReader { geo in
                        ZStack(alignment: .leading) {
                            Capsule().fill(Color.gray.opacity(0.2)).frame(height: 6)
                            Capsule().fill(color(g.status))
                                .frame(width: geo.size.width * min(g.pct, 100) / 100, height: 6)
                        }
                    }
                    .frame(height: 6)
                }
            }

            Text("↑ aim for · ↓ stay under. Guidance from your biology & conditions — not medical advice.")
                .font(.caption2).foregroundStyle(.tertiary)
        }
        .padding()
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}

// MARK: - Nutrition Row

struct NutritionRow: View {
    let log: NutritionLog
    var onTapUSDA: () -> Void = {}

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(log.foodName).font(.headline)
                if log.fdcId != nil {
                    Button { onTapUSDA() } label: {
                        Text("USDA").font(.system(size: 9, weight: .bold))
                            .padding(.horizontal, 5).padding(.vertical, 2)
                            .background(Color.green.opacity(0.15))
                            .foregroundStyle(.green)
                            .clipShape(Capsule())
                    }
                    .buttonStyle(.plain)
                }
                Spacer()
                if let cal = log.calories {
                    Text("\(Int(cal)) kcal")
                        .font(.subheadline).foregroundStyle(.green).fontWeight(.semibold)
                }
            }
            HStack(spacing: 12) {
                if let p = log.proteinG { MacroPill(label: "P", value: p, color: .blue) }
                if let c = log.carbsG { MacroPill(label: "C", value: c, color: .orange) }
                if let f = log.fatG { MacroPill(label: "F", value: f, color: .red) }
                if let fb = log.fiberG { MacroPill(label: "Fiber", value: fb, color: .brown) }
            }
            HStack {
                Text(log.mealType.capitalized).font(.caption).foregroundStyle(.secondary)
                if let s = log.servingSize {
                    Text("· \(s)").font(.caption).foregroundStyle(.tertiary)
                }
            }
        }
        .padding(.vertical, 4)
    }
}

struct MacroPill: View {
    let label: String
    let value: Double
    let color: Color

    var body: some View {
        Text("\(label): \(String(format: "%.0f", value))g")
            .font(.caption2).fontWeight(.medium)
            .padding(.horizontal, 8).padding(.vertical, 2)
            .background(color.opacity(0.15))
            .foregroundStyle(color)
            .clipShape(Capsule())
    }
}

// MARK: - Macro Card

struct MacroCard: View {
    let label: String
    let value: Double
    let unit: String
    let rda: Double
    let color: Color

    private var pct: Double { min((value / rda) * 100, 100) }

    var body: some View {
        VStack(spacing: 4) {
            Text(label).font(.caption2).foregroundStyle(.secondary).textCase(.uppercase)
            Text(unit == "kcal" ? "\(Int(value))" : String(format: "%.1f", value))
                .font(.title3).fontWeight(.bold).foregroundStyle(color)
            Text(unit).font(.caption2).foregroundStyle(.tertiary)
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule().fill(color.opacity(0.15)).frame(height: 5)
                    Capsule().fill(color).frame(width: geo.size.width * pct / 100, height: 5)
                }
            }
            .frame(height: 5)
            Text("\(Int(pct))% DV").font(.system(size: 9)).foregroundStyle(.tertiary)
        }
        .frame(maxWidth: .infinity)
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 12).fill(.ultraThinMaterial))
    }
}

// MARK: - Nutrient Breakdown

struct NutrientBreakdownView: View {
    let nutrients: [USDAFoodNutrient]
    @State private var expandedCats: Set<String> = ["Macronutrients", "Vitamins", "Minerals"]

    private var grouped: [(String, [USDAFoodNutrient])] {
        let order = ["Energy", "Macronutrients", "Fats", "Minerals", "Vitamins",
                      "Other", "Amino Acids", "Fatty Acids", "Sterols", "Carotenoids", "Sugars"]
        var dict: [String: [USDAFoodNutrient]] = [:]
        nutrients.forEach { dict[$0.category, default: []].append($0) }
        return order.compactMap { cat in dict[cat].map { (cat, $0) } }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Nutrient Breakdown").font(.headline).padding(.bottom, 4)
            ForEach(grouped, id: \.0) { cat, items in
                DisclosureGroup(isExpanded: Binding(
                    get: { expandedCats.contains(cat) },
                    set: { if $0 { expandedCats.insert(cat) } else { expandedCats.remove(cat) } }
                )) {
                    VStack(spacing: 2) {
                        ForEach(items) { n in
                            NutrientRowView(nutrient: n)
                        }
                    }
                } label: {
                    HStack {
                        Text(cat).font(.subheadline).fontWeight(.semibold)
                        Text("(\(items.count))").font(.caption).foregroundStyle(.tertiary)
                    }
                }
            }
        }
        .padding()
        .background(RoundedRectangle(cornerRadius: 12).fill(.ultraThinMaterial))
    }
}

struct NutrientRowView: View {
    let nutrient: USDAFoodNutrient

    private var pctColor: Color {
        guard let p = nutrient.percentDv else { return .secondary }
        if p < 25 { return .red }
        if p < 75 { return .orange }
        return .green
    }

    var body: some View {
        HStack(spacing: 8) {
            Text(nutrient.name).font(.caption).foregroundStyle(.secondary).lineLimit(1)
            Spacer()
            Text("\(String(format: "%.1f", nutrient.value)) \(nutrient.unit)")
                .font(.system(.caption, design: .monospaced))
            if let p = nutrient.percentDv {
                Text("\(Int(p))%")
                    .font(.system(size: 10, weight: .semibold, design: .monospaced))
                    .foregroundStyle(pctColor)
                    .frame(width: 36, alignment: .trailing)
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        Capsule().fill(pctColor.opacity(0.15)).frame(height: 4)
                        Capsule().fill(pctColor).frame(width: geo.size.width * min(CGFloat(p), 100) / 100, height: 4)
                    }
                }
                .frame(width: 50, height: 4)
            }
        }
        .padding(.vertical, 1)
    }
}

// MARK: - Add Nutrition Sheet

struct AddNutritionSheet: View {
    @Bindable var vm: NutritionViewModel
    @Environment(\.dismiss) var dismiss

    @State private var foodName = ""
    @State private var mealType = "breakfast"
    @State private var servingSize = ""
    @State private var fdcId: Int?
    @State private var calories = ""
    @State private var proteinG = ""
    @State private var carbsG = ""
    @State private var fatG = ""
    @State private var notes = ""
    @State private var startTime = ""
    @State private var endTime = ""
    @State private var preMealWeightKg = ""
    @State private var postMealWeightKg = ""
    @State private var recipeUrl = ""
    @State private var analyzingRecipe = false
    @State private var recipeInfo = ""
    @State private var recipePreview: RecipeAnalyzeResponse?
    @State private var saving = false
    @State private var showSearch = false
    @State private var searchText = ""
    @State private var selectedImages: [UIImage] = []
    @State private var showImagePicker = false
    @State private var showCamera = false
    @State private var isAnalyzingImages = false
    @State private var imageAnalysisResult = ""

    let mealTypes = ["breakfast", "lunch", "dinner", "snack"]

    var body: some View {
        NavigationStack {
            Form {
                // Image Analysis
                Section {
                    if selectedImages.isEmpty {
                        HStack {
                            Button {
                                showImagePicker = true
                            } label: {
                                Label("Choose Images (max 3)", systemImage: "photo.on.rectangle")
                            }
                            Spacer()
                            Button {
                                showCamera = true
                            } label: {
                                Label("Camera", systemImage: "camera")
                            }
                        }
                    } else {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 8) {
                                ForEach(selectedImages.indices, id: \.self) { i in
                                    ZStack(alignment: .topTrailing) {
                                        Image(uiImage: selectedImages[i])
                                            .resizable().scaledToFill()
                                            .frame(width: 80, height: 80)
                                            .clipShape(RoundedRectangle(cornerRadius: 8))
                                        Button {
                                            selectedImages.remove(at: i)
                                        } label: {
                                            Image(systemName: "xmark.circle.fill")
                                                .foregroundStyle(.white, .black.opacity(0.6))
                                                .font(.system(size: 18))
                                        }
                                        .offset(x: 6, y: -6)
                                    }
                                }
                                if selectedImages.count < 3 {
                                    Button {
                                        showImagePicker = true
                                    } label: {
                                        RoundedRectangle(cornerRadius: 8)
                                            .fill(.quaternary)
                                            .frame(width: 80, height: 80)
                                            .overlay(Image(systemName: "plus").font(.title2).foregroundStyle(.secondary))
                                    }
                                }
                            }
                            .padding(.vertical, 4)
                        }
                        Button {
                            analyzeImages()
                        } label: {
                            if isAnalyzingImages {
                                HStack { ProgressView(); Text("Analysing…") }
                            } else {
                                Label("Analyse Image(s) with Alafia", systemImage: "sparkles")
                                    .frame(maxWidth: .infinity)
                            }
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(isAnalyzingImages)
                    }
                    if !imageAnalysisResult.isEmpty {
                        Text(imageAnalysisResult)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                } header: {
                    Text("Identify Food from Image (Optional)")
                }

                // USDA Search
                Section {
                    Button { showSearch = true } label: {
                        HStack {
                            Image(systemName: "magnifyingglass")
                            Text("Search USDA Food Database")
                            Spacer()
                            if fdcId != nil {
                                Image(systemName: "checkmark.circle.fill")
                                    .foregroundStyle(.green)
                            }
                        }
                    }
                    if fdcId != nil {
                        HStack {
                            Image(systemName: "bolt.fill").foregroundStyle(.green).font(.caption)
                            Text("Nutrients auto-populated from USDA").font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }

                Section("Food Details") {
                    LKTextField(title: "Food name", text: $foodName)
                    Picker("Meal Type", selection: $mealType) {
                        ForEach(mealTypes, id: \.self) { Text($0.capitalized) }
                    }
                    LKTextField(title: "Serving size", text: $servingSize)
                }

                if fdcId == nil {
                    Section("Macros (optional if USDA linked)") {
                        LKNumberField(title: "Calories (kcal)", value: $calories)
                        LKNumberField(title: "Protein (g)", value: $proteinG)
                        LKNumberField(title: "Carbs (g)", value: $carbsG)
                        LKNumberField(title: "Fat (g)", value: $fatG)
                    }
                }

                Section("Meal Timing (Optional)") {
                    LKTextField(title: "Start Time (e.g. 08:00)", text: $startTime)
                        .keyboardType(.numbersAndPunctuation)
                    LKTextField(title: "End Time (e.g. 08:30)", text: $endTime)
                        .keyboardType(.numbersAndPunctuation)
                }

                Section("Weight Tracking (Optional)") {
                    LKNumberField(title: "Pre-Meal Weight (kg)", value: $preMealWeightKg)
                    LKNumberField(title: "Post-Meal Weight (kg)", value: $postMealWeightKg)
                }

                Section("Notes & Recipe") {
                    TextField("Notes (optional)", text: $notes, axis: .vertical)
                        .lineLimit(3...6)
                    LKTextField(title: "Recipe URL (optional)", text: $recipeUrl)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    Button {
                        analyzeRecipe()
                    } label: {
                        HStack {
                            Image(systemName: "link")
                            Text(analyzingRecipe ? "Analyzing…" : "Analyze Recipe")
                            Spacer()
                            if analyzingRecipe { ProgressView() }
                        }
                    }
                    .disabled(recipeUrl.trimmingCharacters(in: .whitespaces).isEmpty || analyzingRecipe)
                    if !recipeInfo.isEmpty {
                        Text(recipeInfo).font(.caption).foregroundStyle(.secondary)
                    }
                    if let rp = recipePreview {
                        RecipePreviewRow(data: rp)
                    }
                }
            }
            .navigationTitle("Add Meal")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Save") { save() }
                        .disabled(foodName.isEmpty || saving)
                        .fontWeight(.semibold)
                }
            }
            .sheet(isPresented: $showSearch) {
                USDASearchSheet(vm: vm) { food in
                    foodName = food.description
                    fdcId = food.fdcId
                    if let s = food.servingSize {
                        servingSize = "\(Int(s)) \(food.servingSizeUnit ?? "g")"
                    }
                }
            }
            .sheet(isPresented: $showImagePicker) {
                ImagePickerView(images: $selectedImages, maxCount: 3)
            }
        }
    }

    private func analyzeImages() {
        // TODO(alafia-model): replace with ALAFIAModel.infer(.vision, images) for food recognition
        isAnalyzingImages = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 1) {
            isAnalyzingImages = false
            imageAnalysisResult = "Image analysis coming soon (ALAFIAModel Phase 5)"
        }
    }

    private func analyzeRecipe() {
        let url = recipeUrl.trimmingCharacters(in: .whitespaces)
        guard !url.isEmpty else { return }
        analyzingRecipe = true; recipeInfo = ""
        Task {
            if let data = await vm.analyzeRecipe(url: url) {
                if foodName.isEmpty { foodName = data.name; fdcId = nil }
                if servingSize.isEmpty { servingSize = "1 serving (of \(data.servings))" }
                recipePreview = data
                recipeInfo = "\(data.name) — \(data.ingredients.count) ingredients, \(data.servings) servings"
                    + (data.learned ? ". Published nutrition learned for this dish." : "")
            } else {
                recipePreview = nil
                recipeInfo = "Could not analyze that recipe link"
            }
            analyzingRecipe = false
        }
    }

    private func save() {
        saving = true
        var log = NutritionLogCreate(
            logDate: .todayISO(),
            mealType: mealType,
            foodName: foodName,
            servingSize: servingSize.isEmpty ? nil : servingSize,
            fdcId: fdcId,
            calories: fdcId != nil ? nil : Double(calories),
            proteinG: fdcId != nil ? nil : Double(proteinG),
            carbsG: fdcId != nil ? nil : Double(carbsG),
            fatG: fdcId != nil ? nil : Double(fatG),
            notes: notes.isEmpty ? nil : notes
        )
        log.startTime = startTime.isEmpty ? nil : startTime
        log.endTime = endTime.isEmpty ? nil : endTime
        log.preMealWeightKg = Double(preMealWeightKg)
        log.postMealWeightKg = Double(postMealWeightKg)
        log.recipeUrl = recipeUrl.isEmpty ? nil : recipeUrl
        Task {
            if await vm.addLog(log) { dismiss() }
            saving = false
        }
    }
}

// MARK: - Recipe Analysis Preview

struct RecipePreviewRow: View {
    let data: RecipeAnalyzeResponse

    private func macro(_ key: String, _ unit: String) -> String {
        guard let x = data.perServing[key] else { return "-" }
        let num = x >= 10 ? String(Int(x.rounded())) : String(format: "%.1f", x)
        return "\(num)\(unit)"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Image(systemName: "sparkles").font(.caption).foregroundStyle(.tint)
                Text("Per serving · \(data.source == "published" ? "recipe (published)" : "recipe (estimated)")")
                    .font(.caption).fontWeight(.semibold)
            }
            HStack {
                previewMacro("Calories", macro("calories", ""))
                Spacer()
                previewMacro("Protein", macro("protein_g", " g"))
                Spacer()
                previewMacro("Carbs", macro("carbs_g", " g"))
                Spacer()
                previewMacro("Fat", macro("fat_g", " g"))
            }
            Text("Suggestions — final nutrients are computed server-side when you save.")
                .font(.caption2).foregroundStyle(.tertiary)
        }
        .padding(.vertical, 4)
    }

    private func previewMacro(_ label: String, _ value: String) -> some View {
        VStack(spacing: 2) {
            Text(value).font(.subheadline).fontWeight(.bold)
            Text(label).font(.system(size: 10)).foregroundStyle(.secondary)
        }
    }
}

// MARK: - USDA Search Sheet

struct USDASearchSheet: View {
    @Bindable var vm: NutritionViewModel
    @Environment(\.dismiss) var dismiss
    var onSelect: (USDAFoodResult) -> Void

    @State private var query = ""
    @State private var searchTask: Task<Void, Never>?

    var body: some View {
        NavigationStack {
            List {
                if vm.isSearching {
                    HStack {
                        ProgressView()
                        Text("Searching USDA database…").font(.caption).foregroundStyle(.secondary)
                    }
                }
                ForEach(vm.searchResults) { food in
                    Button {
                        onSelect(food)
                        dismiss()
                    } label: {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(food.description).font(.subheadline).fontWeight(.medium)
                            HStack(spacing: 8) {
                                if let dt = food.dataType { Text(dt).font(.caption2).foregroundStyle(.tertiary) }
                                Text("\(food.nutrients.count) nutrients").font(.caption2).foregroundStyle(.blue)
                                if let cal = food.nutrients["calories"] {
                                    Text("\(Int(cal)) kcal").font(.caption2).fontWeight(.medium).foregroundStyle(.green)
                                }
                            }
                        }
                        .padding(.vertical, 2)
                    }
                    .buttonStyle(.plain)
                }
            }
            .searchable(text: $query, prompt: "e.g. banana, chicken breast…")
            .onChange(of: query) { _, newVal in
                searchTask?.cancel()
                searchTask = Task {
                    try? await Task.sleep(for: .milliseconds(400))
                    guard !Task.isCancelled else { return }
                    await vm.searchFoods(query: newVal)
                }
            }
            .navigationTitle("Search USDA Foods")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) { Button("Cancel") { dismiss() } }
            }
        }
    }
}

// MARK: - Food Detail Sheet

struct FoodDetailSheet: View {
    @Bindable var vm: NutritionViewModel
    let fdcId: Int
    @Environment(\.dismiss) var dismiss

    var body: some View {
        NavigationStack {
            Group {
                if vm.isLoadingDetail {
                    ProgressView("Loading nutrient data…").frame(maxHeight: .infinity)
                } else if let detail = vm.foodDetail {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 12) {
                            Text(detail.description).font(.title3).fontWeight(.bold)
                            HStack(spacing: 8) {
                                if let dt = detail.dataType { InfoChip(text: dt) }
                                if let cat = detail.foodCategory { InfoChip(text: cat) }
                                InfoChip(text: "FDC \(detail.fdcId)")
                            }

                            NutrientBreakdownView(nutrients: detail.nutrientBreakdown)
                        }
                        .padding()
                    }
                } else {
                    VStack {
                        Image(systemName: "exclamationmark.triangle").font(.largeTitle).foregroundStyle(.red)
                        Text("Failed to load").foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle("Nutrient Profile")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) { Button("Done") { dismiss() } }
            }
            .task { await vm.fetchFoodDetail(fdcId: fdcId) }
        }
    }
}

struct InfoChip: View {
    let text: String
    var body: some View {
        Text(text).font(.caption2).fontWeight(.medium)
            .padding(.horizontal, 8).padding(.vertical, 3)
            .background(Color.blue.opacity(0.1))
            .foregroundStyle(.blue)
            .clipShape(Capsule())
    }
}
