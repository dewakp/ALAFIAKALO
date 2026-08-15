import SwiftUI

/// The clinician persona's tab bar.
///
/// Clinician mode swaps the whole tab bar rather than adding a screen to the
/// patient one. A physician reviewing patients should not be navigating past
/// their own meal diary to do it, and the patient grid is the home screen.
struct ClinicianTabView: View {
    @EnvironmentObject var authManager: AuthManager
    @EnvironmentObject var clinicianMode: ClinicianMode
    @State private var selectedTab = 0

    var body: some View {
        TabView(selection: $selectedTab) {
            NavigationStack { ClinicianDashboardView() }
                .tabItem {
                    Label("Patients", systemImage: "person.2.fill")
                }
                .tag(0)

            NavigationStack { MessagingView() }
                .tabItem {
                    Label("Messages", systemImage: "message.fill")
                }
                .tag(1)

            NavigationStack { TelehealthView() }
                .tabItem {
                    Label("Telehealth", systemImage: "video.fill")
                }
                .tag(2)

            NavigationStack { CalendarView() }
                .tabItem {
                    Label("Calendar", systemImage: "calendar")
                }
                .tag(3)

            NavigationStack { ClinicianAccountView() }
                .tabItem {
                    Label("Account", systemImage: "person.crop.circle")
                }
                .tag(4)
        }
        .tint(.blue)
    }
}

/// Account tab for clinician mode — and the way back to the patient view.
struct ClinicianAccountView: View {
    @EnvironmentObject var authManager: AuthManager
    @EnvironmentObject var clinicianMode: ClinicianMode
    @State private var showProfile = false

    var body: some View {
        List {
            Section {
                HStack(spacing: 12) {
                    Image(systemName: "stethoscope")
                        .font(.title2)
                        .foregroundStyle(.blue)
                        .frame(width: 44, height: 44)
                        .background(Color.blue.opacity(0.12))
                        .clipShape(Circle())
                    VStack(alignment: .leading, spacing: 2) {
                        Text(authManager.currentUser?.fullName ?? "Clinician")
                            .fontWeight(.semibold)
                        if let role = ClinicianRoles.held(by: authManager.currentUser) {
                            Text(role.replacingOccurrences(of: "_", with: " ").capitalized)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }

            Section {
                Button {
                    clinicianMode.exit()
                } label: {
                    Label("Switch to Patient View", systemImage: "arrow.left.arrow.right")
                }
            } footer: {
                Text("Your own health record, meals and tracking live in the patient view.")
            }

            Section("Account") {
                // ProfileSheet is built as a sheet — it carries its own Done
                // button and calls dismiss — so it is presented, not pushed.
                Button {
                    showProfile = true
                } label: {
                    Label("My Profile", systemImage: "person.crop.circle")
                }
                NavigationLink { RolesView() } label: {
                    Label("Role", systemImage: "person.badge.key")
                }
                NavigationLink { SubscriptionView() } label: {
                    Label("ALAFIA Membership", systemImage: "sparkles")
                }
                NavigationLink { DataSharingView() } label: {
                    Label("Share Records", systemImage: "square.and.arrow.up")
                }
            }
        }
        .navigationTitle("Account")
        .sheet(isPresented: $showProfile) {
            ProfileSheet()
        }
    }
}
