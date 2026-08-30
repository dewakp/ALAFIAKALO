import SwiftUI

struct PrivacySettingsView: View {
    @StateObject private var viewModel = PrivacySettingsViewModel()
    @State private var showingDeleteConfirmation = false
    @State private var showingExportOptions = false
    
    var body: some View {
        List {
            // Data Sharing Section
            Section(header: Text("Data Sharing & Privacy")) {
                Toggle("Anonymized Analytics", isOn: $viewModel.settings.allowAnonymizedAnalytics)
                    .onChange(of: viewModel.settings.allowAnonymizedAnalytics) { oldValue, newValue in
                        viewModel.updateSetting(key: "allow_anonymized_analytics", value: newValue)
                    }
                Text("Help improve the platform by sharing anonymized usage data")
                    .font(.caption)
                    .foregroundColor(.secondary)
                
                Toggle("Collective Insights", isOn: $viewModel.settings.allowCollectiveInsights)
                    .onChange(of: viewModel.settings.allowCollectiveInsights) { oldValue, newValue in
                        viewModel.updateSetting(key: "allow_collective_insights", value: newValue)
                    }
                Text("Let your meal photos and corrections train ALAFIA's food recognition "
                     + "for everyone. Your photos stay with your meals either way — this only "
                     + "controls whether they improve the shared model.")
                    .font(.caption)
                    .foregroundColor(.secondary)
                
                Toggle("Research Participation", isOn: $viewModel.settings.allowResearchParticipation)
                    .onChange(of: viewModel.settings.allowResearchParticipation) { oldValue, newValue in
                        viewModel.updateSetting(key: "allow_research_participation", value: newValue)
                    }
                Text("Participate in de-identified health research studies")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            
            // Communications Section
            Section(header: Text("Communications")) {
                Toggle("Marketing Emails", isOn: $viewModel.settings.allowMarketingEmails)
                    .onChange(of: viewModel.settings.allowMarketingEmails) { oldValue, newValue in
                        viewModel.updateSetting(key: "allow_marketing_emails", value: newValue)
                    }
                
                Toggle("Product Updates", isOn: $viewModel.settings.allowProductUpdates)
                    .onChange(of: viewModel.settings.allowProductUpdates) { oldValue, newValue in
                        viewModel.updateSetting(key: "allow_product_updates", value: newValue)
                    }
                
                Toggle("Health Reminders", isOn: $viewModel.settings.allowHealthReminders)
                    .onChange(of: viewModel.settings.allowHealthReminders) { oldValue, newValue in
                        viewModel.updateSetting(key: "allow_health_reminders", value: newValue)
                    }
            }
            
            // AI Section
            Section(header: Text("AI Preferences")) {
                Toggle("AI Coaching", isOn: $viewModel.settings.aiCoachingEnabled)
                    .onChange(of: viewModel.settings.aiCoachingEnabled) { oldValue, newValue in
                        viewModel.updateSetting(key: "ai_coaching_enabled", value: newValue)
                    }
                Text("Receive personalized health recommendations from AI")
                    .font(.caption)
                    .foregroundColor(.secondary)
                
                Toggle("AI Memory", isOn: $viewModel.settings.aiMemoryEnabled)
                    .onChange(of: viewModel.settings.aiMemoryEnabled) { oldValue, newValue in
                        viewModel.updateSetting(key: "ai_memory_enabled", value: newValue)
                    }
                Text("Allow AI to learn from your patterns for better personalization")
                    .font(.caption)
                    .foregroundColor(.secondary)
                
                Picker("AI Explanation Detail", selection: $viewModel.settings.aiExplainabilityLevel) {
                    Text("Minimal").tag("minimal")
                    Text("Standard").tag("standard")
                    Text("Detailed").tag("detailed")
                }
                .onChange(of: viewModel.settings.aiExplainabilityLevel) { oldValue, newValue in
                    viewModel.updateSetting(key: "ai_explainability_level", value: newValue)
                }
            }
            
            // Security Section
            Section(header: Text("Security")) {
                Toggle("Biometric Authentication", isOn: $viewModel.settings.requireBiometricAuth)
                    .onChange(of: viewModel.settings.requireBiometricAuth) { oldValue, newValue in
                        viewModel.updateSetting(key: "require_biometric_auth", value: newValue)
                        // Persist locally so AuthManager can gate on next launch
                        BiometricAuthManager.setPreference(newValue)
                    }
                
                Picker("Session Timeout", selection: $viewModel.settings.sessionTimeoutMinutes) {
                    Text("15 minutes").tag(15)
                    Text("30 minutes").tag(30)
                    Text("1 hour").tag(60)
                    Text("2 hours").tag(120)
                    Text("24 hours").tag(1440)
                }
                .onChange(of: viewModel.settings.sessionTimeoutMinutes) { oldValue, newValue in
                    viewModel.updateSetting(key: "session_timeout_minutes", value: newValue)
                }
            }
            
            // Compliance Info
            Section(header: Text("Compliance & Regulations")) {
                HStack {
                    Text("GDPR Status")
                    Spacer()
                    Text(viewModel.settings.gdprApplies ? "✓ Applies" : "○ Does not apply")
                        .foregroundColor(viewModel.settings.gdprApplies ? .green : .secondary)
                }
                
                HStack {
                    Text("HIPAA Status")
                    Spacer()
                    Text(viewModel.settings.hipaaApplies ? "✓ Applies" : "○ Does not apply")
                        .foregroundColor(viewModel.settings.hipaaApplies ? .green : .secondary)
                }
                
                Text("Your data is protected according to applicable healthcare privacy regulations.")
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .italic()
            }
            
            // Data Rights Section
            Section(header: Text("Your Data Rights").foregroundColor(.red)) {
                Button(action: {
                    showingExportOptions = true
                }) {
                    HStack {
                        VStack(alignment: .leading) {
                            Text("Export My Data")
                                .foregroundColor(.primary)
                            Text("Download all your health data (GDPR Article 20)")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        Spacer()
                        Image(systemName: "arrow.down.doc")
                    }
                }
                
                if let exportStatus = viewModel.exportStatus {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Export Status: \(exportStatus.status.capitalized)")
                            .font(.caption)
                        if exportStatus.status == "ready", let url = exportStatus.downloadUrl {
                            Button("Download Now") {
                                viewModel.downloadExport(url: url)
                            }
                            .font(.caption)
                        }
                    }
                }
                
                Button(action: {
                    showingDeleteConfirmation = true
                }) {
                    HStack {
                        VStack(alignment: .leading) {
                            Text("Delete My Account")
                                .foregroundColor(.red)
                            Text("This action cannot be undone")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        Spacer()
                        Image(systemName: "trash")
                            .foregroundColor(.red)
                    }
                }
            }
        }
        .navigationTitle("Privacy Settings")
        .navigationBarTitleDisplayMode(.large)
        .alert("Confirm Account Deletion", isPresented: $showingDeleteConfirmation) {
            Button("Cancel", role: .cancel) { }
            Button("Delete Account", role: .destructive) {
                viewModel.requestAccountDeletion()
            }
        } message: {
            Text("This action cannot be undone. All your health data, AI memories, and account information will be permanently deleted.\n\nAre you absolutely sure?")
        }
        .confirmationDialog("Export Data", isPresented: $showingExportOptions) {
            Button("Export as JSON") {
                viewModel.requestDataExport(format: "json")
            }
            Button("Export as CSV") {
                viewModel.requestDataExport(format: "csv")
            }
            Button("Cancel", role: .cancel) { }
        } message: {
            Text("Choose export format")
        }
        .alert(viewModel.message, isPresented: .constant(!viewModel.message.isEmpty)) {
            Button("OK", role: .cancel) {
                viewModel.message = ""
            }
        }
        .onAppear {
            viewModel.loadSettings()
        }
    }
}

#Preview {
    NavigationView {
        PrivacySettingsView()
    }
}
