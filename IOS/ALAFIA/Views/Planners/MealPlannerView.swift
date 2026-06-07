import SwiftUI

// MARK: - ViewModel

@Observable
final class MealPlannerViewModel {
    // Form fields
    var dietaryPattern = "balanced"
    var calorieTarget = 2000
    var allergies = ""
    var preferences = ""

    // State
    var currentPlan: MealPlanResponse?
    var savedPlans: [MealPlanResponse] = []
    var selectedDay = "monday"
    var isGenerating = false
    var isLoading = false
    var errorMessage: String?

    static let dietaryPatterns = ["balanced", "renal", "low_sodium", "diabetic", "heart_healthy"]
    static let daysOfWeek = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

    func generatePlan() async {
        isGenerating = true; errorMessage = nil
        let request = MealPlanRequest(
            dietaryPattern: dietaryPattern,
            dailyCalorieTarget: calorieTarget,
            allergies: allergies.isEmpty ? nil : allergies,
            preferences: preferences.isEmpty ? nil : preferences
        )
        do {
            currentPlan = try await APIClient.shared.post("/planners/meal-plan", body: request)
            await loadSavedPlans()
        } catch { errorMessage = error.localizedDescription }
        isGenerating = false
    }

    func loadSavedPlans() async {
        isLoading = true
        do { savedPlans = try await APIClient.shared.get("/planners/meal-plans") }
        catch { errorMessage = error.localizedDescription }
        isLoading = false
    }
}

// MARK: - Main View

struct MealPlannerView: View {
    @State private var vm = MealPlannerViewModel()
    @State private var showForm = true

    var body: some View {
            ScrollView {
                VStack(spacing: 20) {
                    // Toggle form
                    DisclosureGroup("Create Meal Plan", isExpanded: $showForm) {
                        MealPlanForm(vm: vm)
                    }
                    .padding()
                    .background(Color(.systemBackground))
                    .cornerRadius(16)
                    .shadow(color: .black.opacity(0.04), radius: 8, y: 2)

                    // Current plan display
                    if let plan = vm.currentPlan {
                        MealPlanDisplay(plan: plan, selectedDay: $vm.selectedDay)
                    }

                    // Saved plans
                    if !vm.savedPlans.isEmpty {
                        SavedMealPlansList(plans: vm.savedPlans, vm: vm)
                    }
                }
                .padding()
            }
            .navigationTitle("Meal Planner")
            .task { await vm.loadSavedPlans() }
            .refreshable { await vm.loadSavedPlans() }
    }
}

// MARK: - Form

private struct MealPlanForm: View {
    @Bindable var vm: MealPlannerViewModel

    var body: some View {
        VStack(spacing: 16) {
            // Dietary pattern
            VStack(alignment: .leading, spacing: 6) {
                Text("Dietary Pattern")
                    .font(.caption.bold())
                    .foregroundStyle(.secondary)
                Picker("Dietary Pattern", selection: $vm.dietaryPattern) {
                    ForEach(MealPlannerViewModel.dietaryPatterns, id: \.self) { pattern in
                        Text(pattern.replacingOccurrences(of: "_", with: " ").capitalized)
                            .tag(pattern)
                    }
                }
                .pickerStyle(.menu)
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            // Calorie target
            VStack(alignment: .leading, spacing: 6) {
                Text("Daily Calorie Target")
                    .font(.caption.bold())
                    .foregroundStyle(.secondary)
                Stepper("\(vm.calorieTarget) kcal", value: $vm.calorieTarget, in: 1000...4000, step: 100)
            }

            // Allergies
            VStack(alignment: .leading, spacing: 6) {
                Text("Allergies")
                    .font(.caption.bold())
                    .foregroundStyle(.secondary)
                TextField("e.g. peanuts, shellfish", text: $vm.allergies)
                    .textFieldStyle(.roundedBorder)
            }

            // Preferences
            VStack(alignment: .leading, spacing: 6) {
                Text("Preferences")
                    .font(.caption.bold())
                    .foregroundStyle(.secondary)
                TextField("e.g. vegetarian, high protein", text: $vm.preferences)
                    .textFieldStyle(.roundedBorder)
            }

            // Generate button
            Button {
                Task { await vm.generatePlan() }
            } label: {
                Group {
                    if vm.isGenerating {
                        ProgressView()
                            .tint(.white)
                    } else {
                        Label("Generate Meal Plan", systemImage: "wand.and.stars")
                    }
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .background(Color.green)
                .foregroundStyle(.white)
                .fontWeight(.semibold)
                .cornerRadius(12)
            }
            .disabled(vm.isGenerating)

            if let error = vm.errorMessage {
                Text(error)
                    .font(.caption)
                    .foregroundStyle(.red)
            }
        }
        .padding(.top, 8)
    }
}

// MARK: - Plan Display

private struct MealPlanDisplay: View {
    let plan: MealPlanResponse
    @Binding var selectedDay: String

    var body: some View {
        VStack(spacing: 16) {
            // Header
            VStack(spacing: 4) {
                Text(plan.planName)
                    .font(.title3.bold())
                if let pattern = plan.dietaryPattern {
                    Text(pattern.replacingOccurrences(of: "_", with: " ").capitalized)
                        .font(.caption)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 4)
                        .background(Color.green.opacity(0.15))
                        .foregroundStyle(.green)
                        .cornerRadius(8)
                }
                if let cal = plan.totalDailyCalories {
                    Text("\(cal) kcal/day")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            // Day picker
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(MealPlannerViewModel.daysOfWeek, id: \.self) { day in
                        Button {
                            selectedDay = day
                        } label: {
                            Text(day.prefix(3).capitalized)
                                .font(.caption.bold())
                                .padding(.horizontal, 14)
                                .padding(.vertical, 8)
                                .background(selectedDay == day ? Color.green : Color(.systemGray5))
                                .foregroundStyle(selectedDay == day ? .white : .primary)
                                .cornerRadius(8)
                        }
                    }
                }
            }

            // Meals for selected day
            if let planData = plan.planData, let dayMeals = planData[selectedDay] {
                MealSection(title: "Breakfast", icon: "sunrise.fill", meals: dayMeals.breakfast)
                MealSection(title: "Lunch", icon: "sun.max.fill", meals: dayMeals.lunch)
                MealSection(title: "Dinner", icon: "moon.fill", meals: dayMeals.dinner)
                MealSection(title: "Snacks", icon: "cup.and.saucer.fill", meals: dayMeals.snacks)
            } else {
                Text("No meals planned for this day")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .padding()
            }

            // Shopping list
            if let list = plan.shoppingList, !list.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Label("Shopping List", systemImage: "cart.fill")
                        .font(.headline)
                    ForEach(list, id: \.self) { item in
                        HStack(spacing: 8) {
                            Image(systemName: "circle")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                            Text(item)
                                .font(.subheadline)
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding()
                .background(Color(.secondarySystemBackground))
                .cornerRadius(12)
            }

            // Advice
            if let advice = plan.advice, !advice.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Label("Advice", systemImage: "lightbulb.fill")
                        .font(.headline)
                    Text(advice)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding()
                .background(Color(.secondarySystemBackground))
                .cornerRadius(12)
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(16)
        .shadow(color: .black.opacity(0.04), radius: 8, y: 2)
    }
}

// MARK: - Meal Section

private struct MealSection: View {
    let title: String
    let icon: String
    let meals: [MealItem]?

    var body: some View {
        if let meals, !meals.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Label(title, systemImage: icon)
                    .font(.subheadline.bold())

                ForEach(meals, id: \.name) { item in
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(item.name)
                                .font(.subheadline)
                            if let desc = item.description, !desc.isEmpty {
                                Text(desc)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        Spacer()
                        if let cal = item.calories {
                            Text("\(cal) kcal")
                                .font(.caption.bold())
                                .foregroundStyle(.orange)
                        }
                    }
                    .padding(.vertical, 4)

                    if let p = item.proteinG, let c = item.carbsG, let f = item.fatG {
                        HStack(spacing: 12) {
                            MacroBadge(label: "P", value: p, color: .blue)
                            MacroBadge(label: "C", value: c, color: .green)
                            MacroBadge(label: "F", value: f, color: .orange)
                        }
                        .font(.caption2)
                    }
                }
            }
            .padding()
            .background(Color(.secondarySystemBackground))
            .cornerRadius(12)
        }
    }
}

// MARK: - Macro Badge

private struct MacroBadge: View {
    let label: String
    let value: Double
    let color: Color

    var body: some View {
        Text("\(label): \(String(format: "%.0f", value))g")
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(color.opacity(0.12))
            .foregroundStyle(color)
            .cornerRadius(4)
    }
}

// MARK: - Saved Plans List

private struct SavedMealPlansList: View {
    let plans: [MealPlanResponse]
    @Bindable var vm: MealPlannerViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Saved Plans", systemImage: "tray.full.fill")
                .font(.headline)

            ForEach(plans) { plan in
                Button {
                    vm.currentPlan = plan
                    vm.selectedDay = "monday"
                } label: {
                    HStack {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(plan.planName)
                                .font(.subheadline.bold())
                                .foregroundStyle(.primary)
                            HStack(spacing: 8) {
                                if let pattern = plan.dietaryPattern {
                                    Text(pattern.replacingOccurrences(of: "_", with: " ").capitalized)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                if let start = plan.startDate {
                                    Text(start)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                        Spacer()
                        Image(systemName: "chevron.right")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .padding()
                    .background(Color(.secondarySystemBackground))
                    .cornerRadius(12)
                }
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(16)
        .shadow(color: .black.opacity(0.04), radius: 8, y: 2)
    }
}

#Preview {
    MealPlannerView()
}
