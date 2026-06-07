import XCTest
@testable import ALAFIA

final class UserModelTests: XCTestCase {

    private let decoder: JSONDecoder = {
        let d = JSONDecoder()
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        d.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let str = try container.decode(String.self)
            if let date = iso.date(from: str) { return date }
            iso.formatOptions = [.withInternetDateTime]
            if let date = iso.date(from: str) { return date }
            let df = DateFormatter()
            df.dateFormat = "yyyy-MM-dd"
            if let date = df.date(from: str) { return date }
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Bad date: \(str)")
        }
        return d
    }()

    func testUserDecodesFromJSON() throws {
        let json = """
        {
            "id": 1,
            "email": "test@example.com",
            "full_name": "Test User",
            "date_of_birth": null,
            "gender": "male",
            "gender_at_birth": null,
            "profile_picture_url": null,
            "blood_type": null,
            "insurance_id": null,
            "insurance_provider": null,
            "insurance_country": null,
            "height_cm": 180.0,
            "current_weight_kg": 75.0,
            "target_weight_kg": null,
            "locale": "en",
            "timezone": "UTC",
            "country": "US",
            "preferred_units": "metric",
            "preferred_language": "en",
            "allergies": null,
            "food_intolerances": null,
            "dietary_restrictions": null,
            "dietary_preferences": null,
            "family_history": null,
            "activity_level": "moderate",
            "fitness_goals": null,
            "preferred_activities": null,
            "exercise_frequency_per_week": 3,
            "smoking_status": null,
            "alcohol_consumption": null,
            "sleep_schedule": null,
            "occupation": null,
            "stress_level": null,
            "ai_coaching_enabled": true,
            "ai_personality_preference": null,
            "ai_language_complexity": null,
            "data_sharing_consent": true,
            "ai_training_consent": false,
            "is_active": true,
            "created_at": "2026-01-01T00:00:00Z",
            "system_id": "SID-12345",
            "primary_role": "patient",
            "active_roles": ["patient"],
            "is_healthcare_professional": false
        }
        """.data(using: .utf8)!

        let user = try decoder.decode(User.self, from: json)

        XCTAssertEqual(user.id, 1)
        XCTAssertEqual(user.email, "test@example.com")
        XCTAssertEqual(user.fullName, "Test User")
        XCTAssertEqual(user.heightCm, 180.0)
        XCTAssertEqual(user.systemId, "SID-12345")
        XCTAssertTrue(user.isActive)
        XCTAssertEqual(user.firstName, "Test")
    }

    func testUserFirstNameSingleWord() throws {
        let json = """
        {
            "id": 2,
            "email": "a@b.com",
            "full_name": "Madonna",
            "is_active": true,
            "created_at": "2026-01-01T00:00:00Z"
        }
        """.data(using: .utf8)!

        let user = try decoder.decode(User.self, from: json)
        XCTAssertEqual(user.firstName, "Madonna")
    }
}

final class APIErrorTests: XCTestCase {

    func testUnauthorizedDescription() {
        let error = APIError.unauthorized
        XCTAssertEqual(error.errorDescription, "Please log in again")
    }

    func testServerErrorDescription() {
        let error = APIError.serverError
        XCTAssertEqual(error.errorDescription, "Server error — try again later")
    }

    func testClientErrorPreservesMessage() {
        let error = APIError.clientError("Email already registered")
        XCTAssertEqual(error.errorDescription, "Email already registered")
    }

    func testUnknownErrorShowsCode() {
        let error = APIError.unknown(418)
        XCTAssertEqual(error.errorDescription, "Unexpected error (418)")
    }
}
