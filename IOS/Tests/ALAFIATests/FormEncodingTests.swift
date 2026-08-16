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
