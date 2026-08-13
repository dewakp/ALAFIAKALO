import SwiftUI

struct MainTabView: View {
    @EnvironmentObject var authManager: AuthManager
    @EnvironmentObject var deepLinkRouter: DeepLinkRouter
    @State private var selectedTab = 1   // Home by default

    var body: some View {
        TabView(selection: $selectedTab) {
            PromptView()
                .tabItem {
                    Label("Ask", systemImage: "sparkles")
                }
                .tag(0)

            DashboardView()
                .tabItem {
                    Label("Home", systemImage: "house.fill")
                }
                .tag(1)

            NutritionView()
                .tabItem {
                    Label("Nutrition", systemImage: "leaf.fill")
                }
                .tag(2)

            FitnessView()
                .tabItem {
                    Label("Fitness", systemImage: "figure.run")
                }
                .tag(3)

            HealthHubView()
                .tabItem {
                    Label("Health", systemImage: "heart.text.clipboard")
                }
                .tag(4)

            AIChatView()
                .tabItem {
                    Label("AI", systemImage: "brain.head.profile")
                }
                .tag(5)
        }
        .tint(.green)
        // Consume deep-link routes (push-notification taps, alafia:// URLs).
        // Top-level destinations select their tab; everything else lives in the
        // Health hub, so route there.
        .onChange(of: deepLinkRouter.pendingRoute) { _, route in
            guard let route else { return }
            switch route {
            case .dashboard: selectedTab = 1
            case .nutrition: selectedTab = 2
            case .fitness:   selectedTab = 3
            case .aiChat:    selectedTab = 5
            case .labs, .medications, .mood, .wellness, .telehealth,
                 .messaging, .insurance, .calendar, .profile:
                selectedTab = 4
            case .passwordReset, .unknown:
                break
            }
            deepLinkRouter.clearRoute()
        }
        .onAppear {
            #if DEBUG
            // Automation hooks (DEBUG only — never in a release build).
            let env = ProcessInfo.processInfo.environment
            // Single-screen screenshot: jump straight to a tab (no openurl dialog).
            if let r = env["ALAFIA_TEST_ROUTE"] {
                selectedTab = tabIndexForRoute(r)
            }
            // Auto-tour for app-preview video: cycle a comma-separated route list,
            // holding each ALAFIA_TEST_TOUR_DWELL seconds.
            if let routesStr = env["ALAFIA_TEST_TOUR_ROUTES"], !routesStr.isEmpty {
                let dwell = Double(env["ALAFIA_TEST_TOUR_DWELL"] ?? "4") ?? 4
                let seq = routesStr.split(separator: ",").map { String($0).trimmingCharacters(in: .whitespaces) }
                for (i, route) in seq.enumerated() {
                    DispatchQueue.main.asyncAfter(deadline: .now() + dwell * Double(i)) {
                        withAnimation(.easeInOut(duration: 0.45)) {
                            selectedTab = tabIndexForRoute(route)
                        }
                    }
                }
            }
            #endif
        }
    }
}

#if DEBUG
/// Maps an automation route name to its tab index (DEBUG screenshot/video tooling).
private func tabIndexForRoute(_ route: String) -> Int {
    switch route {
    case "ask":               return 0
    case "home", "dashboard": return 1
    case "nutrition":         return 2
    case "fitness":           return 3
    case "health":            return 4
    case "ai":                return 5
    default:                  return 1
    }
}
#endif

/// Health Hub groups all features into sections
struct HealthHubView: View {
    @EnvironmentObject var authManager: AuthManager

    private struct SupportLink {
        let title: String
        let icon: String
        let path: String
    }

    private static let supportLinks = [
        SupportLink(title: "Help", icon: "questionmark.circle", path: "/help"),
        SupportLink(title: "Contact Us", icon: "envelope", path: "/contact"),
        SupportLink(title: "Investors", icon: "chart.line.uptrend.xyaxis", path: "/investors"),
        SupportLink(title: "Privacy", icon: "lock.shield", path: "/privacy"),
    ]

    private var isClinician: Bool {
        let clinicianRoles: Set<String> = [
            "physician", "surgeon", "nurse_practitioner",
            "physician_assistant", "resident", "fellow", "attending_physician",
            "cardiologist", "dermatologist", "endocrinologist", "gastroenterologist",
            "neurologist", "oncologist", "pediatrician", "radiologist",
            "general_surgeon", "orthopedic_surgeon", "neurosurgeon",
            "cardiothoracic_surgeon", "plastic_surgeon", "vascular_surgeon",
            "oral_surgeon", "clinical_nurse_specialist", "nurse_anesthetist",
            "nurse_midwife", "charge_nurse", "nurse_administrator",
            "medical_director", "chief_medical_officer"
        ]
        guard let user = authManager.currentUser else { return false }
        var roles = user.activeRoles ?? []
        if let primary = user.primaryRole { roles.append(primary) }
        return !roles.filter { clinicianRoles.contains($0) }.isEmpty
    }

    var body: some View {
        NavigationStack {
            List {
                Section("ALAFIA Membership") {
                    NavigationLink {
                        SubscriptionView()
                    } label: {
                        Label("Subscription", systemImage: "sparkles")
                            .foregroundStyle(Color(red: 0.49, green: 0.30, blue: 1.0))
                    }
                }

                Section("Health Tracking") {
                    NavigationLink {
                        LabsView()
                    } label: {
                        Label("Labs / EHR", systemImage: "flask.fill")
                            .foregroundStyle(.purple)
                    }

                    NavigationLink {
                        LabChartsView()
                    } label: {
                        Label("Lab Charts", systemImage: "chart.line.uptrend.xyaxis")
                            .foregroundStyle(.blue)
                    }

                    NavigationLink {
                        MedicationsView()
                    } label: {
                        Label("Medications", systemImage: "pills.fill")
                            .foregroundStyle(.orange)
                    }

                    NavigationLink {
                        LifestyleView()
                    } label: {
                        Label("Lifestyle & Vitals", systemImage: "heart.fill")
                            .foregroundStyle(.red)
                    }

                    NavigationLink {
                        EliminationView()
                    } label: {
                        Label("Elimination", systemImage: "drop.triangle.fill")
                            .foregroundStyle(.brown)
                    }

                    NavigationLink {
                        WellnessView()
                    } label: {
                        Label("Wellness", systemImage: "gauge.with.dots.needle.67percent")
                            .foregroundStyle(.green)
                    }

                    NavigationLink {
                        ChartDashboardView()
                    } label: {
                        Label("Chart Dashboard", systemImage: "chart.bar.xaxis")
                            .foregroundStyle(.indigo)
                    }

                    NavigationLink {
                        WeightTrendView()
                    } label: {
                        Label("Weight Trend", systemImage: "scalemass.fill")
                            .foregroundStyle(.green)
                    }
                }

                Section("Mental Health") {
                    NavigationLink {
                        MoodView()
                    } label: {
                        Label("Mood", systemImage: "brain")
                            .foregroundStyle(.pink)
                    }

                    NavigationLink {
                        MentalHealthView()
                    } label: {
                        Label("Mental Health", systemImage: "brain.head.profile.fill")
                            .foregroundStyle(.teal)
                    }
                }

                Section("Community") {
                    NavigationLink {
                        CommunityHealthView()
                    } label: {
                        Label("Community Health", systemImage: "globe.americas.fill")
                            .foregroundStyle(.blue)
                    }

                    NavigationLink {
                        FacilitiesView()
                    } label: {
                        Label("Facility Directory", systemImage: "building.2.fill")
                            .foregroundStyle(.teal)
                    }

                    NavigationLink {
                        FDARecallsView()
                    } label: {
                        Label("Food & Drug Recalls", systemImage: "exclamationmark.shield.fill")
                            .foregroundStyle(.orange)
                    }

                    NavigationLink {
                        SurveillanceView()
                    } label: {
                        Label("Disease Surveillance", systemImage: "dot.radiowaves.left.and.right")
                            .foregroundStyle(.red)
                    }
                }

                Section("Planning") {
                    NavigationLink {
                        MealPlannerView()
                    } label: {
                        Label("Meal Planner", systemImage: "fork.knife")
                            .foregroundStyle(.orange)
                    }

                    NavigationLink {
                        ExercisePlannerView()
                    } label: {
                        Label("Exercise Planner", systemImage: "figure.walk")
                            .foregroundStyle(.cyan)
                    }

                    NavigationLink {
                        PantryView()
                    } label: {
                        Label("Pantry & Fridge", systemImage: "refrigerator.fill")
                            .foregroundStyle(.brown)
                    }

                    NavigationLink {
                        CalendarView()
                    } label: {
                        Label("Calendar", systemImage: "calendar")
                            .foregroundStyle(.cyan)
                    }
                }

                Section("Care") {
                    NavigationLink {
                        TelehealthView()
                    } label: {
                        Label("Telehealth", systemImage: "video.fill")
                            .foregroundStyle(.mint)
                    }

                    NavigationLink {
                        MessagingView()
                    } label: {
                        Label("Messages", systemImage: "message.fill")
                            .foregroundStyle(.indigo)
                    }

                    NavigationLink {
                        PhysicianDirectoryView()
                    } label: {
                        Label("Physician Directory", systemImage: "stethoscope")
                            .foregroundStyle(.indigo)
                    }

                    NavigationLink {
                        PharmacyView()
                    } label: {
                        Label("Pharmacy", systemImage: "cross.vial.fill")
                            .foregroundStyle(.teal)
                    }

                    if isClinician {
                        NavigationLink {
                            ClinicianDashboardView()
                        } label: {
                            Label("Clinician Dashboard", systemImage: "list.clipboard")
                                .foregroundStyle(.blue)
                        }
                    }
                }

                Section("Therapies") {
                    NavigationLink {
                        HemodialysisView()
                    } label: {
                        Label("Hemodialysis", systemImage: "waveform.path.ecg")
                            .foregroundStyle(.blue)
                    }

                    NavigationLink {
                        PeritonealDialysisView()
                    } label: {
                        Label("Peritoneal Dialysis", systemImage: "drop.fill")
                            .foregroundStyle(.teal)
                    }

                    NavigationLink {
                        ChemotherapyView()
                    } label: {
                        Label("Chemotherapy", systemImage: "cross.vial")
                            .foregroundStyle(.purple)
                    }
                }

                Section("Tools") {
                    NavigationLink {
                        ImageAIView()
                    } label: {
                        Label("Image AI", systemImage: "camera.viewfinder")
                            .foregroundStyle(.purple)
                    }

                    NavigationLink {
                        PdfToolsView()
                    } label: {
                        Label("PDF Tools", systemImage: "doc.text")
                            .foregroundStyle(.brown)
                    }

                    NavigationLink {
                        DataSharingView()
                    } label: {
                        Label("Data Sharing", systemImage: "square.and.arrow.up")
                            .foregroundStyle(.indigo)
                    }
                }

                Section("Profile") {
                    NavigationLink {
                        RolesView()
                    } label: {
                        Label("Role", systemImage: "person.2.badge.gearshape")
                            .foregroundStyle(.indigo)
                    }

                    NavigationLink {
                        ChronicConditionsView()
                    } label: {
                        Label("Health Conditions", systemImage: "heart.text.square")
                            .foregroundStyle(.red)
                    }

                    NavigationLink {
                        AdvancedDirectivesView()
                    } label: {
                        Label("Advanced Directives", systemImage: "heart.text.square.fill")
                            .foregroundStyle(.red)
                    }

                    NavigationLink {
                        InsuranceView()
                    } label: {
                        Label("Insurance Plans", systemImage: "shield.lefthalf.filled")
                            .foregroundStyle(.green)
                    }

                    NavigationLink {
                        HealthSyncView()
                    } label: {
                        Label("Health Sync", systemImage: "arrow.triangle.2.circlepath")
                            .foregroundStyle(.green)
                    }

                    NavigationLink {
                        PrivacySettingsView()
                    } label: {
                        Label("Privacy Settings", systemImage: "lock.shield")
                            .foregroundStyle(.gray)
                    }
                }

                // Footer of the hub — the same public pages the web
                // footer carries. They are web pages, so they open in Safari.
                Section {
                    ForEach(Self.supportLinks, id: \.path) { link in
                        if let url = AppConfig.webURL(link.path) {
                            Link(destination: url) {
                                Label(link.title, systemImage: link.icon)
                                    .foregroundStyle(.orange)
                            }
                        }
                    }
                } header: {
                    Text("Support")
                } footer: {
                    Text("Opens alafia.app in your browser.")
                }
            }
            .navigationTitle("Health Hub")
        }
    }
}
