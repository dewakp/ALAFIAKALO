import XCTest
@testable import ALAFIA

// MARK: - NutritionLog Model Tests

final class NutritionLogModelTests: XCTestCase {

    private let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        d.dateDecodingStrategy = .custom { dec in
            let c = try dec.singleValueContainer()
            let s = try c.decode(String.self)
            if let date = iso.date(from: s) { return date }
            iso.formatOptions = [.withInternetDateTime]
            if let date = iso.date(from: s) { return date }
            throw DecodingError.dataCorruptedError(in: c, debugDescription: "Bad date: \(s)")
        }
        return d
    }()

    private func makeLog(extras: [String: Any] = [:]) throws -> NutritionLog {
        var base: [String: Any] = [
            "id": 1, "user_id": 42,
            "log_date": "2026-04-28",
            "meal_type": "breakfast",
            "food_name": "Oatmeal",
            "calories": 150.0,
            "protein_g": 5.0,
            "carbs_g": 27.0,
            "fat_g": 2.5,
            "created_at": "2026-04-28T08:00:00Z",
        ]
        base.merge(extras) { _, new in new }
        let data = try JSONSerialization.data(withJSONObject: base)
        return try decoder.decode(NutritionLog.self, from: data)
    }

    func testBasicDecoding() throws {
        let log = try makeLog()
        XCTAssertEqual(log.id, 1)
        XCTAssertEqual(log.foodName, "Oatmeal")
        XCTAssertEqual(log.mealType, "breakfast")
        XCTAssertEqual(log.calories, 150.0)
        XCTAssertEqual(log.proteinG, 5.0)
    }

    func testOptionalNutrientsAreNilWhenAbsent() throws {
        let log = try makeLog()
        XCTAssertNil(log.fiberG)
        XCTAssertNil(log.sodiumMg)
        XCTAssertNil(log.vitaminCMg)
        XCTAssertNil(log.notes)
    }

    func testExtendedNutrientsDecoded() throws {
        let log = try makeLog(extras: [
            "extended_nutrients": ["omega3_g": 0.5, "selenium_mcg": 12.0]
        ])
        XCTAssertEqual(log.extendedNutrients?["omega3_g"], 0.5)
        XCTAssertEqual(log.extendedNutrients?["selenium_mcg"], 12.0)
    }

    func testMealTypeBreakfastLunchDinner() throws {
        for mealType in ["breakfast", "lunch", "dinner", "snack"] {
            let log = try makeLog(extras: ["meal_type": mealType])
            XCTAssertEqual(log.mealType, mealType)
        }
    }

    // NutritionLogCreate — encoding

    func testNutritionLogCreateEncodes() throws {
        let create = NutritionLogCreate(
            logDate: "2026-04-28",
            mealType: "lunch",
            foodName: "Brown rice",
            servingSize: "200g",
            fdcId: nil,
            calories: 220.0,
            proteinG: 4.5,
            carbsG: 45.0,
            fatG: 1.0,
            notes: "side dish"
        )
        let data = try JSONEncoder().encode(create)
        let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]
        XCTAssertEqual(json["log_date"] as? String, "2026-04-28")
        XCTAssertEqual(json["meal_type"] as? String, "lunch")
        XCTAssertEqual(json["food_name"] as? String, "Brown rice")
        XCTAssertNil(json["fdc_id"])
    }
}

// MARK: - LabResult Model Tests

final class LabResultModelTests: XCTestCase {

    private let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        d.dateDecodingStrategy = .custom { dec in
            let c = try dec.singleValueContainer()
            let s = try c.decode(String.self)
            if let date = iso.date(from: s) { return date }
            iso.formatOptions = [.withInternetDateTime]
            if let date = iso.date(from: s) { return date }
            throw DecodingError.dataCorruptedError(in: c, debugDescription: "Bad date: \(s)")
        }
        return d
    }()

    private func makeResult(extras: [String: Any] = [:]) throws -> LabResult {
        var base: [String: Any] = [
            "id": 10, "user_id": 42,
            "test_date": "2026-04-28",
            "test_name": "Albumin",
            "value": 4.2,
            "unit": "g/dL",
            "status": "final",
            "created_at": "2026-04-28T10:00:00Z",
        ]
        base.merge(extras) { _, new in new }
        let data = try JSONSerialization.data(withJSONObject: base)
        return try decoder.decode(LabResult.self, from: data)
    }

    func testBasicDecoding() throws {
        let r = try makeResult()
        XCTAssertEqual(r.id, 10)
        XCTAssertEqual(r.testName, "Albumin")
        XCTAssertEqual(r.value, 4.2)
        XCTAssertEqual(r.unit, "g/dL")
        XCTAssertEqual(r.status, "final")
    }

    func testReferenceRangeDecoded() throws {
        let r = try makeResult(extras: ["reference_range_low": 3.4, "reference_range_high": 4.8])
        XCTAssertEqual(r.referenceRangeLow, 3.4)
        XCTAssertEqual(r.referenceRangeHigh, 4.8)
        XCTAssertEqual(r.referenceRange, "3.4 - 4.8 g/dL")
    }

    func testDisplayValueWithUnit() throws {
        let r = try makeResult()
        XCTAssertEqual(r.displayValue, "4.2 g/dL")
    }

    func testDisplayValueFallsBackToValueString() throws {
        var base: [String: Any] = [
            "id": 11, "user_id": 42,
            "test_date": "2026-04-28",
            "test_name": "Culture",
            "value_string": "Negative",
            "unit": nil,
            "status": "final",
            "created_at": "2026-04-28T10:00:00Z",
        ]
        let data = try JSONSerialization.data(withJSONObject: base)
        let r = try decoder.decode(LabResult.self, from: data)
        XCTAssertEqual(r.displayValue, "Negative")
    }

    func testOptionalFieldsNilWhenAbsent() throws {
        let r = try makeResult()
        XCTAssertNil(r.loincCode)
        XCTAssertNil(r.category)
        XCTAssertNil(r.orderingProvider)
        XCTAssertNil(r.performingLab)
        XCTAssertNil(r.referenceRange)
    }
}

// MARK: - Medication Model Tests

final class MedicationModelTests: XCTestCase {

    private let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        d.dateDecodingStrategy = .custom { dec in
            let c = try dec.singleValueContainer()
            let s = try c.decode(String.self)
            if let date = iso.date(from: s) { return date }
            iso.formatOptions = [.withInternetDateTime]
            if let date = iso.date(from: s) { return date }
            throw DecodingError.dataCorruptedError(in: c, debugDescription: "Bad date: \(s)")
        }
        return d
    }()

    private func makeMed(extras: [String: Any] = [:]) throws -> Medication {
        var base: [String: Any] = [
            "id": 5, "user_id": 42,
            "name": "Lisinopril",
            "dosage": "10",
            "dosage_unit": "mg",
            "frequency": "once daily",
            "route": "oral",
            "is_active": true,
            "created_at": "2026-04-01T00:00:00Z",
        ]
        base.merge(extras) { _, new in new }
        let data = try JSONSerialization.data(withJSONObject: base)
        return try decoder.decode(Medication.self, from: data)
    }

    func testBasicDecoding() throws {
        let med = try makeMed()
        XCTAssertEqual(med.id, 5)
        XCTAssertEqual(med.name, "Lisinopril")
        XCTAssertEqual(med.dosage, "10")
        XCTAssertEqual(med.dosageUnit, "mg")
        XCTAssertTrue(med.isActive)
    }

    func testDosageDisplay() throws {
        let med = try makeMed()
        XCTAssertEqual(med.dosageDisplay, "10 mg")
    }

    func testDosageDisplayWithNilUnit() throws {
        let med = try makeMed(extras: ["dosage_unit": NSNull()])
        XCTAssertEqual(med.dosageDisplay, "10")
    }

    func testDosageDisplayBothNil() throws {
        let med = try makeMed(extras: ["dosage": NSNull(), "dosage_unit": NSNull()])
        XCTAssertEqual(med.dosageDisplay, "")
    }

    func testOptionalFieldsNilWhenAbsent() throws {
        let med = try makeMed()
        XCTAssertNil(med.rxnormCode)
        XCTAssertNil(med.reason)
        XCTAssertNil(med.sideEffects)
        XCTAssertNil(med.prescribingDoctor)
    }

    func testInactiveMedication() throws {
        let med = try makeMed(extras: ["is_active": false])
        XCTAssertFalse(med.isActive)
    }

    // MedicationCreate — encoding

    func testMedicationCreateEncodes() throws {
        let create = MedicationCreate(
            name: "Warfarin",
            dosage: "5",
            dosageUnit: "mg",
            frequency: "once daily",
            route: "oral",
            startDate: "2026-01-01",
            prescribingDoctor: "Dr. Smith",
            reason: "AFib"
        )
        let data = try JSONEncoder().encode(create)
        let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]
        XCTAssertEqual(json["name"] as? String, "Warfarin")
        XCTAssertEqual(json["dosage_unit"] as? String, "mg")
        XCTAssertEqual(json["prescribing_doctor"] as? String, "Dr. Smith")
        XCTAssertEqual(json["is_active"] as? Bool, true)
    }
}
