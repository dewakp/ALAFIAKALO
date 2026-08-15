import Foundation
import Combine

/// Roles that can practise in clinician mode.
///
/// This list lives here rather than inside a view because three places used to
/// need it — the tab bar, the Health hub and the Role screen — and a copy in
/// each is how they drift apart.
enum ClinicianRoles {
    static let all: Set<String> = [
        "physician", "surgeon", "nurse_practitioner",
        "physician_assistant", "resident", "fellow", "attending_physician",
        "cardiologist", "dermatologist", "endocrinologist", "gastroenterologist",
        "neurologist", "oncologist", "pediatrician", "radiologist",
        "general_surgeon", "orthopedic_surgeon", "neurosurgeon",
        "cardiothoracic_surgeon", "plastic_surgeon", "vascular_surgeon",
        "oral_surgeon", "clinical_nurse_specialist", "nurse_anesthetist",
        "nurse_midwife", "charge_nurse", "nurse_administrator",
        "medical_director", "chief_medical_officer",
    ]

    /// True when the user holds any role that can enter clinician mode.
    static func contains(user: User?) -> Bool {
        guard let user else { return false }
        var roles = user.activeRoles ?? []
        if let primary = user.primaryRole { roles.append(primary) }
        return roles.contains { all.contains($0) }
    }

    /// The clinician role the user actually holds, for labelling.
    static func held(by user: User?) -> String? {
        guard let user else { return nil }
        var roles = user.activeRoles ?? []
        if let primary = user.primaryRole { roles.append(primary) }
        return roles.first { all.contains($0) }
    }
}

/// Which persona the app is presenting: the user's own record, or their
/// clinical practice. Switching swaps the entire tab bar rather than adding a
/// screen, so a physician reviewing patients is not navigating past their own
/// meal diary to do it.
@MainActor
final class ClinicianMode: ObservableObject {
    @Published private(set) var isActive = false

    /// Enter clinician mode. Callers pass the current user so a patient account
    /// can never be put into a mode its roles do not allow.
    func enter(as user: User?) {
        guard ClinicianRoles.contains(user: user) else { return }
        isActive = true
    }

    func exit() {
        isActive = false
    }

    /// Drop out of clinician mode when the signed-in user can no longer hold it
    /// — a different account signing in, or a role revoked mid-session.
    func reconcile(with user: User?) {
        if isActive && !ClinicianRoles.contains(user: user) {
            isActive = false
        }
    }
}
