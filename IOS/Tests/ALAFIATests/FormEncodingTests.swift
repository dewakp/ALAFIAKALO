// Copyright © 2026 Wole Akpose / 6igma Health Inc.
// All rights reserved. ALAFIA — proprietary and confidential.

import XCTest
@testable import ALAFIA

/// Form-body encoding.
///
/// `postForm`/`postFormWithCSRF` built the body with `.urlQueryAllowed`, which is
/// the character set for query STRINGS and therefore leaves `& = + ; $` intact —
/// they are legal there. In an `application/x-www-form-urlencoded` BODY, `&`
/// separates fields, so a password containing one was cut short at it.
///
/// Observed against the running API: the password `f8&$dfUHa%fg9R_SA@qK` arrived
/// as `f8`, the server answered 401 "Incorrect email or password", and the app
/// showed "Please log in again" with the correct password on screen. Web and
/// Android were unaffected — they use URLSearchParams and Retrofit @Field, which
/// encode properly. Only iOS hand-rolled it.
final class FormEncodingTests: XCTestCase {

    /// Parse a form body the way a server does, so the assertions are about what
    /// actually arrives rather than about the string we produced.
    private func parse(_ body: String) -> [String: String] {
        var out: [String: String] = [:]
        for pair in body.split(separator: "&") {
            let kv = pair.split(separator: "=", maxSplits: 1).map(String.init)
            guard kv.count == 2 else { continue }
            out[kv[0].removingPercentEncoding ?? kv[0]] = kv[1].removingPercentEncoding ?? kv[1]
        }
        return out
    }

    func testAmpersandInPasswordSurvives() {
        let password = "f8&$dfUHa%fg9R_SA@qK"
        let body = APIClient.formURLEncoded(["username": "deji.adesida@alafia.app",
                                             "password": password])
        let parsed = parse(body)
        XCTAssertEqual(parsed["password"], password,
                       "the password was truncated at a separator — this is the login bug")
        XCTAssertEqual(parsed["username"], "deji.adesida@alafia.app")
    }

    func testPlusIsNotDeliveredAsASpace() {
        // The quiet one: `+` survives the wire and decodes server-side to a
        // space, so the password is wrong and nothing reports it.
        let password = "correct horse+battery"
        let parsed = parse(APIClient.formURLEncoded(["password": password]))
        XCTAssertEqual(parsed["password"], password)
        XCTAssertTrue(APIClient.formURLEncoded(["p": "a+b"]).contains("%2B"),
                      "+ must be percent-encoded, not passed through")
    }

    func testEveryReservedCharacterRoundTrips() {
        for ch in ["&", "=", ";", "$", "+", "%", "?", "#", "/", ":", "@", " ", "\"", "'"] {
            let password = "pw\(ch)tail"
            let parsed = parse(APIClient.formURLEncoded(["password": password]))
            XCTAssertEqual(parsed["password"], password,
                           "\(ch) did not survive the round trip")
        }
    }

    func testUnreservedCharactersAreLeftAlone() {
        // Not merely cosmetic: over-encoding is how a working password starts
        // failing after an "improvement".
        let body = APIClient.formURLEncoded(["password": "abcXYZ019-._~"])
        XCTAssertEqual(body, "password=abcXYZ019-._~")
    }

    func testKeysAreEncodedToo() {
        let parsed = parse(APIClient.formURLEncoded(["odd key&": "v"]))
        XCTAssertEqual(parsed["odd key&"], "v")
    }

    func testUnicodePasswordSurvives() {
        let password = "pässwörd✓"
        let parsed = parse(APIClient.formURLEncoded(["password": password]))
        XCTAssertEqual(parsed["password"], password)
    }
}

/// A dose typed as `0,5` must not be lost on the way to the server.
///
/// The same shape as the truncated password above, on a clinical field:
/// `Double("0,5")` is **nil**, so `MedicationsView.saveDose`'s
/// `guard let value = Double(amount)` simply refused to save, and the weights
/// in `HemodialysisView` went to nil and were dropped without a word. Five of
/// ALAFIA's eleven languages use a non-dot decimal separator — fr, de, es, pt
/// use `,` and ar uses `٫` (U+066B) — and the keyboard follows the DEVICE
/// locale, so it applies however the patient set the in-app language.
///
/// These assertions are duplicated almost verbatim in Android's
/// `LocaleDecimalTest`. That is deliberate: §3av's rule is that when the two
/// mobile clients disagree the matching pair is the specification, and a
/// parser is only useful here if both read a typed number the same way.
final class LocaleDecimalTests: XCTestCase {

    func testCommaDecimalIsTheNumberThePatientMeant() {
        XCTAssertEqual(LocaleDecimal.parse("0,5"), 0.5)
        XCTAssertEqual(LocaleDecimal.parse("72,5"), 72.5)
        XCTAssertEqual(LocaleDecimal.parse("37,2"), 37.2)
    }

    func testTheDoseThatUsedToBeRefused() {
        XCTAssertNil(Double("0,5"), "the old behaviour — a half tablet would not save")
        XCTAssertEqual(LocaleDecimal.parse("0,5"), 0.5)
    }

    func testArabicSeparatorAndDigits() {
        XCTAssertEqual(LocaleDecimal.parse("0\u{066B}5"), 0.5)
        XCTAssertEqual(LocaleDecimal.parse("\u{0661}\u{0662}\u{0663}\u{066B}\u{0665}"), 123.5)
    }

    func testDotDecimalIsUnchanged() {
        XCTAssertEqual(LocaleDecimal.parse("0.5"), 0.5)
        XCTAssertEqual(LocaleDecimal.parse("1000"), 1000)
        XCTAssertEqual(LocaleDecimal.parse("  0.5  "), 0.5)
        XCTAssertEqual(LocaleDecimal.parse("-1.5"), -1.5)
    }

    func testLoneCommaIsDecimalBecauseTheKeypadHasNoGroupingKey() {
        XCTAssertEqual(LocaleDecimal.parse("1,234"), 1.234)
    }

    func testRepeatedSeparatorsAreGrouping() {
        XCTAssertEqual(LocaleDecimal.parse("1.234.567"), 1234567)
        XCTAssertEqual(LocaleDecimal.parse("1,234,567"), 1234567)
    }

    func testBothSeparatorsMeansTheLastOneIsTheDecimalPoint() {
        XCTAssertEqual(LocaleDecimal.parse("1.234,56"), 1234.56)   // de
        XCTAssertEqual(LocaleDecimal.parse("1,234.56"), 1234.56)   // en
    }

    func testFrenchGroupingSpaceIsNotPartOfTheNumber() {
        XCTAssertEqual(LocaleDecimal.parse("1\u{00A0}234,5"), 1234.5)
        XCTAssertEqual(LocaleDecimal.parse("1 234,5"), 1234.5)
    }

    func testNonsenseIsRefusedRatherThanHalfParsed() {
        XCTAssertNil(LocaleDecimal.parse("1.2.3"))    // not groups of three
        XCTAssertNil(LocaleDecimal.parse("abc"))
        XCTAssertNil(LocaleDecimal.parse("12kg"))
        XCTAssertNil(LocaleDecimal.parse(""))
        XCTAssertNil(LocaleDecimal.parse("   "))
        XCTAssertNil(LocaleDecimal.parse(nil))
        XCTAssertNil(LocaleDecimal.parse("."))
        XCTAssertNil(LocaleDecimal.parse(","))
    }

    func testNormalisationIsPinnedSeparatelyFromParsing() {
        XCTAssertEqual(LocaleDecimal.normalise("0,5"), "0.5")
        XCTAssertEqual(LocaleDecimal.normalise("1.234,56"), "1234.56")
        XCTAssertEqual(LocaleDecimal.normalise("1,234,567"), "1234567")
        XCTAssertNil(LocaleDecimal.normalise("1.2.3"))
    }
}
