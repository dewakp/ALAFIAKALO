// Copyright © 2026 Wole Akpose / 6igma Health Inc.
// All rights reserved. ALAFIA — proprietary and confidential.

package com.alafia.android.billing

import android.app.Activity
import android.content.Context
import android.util.Log
import com.android.billingclient.api.*

/**
 * Thin wrapper around Google Play Billing v7 for the ALAFIA Membership
 * subscriptions. Flow:
 *
 *   start()  → connect + query the SUBS product details for EVERY offered id
 *   launch(activity, productId) → open the Play purchase sheet for that plan
 *   Play calls purchasesUpdatedListener → onPurchase(token, orderId, productId)
 *   The screen verifies the token with the backend (source of truth), then
 *   calls acknowledge(token) so Play doesn't auto-refund after 3 days.
 *
 * The backend still owns entitlement; this class only drives the store UI and
 * surfaces the purchase token for server-side verification.
 *
 * ── Why this takes a LIST of product ids ─────────────────────────────────────
 * It used to take exactly one, hardcoded by the screen as `alafia_plus_monthly`,
 * so Android could not sell the annual plan at all while web and iOS both
 * offered it — a §3 parity gap on the paywall. iOS gets both plans by asking
 * StoreKit for both ids; this is the same move against Play, and it is why no
 * backend model change was needed: the STORE quotes the price it will actually
 * charge.
 *
 * ── Why the purchased product id travels with the callback ───────────────────
 * With two products, "what was bought" is no longer implied. The screen sends
 * the product id to `verifyGooglePurchase`, so reporting a fixed id would credit
 * an annual purchase as a monthly one — the backend would record the wrong plan
 * and the wrong period end, and nothing downstream could tell. Play already
 * names the product on the Purchase, so it is read from there rather than
 * assumed.
 */
class BillingManager(
    context: Context,
    private val productIds: List<String>,
    private val onReady: () -> Unit,
    private val onPurchase: (purchaseToken: String, orderId: String?, productId: String?) -> Unit,
    private val onError: (String) -> Unit,
) {
    private val appContext = context.applicationContext

    /** Play's details per product id, populated once the SUBS query returns. */
    private val details = mutableMapOf<String, ProductDetails>()
    private val ackInFlight = mutableSetOf<String>()

    private val purchasesListener = PurchasesUpdatedListener { result, purchases ->
        when (result.responseCode) {
            BillingClient.BillingResponseCode.OK -> purchases?.forEach(::handlePurchase)
            BillingClient.BillingResponseCode.USER_CANCELED -> { /* silent — user backed out */ }
            else -> onError(result.debugMessage.ifBlank { "Purchase failed (${result.responseCode})" })
        }
    }

    private val billingClient: BillingClient = BillingClient.newBuilder(appContext)
        .setListener(purchasesListener)
        .enablePendingPurchases(
            PendingPurchasesParams.newBuilder().enableOneTimeProducts().build()
        )
        .build()

    fun start() {
        billingClient.startConnection(object : BillingClientStateListener {
            override fun onBillingSetupFinished(result: BillingResult) {
                if (result.responseCode == BillingClient.BillingResponseCode.OK) {
                    queryProducts()
                    queryExistingPurchases()
                } else {
                    onError("Billing unavailable: ${result.debugMessage}")
                }
            }

            override fun onBillingServiceDisconnected() {
                // Left to the caller to retry via start() if needed.
            }
        })
    }

    private fun queryProducts() {
        val params = QueryProductDetailsParams.newBuilder()
            .setProductList(
                productIds.map { id ->
                    QueryProductDetailsParams.Product.newBuilder()
                        .setProductId(id)
                        .setProductType(BillingClient.ProductType.SUBS)
                        .build()
                }
            )
            .build()
        billingClient.queryProductDetailsAsync(params) { result, found ->
            if (result.responseCode != BillingClient.BillingResponseCode.OK) {
                onError("Couldn't load subscriptions: ${result.debugMessage}")
                return@queryProductDetailsAsync
            }
            details.clear()
            found.forEach { details[it.productId] = it }

            // Partial success is NOT failure. If one plan is missing from Play
            // Console the other is still purchasable, and refusing everything
            // would wall off a paying customer over a configuration gap in a
            // plan they did not choose. Report what is missing and carry on.
            val missing = productIds - details.keys
            if (details.isEmpty()) {
                onError("No subscription products found. Are $productIds configured in Play Console?")
            } else {
                if (missing.isNotEmpty()) {
                    Log.w("BillingManager", "not offered by Play: $missing")
                }
                onReady()
            }
        }
    }

    /** Play's own formatted price for a plan, e.g. "$14.00" — or null if absent. */
    fun formattedPrice(productId: String): String? =
        details[productId]
            ?.subscriptionOfferDetails
            ?.firstOrNull()
            ?.pricingPhases
            ?.pricingPhaseList
            ?.firstOrNull()
            ?.formattedPrice

    /** True when Play has details for this plan and it can actually be bought. */
    fun isAvailable(productId: String): Boolean = details.containsKey(productId)

    /** Re-report any already-owned (e.g. restored) purchase for verification. */
    private fun queryExistingPurchases() {
        val params = QueryPurchasesParams.newBuilder()
            .setProductType(BillingClient.ProductType.SUBS)
            .build()
        billingClient.queryPurchasesAsync(params) { result, purchases ->
            if (result.responseCode == BillingClient.BillingResponseCode.OK) {
                purchases.forEach(::handlePurchase)
            }
        }
    }

    fun launch(activity: Activity, productId: String) {
        val chosen = details[productId]
        if (chosen == null) {
            onError("That plan is still loading — try again in a moment.")
            return
        }
        val offerToken = chosen.subscriptionOfferDetails?.firstOrNull()?.offerToken
        if (offerToken == null) {
            onError("No purchase offer available for this subscription.")
            return
        }
        val flowParams = BillingFlowParams.newBuilder()
            .setProductDetailsParamsList(
                listOf(
                    BillingFlowParams.ProductDetailsParams.newBuilder()
                        .setProductDetails(chosen)
                        .setOfferToken(offerToken)
                        .build()
                )
            )
            .build()
        val result = billingClient.launchBillingFlow(activity, flowParams)
        if (result.responseCode != BillingClient.BillingResponseCode.OK) {
            onError("Couldn't open checkout: ${result.debugMessage}")
        }
    }

    private fun handlePurchase(purchase: Purchase) {
        if (purchase.purchaseState != Purchase.PurchaseState.PURCHASED) return
        // Which plan was bought comes from Play, not from whatever the screen
        // had selected — a restored purchase arrives with no selection at all.
        onPurchase(purchase.purchaseToken, purchase.orderId, purchase.products.firstOrNull())
    }

    /** Acknowledge a purchase after the backend has verified it. Idempotent. */
    fun acknowledge(purchaseToken: String) {
        if (purchaseToken in ackInFlight) return
        ackInFlight.add(purchaseToken)
        val params = AcknowledgePurchaseParams.newBuilder()
            .setPurchaseToken(purchaseToken)
            .build()
        billingClient.acknowledgePurchase(params) { result ->
            ackInFlight.remove(purchaseToken)
            if (result.responseCode != BillingClient.BillingResponseCode.OK) {
                Log.w("BillingManager", "acknowledge failed: ${result.debugMessage}")
            }
        }
    }

    fun end() {
        try { billingClient.endConnection() } catch (_: Exception) { }
    }
}
