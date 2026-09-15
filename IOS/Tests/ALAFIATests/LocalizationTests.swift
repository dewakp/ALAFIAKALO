import XCTest
@testable import ALAFIA

/// Text built in code must follow the language the patient chose in the app.
///
/// SwiftUI draws a view in the chosen language through `\.locale`, but a
/// `String` a view model assembles never passes through that environment, and
/// `String(localized:)` alone reads the DEVICE language. On an English phone set
/// to French in the app, that is a French screen with English error messages.
final class LocalizationTests: XCTestCase {
    private var previous: String?

    override func setUp() {
        super.setUp()
        previous = UserDefaults.standard.string(forKey: AppLanguage.storageKey)
    }

    override func tearDown() {
        // The test host shares the app's defaults on this simulator; put the
        // patient's choice back exactly as it was.
        if let previous {
            UserDefaults.standard.set(previous, forKey: AppLanguage.storageKey)
        } else {
            UserDefaults.standard.removeObject(forKey: AppLanguage.storageKey)
        }
        super.tearDown()
    }

    func testCodeBuiltTextFollowsTheChosenLanguageNotTheDevice() {
        AppLanguage.choose("fr")
        XCTAssertEqual(AppLanguage.text("Password"), "Mot de passe")

        AppLanguage.choose("es")
        XCTAssertEqual(AppLanguage.text("Password"), "Contraseña")
    }

    func testAnInterpolatedMessageIsTranslatedAndKeepsItsValue() {
        // The shape of every "Failed to …: \(error.localizedDescription)" message.
        AppLanguage.choose("fr")
        let message = AppLanguage.text("Purchase failed: \("card declined")")
        XCTAssertTrue(message.contains("card declined"), message)
        XCTAssertFalse(message.hasPrefix("Purchase failed"), "still English: \(message)")
    }

    func testEnglishIsTheSourceText() {
        AppLanguage.choose("en")
        XCTAssertEqual(AppLanguage.text("Password"), "Password")
    }
}
