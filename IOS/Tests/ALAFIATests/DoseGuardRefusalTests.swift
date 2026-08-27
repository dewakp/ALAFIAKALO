import XCTest
@testable import ALAFIA

/// The dose guard's refusal must survive the trip to the UI.
///
/// The body below is the real response captured from
/// `POST /medications/dose-logs` for "Calcium Carbonated" 1000 mg — the 422 that
/// blocked a production dose. `APIClient` decoded `detail` as a String, which
/// simply fails on an object, so the user was shown "Request failed (422)": no
/// reason, no suggestion, no route forward, on a guard that had already worked
/// out that the name should be "Calcium Carbonate".
final class DoseGuardRefusalTests: XCTestCase {

    private let refusalBody = Data("""
    {"detail": {
       "message": "This dose looks wrong — please check it.",
       "findings": [{
         "level": "error",
         "code": "unknown_medication",
         "message": "“Calcium Carbonated” isn’t a medication in RxNorm. The closest match is “Calcium Carbonate” — please confirm what was taken.",
         "suggestion": "Calcium Carbonate"
       }],
       "override_with": "acknowledge_unusual"
    }}
    """.utf8)

    func testRefusalIsDecodedNotFlattened() throws {
        let error = APIError.structured(message: "This dose looks wrong — please check it.",
                                        status: 422, body: refusalBody)
        let refusal = try XCTUnwrap(DoseGuardRefusal.from(error), "the refusal must reach the UI")
        XCTAssertEqual(refusal.detail.findings.count, 1)
        XCTAssertEqual(refusal.detail.findings[0].code, "unknown_medication")
        XCTAssertEqual(refusal.detail.findings[0].level, "error")
    }

    /// The correction is the whole point: the guard already knows the answer.
    func testSuggestedSpellingSurvives() throws {
        let refusal = try XCTUnwrap(DoseGuardRefusal.from(
            APIError.structured(message: "x", status: 422, body: refusalBody)))
        XCTAssertEqual(refusal.detail.findings[0].suggestion, "Calcium Carbonate")
    }

    /// Without this the user is blocked with no route forward on a true record.
    func testOverrideFieldSurvives() throws {
        let refusal = try XCTUnwrap(DoseGuardRefusal.from(
            APIError.structured(message: "x", status: 422, body: refusalBody)))
        XCTAssertEqual(refusal.detail.overrideWith, "acknowledge_unusual")
    }

    /// An ordinary failure must still take the ordinary path. A refusal has a
    /// reason and a way through; a dead network has neither.
    func testNonRefusalIsNotMistakenForOne() {
        XCTAssertNil(DoseGuardRefusal.from(APIError.serverError))
        XCTAssertNil(DoseGuardRefusal.from(APIError.clientError("already logged")))
        XCTAssertNil(DoseGuardRefusal.from(
            APIError.structured(message: "x", status: 400, body: refusalBody)))
    }

    /// FastAPI's own validation errors are also 422, with `detail` as a LIST.
    /// Those carry nothing a patient can act on, so they must not render as a
    /// guard panel with an empty explanation.
    func testPydanticValidationErrorIsNotARefusal() {
        let pydantic = Data("""
        {"detail":[{"loc":["body","dose_amount"],"msg":"field required"}]}
        """.utf8)
        XCTAssertNil(DoseGuardRefusal.from(
            APIError.structured(message: "x", status: 422, body: pydantic)))
    }

    /// A refusal with nothing to say is no better than the generic message.
    func testEmptyFindingsIsNotARefusal() {
        let empty = Data("""
        {"detail":{"message":"nope","findings":[],"override_with":"acknowledge_unusual"}}
        """.utf8)
        XCTAssertNil(DoseGuardRefusal.from(
            APIError.structured(message: "x", status: 422, body: empty)))
    }

    /// `acknowledge_unusual` must reach the wire, or "log it anyway" silently
    /// repeats the request that was already refused.
    func testAcknowledgeFlagIsEncoded() throws {
        let dose = MedicationDoseLogCreate(
            medicationName: "Calcium Carbonate", logDate: "2026-08-27",
            doseAmount: 1000, doseUnit: "mg", acknowledgeUnusual: true)
        let json = try JSONSerialization.jsonObject(
            with: try JSONEncoder().encode(dose)) as? [String: Any]
        XCTAssertEqual(json?["acknowledge_unusual"] as? Bool, true)
    }

    /// It must also default to false — an override is a decision, not a default.
    func testAcknowledgeFlagDefaultsToFalse() throws {
        let dose = MedicationDoseLogCreate(
            medicationName: "Calcium Carbonate", logDate: "2026-08-27",
            doseAmount: 1000, doseUnit: "mg")
        let json = try JSONSerialization.jsonObject(
            with: try JSONEncoder().encode(dose)) as? [String: Any]
        XCTAssertEqual(json?["acknowledge_unusual"] as? Bool, false)
    }
}

/// The picker's provenance line is what separates a drug this patient takes from
/// one they typed once by mistake — 489 logs versus 1, on this record.
final class MedicationSuggestionTests: XCTestCase {

    func testHistoryShowsCountAndLastTaken() {
        let s = MedicationSuggestion(name: "Calcium carbonate", timesLogged: 489, lastTaken: "2026-08-24")
        XCTAssertEqual(s.provenance, "Taken 489× · last 2026-08-24")
    }

    func testPrescriptionSaysSo() {
        let s = MedicationSuggestion(name: "Calcitriol", timesLogged: nil, lastTaken: nil)
        XCTAssertEqual(s.provenance, "On your prescription list")
    }

    /// Case-insensitive identity: the same drug arrives as both
    /// "Calcium Carbonate" and "Calcium carbonate", and two rows misstate a regimen.
    func testIdentityIsCaseInsensitive() {
        XCTAssertEqual(MedicationSuggestion(name: "Calcium Carbonate", timesLogged: 1, lastTaken: nil).id,
                       MedicationSuggestion(name: "calcium carbonate", timesLogged: 2, lastTaken: nil).id)
    }
}
