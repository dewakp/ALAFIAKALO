package com.alafia.android.util

import java.time.Instant
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle

/**
 * Date/time display in the device's LOCAL timezone + locale.
 *
 * The backend stores UTC. Parsing a server timestamp with LocalDateTime.parse() after
 * stripping the 'Z' treats the UTC clock value as LOCAL, which makes times race ahead of
 * the user's clock. Here we parse to an [Instant] (naive strings assumed UTC) and render
 * with ZoneId.systemDefault(), never a stripped-zone LocalDateTime.
 */
object AppDate {

    private val zone: ZoneId get() = ZoneId.systemDefault()

    /** Parse a server value to an Instant. Naive (no-offset) strings are treated as UTC. */
    fun parse(s: String?): Instant? {
        if (s.isNullOrBlank()) return null
        // offset/Z present
        runCatching { return OffsetDateTime.parse(s).toInstant() }
        runCatching { return Instant.parse(s) }
        // naive datetime (no zone) → assume UTC
        val body = s.substringBefore("+").removeSuffix("Z").let { if (it.contains(".")) it.substringBefore(".") else it }
        runCatching { return LocalDateTime.parse(body, DateTimeFormatter.ISO_LOCAL_DATE_TIME).toInstant(ZoneOffset.UTC) }
        // date-only → local midnight
        runCatching { return LocalDate.parse(s.take(10)).atStartOfDay(zone).toInstant() }
        return null
    }

    /** Localized date + time in the device timezone, e.g. "Jul 21, 2026, 10:46 PM". */
    fun dateTime(s: String?): String {
        val i = parse(s) ?: return s ?: ""
        return DateTimeFormatter.ofLocalizedDateTime(FormatStyle.MEDIUM, FormatStyle.SHORT).withZone(zone).format(i)
    }

    /** Localized date only. */
    fun date(s: String?): String {
        val i = parse(s) ?: return s ?: ""
        return DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM).withZone(zone).format(i)
    }

    /** Local time only (HH:mm). */
    fun time(s: String?): String {
        val i = parse(s) ?: return s ?: ""
        return DateTimeFormatter.ofPattern("HH:mm").withZone(zone).format(i)
    }

    /** Compact local date + time, e.g. "M/d HH:mm" (chat/community lists). */
    fun shortDateTime(s: String?): String {
        val i = parse(s) ?: return s ?: ""
        return DateTimeFormatter.ofPattern("M/d HH:mm").withZone(zone).format(i)
    }
}
