package com.alafia.android.views.nutrition

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.util.Base64
import java.io.ByteArrayOutputStream
import kotlin.math.max

/**
 * A small thumbnail of a meal photo, kept with the meal.
 *
 * The full photo goes to media storage through the vision call and is only
 * written when that analysis runs. This is saved on the log row itself, so a
 * list of meals shows what each one was with no request per row — the same
 * thumbnail the web client stores, in the same `data:` URI form, so a meal
 * logged on either renders on both.
 */
private const val MAX_EDGE = 96
private const val QUALITY = 70

/**
 * Returns a `data:image/jpeg;base64,…` thumbnail, or null when the bytes
 * cannot be decoded.
 *
 * Null rather than an exception: a meal must stay savable when its picture is
 * unreadable. The thumbnail is a nicety; the meal is the record.
 */
fun mealThumbnail(bytes: ByteArray?): String? {
    if (bytes == null || bytes.isEmpty()) return null
    return runCatching {
        val source = BitmapFactory.decodeByteArray(bytes, 0, bytes.size) ?: return null
        val longest = max(source.width, source.height)
        val scale = if (longest > MAX_EDGE) MAX_EDGE.toFloat() / longest else 1f
        val w = (source.width * scale).toInt().coerceAtLeast(1)
        val h = (source.height * scale).toInt().coerceAtLeast(1)

        val scaled = Bitmap.createScaledBitmap(source, w, h, true)
        val out = ByteArrayOutputStream()
        scaled.compress(Bitmap.CompressFormat.JPEG, QUALITY, out)
        if (scaled !== source) scaled.recycle()

        "data:image/jpeg;base64," + Base64.encodeToString(out.toByteArray(), Base64.NO_WRAP)
    }.getOrNull()
}

/** Decode a stored thumbnail back to a Bitmap for display, or null. */
fun decodeThumbnail(dataUri: String?): Bitmap? {
    val payload = dataUri?.takeIf { it.startsWith("data:image") }
        ?.substringAfter(',', "")
        ?.takeIf { it.isNotEmpty() } ?: return null
    return runCatching {
        val bytes = Base64.decode(payload, Base64.DEFAULT)
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
    }.getOrNull()
}
