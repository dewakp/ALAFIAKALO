// Copyright © 2026 Wole Akpose / 6igma Health Inc.
// All rights reserved. ALAFIA — proprietary and confidential.

import Foundation

/// A number the patient TYPED, in whatever decimal separator their keyboard
/// gave them.
///
/// `Double("0,5")` is **nil** — Swift's initialiser is locale-independent and
/// accepts only a dot, exactly as Kotlin's `toDoubleOrNull` does. Measured
/// across ALAFIA's eleven languages, five use something else:
///
///     fr [,]   de [,]   es [,]   pt [,]   ar [٫]        sw [.]   en [.]
///
/// The keyboard follows the DEVICE locale, so this applies however the patient
/// set the in-app language. The damage was silent and landed on the most
/// dangerous field in the product — `MedicationsView.saveDose` read
/// `guard let value = Double(amount)`, so a half-tablet typed as `0,5` simply
/// would not save, and the weights in `HemodialysisView` went to nil and were
/// dropped without a word.
///
/// **A lone comma is a decimal separator, not grouping.** These fields use a
/// decimal keypad, which offers no grouping key — the patient *cannot* type a
/// thousands separator — so `1,234` is 1.234. Repeated separators
/// (`1.234.567`) ARE grouping, but only when every group after the first is
/// three digits; `1.2.3` is nonsense and is refused rather than becoming 123.
///
/// Deliberately NOT `NumberFormatter` with the current locale: §3aw records
/// that the app's language is an `\.locale` environment choice, NOT the device
/// locale, so a formatter keyed to either one would disagree with the keyboard
/// for anyone whose phone and app languages differ. This reads what was typed.
///
/// The Android twin is `com.alafia.android.LocaleDecimal`; the two are kept
/// deliberately identical in behaviour, including the refusals.
enum LocaleDecimal {

    /// The typed text as a number, or nil when it is not one.
    static func parse(_ raw: String?) -> Double? {
        guard let normalised = normalise(raw) else { return nil }
        return Double(normalised)
    }

    /// Typed text -> a string `Double.init` accepts, or nil.
    ///
    /// Exposed so the tests can pin the separator decision itself: a wrong
    /// separator and a failed parse are different bugs and should not be
    /// indistinguishable.
    static func normalise(_ raw: String?) -> String? {
        guard let trimmed = raw?.trimmingCharacters(in: .whitespacesAndNewlines),
              !trimmed.isEmpty else { return nil }

        // Arabic-Indic digits and the Arabic separators come from an Arabic
        // keyboard; the spaces are French grouping.
        var mapped = ""
        for scalar in trimmed.unicodeScalars {
            switch scalar {
            case "\u{0660}"..."\u{0669}":
                mapped.append(Character(UnicodeScalar(scalar.value - 0x0660 + 48)!))
            case "\u{06F0}"..."\u{06F9}":
                mapped.append(Character(UnicodeScalar(scalar.value - 0x06F0 + 48)!))
            case "\u{066B}": mapped.append(".")   // Arabic decimal separator
            case "\u{066C}": mapped.append(",")   // Arabic thousands separator
            case " ", "\u{00A0}", "\u{202F}", "\u{2009}": break
            default: mapped.append(Character(scalar))
            }
        }

        var s = mapped
        var sign = ""
        if s.hasPrefix("-") { sign = "-"; s.removeFirst() }
        else if s.hasPrefix("+") { s.removeFirst() }
        guard !s.isEmpty else { return nil }

        // Anything that is not a digit or a separator is not a number. This is
        // what keeps "12kg" out rather than letting it half-parse the way
        // JavaScript's parseFloat would.
        guard s.allSatisfy({ $0.isASCII && ($0.isNumber || $0 == "." || $0 == ",") }) else {
            return nil
        }

        let dots = s.filter { $0 == "." }.count
        let commas = s.filter { $0 == "," }.count
        let body: String

        if dots == 0 && commas == 0 {
            body = s
        } else if dots > 0 && commas > 0 {
            // Both kinds: the LAST is the decimal separator and everything
            // before it is grouping — "1.234,56" (de) and "1,234.56" (en).
            let lastDot = s.lastIndex(of: ".")
            let lastComma = s.lastIndex(of: ",")
            let decimalAt = max(lastDot ?? s.startIndex, lastComma ?? s.startIndex)
            let whole = s[s.startIndex..<decimalAt]
                .replacingOccurrences(of: ".", with: "")
                .replacingOccurrences(of: ",", with: "")
            let fraction = String(s[s.index(after: decimalAt)...])
            guard !whole.isEmpty, !fraction.isEmpty else { return nil }
            body = "\(whole).\(fraction)"
        } else if dots == 1 || commas == 1 {
            // Exactly one separator: the decimal point, whichever glyph.
            body = s.replacingOccurrences(of: ",", with: ".")
        } else {
            // Repeated separators of one kind are grouping, and only when
            // every group after the first is three digits.
            let separator: Character = dots > 1 ? "." : ","
            let parts = s.split(separator: separator, omittingEmptySubsequences: false)
            guard let first = parts.first, !first.isEmpty else { return nil }
            guard parts.dropFirst().allSatisfy({ $0.count == 3 }) else { return nil }
            body = parts.joined()
        }

        guard !body.isEmpty, body != "." else { return nil }
        return sign + body
    }
}
