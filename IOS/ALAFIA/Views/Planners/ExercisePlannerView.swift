import SwiftUI

// MARK: - ViewModel

@Observable
final class ExercisePlannerViewModel {
    // Form fields
    var fitnessLevel = "moderate"
    var weeklyMinutesTarget = 150
    var limitations = ""

    // State
    var currentPlan: ExercisePlanResponse?
    var savedPlans: [ExercisePlanResponse] = []
    var selectedDay = "monday"
    var isGenerating = false
    var isLoading = false
    var errorMessage: String?

    static let fitnessLevels = ["beginner", "moderate", "advanced"]
    static let daysOfWeek = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

    func generatePlan() async {
        isGenerating = true; errorMessage = nil
        let request = ExercisePlanRequest(
            fitnessLevel: fitnessLevel,
            weeklyMinutesTarget: weeklyMinutesTarget,
            limitations: limitations.isEmpty ? nil : limitations
        )
        do {
            currentPlan = try await APIClient.shared.post("/planners/exercise-plan", body: request)
            await loadSavedPlans()
        } catch { errorMessage = error.localizedDescription }
        isGenerating = false
    }

    func loadSavedPlans() async {
        isLoading = true
        do { savedPlans = try await APIClient.shared.get("/planners/exercise-plans") }
        catch { errorMessage = error.localizedDescription }
        isLoading = false
    }
}

// MARK: - Main View

struct ExercisePlannerView: View {
    @State private var vm = ExercisePlannerViewModel()
    @State private var showForm = true

    var body: some View {
            ScrollView {
                VStack(spacing: 20) {
                    // Toggle form
                    DisclosureGroup("Create Exercise Plan", isExpanded: $showForm) {
                        ExercisePlanForm(vm: vm)
                    }
                    .padding()
                    .background(Color(.systemBackground))
                    .cornerRadius(16)
                    .shadow(color: .black.opacity(0.04), radius: 8, y: 2)

                    // Current plan display
                    if let plan = vm.currentPlan {
                        ExercisePlanDisplay(plan: plan, selectedDay: $vm.selectedDay)
                    }

                    // Saved plans
                    if !vm.savedPlans.isEmpty {
                        SavedExercisePlansList(plans: vm.savedPlans, vm: vm)
                    }
                }
                .padding()
            }
            .navigationTitle("Exercise Planner")
            .task { await vm.loadSavedPlans() }
            .refreshable { await vm.loadSavedPlans() }
    }
}

// MARK: - Form

private struct ExercisePlanForm: View {
    @Bindable var vm: ExercisePlannerViewModel

    var body: some View {
        VStack(spacing: 16) {
            // Fitness level
            VStack(alignment: .leading, spacing: 6) {
                Text("Fitness Level")
                    .font(.caption.bold())
                    .foregroundStyle(.secondary)
                Picker("Fitness Level", selection: $vm.fitnessLevel) {
                    ForEach(ExercisePlannerViewModel.fitnessLevels, id: \.self) { level in
                        Text(level.capitalized).tag(level)
                    }
                }
                .pickerStyle(.segmented)
            }

            // Weekly minutes target
            VStack(alignment: .leading, spacing: 6) {
                Text("Weekly Minutes Target")
                    .font(.caption.bold())
                    .foregroundStyle(.secondary)
                Stepper("\(vm.weeklyMinutesTarget) min/week", value: $vm.weeklyMinutesTarget, in: 30...600, step: 15)
            }

            // Limitations
            VStack(alignment: .leading, spacing: 6) {
                Text("Limitations / Injuries")
                    .font(.caption.bold())
                    .foregroundStyle(.secondary)
                TextField("e.g. bad knees, lower back pain", text: $vm.limitations)
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
                        Label("Generate Exercise Plan", systemImage: "figure.run")
                    }
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .background(Color.blue)
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

private struct ExercisePlanDisplay: View {
    let plan: ExercisePlanResponse
    @Binding var selectedDay: String

    var body: some View {
        VStack(spacing: 16) {
            // Header
            VStack(spacing: 4) {
                Text(plan.planName)
                    .font(.title3.bold())
                HStack(spacing: 12) {
                    if let level = plan.fitnessLevel {
                        Label(level.capitalized, systemImage: "gauge.medium")
                            .font(.caption)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 4)
                            .background(levelColor(level).opacity(0.15))
                            .foregroundStyle(levelColor(level))
                            .cornerRadius(8)
                    }
                    if let target = plan.weeklyMinutesTarget {
                        Label("\(target) min/week", systemImage: "clock")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            // Day picker
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(ExercisePlannerViewModel.daysOfWeek, id: \.self) { day in
                        let hasExercises = plan.planData?[day]?.isEmpty == false
                        Button {
                            selectedDay = day
                        } label: {
                            VStack(spacing: 4) {
                                Text(day.prefix(3).capitalized)
                                    .font(.caption.bold())
                                if hasExercises {
                                    Circle()
                                        .fill(Color.blue)
                                        .frame(width: 6, height: 6)
                                } else {
                                    Circle()
                                        .fill(Color.clear)
                                        .frame(width: 6, height: 6)
                                }
                            }
                            .padding(.horizontal, 12)
                            .padding(.vertical, 8)
                            .background(selectedDay == day ? Color.blue : Color(.systemGray5))
                            .foregroundStyle(selectedDay == day ? .white : .primary)
                            .cornerRadius(8)
                        }
                    }
                }
            }

            // Exercises for selected day
            if let planData = plan.planData, let exercises = planData[selectedDay], !exercises.isEmpty {
                ForEach(exercises, id: \.name) { exercise in
                    ExerciseCard(exercise: exercise)
                }
            } else {
                VStack(spacing: 8) {
                    Image(systemName: "figure.cooldown")
                        .font(.title)
                        .foregroundStyle(.secondary)
                    Text("Rest Day")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 24)
            }

            // Advice
            if let advice = plan.advice, !advice.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Label("Coach Notes", systemImage: "text.bubble.fill")
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

    private func levelColor(_ level: String) -> Color {
        switch level.lowercased() {
        case "beginner": return .green
        case "moderate": return .orange
        case "advanced": return .red
        default: return .blue
        }
    }
}

// MARK: - Exercise Card

private struct ExerciseCard: View {
    let exercise: ExerciseItem

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(exercise.name)
                .font(.subheadline.bold())

            if let desc = exercise.description, !desc.isEmpty {
                Text(desc)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            HStack(spacing: 12) {
                if let duration = exercise.durationMinutes {
                    Label("\(duration) min", systemImage: "clock")
                        .font(.caption)
                        .foregroundStyle(.blue)
                }
                if let sets = exercise.sets {
                    Label("\(sets) sets", systemImage: "arrow.2.squarepath")
                        .font(.caption)
                        .foregroundStyle(.purple)
                }
                if let reps = exercise.reps {
                    Label("\(reps) reps", systemImage: "repeat")
                        .font(.caption)
                        .foregroundStyle(.orange)
                }
            }

            // Muscle groups as tags
            if let groups = exercise.muscleGroups, !groups.isEmpty {
                FlowLayout(spacing: 6) {
                    ForEach(groups, id: \.self) { group in
                        Text(group)
                            .font(.caption2.bold())
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(Color.blue.opacity(0.12))
                            .foregroundStyle(.blue)
                            .cornerRadius(6)
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(Color(.secondarySystemBackground))
        .cornerRadius(12)
    }
}

// MARK: - Saved Plans List

private struct SavedExercisePlansList: View {
    let plans: [ExercisePlanResponse]
    @Bindable var vm: ExercisePlannerViewModel

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
                                if let level = plan.fitnessLevel {
                                    Text(level.capitalized)
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
    ExercisePlannerView()
}
