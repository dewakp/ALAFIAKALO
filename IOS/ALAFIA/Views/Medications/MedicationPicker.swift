import SwiftUI

/// One option offered in the intake form, with the evidence for offering it.
///
/// `timesLogged` is the difference between a drug this patient takes and one
/// they typed once by mistake, which is why provenance is shown rather than a
/// bare name: on this record "Calcium carbonate" has 489 logs and "Calcium
/// Calcitriol" has one.
struct MedicationSuggestion: Identifiable, Equatable {
    let name: String
    let timesLogged: Int?
    let lastTaken: String?

    var id: String { name.lowercased() }

    /// nil `timesLogged` means it came from the prescription list, not history.
    var provenance: String {
        guard let timesLogged else { return "On your prescription list" }
        if let lastTaken { return "Taken \(timesLogged)× · last \(lastTaken)" }
        return "Taken \(timesLogged)×"
    }
}

/// Type-ahead over what this patient actually takes.
///
/// The field was a plain `TextField` beside a menu listing PRESCRIPTIONS only.
/// On an account holding 943 dose logs and zero prescriptions that menu was
/// empty and typing "Calcium" offered nothing — while the patient's own history
/// held Calcium carbonate 489 times (canon §3aa: prescribed and taken are
/// different facts).
///
/// Worth stating plainly: a picker is also a SAFETY control. The 422 that
/// blocked a real dose was "Calcium Carbonated", one letter off a drug logged
/// hundreds of times. **Choosing from a list cannot produce a typo** — that is
/// the actual fix for it, not a looser guard.
///
/// Matching is local: the list is this patient's own drugs, so there is no
/// request per keystroke and no failure mode where the suggestions vanish.
struct MedicationPickerField: View {
    @Binding var name: String
    let options: [MedicationSuggestion]
    /// Called when an option is chosen, so the form can adopt its unit too.
    var onSelect: (MedicationSuggestion) -> Void = { _ in }

    @FocusState private var focused: Bool
    @State private var dismissed = false

    private var matches: [MedicationSuggestion] {
        let q = name.trimmingCharacters(in: .whitespaces).lowercased()
        guard !q.isEmpty else { return Array(options.prefix(8)) }
        return Array(options.filter { $0.name.lowercased().contains(q) }.prefix(8))
    }

    /// An exact hit needs no list — it would only cover the next field.
    private var showList: Bool {
        guard focused, !dismissed, !matches.isEmpty else { return false }
        let typed = name.trimmingCharacters(in: .whitespaces).lowercased()
        return !(matches.count == 1 && matches[0].name.lowercased() == typed)
    }

    var body: some View {
        TextField("Medication name", text: $name)
            .focused($focused)
            .autocorrectionDisabled()
            .textInputAutocapitalization(.words)
            .onChange(of: name) { _, _ in dismissed = false }

        if showList {
            ForEach(matches) { option in
                Button {
                    name = option.name
                    dismissed = true
                    focused = false
                    onSelect(option)
                } label: {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(option.name)
                            .font(.subheadline)
                            .foregroundStyle(.primary)
                        Text(option.provenance)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
        } else if options.isEmpty {
            // Not an error, and not a silent blank: this account genuinely has
            // nothing logged yet. Say which it is (canon §3aa).
            Text("Nothing logged yet — type the medication name.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }
}

/// What the dose guard refused, rendered so the patient can act on it.
///
/// The API returns `findings` naming the cause and `override_with`. Dropping
/// them left "This dose looks wrong — please check it.", which reads as the DOSE
/// being questioned — so a correct 1000 mg calcium tablet looked like a false
/// positive with no way through, when it was the NAME that was wrong and RxNorm
/// had already computed the fix.
struct DoseGuardFindingsView: View {
    let detail: DoseGuardRefusal.Detail
    let onUseSuggestion: (String) -> Void
    let onAcknowledge: () -> Void

    // Each element is its OWN Form row, exactly like MedicationPickerField.
    //
    // The first version wrapped all of this in a single `VStack`, which a Form
    // renders as ONE row — and a List row holding several buttons swallows the
    // taps rather than routing them, so BOTH exits were dead on the device.
    // The panel looked perfect in a screenshot and could not be used: the guard
    // explained itself and then refused to act, which is the failure this whole
    // panel exists to prevent. The build was green and the unit tests were
    // green; only tapping it in the simulator found this.
    var body: some View {
        Label(detail.message, systemImage: "exclamationmark.triangle.fill")
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(.orange)

        ForEach(detail.findings) { finding in
            Text(finding.message)
                .font(.footnote)
                .foregroundStyle(.primary)

            if let suggestion = finding.suggestion, !suggestion.isEmpty {
                Button("Use \u{201C}\(suggestion)\u{201D}") { onUseSuggestion(suggestion) }
                    .font(.footnote.weight(.semibold))
                    .buttonStyle(.borderless)
            }
        }

        if detail.overrideWith != nil {
            // A guard with no route forward blocks a true clinical record.
            Button("This is correct — log it anyway", action: onAcknowledge)
                .font(.footnote)
                .buttonStyle(.borderless)
                .foregroundStyle(.secondary)
        }
    }
}
