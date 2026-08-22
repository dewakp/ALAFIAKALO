import SwiftUI

/// Structured capture for drugs given DURING a dialysis session.
///
/// The HD flowsheet had no drugs field at all — a decade of Epogene, Venofer and
/// Doxercalciferol reached the database only by import, and nothing else in the
/// app could see it (CLAUDE.md §3aa: the medication picture has THREE sources,
/// and this is the unread one).
///
/// It still serialises to the same `Name (dose); Name (dose)` string the 1,964
/// historical rows use, so a row typed in 2019 and a row captured here parse
/// identically and no migration is needed to make history readable.
struct DrugRow: Identifiable, Equatable {
    let id = UUID()
    var name: String = ""
    var dose: String = ""
}

enum FlowsheetDrugText {
    /// `Name (dose); Name` → rows. Mirrors the backend parser.
    static func parse(_ text: String?) -> [DrugRow] {
        guard let text, !text.trimmingCharacters(in: .whitespaces).isEmpty else { return [] }

        // Split on ";" at paren depth 0 only. A semicolon also occurs INSIDE a
        // dose — "Sodium Citrate (12 ml Venous; 3ml Arterial)" is ONE drug, and
        // splitting naively invents one called "3ml Arterial)".
        var items: [String] = []
        var depth = 0
        var current = ""
        for ch in text {
            if ch == "(" { depth += 1 }
            else if ch == ")" { depth = max(0, depth - 1) }
            if ch == ";" && depth == 0 {
                items.append(current); current = ""
            } else {
                current.append(ch)
            }
        }
        items.append(current)

        return items.compactMap { raw in
            let item = raw.trimmingCharacters(in: .whitespaces)
            guard !item.isEmpty else { return nil }
            guard let open = item.firstIndex(of: "("), let close = item.lastIndex(of: ")"),
                  open < close else {
                return DrugRow(name: item, dose: "")
            }
            let name = String(item[item.startIndex..<open]).trimmingCharacters(in: .whitespaces)
            let dose = String(item[item.index(after: open)..<close])
                .trimmingCharacters(in: .whitespaces)
            guard !name.isEmpty else { return nil }
            return DrugRow(name: name, dose: dose)
        }
    }

    /// Rows → `Name (dose); Name`. Round-trips with `parse`.
    static func format(_ rows: [DrugRow]) -> String {
        rows.compactMap { row -> String? in
            // Parentheses delimit the dose; one inside a name would make the
            // value re-parse as something else.
            let name = row.name.replacingOccurrences(of: "(", with: "")
                .replacingOccurrences(of: ")", with: "")
                .trimmingCharacters(in: .whitespaces)
            guard !name.isEmpty else { return nil }   // a dose with no drug is not a fact
            let dose = row.dose.replacingOccurrences(of: "(", with: "")
                .replacingOccurrences(of: ")", with: "")
                .trimmingCharacters(in: .whitespaces)
            return dose.isEmpty ? name : "\(name) (\(dose))"
        }.joined(separator: "; ")
    }

    /// Offered as suggestions. Mirrors COMMON_DIALYSIS_DRUGS on the backend;
    /// free text stays available so an unlisted drug can still be recorded.
    static let common: [(name: String, hint: String)] = [
        ("Epogene", "e.g. 3,000 SQ"),
        ("Aranesp", "e.g. 60 mcg"),
        ("Venofer", "e.g. 100 mg"),
        ("Ferrlecit", "e.g. 125 mg"),
        ("Doxercalciferol", "e.g. 2 mcg"),
        ("Paricalcitol", "e.g. 5 mcg"),
        ("Calcitriol", "e.g. 1 mcg"),
        ("Sodium Citrate", "e.g. 2.5 ml x 2"),
        ("Heparin", "e.g. 5,000 units"),
        ("Alteplase", "e.g. 2 mg"),
    ]
}

struct DrugsAdministeredEditor: View {
    /// The serialised field value. The editor owns rows and writes back a string.
    @Binding var text: String
    @State private var rows: [DrugRow] = []
    @State private var seeded = false

    var body: some View {
        Group {
            if rows.isEmpty {
                Text("No drugs recorded for this session.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            ForEach($rows) { $row in
                VStack(alignment: .leading, spacing: 4) {
                    TextField("Drug", text: $row.name)
                        .textInputAutocapitalization(.words)
                        .autocorrectionDisabled()
                    TextField(hint(for: row.name), text: $row.dose)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .autocorrectionDisabled()
                }
                .onChange(of: row) { _, _ in push() }
            }
            .onDelete { offsets in
                rows.remove(atOffsets: offsets)
                push()
            }

            Menu {
                ForEach(FlowsheetDrugText.common, id: \.name) { drug in
                    Button(drug.name) {
                        rows.append(DrugRow(name: drug.name))
                        push()
                    }
                }
                Divider()
                Button("Other…") {
                    rows.append(DrugRow())
                    push()
                }
            } label: {
                Label("Add drug", systemImage: "plus.circle")
            }
        }
        .onAppear {
            // Seed once: re-parsing on every render would fight the user's typing.
            guard !seeded else { return }
            rows = FlowsheetDrugText.parse(text)
            seeded = true
        }
    }

    private func hint(for name: String) -> String {
        FlowsheetDrugText.common
            .first { $0.name.lowercased() == name.lowercased() }?.hint ?? "dose"
    }

    private func push() { text = FlowsheetDrugText.format(rows) }
}
