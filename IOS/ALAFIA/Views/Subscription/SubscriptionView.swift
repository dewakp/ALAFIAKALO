import SwiftUI
import StoreKit

private let plusProductId = "alafia_plus_monthly"

private let plusFeatures = [
    "Unlimited AI health-guide conversations",
    "Advanced labs & vitals trend forecasting",
    "Meal & exercise planners with AI photo analysis",
    "Priority sync across web, iOS & Android",
]

/// Drives the App Store purchase for the single ALAFIA Plus subscription and
/// verifies it server-side. The backend owns entitlement — every purchase (new,
/// restored, or renewed via `Transaction.updates`) is POSTed to
/// `/subscription/verify/apple` as a signed JWS, and `GET /subscription/status`
/// is the source of truth reflected in the UI.
@MainActor
final class StoreManager: ObservableObject {
    @Published var product: Product?
    @Published var isLoading = true
    @Published var purchasing = false
    @Published var status: SubscriptionStatus?
    @Published var errorMessage: String?

    private var updatesTask: Task<Void, Never>?

    var entitled: Bool { status?.entitled == true }

    func start() async {
        if updatesTask == nil { updatesTask = listenForTransactions() }
        await loadProduct()
        await refreshStatus()
        await syncCurrentEntitlements()
    }

    func stop() {
        updatesTask?.cancel()
        updatesTask = nil
    }

    private func loadProduct() async {
        do {
            product = try await Product.products(for: [plusProductId]).first
            if product == nil {
                errorMessage = "Subscription isn’t available. Is it configured in App Store Connect?"
            }
        } catch {
            errorMessage = "Couldn’t load the subscription."
        }
        isLoading = false
    }

    func refreshStatus() async {
        status = try? await APIClient.shared.get("/subscription/status")
    }

    func purchase() async {
        guard let product else { return }
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
            if case .verified(let transaction) = result, transaction.productID == plusProductId {
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
    @StateObject private var store = StoreManager()
    @State private var plans: SubscriptionPlans?

    private var priceLabel: String {
        if let display = store.product?.displayPrice { return display }
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
                    Text(plans?.productName ?? "ALAFIA Plus")
                        .font(.title).bold()
                }
                Text("Unlock the full ALAFIA experience across every device.")
                    .foregroundColor(.secondary)

                if store.isLoading {
                    HStack { Spacer(); ProgressView(); Spacer() }.padding(.vertical, 40)
                } else if store.entitled {
                    subscribedCard
                } else {
                    offerCard
                }
            }
            .padding()
        }
        .navigationTitle("ALAFIA Plus")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            plans = try? await APIClient.shared.get("/subscription/plans")
            await store.start()
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

    private var offerCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .lastTextBaseline, spacing: 4) {
                Text(priceLabel).font(.system(size: 36, weight: .heavy))
                Text("/ month").foregroundColor(.secondary)
            }
            ForEach(plusFeatures, id: \.self) { feature in
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
            .disabled(store.product == nil || store.purchasing)

            Text("Billed monthly through the App Store. Cancel anytime in Settings → Apple ID → Subscriptions.")
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
                if let price = s.priceUsd { Text(String(format: "Price: $%.2f / month", price)) }
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
        case "paypal": return "PayPal"
        case "google_play": return "Google Play"
        case "apple": return "App Store"
        default: return p
        }
    }
}
