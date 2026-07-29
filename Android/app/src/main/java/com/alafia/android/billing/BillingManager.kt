package com.alafia.android.billing

import android.app.Activity
import android.content.Context
import android.util.Log
import com.android.billingclient.api.*

/**
 * Thin wrapper around Google Play Billing v7 for the single ALAFIA Membership
 * subscription product. Flow:
 *
 *   start()  → connect + query the SUBS product details
 *   launch(activity) → open the Play purchase sheet
 *   Play calls purchasesUpdatedListener → onPurchase(token, orderId)
 *   The screen verifies the token with the backend (source of truth), then
 *   calls acknowledge(token) so Play doesn't auto-refund after 3 days.
 *
 * The backend still owns entitlement; this class only drives the store UI and
 * surfaces the purchase token for server-side verification.
 */
class BillingManager(
    context: Context,
    private val productId: String,
    private val onReady: () -> Unit,
    private val onPurchase: (purchaseToken: String, orderId: String?) -> Unit,
    private val onError: (String) -> Unit,
) {
    private val appContext = context.applicationContext
    private var productDetails: ProductDetails? = null
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
                    queryProduct()
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

    private fun queryProduct() {
        val params = QueryProductDetailsParams.newBuilder()
            .setProductList(
                listOf(
                    QueryProductDetailsParams.Product.newBuilder()
                        .setProductId(productId)
                        .setProductType(BillingClient.ProductType.SUBS)
                        .build()
                )
            )
            .build()
        billingClient.queryProductDetailsAsync(params) { result, details ->
            if (result.responseCode == BillingClient.BillingResponseCode.OK && details.isNotEmpty()) {
                productDetails = details.first()
                onReady()
            } else {
                onError("Subscription product not found. Is “$productId” configured in Play Console?")
            }
        }
    }

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

    fun launch(activity: Activity) {
        val details = productDetails
        if (details == null) {
            onError("Subscription is still loading — try again in a moment.")
            return
        }
        val offerToken = details.subscriptionOfferDetails?.firstOrNull()?.offerToken
        if (offerToken == null) {
            onError("No purchase offer available for this subscription.")
            return
        }
        val flowParams = BillingFlowParams.newBuilder()
            .setProductDetailsParamsList(
                listOf(
                    BillingFlowParams.ProductDetailsParams.newBuilder()
                        .setProductDetails(details)
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
        // Hand the token to the screen for backend verification.
        onPurchase(purchase.purchaseToken, purchase.orderId)
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
