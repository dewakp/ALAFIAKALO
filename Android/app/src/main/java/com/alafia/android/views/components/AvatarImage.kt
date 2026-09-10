package com.alafia.android.views.components

import android.graphics.BitmapFactory
import android.util.Base64
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.Image
import kotlin.math.abs

/**
 * One avatar, used by every screen that shows a person.
 *
 * Matches the web `Avatar` and iOS `AvatarView`: photo, then initials, then
 * "?". Sharing the tint palette means the same person is the same colour on
 * every platform, which is what makes a colour useful for recognition at all.
 *
 * The photo arrives as a `data:` URI on the user payload rather than a URL to
 * fetch — the server has already cropped and re-encoded it to 256 px, and one
 * fewer authenticated round-trip per face matters in a list.
 */
private val TINTS = listOf(
    Color(0xFF0EA5E9), Color(0xFF8B5CF6), Color(0xFFF59E0B),
    Color(0xFF10B981), Color(0xFFEF4444), Color(0xFF6366F1),
)

fun avatarTint(userId: Int): Color = TINTS[abs(userId) % TINTS.size]

fun avatarInitials(name: String?): String {
    val letters = (name ?: "").trim().split(Regex("\\s+"))
        .filter { it.isNotEmpty() }
        .take(2)
        .mapNotNull { it.firstOrNull()?.uppercaseChar() }
        .joinToString("")
    return letters.ifEmpty { "?" }
}

@Composable
fun AvatarImage(
    url: String?,
    name: String?,
    userId: Int,
    size: Dp = 44.dp,
    modifier: Modifier = Modifier,
) {
    val bitmap = remember(url) {
        // Anything that is not a data: URI — including a real http URL, which
        // this app does not currently receive — falls through to initials
        // rather than rendering a broken image.
        val payload = url?.takeIf { it.startsWith("data:image") }
            ?.substringAfter(',', "")
            ?.takeIf { it.isNotEmpty() }
        payload?.let {
            runCatching {
                val bytes = Base64.decode(it, Base64.DEFAULT)
                BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
            }.getOrNull()
        }
    }

    // A name, not "avatar" — a list of twenty "image" announcements tells a
    // TalkBack user nothing.
    val label = name ?: "Profile photo"

    if (bitmap != null) {
        Image(
            bitmap = bitmap.asImageBitmap(),
            contentDescription = label,
            contentScale = ContentScale.Crop,
            modifier = modifier.size(size).clip(CircleShape),
        )
    } else {
        Box(
            contentAlignment = Alignment.Center,
            modifier = modifier
                .size(size)
                .clip(CircleShape)
                .background(avatarTint(userId))
                .semantics { contentDescription = label },
        ) {
            Text(
                text = avatarInitials(name),
                color = Color.White,
                fontWeight = FontWeight.Bold,
                fontSize = (size.value * 0.36f).coerceAtLeast(11f).sp,
                style = MaterialTheme.typography.labelLarge,
            )
        }
    }
}
