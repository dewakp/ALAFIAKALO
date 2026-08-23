import SwiftUI
import StoreKit

private let monthlyProductId = "alafia_plus_monthly"
private let annualProductId = "alafia_plus_annual"
private let membershipProductIds = [monthlyProductId, annualProductId]

private let membershipFeatures = [
    "Unlimited AI health-guide conversations",
    "Advanced labs & vitals trend forecasting",
    "Meal & exercise planners with AI photo analysis",
    "Priority sync across web, iOS & Android",
]

/// Drives the App Store purchase for the ALAFIA Membership (monthly or annual)
/// and verifies it server-side. The backend owns entitlement — every purchase
/// (new, restored, or renewed via `Transaction.updates`) is POSTed to
/// `/subscription/verify/apple` as a signed JWS, and `GET /subscription/status`
/// is the source of truth reflected in the UI.
@MainActor
final class StoreManager: ObservableObject {
    @Published var monthly: Product?
    @Published var annual: Product?
    @Published var selected: Product?          // the plan the user is about to buy
    @Published var isLoading = true
    @Published var purchasing = false
    @Published var status: SubscriptionStatus?
    @Published var errorMessage: String?

    private var updatesTask: Task<Void, Never>?

    var entitled: Bool { status?.entitled == true }
    var hasBothPlans: Bool { monthly != nil && annual != nil }

    func start() async {
        if updatesTask == nil { updatesTask = listenForTransactions() }
        await loadProducts()
        await refreshStatus()
        await syncCurrentEntitlements()
    }

    func stop() {
        updatesTask?.cancel()
        updatesTask = nil
    }

    func select(id: String) {
        selected = [monthly, annual].compactMap { $0 }.first { $0.id == id }
    }

    private func loadProducts() async {
        do {
            let products = try await Product.products(for: membershipProductIds)
            monthly = products.first { $0.id == monthlyProductId }
            annual = products.first { $0.id == annualProductId }
            selected = monthly ?? annual ?? products.first
            if selected == nil {
                errorMessage = "Membership isn’t available. Is it configured in App Store Connect?"
            }
        } catch {
            errorMessage = "Couldn’t load the membership options."
        }
        isLoading = false
    }

    func refreshStatus() async {
        status = try? await APIClient.shared.get("/subscription/status")
    }

    func purchase() async {
        guard let product = selected else { return }
        purchasing = true
        defer { purchasing = false }
        do {
            let result = try await product.purchase()
            switch result {
            case .success(let verification):
                await handle(verification)
            case .userCancelled:
                break
            case .pending:
                errorMessage = "Your purchase is pending approval."
            @unknown default:
                break
            }
        } catch {
            errorMessage = "Purchase failed: \(error.localizedDescription)"
        }
    }

    /// Verify a StoreKit transaction with the backend, then finish it.
    private func handle(_ verification: VerificationResult<StoreKit.Transaction>) async {
        guard case .verified(let transaction) = verification else {
            errorMessage = "Could not verify the purchase with the App Store."
            return
        }
        let body = AppleVerifyRequest(
            signedTransaction: verification.jwsRepresentation,
            receiptData: nil,
            transactionId: String(transaction.id)
        )
        do {
            status = try await APIClient.shared.post("/subscription/verify/apple", body: body)
        } catch {
            errorMessage = "Purchase recorded but verification failed — it may update shortly."
        }
        await transaction.finish()
    }

    /// Re-verify any active entitlement on open (covers reinstalls / new devices).
    private func syncCurrentEntitlements() async {
        for await result in StoreKit.Transaction.currentEntitlements {
            if case .verified(let transaction) = result, membershipProductIds.contains(transaction.productID) {
                await handle(result)
            }
        }
    }

    private func listenForTransactions() -> Task<Void, Never> {
        Task.detached { [weak self] in
            for await update in StoreKit.Transaction.updates {
                await self?.handle(update)
            }
        }
    }

    deinit { updatesTask?.cancel() }
}

struct SubscriptionView: View {
    /// `true` when this is the membership WALL rather than a settings screen:
    /// the user has no way past it except paying, restoring, or signing out.
    var blocking: Bool = false

    @EnvironmentObject private var authManager: AuthManager
    @EnvironmentObject private var entitlement: EntitlementManager
    @StateObject private var store = StoreManager()
    @State private var plans: SubscriptionPlans?
    @State private var restoring = false

    private var isAnnual: Bool { store.selected?.id == annualProductId }

    private var priceLabel: String {
        if let display = store.selected?.displayPrice { return display }
        if let usd = plans?.rails.first(where: { $0.provider == "apple" })?.priceUsd {
            return String(format: "$%.2f", usd)
        }
        return "—"
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                HStack(spacing: 8) {
                    Image(systemName: "sparkles")
                        .foregroundColor(Color(red: 0.49, green: 0.30, blue: 1.0))
                    Text(plans?.productName ?? "ALAFIA Membership")
                        .font(.title).bold()
                }
                Text(blocking
                     ? "ALAFIA needs an active membership. Subscribe to continue — if you already pay on another device, restore it below."
                     : "Unlock the full ALAFIA experience across every device.")
                    .foregroundColor(.secondary)

                if store.isLoading {
                    HStack { Spacer(); ProgressView(); Spacer() }.padding(.vertical, 40)
                } else if store.entitled {
                    subscribedCard
                } else {
                    offerCard
                    if blocking { blockedFooter }
                }
            }
            .padding()
        }
        .navigationTitle("ALAFIA Membership")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            plans = try? await APIClient.shared.get("/subscription/plans")
            await store.start()
        }
        // A purchase (new OR restored) is verified server-side by StoreManager;
        // when the backend agrees, open the app without another round-trip.
        .onChange(of: store.entitled) { _, nowEntitled in
            if nowEntitled { entitlement.markEntitled() }
        }
        .onDisappear { store.stop() }
        .alert("Notice", isPresented: Binding(
            get: { store.errorMessage != nil },
            set: { if !$0 { store.errorMessage = nil } }
        )) {
            Button("OK", role: .cancel) { store.errorMessage = nil }
        } message: {
            Text(store.errorMessage ?? "")
        }
    }

    /// The only two ways out of the wall that are not "pay": a purchase this
    /// device has not seen yet, and signing out. Without them a user who already
    /// paid on Android — or who mistyped their email at signup — is simply stuck.
    private var blockedFooter: some View {
        VStack(spacing: 12) {
            Button {
                Task {
                    restoring = true
                    defer { restoring = false }
                    try? await AppStore.sync()      // pulls entitlements onto this device
                    await store.start()             // re-verifies them with the backend
                    await entitlement.refresh()
                }
            } label: {
                if restoring { ProgressView() } else { Text("Restore purchases") }
            }
            .disabled(restoring)

            Button("Sign out", role: .destructive) {
                store.stop()
                entitlement.reset()
                authManager.logout()
            }
            .font(.footnote)
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 4)
    }

    private var offerCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            // Monthly / Annual chooser — only when both products load.
            if store.hasBothPlans {
                Picker("Billing period", selection: Binding(
                    get: { store.selected?.id ?? monthlyProductId },
                    set: { store.select(id: $0) }
                )) {
                    Text("Monthly").tag(monthlyProductId)
                    Text("Annual").tag(annualProductId)
                }
                .pickerStyle(.segmented)
            }

            HStack(alignment: .lastTextBaseline, spacing: 4) {
                Text(priceLabel).font(.system(size: 36, weight: .heavy))
                Text(isAnnual ? "/ year" : "/ month").foregroundColor(.secondary)
            }
            if isAnnual, let annual = store.annual {
                Text("Billed yearly (\(annual.displayPrice)).")
                    .font(.footnote).foregroundColor(.green)
            }

            ForEach(membershipFeatures, id: \.self) { feature in
                HStack(alignment: .top, spacing: 10) {
                    Image(systemName: "checkmark.circle.fill").foregroundColor(.green)
                    Text(feature)
                }
            }
            Button {
                Task { await store.purchase() }
            } label: {
                HStack {
                    if store.purchasing { ProgressView().tint(.white) }
                    else { Text("Subscribe").bold() }
                }
                .frame(maxWidth: .infinity).padding(.vertical, 14)
            }
            .buttonStyle(.borderedProminent)
            .disabled(store.selected == nil || store.purchasing)

            Text("Billed \(isAnnual ? "yearly" : "monthly") through the App Store. Cancel anytime in Settings → Apple ID → Subscriptions.")
                .font(.caption).foregroundColor(.secondary)
        }
        .padding()
        .background(RoundedRectangle(cornerRadius: 16).stroke(Color(.separator)))
    }

    private var subscribedCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                Image(systemName: "checkmark.seal.fill").foregroundColor(.green)
                Text("You’re subscribed").font(.headline)
            }
            if let s = store.status {
                Text("Plan: \(s.productName)")
                if let price = s.priceUsd {
                    Text(String(format: "Price: $%.2f / %@", price, s.plan == "plus_annual" ? "year" : "month"))
                }
                Text("Billing via: \(prettyProvider(s.provider))")
                if let end = s.currentPeriodEnd {
                    let label = s.cancelAtPeriodEnd ? "Access ends" : "Renews"
                    Text("\(label) on \(AppDate.date(end))")
                }
                if s.provider == "apple" {
                    Text("Manage or cancel in Settings → Apple ID → Subscriptions.")
                        .font(.caption).foregroundColor(.secondary).padding(.top, 4)
                }
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 16).fill(Color.green.opacity(0.08)))
    }

    private func prettyProvider(_ p: String) -> String {
        switch p {
        case "stripe": return "Card (Stripe)"
        case "google_play": return "Google Play"
        case "apple": return "App Store"
        default: return p
        }
    }
}
