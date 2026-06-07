import SwiftUI

// MARK: - ViewModel

@Observable
final class DataSharingViewModel {
    enum Tab: String, CaseIterable { case grants = "Active Grants"; case invitations = "Invitations" }

    var selectedTab: Tab = .grants

    // Grants
    var grants: [DataGrant] = []
    var isLoadingGrants = false

    // Invitations
    var invitations: [DataShareInvitation] = []
    var isLoadingInvitations = false

    // Data types for grant creation
    var availableDataTypes: [String] = []

    var errorMessage: String?

    // Grant sheet
    var showGrantSheet = false
    var grantEmail = ""
    var grantDataType = ""
    var grantCanRead = true
    var grantCanWrite = false
    var grantHasExpiry = false
    var grantExpiryDate = Calendar.current.date(byAdding: .month, value: 1, to: Date()) ?? Date()
    var isSavingGrant = false

    // Invitation sheet
    var showInvitationSheet = false
    var invEmail = ""
    var invSelectedTypes: Set<String> = []
    var invMessage = ""
    var isSavingInvitation = false

    // MARK: - Load

    func loadGrants() async {
        isLoadingGrants = true; errorMessage = nil
        do {
            grants = try await APIClient.shared.get("/data-sharing/grants")
        } catch { errorMessage = error.localizedDescription }
        isLoadingGrants = false
    }

    func loadInvitations() async {
        isLoadingInvitations = true; errorMessage = nil
        do {
            invitations = try await APIClient.shared.get("/data-sharing/invitations")
        } catch { errorMessage = error.localizedDescription }
        isLoadingInvitations = false
    }

    func loadDataTypes() async {
        do {
            availableDataTypes = try await APIClient.shared.get("/data-sharing/types")
        } catch { /* silently use empty list */ }
    }

    func loadAll() async {
        async let g: () = loadGrants()
        async let i: () = loadInvitations()
        async let t: () = loadDataTypes()
        _ = await (g, i, t)
    }

    // MARK: - Grant Actions

    func deleteGrant(id: Int) async {
        do {
            try await APIClient.shared.delete("/data-sharing/grants/\(id)")
            grants.removeAll { $0.id == id }
        } catch { errorMessage = error.localizedDescription }
    }

    func submitGrant() async {
        isSavingGrant = true; errorMessage = nil
        let body = DataGrantCreate(
            granteeEmail: grantEmail,
            dataType: grantDataType,
            canRead: grantCanRead,
            canWrite: grantCanWrite,
            expiresAt: grantHasExpiry ? Self.dateFormatter.string(from: grantExpiryDate) : nil
        )
        do {
            let created: DataGrant = try await APIClient.shared.post("/data-sharing/grants", body: body)
            grants.insert(created, at: 0)
            showGrantSheet = false
            resetGrantForm()
        } catch { errorMessage = error.localizedDescription }
        isSavingGrant = false
    }

    func resetGrantForm() {
        grantEmail = ""
        grantDataType = availableDataTypes.first ?? ""
        grantCanRead = true
        grantCanWrite = false
        grantHasExpiry = false
        grantExpiryDate = Calendar.current.date(byAdding: .month, value: 1, to: Date()) ?? Date()
        isSavingGrant = false
    }

    // MARK: - Invitation Actions

    func acceptInvitation(id: Int) async {
        do {
            let _: DataShareInvitation = try await APIClient.shared.post("/data-sharing/invitations/\(id)/accept", body: DataSharingEmptyBody())
            await loadInvitations()
        } catch { errorMessage = error.localizedDescription }
    }

    func declineInvitation(id: Int) async {
        do {
            let _: DataShareInvitation = try await APIClient.shared.post("/data-sharing/invitations/\(id)/decline", body: DataSharingEmptyBody())
            await loadInvitations()
        } catch { errorMessage = error.localizedDescription }
    }

    func submitInvitation() async {
        isSavingInvitation = true; errorMessage = nil
        let body = InvitationCreate(
            recipientEmail: invEmail,
            dataTypes: Array(invSelectedTypes),
            message: invMessage.isEmpty ? nil : invMessage
        )
        do {
            let _: DataShareInvitation = try await APIClient.shared.post("/data-sharing/invitations", body: body)
            showInvitationSheet = false
            resetInvitationForm()
            await loadInvitations()
        } catch { errorMessage = error.localizedDescription }
        isSavingInvitation = false
    }

    func resetInvitationForm() {
        invEmail = ""
        invSelectedTypes = []
        invMessage = ""
        isSavingInvitation = false
    }

    static let dateFormatter: DateFormatter = {
        let df = DateFormatter()
        df.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        df.locale = Locale(identifier: "en_US_POSIX")
        return df
    }()
}

// MARK: - Helper Types

private struct DataSharingEmptyBody: Codable {}

private struct InvitationCreate: Codable {
    let recipientEmail: String
    let dataTypes: [String]
    let message: String?

    enum CodingKeys: String, CodingKey {
        case recipientEmail = "recipient_email"
        case dataTypes = "data_types"
        case message
    }
}

// MARK: - Main View

struct DataSharingView: View {
    @State private var vm = DataSharingViewModel()

    var body: some View {
            VStack(spacing: 0) {
                Picker("Section", selection: $vm.selectedTab) {
                    ForEach(DataSharingViewModel.Tab.allCases, id: \.self) {
                        Text($0.rawValue).tag($0)
                    }
                }
                .pickerStyle(.segmented)
                .padding()

                Group {
                    switch vm.selectedTab {
                    case .grants: grantsTab
                    case .invitations: invitationsTab
                    }
                }
            }
            .navigationTitle("Data Sharing")
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        if vm.selectedTab == .grants {
                            vm.resetGrantForm()
                            vm.grantDataType = vm.availableDataTypes.first ?? ""
                            vm.showGrantSheet = true
                        } else {
                            vm.resetInvitationForm()
                            vm.showInvitationSheet = true
                        }
                    } label: {
                        Image(systemName: "plus")
                    }
                }
            }
            .sheet(isPresented: $vm.showGrantSheet) {
                GrantAccessSheet(vm: vm)
            }
            .sheet(isPresented: $vm.showInvitationSheet) {
                SendInvitationSheet(vm: vm)
            }
            .task { await vm.loadAll() }
            .refreshable { await vm.loadAll() }
    }

    // MARK: - Grants Tab

    @ViewBuilder
    private var grantsTab: some View {
        if vm.isLoadingGrants {
            ProgressView("Loading grants…")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if vm.grants.isEmpty {
            EmptyStateView(icon: "person.badge.key", title: "No Active Grants", message: "Tap + to grant someone access to your health data.")
        } else {
            List {
                ForEach(vm.grants) { grant in
                    GrantRow(grant: grant)
                        .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                            Button(role: .destructive) {
                                Task { await vm.deleteGrant(id: grant.id) }
                            } label: {
                                Label("Revoke", systemImage: "trash")
                            }
                        }
                }
            }
            .listStyle(.insetGrouped)
        }
    }

    // MARK: - Invitations Tab

    @ViewBuilder
    private var invitationsTab: some View {
        if vm.isLoadingInvitations {
            ProgressView("Loading invitations…")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if vm.invitations.isEmpty {
            EmptyStateView(icon: "envelope.badge", title: "No Invitations", message: "Tap + to send a data sharing invitation.")
        } else {
            List {
                ForEach(vm.invitations) { invitation in
                    InvitationRow(invitation: invitation, onAccept: {
                        Task { await vm.acceptInvitation(id: invitation.id) }
                    }, onDecline: {
                        Task { await vm.declineInvitation(id: invitation.id) }
                    })
                }
            }
            .listStyle(.insetGrouped)
        }
    }
}

// MARK: - Grant Row

private struct GrantRow: View {
    let grant: DataGrant

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(grant.granteeDisplayName ?? grant.granteeEmail ?? "Unknown")
                .font(.headline)
            if let email = grant.granteeEmail, grant.granteeDisplayName != nil {
                Text(email)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            HStack(spacing: 6) {
                dataTypeBadge(grant.dataType)
                if grant.canRead { permissionBadge("Read", color: .green) }
                if grant.canWrite { permissionBadge("Write", color: .orange) }
            }

            if let expires = grant.expiresAt {
                Text("Expires: \(expires.prefix(10))")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
    }

    private func dataTypeBadge(_ type: String) -> some View {
        Text(type)
            .font(.caption.bold())
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(Color.accentColor.opacity(0.15))
            .foregroundStyle(Color.accentColor)
            .clipShape(Capsule())
    }

    private func permissionBadge(_ label: String, color: Color) -> some View {
        Text(label)
            .font(.caption2.bold())
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(color.opacity(0.15))
            .foregroundStyle(color)
            .clipShape(Capsule())
    }
}

// MARK: - Invitation Row

private struct InvitationRow: View {
    let invitation: DataShareInvitation
    let onAccept: () -> Void
    let onDecline: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(invitation.recipientEmail ?? "Unknown")
                    .font(.headline)
                Spacer()
                statusBadge(invitation.status)
            }

            if let types = invitation.dataTypes, !types.isEmpty {
                HStack(spacing: 4) {
                    ForEach(types, id: \.self) { type in
                        Text(type)
                            .font(.caption2)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Color.secondary.opacity(0.12))
                            .clipShape(Capsule())
                    }
                }
            }

            if invitation.status.lowercased() == "pending" {
                HStack(spacing: 12) {
                    Button {
                        onAccept()
                    } label: {
                        Label("Accept", systemImage: "checkmark")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(.green)
                    .controlSize(.small)

                    Button {
                        onDecline()
                    } label: {
                        Label("Decline", systemImage: "xmark")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)
                    .tint(.red)
                    .controlSize(.small)
                }
                .padding(.top, 4)
            }
        }
        .padding(.vertical, 4)
    }

    private func statusBadge(_ status: String) -> some View {
        Text(status.capitalized)
            .font(.caption.bold())
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(statusColor(status).opacity(0.15))
            .foregroundStyle(statusColor(status))
            .clipShape(Capsule())
    }

    private func statusColor(_ status: String) -> Color {
        switch status.lowercased() {
        case "pending": return .orange
        case "accepted": return .green
        case "declined": return .red
        default: return .gray
        }
    }
}

// MARK: - Grant Access Sheet

private struct GrantAccessSheet: View {
    @Bindable var vm: DataSharingViewModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section("Grantee") {
                    TextField("Email address", text: $vm.grantEmail)
                        .keyboardType(.emailAddress)
                        .textContentType(.emailAddress)
                        .autocapitalization(.none)
                }
                Section("Data Type") {
                    if vm.availableDataTypes.isEmpty {
                        TextField("Data type", text: $vm.grantDataType)
                    } else {
                        Picker("Type", selection: $vm.grantDataType) {
                            ForEach(vm.availableDataTypes, id: \.self) {
                                Text($0).tag($0)
                            }
                        }
                    }
                }
                Section("Permissions") {
                    Toggle("Can Read", isOn: $vm.grantCanRead)
                    Toggle("Can Write", isOn: $vm.grantCanWrite)
                }
                Section("Expiry") {
                    Toggle("Set Expiry Date", isOn: $vm.grantHasExpiry)
                    if vm.grantHasExpiry {
                        DatePicker("Expires", selection: $vm.grantExpiryDate, displayedComponents: .date)
                    }
                }
            }
            .navigationTitle("Grant Access")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Grant") { Task { await vm.submitGrant() } }
                        .disabled(vm.grantEmail.isEmpty || vm.isSavingGrant)
                }
            }
        }
    }
}

// MARK: - Send Invitation Sheet

private struct SendInvitationSheet: View {
    @Bindable var vm: DataSharingViewModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section("Recipient") {
                    TextField("Email address", text: $vm.invEmail)
                        .keyboardType(.emailAddress)
                        .textContentType(.emailAddress)
                        .autocapitalization(.none)
                }
                Section("Data Types") {
                    if vm.availableDataTypes.isEmpty {
                        Text("No data types available")
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(vm.availableDataTypes, id: \.self) { type in
                            Toggle(type, isOn: Binding(
                                get: { vm.invSelectedTypes.contains(type) },
                                set: { isOn in
                                    if isOn { vm.invSelectedTypes.insert(type) }
                                    else { vm.invSelectedTypes.remove(type) }
                                }
                            ))
                        }
                    }
                }
                Section("Message (Optional)") {
                    TextField("Add a message…", text: $vm.invMessage, axis: .vertical)
                        .lineLimit(3...6)
                }
            }
            .navigationTitle("Send Invitation")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Send") { Task { await vm.submitInvitation() } }
                        .disabled(vm.invEmail.isEmpty || vm.invSelectedTypes.isEmpty || vm.isSavingInvitation)
                }
            }
        }
    }
}
