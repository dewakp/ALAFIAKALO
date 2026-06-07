import SwiftUI

// MARK: - ViewModel

@Observable
final class CommunityHealthViewModel {
    var isLoading = false
    var errorMessage: String?
    var stats: CommunityDashboardStats?
    var alerts: [CommunityHealthAlert] = []
    var guidelines: [HealthGuideline] = []
    var reports: [CommunityHealthReport] = []
    var categories: [AlertCategoryInfo] = []
    var sources: [AlertSourceInfo] = []

    func loadAll() async {
        isLoading = true
        errorMessage = nil
        do {
            async let s: CommunityDashboardStats = APIClient.shared.get("/community/dashboard")
            async let a: [CommunityHealthAlert] = APIClient.shared.get("/community/alerts")
            async let g: [HealthGuideline] = APIClient.shared.get("/community/guidelines")
            async let r: [CommunityHealthReport] = APIClient.shared.get("/community/reports")
            async let c: [AlertCategoryInfo] = APIClient.shared.get("/community/categories")
            async let src: [AlertSourceInfo] = APIClient.shared.get("/community/sources")
            let (statsVal, alertsVal, guidelinesVal, reportsVal, catsVal, srcsVal) = try await (s, a, g, r, c, src)
            stats = statsVal
            alerts = alertsVal
            guidelines = guidelinesVal
            reports = reportsVal
            categories = catsVal
            sources = srcsVal
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }

    func submitReport(_ report: ReportCreate) async {
        do {
            let _: CommunityHealthReport = try await APIClient.shared.post("/community/reports", body: report)
            await loadAll()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func toggleBookmark(_ alertId: Int) async {
        do {
            let _: [String: Bool] = try await APIClient.shared.post("/community/alerts/\(alertId)/bookmark", body: EmptyBody())
            await loadAll()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func seedData() async {
        do {
            let _: [String: String] = try await APIClient.shared.post("/community/seed", body: EmptyBody())
            await loadAll()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func deleteReport(_ reportId: Int) async {
        do {
            try await APIClient.shared.delete("/community/reports/\(reportId)")
            reports.removeAll { $0.id == reportId }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func loadSubscription() async -> AlertSubscription? {
        do {
            return try await APIClient.shared.get("/community/subscriptions")
        } catch {
            return nil
        }
    }

    func saveSubscription(_ sub: SubscriptionCreate) async {
        do {
            let _: AlertSubscription = try await APIClient.shared.put("/community/subscriptions", body: sub)
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

// MARK: - Main View

struct CommunityHealthView: View {
    @State private var vm = CommunityHealthViewModel()
    @State private var selectedTab = 0
    @State private var selectedAlert: CommunityHealthAlert?
    @State private var selectedGuideline: HealthGuideline?
    @State private var showReportForm = false
    @State private var alertSearch = ""
    @State private var alertCategoryFilter = "all"
    @State private var alertSeverityFilter = "all"
    @State private var guidelineSearch = ""
    @State private var guidelineCategoryFilter = "all"

    var body: some View {
            Group {
                if vm.isLoading && vm.stats == nil {
                    ProgressView("Loading community health data...")
                } else if let error = vm.errorMessage, vm.stats == nil {
                    VStack(spacing: 12) {
                        Image(systemName: "exclamationmark.triangle")
                            .font(.largeTitle)
                            .foregroundStyle(.orange)
                        Text(error)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Button("Retry") { Task { await vm.loadAll() } }
                    }
                } else {
                    VStack(spacing: 0) {
                        Picker("Section", selection: $selectedTab) {
                            Text("Dashboard").tag(0)
                            Text("Alerts").tag(1)
                            Text("Guidelines").tag(2)
                            Text("Reports").tag(3)
                            Text("Settings").tag(4)
                        }
                        .pickerStyle(.segmented)
                        .padding()

                        switch selectedTab {
                        case 0: dashboardTab
                        case 1: alertsTab
                        case 2: guidelinesTab
                        case 3: reportsTab
                        case 4: subscriptionSettingsTab
                        default: EmptyView()
                        }
                    }
                }
            }
            .navigationTitle("🌍 Community Health")
            .task { await vm.loadAll() }
            .refreshable { await vm.loadAll() }
            .sheet(item: $selectedAlert) { alert in
                AlertDetailSheet(alert: alert, onBookmark: { Task { await vm.toggleBookmark(alert.id) } })
            }
            .sheet(item: $selectedGuideline) { guideline in
                GuidelineDetailSheet(guideline: guideline)
            }
            .sheet(isPresented: $showReportForm) {
                ReportFormSheet { report in
                    Task { await vm.submitReport(report) }
                    showReportForm = false
                }
            }
    }

    // MARK: - Dashboard Tab

    @ViewBuilder
    private var dashboardTab: some View {
        ScrollView {
            if let s = vm.stats {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 100))], spacing: 12) {
                    CommunityStatCard(icon: "🚨", value: s.totalActiveAlerts, label: "Active Alerts", color: .blue)
                    CommunityStatCard(icon: "🔴", value: s.criticalAlerts, label: "Critical", color: .red)
                    CommunityStatCard(icon: "💊", value: s.activeRecalls, label: "Recalls", color: .orange)
                    CommunityStatCard(icon: "🦠", value: s.activeOutbreaks, label: "Outbreaks", color: .purple)
                    CommunityStatCard(icon: "📢", value: s.activeAdvisories, label: "Advisories", color: .indigo)
                    CommunityStatCard(icon: "☠️", value: s.activePoisonAlerts, label: "Poison", color: .brown)
                    CommunityStatCard(icon: "📋", value: s.totalGuidelines, label: "Guidelines", color: .green)
                    CommunityStatCard(icon: "📬", value: s.unreadAlerts, label: "Unread", color: .pink)
                }
                .padding(.horizontal)

                if !s.latestOutbreaks.isEmpty {
                    sectionHeader("🦠 Latest Outbreaks")
                    ForEach(s.latestOutbreaks) { alert in
                        AlertRow(alert: alert)
                            .onTapGesture { selectedAlert = alert }
                    }
                    .padding(.horizontal)
                }

                if !s.latestRecalls.isEmpty {
                    sectionHeader("💊 Recent Recalls")
                    ForEach(s.latestRecalls) { alert in
                        AlertRow(alert: alert)
                            .onTapGesture { selectedAlert = alert }
                    }
                    .padding(.horizontal)
                }

                if !s.latestAdvisories.isEmpty {
                    sectionHeader("📢 Active Advisories")
                    ForEach(s.latestAdvisories) { alert in
                        AlertRow(alert: alert)
                            .onTapGesture { selectedAlert = alert }
                    }
                    .padding(.horizontal)
                }
            }
        }
    }

    // MARK: - Alerts Tab

    private var filteredAlerts: [CommunityHealthAlert] {
        vm.alerts.filter { alert in
            let matchesSearch = alertSearch.isEmpty || alert.title.localizedCaseInsensitiveContains(alertSearch) ||
                (alert.summary ?? "").localizedCaseInsensitiveContains(alertSearch)
            let matchesCategory = alertCategoryFilter == "all" || alert.category == alertCategoryFilter
            let matchesSeverity = alertSeverityFilter == "all" || alert.severity == alertSeverityFilter
            return matchesSearch && matchesCategory && matchesSeverity
        }
    }

    @ViewBuilder
    private var alertsTab: some View {
        VStack(spacing: 0) {
            // Search bar
            HStack {
                Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                TextField("Search alerts...", text: $alertSearch)
            }
            .padding(10)
            .background(Color(.secondarySystemBackground))
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .padding(.horizontal)
            .padding(.bottom, 4)

            // Filter chips
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    filterChip("All", isSelected: alertCategoryFilter == "all") { alertCategoryFilter = "all" }
                    ForEach(vm.categories, id: \.name) { cat in
                        filterChip(cat.name.replacingOccurrences(of: "_", with: " ").capitalized, isSelected: alertCategoryFilter == cat.name) { alertCategoryFilter = cat.name }
                    }
                }
                .padding(.horizontal)
            }
            .padding(.bottom, 4)

            // Severity filter
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    filterChip("All Severity", isSelected: alertSeverityFilter == "all") { alertSeverityFilter = "all" }
                    ForEach(["critical", "high", "moderate", "low", "info"], id: \.self) { sev in
                        filterChip(sev.capitalized, isSelected: alertSeverityFilter == sev) { alertSeverityFilter = sev }
                    }
                }
                .padding(.horizontal)
            }
            .padding(.bottom, 8)

            if filteredAlerts.isEmpty {
                Spacer()
                ContentUnavailableView("No Alerts", systemImage: "checkmark.circle", description: Text(alertSearch.isEmpty ? "No active alerts at this time" : "No alerts match your filters"))
                Spacer()
            } else {
                List(filteredAlerts) { alert in
                    AlertRow(alert: alert)
                        .onTapGesture { selectedAlert = alert }
                        .listRowSeparator(.hidden)
                }
                .listStyle(.plain)
            }
        }
    }

    // MARK: - Guidelines Tab

    private var filteredGuidelines: [HealthGuideline] {
        vm.guidelines.filter { g in
            let matchesSearch = guidelineSearch.isEmpty || g.title.localizedCaseInsensitiveContains(guidelineSearch) ||
                (g.summary ?? "").localizedCaseInsensitiveContains(guidelineSearch)
            let matchesCategory = guidelineCategoryFilter == "all" || g.category == guidelineCategoryFilter
            return matchesSearch && matchesCategory
        }
    }

    @ViewBuilder
    private var guidelinesTab: some View {
        VStack(spacing: 0) {
            // Search bar
            HStack {
                Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                TextField("Search guidelines...", text: $guidelineSearch)
            }
            .padding(10)
            .background(Color(.secondarySystemBackground))
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .padding(.horizontal)
            .padding(.bottom, 4)

            // Category filter
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    filterChip("All", isSelected: guidelineCategoryFilter == "all") { guidelineCategoryFilter = "all" }
                    ForEach(["clinical_practice", "public_health", "preventive_care", "chronic_disease", "infectious_disease",
                             "mental_health", "nutrition", "maternal_child", "immunization", "emergency",
                             "environmental", "occupational", "general"], id: \.self) { cat in
                        filterChip(cat.replacingOccurrences(of: "_", with: " ").capitalized, isSelected: guidelineCategoryFilter == cat) {
                            guidelineCategoryFilter = cat
                        }
                    }
                }
                .padding(.horizontal)
            }
            .padding(.bottom, 8)

            if filteredGuidelines.isEmpty {
                Spacer()
                ContentUnavailableView("No Guidelines", systemImage: "doc.text", description: Text(guidelineSearch.isEmpty ? "No guidelines available" : "No guidelines match your filters"))
                Spacer()
            } else {
                List(filteredGuidelines) { guideline in
                    GuidelineRow(guideline: guideline)
                        .onTapGesture { selectedGuideline = guideline }
                        .listRowSeparator(.hidden)
                }
                .listStyle(.plain)
            }
        }
    }

    // MARK: - Reports Tab

    @ViewBuilder
    private var reportsTab: some View {
        VStack {
            HStack {
                Spacer()
                Button("Submit Report") { showReportForm = true }
                    .buttonStyle(.borderedProminent)
                    .tint(.green)
            }
            .padding(.horizontal)
            .padding(.top, 8)

            if vm.reports.isEmpty {
                Spacer()
                ContentUnavailableView("No Reports", systemImage: "doc.badge.plus",
                    description: Text("Submit a community health report"))
                Spacer()
            } else {
                List {
                    ForEach(vm.reports) { report in
                        ReportRow(report: report)
                            .listRowSeparator(.hidden)
                    }
                    .onDelete { indexSet in
                        Task {
                            for index in indexSet {
                                await vm.deleteReport(vm.reports[index].id)
                            }
                        }
                    }
                }
                .listStyle(.plain)
            }
        }
    }

    // MARK: - Subscription Settings Tab

    @ViewBuilder
    private var subscriptionSettingsTab: some View {
        CommunitySubscriptionSettingsView(vm: vm)
    }

    // MARK: - Filter Chip Helper

    private func filterChip(_ title: String, isSelected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 12, weight: isSelected ? .semibold : .regular))
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(isSelected ? Color.accentColor : Color(.secondarySystemBackground))
                .foregroundStyle(isSelected ? .white : .primary)
                .clipShape(Capsule())
        }
    }

    private func sectionHeader(_ title: String) -> some View {
        Text(title)
            .font(.headline)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal)
            .padding(.top, 16)
            .padding(.bottom, 4)
    }
}

// MARK: - Stat Card

private struct CommunityStatCard: View {
    let icon: String
    let value: Int
    let label: String
    let color: Color

    var body: some View {
        VStack(spacing: 4) {
            Text(icon).font(.title2)
            Text("\(value)").font(.title2).bold().foregroundStyle(color)
            Text(label).font(.caption2).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
        .background(color.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}

// MARK: - Alert Row

private struct AlertRow: View {
    let alert: CommunityHealthAlert

    var severityColor: Color {
        switch alert.severity {
        case "critical": return .red
        case "high": return .orange
        case "moderate": return .yellow
        case "low": return .green
        case "info": return .blue
        default: return .gray
        }
    }

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Text(alert.categoryIcon)
                .font(.title3)

            VStack(alignment: .leading, spacing: 4) {
                Text(alert.title)
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .lineLimit(2)

                if let summary = alert.summary {
                    Text(summary)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }

                HStack(spacing: 6) {
                    Text(alert.severity.uppercased())
                        .font(.system(size: 9, weight: .bold))
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(severityColor.opacity(0.2))
                        .foregroundStyle(severityColor)
                        .clipShape(Capsule())

                    Text(alert.source.uppercased())
                        .font(.system(size: 9, weight: .bold))
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(.blue.opacity(0.1))
                        .foregroundStyle(.blue)
                        .clipShape(Capsule())

                    if alert.isGlobal {
                        Text("🌍 Global")
                            .font(.system(size: 9))
                    }

                    if let cases = alert.confirmedCases {
                        Text("📊 \(cases)")
                            .font(.system(size: 9))
                            .foregroundStyle(.red)
                    }

                    if let date = alert.issuedDate {
                        Text(date)
                            .font(.system(size: 9))
                            .foregroundStyle(.tertiary)
                    }
                }
            }

            Spacer()
            Image(systemName: "chevron.right")
                .font(.caption)
                .foregroundStyle(.tertiary)
        }
        .padding(12)
        .background(Color(.systemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .shadow(color: .black.opacity(0.05), radius: 4, y: 2)
    }
}

// MARK: - Alert Detail Sheet

private struct AlertDetailSheet: View {
    let alert: CommunityHealthAlert
    let onBookmark: () -> Void
    @Environment(\.dismiss) var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    // Header
                    HStack(spacing: 8) {
                        Text(alert.categoryIcon).font(.title)
                        VStack(alignment: .leading) {
                            HStack(spacing: 4) {
                                Text(alert.severity.uppercased())
                                    .font(.system(size: 10, weight: .bold))
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background(AlertRow(alert: alert).severityColor.opacity(0.2))
                                    .clipShape(Capsule())
                                Text(alert.source.uppercased())
                                    .font(.system(size: 10, weight: .bold))
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background(.blue.opacity(0.1))
                                    .foregroundStyle(.blue)
                                    .clipShape(Capsule())
                                if alert.isGlobal {
                                    Text("🌍 Global")
                                        .font(.system(size: 10))
                                }
                            }
                        }
                    }

                    Text(alert.title)
                        .font(.title2)
                        .fontWeight(.bold)

                    if let summary = alert.summary {
                        Text(summary)
                            .foregroundStyle(.secondary)
                    }

                    if let description = alert.description {
                        Text(description)
                            .font(.callout)
                    }

                    // Dates
                    if alert.issuedDate != nil || alert.effectiveDate != nil {
                        detailSection("📅 Dates") {
                            if let d = alert.issuedDate { detailRow("Issued", d) }
                            if let d = alert.effectiveDate { detailRow("Effective", d) }
                            if let d = alert.expiryDate { detailRow("Expires", d) }
                        }
                    }

                    // Outbreak details
                    if let disease = alert.diseaseName {
                        detailSection("🦠 Outbreak Details") {
                            detailRow("Disease", disease)
                            if let p = alert.pathogen { detailRow("Pathogen", p) }
                            if let c = alert.confirmedCases { detailRow("Confirmed Cases", "\(c)") }
                            if let d = alert.deaths { detailRow("Deaths", "\(d)") }
                        }
                    }

                    // Recall details
                    if let product = alert.productName {
                        detailSection("📦 Recall Details") {
                            detailRow("Product", product)
                            if let t = alert.productType { detailRow("Type", t) }
                            if let m = alert.manufacturer { detailRow("Manufacturer", m) }
                            if let c = alert.recallClass { detailRow("Class", "Class \(c)") }
                            if let r = alert.reasonForRecall { detailRow("Reason", r) }
                            if let lots = alert.lotNumbers, !lots.isEmpty {
                                detailRow("Lot Numbers", lots.joined(separator: ", "))
                            }
                        }
                    }

                    // Affected areas
                    if let countries = alert.affectedCountries, !countries.isEmpty {
                        detailSection("📍 Affected Areas") {
                            detailRow("Countries", countries.joined(separator: ", "))
                            if let regions = alert.affectedRegions, !regions.isEmpty {
                                detailRow("Regions", regions.joined(separator: ", "))
                            }
                        }
                    }

                    // Recommended actions
                    if let actions = alert.recommendedActions, !actions.isEmpty {
                        detailSection("✅ Recommended Actions") {
                            ForEach(actions, id: \.self) { action in
                                HStack(alignment: .top, spacing: 8) {
                                    Text("•").foregroundStyle(.green)
                                    Text(action).font(.callout)
                                }
                            }
                        }
                    }

                    // Target population
                    if let pop = alert.targetPopulation, !pop.isEmpty {
                        detailSection("👥 Target Population") {
                            CommunityFlowLayout(spacing: 4) {
                                ForEach(pop, id: \.self) { p in
                                    Text(p)
                                        .font(.caption)
                                        .padding(.horizontal, 8)
                                        .padding(.vertical, 4)
                                        .background(.gray.opacity(0.1))
                                        .clipShape(Capsule())
                                }
                            }
                        }
                    }

                    // Source link
                    if let url = alert.sourceUrl, let link = URL(string: url) {
                        Link(destination: link) {
                            Label("View Original Source", systemImage: "link")
                                .font(.callout)
                        }
                        .padding(.top, 8)
                    }

                    // Tags
                    if let tags = alert.tags, !tags.isEmpty {
                        HStack(spacing: 4) {
                            ForEach(tags, id: \.self) { tag in
                                Text("#\(tag)")
                                    .font(.system(size: 10))
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
                .padding()
            }
            .navigationTitle("Alert Details")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Done") { dismiss() }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button(action: onBookmark) {
                        Image(systemName: "bookmark")
                    }
                }
            }
        }
    }

    private func detailSection(_ title: String, @ViewBuilder content: () -> some View) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).font(.headline)
            content()
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func detailRow(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label).font(.caption).foregroundStyle(.secondary)
            Spacer()
            Text(value).font(.callout).fontWeight(.medium)
        }
    }
}

// MARK: - Guideline Row

private struct GuidelineRow: View {
    let guideline: HealthGuideline

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Text("📋").font(.title3)
            VStack(alignment: .leading, spacing: 4) {
                Text(guideline.title)
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .lineLimit(2)
                if let summary = guideline.summary {
                    Text(summary)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
                HStack(spacing: 6) {
                    Text(guideline.source.uppercased())
                        .font(.system(size: 9, weight: .bold))
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(.green.opacity(0.1))
                        .foregroundStyle(.green)
                        .clipShape(Capsule())
                    Text(guideline.category.replacingOccurrences(of: "_", with: " ").capitalized)
                        .font(.system(size: 9))
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(.teal.opacity(0.1))
                        .clipShape(Capsule())
                    if let v = guideline.version {
                        Text("v\(v)").font(.system(size: 9)).foregroundStyle(.tertiary)
                    }
                }
            }
            Spacer()
            Image(systemName: "chevron.right")
                .font(.caption)
                .foregroundStyle(.tertiary)
        }
        .padding(12)
        .background(Color(.systemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .shadow(color: .black.opacity(0.05), radius: 4, y: 2)
    }
}

// MARK: - Guideline Detail Sheet

private struct GuidelineDetailSheet: View {
    let guideline: HealthGuideline
    @Environment(\.dismiss) var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    HStack(spacing: 6) {
                        Text(guideline.source.uppercased())
                            .font(.system(size: 11, weight: .bold))
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(.green.opacity(0.15))
                            .foregroundStyle(.green)
                            .clipShape(Capsule())
                        Text(guideline.category.replacingOccurrences(of: "_", with: " ").capitalized)
                            .font(.caption)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(.teal.opacity(0.1))
                            .clipShape(Capsule())
                        if guideline.isCurrent {
                            Text("✅ Current")
                                .font(.caption)
                                .foregroundStyle(.green)
                        }
                    }

                    Text(guideline.title)
                        .font(.title2)
                        .fontWeight(.bold)

                    if let summary = guideline.summary {
                        Text(summary).foregroundStyle(.secondary)
                    }

                    if let text = guideline.fullText {
                        Text(text).font(.callout)
                    }

                    if let recs = guideline.recommendations, !recs.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("📌 Key Recommendations").font(.headline)
                            ForEach(Array(recs.enumerated()), id: \.offset) { _, rec in
                                HStack(alignment: .top, spacing: 8) {
                                    Text("•").foregroundStyle(.green)
                                    Text(rec).font(.callout)
                                }
                            }
                        }
                        .padding()
                        .background(Color(.secondarySystemBackground))
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                    }

                    if let date = guideline.effectiveDate {
                        HStack {
                            Text("Effective:").font(.caption).foregroundStyle(.secondary)
                            Text(date).font(.callout).fontWeight(.medium)
                        }
                    }

                    if let pop = guideline.targetPopulation, !pop.isEmpty {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("👥 Target Population").font(.caption).fontWeight(.semibold)
                            CommunityFlowLayout(spacing: 4) {
                                ForEach(pop, id: \.self) { p in
                                    Text(p)
                                        .font(.caption)
                                        .padding(.horizontal, 8)
                                        .padding(.vertical, 4)
                                        .background(.gray.opacity(0.1))
                                        .clipShape(Capsule())
                                }
                            }
                        }
                    }

                    if let url = guideline.sourceUrl, let link = URL(string: url) {
                        Link(destination: link) {
                            Label("View Full Guideline", systemImage: "link")
                                .font(.callout)
                        }
                    }

                    if let tags = guideline.tags, !tags.isEmpty {
                        HStack(spacing: 4) {
                            ForEach(tags, id: \.self) { tag in
                                Text("#\(tag)")
                                    .font(.system(size: 10))
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
                .padding()
            }
            .navigationTitle("Guideline")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}

// MARK: - Report Row

private struct ReportRow: View {
    let report: CommunityHealthReport

    var severityColor: Color {
        switch report.severity {
        case "critical": return .red
        case "high": return .orange
        case "moderate": return .yellow
        case "low": return .green
        default: return .gray
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Text(report.severity?.uppercased() ?? "")
                    .font(.system(size: 9, weight: .bold))
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(severityColor.opacity(0.2))
                    .clipShape(Capsule())
                Text(report.reportType.replacingOccurrences(of: "_", with: " ").capitalized)
                    .font(.system(size: 9))
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(.gray.opacity(0.1))
                    .clipShape(Capsule())
                if report.isVerified {
                    Text("✅ Verified")
                        .font(.system(size: 9))
                        .foregroundStyle(.green)
                }
                if let loc = report.locationName {
                    Text("📍 \(loc)")
                        .font(.system(size: 9))
                        .foregroundStyle(.secondary)
                }
            }
            Text(report.title).font(.subheadline).fontWeight(.semibold)
            if let desc = report.description {
                Text(desc).font(.caption).foregroundStyle(.secondary).lineLimit(2)
            }
            if let symptoms = report.symptomsReported, !symptoms.isEmpty {
                HStack(spacing: 4) {
                    ForEach(symptoms, id: \.self) { s in
                        Text(s)
                            .font(.system(size: 9))
                            .padding(.horizontal, 4)
                            .padding(.vertical, 1)
                            .background(.red.opacity(0.1))
                            .foregroundStyle(.red)
                            .clipShape(Capsule())
                    }
                }
            }
        }
        .padding(12)
        .background(Color(.systemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .shadow(color: .black.opacity(0.05), radius: 4, y: 2)
    }
}

// MARK: - Report Form Sheet

private struct ReportFormSheet: View {
    let onSubmit: (ReportCreate) -> Void
    @Environment(\.dismiss) var dismiss
    @State private var form = ReportCreate()
    @State private var symptomsText = ""

    let reportTypes = ["symptom_cluster", "food_contamination", "water_contamination", "air_quality",
        "disease_outbreak", "drug_reaction", "poisoning", "environmental_hazard", "vaccine_reaction", "other"]

    var body: some View {
        NavigationStack {
            Form {
                Section("Report Details") {
                    Picker("Type", selection: $form.reportType) {
                        ForEach(reportTypes, id: \.self) { t in
                            Text(t.replacingOccurrences(of: "_", with: " ").capitalized).tag(t)
                        }
                    }
                    TextField("Title", text: $form.title)
                    TextField("Description", text: $form.description, axis: .vertical)
                        .lineLimit(3...6)
                    Picker("Severity", selection: $form.severity) {
                        Text("Info").tag("info")
                        Text("Low").tag("low")
                        Text("Moderate").tag("moderate")
                        Text("High").tag("high")
                        Text("Critical").tag("critical")
                    }
                }

                Section("Location") {
                    TextField("Location Name", text: Binding(
                        get: { form.locationName ?? "" },
                        set: { form.locationName = $0.isEmpty ? nil : $0 }
                    ))
                    TextField("Country (ISO code)", text: Binding(
                        get: { form.country ?? "" },
                        set: { form.country = $0.isEmpty ? nil : $0 }
                    ))
                }

                Section("Details") {
                    Stepper("# Affected: \(form.numberAffected)", value: $form.numberAffected, in: 1...10000)
                    TextField("Symptoms (comma-separated)", text: $symptomsText)
                }
            }
            .navigationTitle("Submit Report")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Submit") {
                        var report = form
                        if !symptomsText.isEmpty {
                            report.symptomsReported = symptomsText.components(separatedBy: ",").map { $0.trimmingCharacters(in: .whitespaces) }
                        }
                        onSubmit(report)
                    }
                    .disabled(form.title.isEmpty)
                    .fontWeight(.bold)
                }
            }
        }
    }
}

// MARK: - Subscription Settings View

private struct CommunitySubscriptionSettingsView: View {
    let vm: CommunityHealthViewModel
    @State private var isLoading = true
    @State private var categories: [String] = []
    @State private var sources: [String] = []
    @State private var severities: [String] = []
    @State private var countries: [String] = []
    @State private var pushEnabled = true
    @State private var emailEnabled = false
    @State private var smsEnabled = false
    @State private var countryInput = ""
    @State private var saving = false

    let allCategories = ["disease_outbreak", "drug_recall", "food_recall", "medical_device_recall",
        "safety_advisory", "travel_advisory", "environmental_hazard", "public_health_emergency",
        "vaccine_update", "drug_safety", "food_safety", "water_safety", "air_quality",
        "chemical_exposure", "radiation", "natural_disaster", "biological_threat"]

    let allSeverities = ["info", "low", "moderate", "high", "critical"]

    let allSources = ["who", "cdc", "fda", "ema", "ecdc", "paho", "local_health",
        "state_health", "national_health", "hospital", "research", "public_report"]

    var body: some View {
        Form {
            Section("Alert Categories") {
                Text("Select which alert types you want to receive:")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                CommunityFlowLayout(spacing: 6) {
                    ForEach(allCategories, id: \.self) { cat in
                        toggleChip(cat.replacingOccurrences(of: "_", with: " ").capitalized,
                                   isSelected: categories.contains(cat)) {
                            if categories.contains(cat) { categories.removeAll { $0 == cat } }
                            else { categories.append(cat) }
                        }
                    }
                }
            }

            Section("Sources") {
                CommunityFlowLayout(spacing: 6) {
                    ForEach(allSources, id: \.self) { src in
                        toggleChip(src.uppercased(),
                                   isSelected: sources.contains(src)) {
                            if sources.contains(src) { sources.removeAll { $0 == src } }
                            else { sources.append(src) }
                        }
                    }
                }
            }

            Section("Severity Levels") {
                CommunityFlowLayout(spacing: 6) {
                    ForEach(allSeverities, id: \.self) { sev in
                        toggleChip(sev.capitalized,
                                   isSelected: severities.contains(sev)) {
                            if severities.contains(sev) { severities.removeAll { $0 == sev } }
                            else { severities.append(sev) }
                        }
                    }
                }
            }

            Section("Countries (ISO codes)") {
                HStack {
                    TextField("Add country code", text: $countryInput)
                        .textInputAutocapitalization(.characters)
                    Button("Add") {
                        let code = countryInput.trimmingCharacters(in: .whitespaces).uppercased()
                        if !code.isEmpty && !countries.contains(code) {
                            countries.append(code)
                            countryInput = ""
                        }
                    }
                    .disabled(countryInput.trimmingCharacters(in: .whitespaces).isEmpty)
                }
                if !countries.isEmpty {
                    CommunityFlowLayout(spacing: 4) {
                        ForEach(countries, id: \.self) { c in
                            HStack(spacing: 2) {
                                Text(c).font(.caption)
                                Button { countries.removeAll { $0 == c } } label: {
                                    Image(systemName: "xmark.circle.fill")
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                }
                            }
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(Color(.secondarySystemBackground))
                            .clipShape(Capsule())
                        }
                    }
                }
            }

            Section("Notification Channels") {
                Toggle("Push Notifications", isOn: $pushEnabled)
                Toggle("Email Notifications", isOn: $emailEnabled)
                Toggle("SMS Notifications", isOn: $smsEnabled)
            }

            Section {
                Button(action: save) {
                    HStack {
                        Spacer()
                        Text(saving ? "Saving..." : "Save Preferences")
                            .fontWeight(.semibold)
                        Spacer()
                    }
                }
                .disabled(saving)
            }
        }
        .task { await loadSubscription() }
    }

    private func loadSubscription() async {
        if let sub = await vm.loadSubscription() {
            categories = sub.categories ?? []
            sources = sub.sources ?? []
            severities = sub.severities ?? []
            countries = sub.countries ?? []
            pushEnabled = sub.pushEnabled
            emailEnabled = sub.emailEnabled
            smsEnabled = sub.smsEnabled
        }
        isLoading = false
    }

    private func save() {
        saving = true
        Task {
            let sub = SubscriptionCreate(
                categories: categories.isEmpty ? [] : categories,
                sources: sources.isEmpty ? [] : sources,
                countries: countries.isEmpty ? [] : countries,
                severities: severities.isEmpty ? ["critical", "high"] : severities,
                pushEnabled: pushEnabled,
                emailEnabled: emailEnabled,
                smsEnabled: smsEnabled
            )
            await vm.saveSubscription(sub)
            saving = false
        }
    }

    @ViewBuilder
    private func toggleChip(_ title: String, isSelected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 11, weight: isSelected ? .semibold : .regular))
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(isSelected ? Color.accentColor.opacity(0.2) : Color(.tertiarySystemBackground))
                .foregroundStyle(isSelected ? Color.accentColor : Color.secondary)
                .clipShape(Capsule())
                .overlay(Capsule().stroke(isSelected ? Color.accentColor : Color.clear, lineWidth: 1))
        }
    }
}

// MARK: - Flow Layout Helper

private struct CommunityFlowLayout: Layout {
    var spacing: CGFloat = 4

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let sizes = subviews.map { $0.sizeThatFits(.unspecified) }
        var width: CGFloat = 0
        var height: CGFloat = 0
        var lineWidth: CGFloat = 0
        var lineHeight: CGFloat = 0
        let maxWidth = proposal.width ?? .infinity

        for size in sizes {
            if lineWidth + size.width > maxWidth && lineWidth > 0 {
                width = max(width, lineWidth - spacing)
                height += lineHeight + spacing
                lineWidth = 0
                lineHeight = 0
            }
            lineWidth += size.width + spacing
            lineHeight = max(lineHeight, size.height)
        }
        width = max(width, lineWidth - spacing)
        height += lineHeight
        return CGSize(width: width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let sizes = subviews.map { $0.sizeThatFits(.unspecified) }
        var x = bounds.minX
        var y = bounds.minY
        var lineHeight: CGFloat = 0

        for (index, subview) in subviews.enumerated() {
            let size = sizes[index]
            if x + size.width > bounds.maxX && x > bounds.minX {
                x = bounds.minX
                y += lineHeight + spacing
                lineHeight = 0
            }
            subview.place(at: CGPoint(x: x, y: y), proposal: .unspecified)
            x += size.width + spacing
            lineHeight = max(lineHeight, size.height)
        }
    }
}
