import SwiftUI

/// The intradialytic readings grid on the patient's own flowsheet.
///
/// iOS could DISPLAY readings and never record one: the model existed
/// (`IntradialyticReadingCreate`) and nothing ever called the endpoint, so a
/// patient on iPhone could see a treatment's BP/pulse/UF timeline only if it had
/// been entered somewhere else. Web has had this grid all along.
///
/// Write semantics match web exactly, and they matter:
///
///   - A row that already exists is PUT, never re-POSTed. Re-posting is how
///     editing a session grew its flowsheet — the corrected row differs from the
///     stored one, so it landed as an extra reading rather than replacing it.
///   - A row removed here is DELETEd server-side, or it silently returns on
///     reload.
///   - `reading_time` is NORMALISED, not merely validated. "14:30 " passes a
///     trimmed regex and is then rejected by the API as an invalid timezone
///     sign, on a completed flowsheet.
///   - A blank time is sent as null. The column is nullable precisely so
///     "not stated" survives as not stated instead of becoming a measured
///     00:00 — 3664 rows were fabricated that way.
struct IntradialyticEditor: View {
    @Binding var rows: [EditableReading]
    /// Server ids of rows the user removed. Deleting locally is not enough —
    /// the row returns on the next load unless it is DELETEd.
    @Binding var removedIds: [Int]

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Intradialytic Readings").font(.subheadline.bold())
                Spacer()
                Text("^[\(rows.count) row](inflect: true)")
                    .font(.caption).foregroundStyle(.secondary)
            }

            ForEach($rows) { $row in
                ReadingRowEditor(row: $row) {
                    if let serverId = row.serverId { removedIds.append(serverId) }
                    rows.removeAll { $0.id == row.id }
                }
            }

            Button {
                // Carry the previous row's machine settings forward: on a real
                // flowsheet blood flow and dialysate rate rarely change between
                // timepoints, and retyping them invites transcription errors.
                var next = EditableReading()
                if let last = rows.last {
                    next.bloodFlowRate = last.bloodFlowRate
                    next.dialysateRate = last.dialysateRate
                    next.ufRate = last.ufRate
                }
                rows.append(next)
            } label: {
                Label("Add reading", systemImage: "plus.circle")
            }
            .buttonStyle(.bordered)
        }
    }
}

private struct ReadingRowEditor: View {
    @Binding var row: EditableReading
    let onDelete: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                TextField("HH:MM", text: $row.readingTime)
                    .frame(width: 74)
                    .textFieldStyle(.roundedBorder)
                if !row.readingTime.isEmpty && row.normalisedTime == nil {
                    // Say it here rather than let the API reject the save.
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundStyle(.orange)
                        .accessibilityLabel("Not a valid time")
                }
                Spacer()
                Button(role: .destructive, action: onDelete) {
                    Image(systemName: "trash")
                }
                .buttonStyle(.borderless)
                .accessibilityLabel("Delete reading")
            }
            HStack(spacing: 6) {
                num("Sys", $row.systolicBp)
                num("Dia", $row.diastolicBp)
                num("Pulse", $row.pulse)
                num("MAP", $row.meanArterialPressure)
            }
            HStack(spacing: 6) {
                num("BFR", $row.bloodFlowRate)
                num("DR", $row.dialysateRate)
                num("UFR", $row.ufRate)
                num("UF Vol", $row.ufVolumeRemoved)
            }
            HStack(spacing: 6) {
                num("Art P", $row.arterialPressure)
                num("Ven P", $row.venousPressure)
                TextField("Remarks", text: $row.remarks).textFieldStyle(.roundedBorder)
            }
        }
        .padding(10)
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 10))
    }

    private func num(_ label: String, _ value: Binding<String>) -> some View {
        TextField(label, text: value)
            .keyboardType(.decimalPad)
            .textFieldStyle(.roundedBorder)
            .frame(minWidth: 52)
    }
}

/// One row of the grid. `serverId` is what decides PUT vs POST — a row that came
/// from the server is updated in place, a new one is created.
struct EditableReading: Identifiable, Equatable {
    let id = UUID()
    var serverId: Int?
    var readingTime = ""
    var systolicBp = ""
    var diastolicBp = ""
    var pulse = ""
    var meanArterialPressure = ""
    var dialysateRate = ""
    var dialysateVolumeRemaining = ""
    var ufRate = ""
    var ufVolumeRemoved = ""
    var bloodFlowRate = ""
    var arterialPressure = ""
    var venousPressure = ""
    var effluentPressure = ""
    var accessState = ""
    var salineAmount = ""
    var remarks = ""

    init() {}

    init(from r: IntradialyticReading) {
        serverId = r.id
        readingTime = Self.clock(r.readingTime)
        systolicBp = r.systolicBp.map(String.init) ?? ""
        diastolicBp = r.diastolicBp.map(String.init) ?? ""
        pulse = r.pulse.map(String.init) ?? ""
        meanArterialPressure = Self.num(r.meanArterialPressure)
        dialysateRate = Self.num(r.dialysateRate)
        dialysateVolumeRemaining = Self.num(r.dialysateVolumeRemaining)
        ufRate = Self.num(r.ufRate)
        ufVolumeRemoved = Self.num(r.ufVolumeRemoved)
        bloodFlowRate = Self.num(r.bloodFlowRate)
        arterialPressure = Self.num(r.arterialPressure)
        venousPressure = Self.num(r.venousPressure)
        effluentPressure = Self.num(r.effluentPressure)
        accessState = r.accessState ?? ""
        salineAmount = r.salineAmount ?? ""
        remarks = r.remarks ?? ""
    }

    /// Canonical "HH:MM", or nil when the text cannot be one. NORMALISE rather
    /// than validate: an earlier web fix tested `regex.test(t.trim())` and then
    /// posted the untrimmed value, so "14:30 " passed the guard and was rejected
    /// by the API with "invalid time format, invalid timezone sign".
    var normalisedTime: String? {
        let t = readingTime.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty else { return nil }
        let parts = t.split(separator: ":")
        guard parts.count >= 2, let h = Int(parts[0]), let m = Int(parts[1]),
              (0...23).contains(h), (0...59).contains(m) else { return nil }
        return String(format: "%02d:%02d", h, m)
    }

    /// True when the row holds nothing worth sending. An empty row added and
    /// then abandoned must not become a reading.
    var isBlank: Bool {
        normalisedTime == nil && [systolicBp, diastolicBp, pulse, meanArterialPressure,
                                  dialysateRate, ufRate, ufVolumeRemoved, bloodFlowRate,
                                  arterialPressure, venousPressure, remarks]
            .allSatisfy { $0.trimmingCharacters(in: .whitespaces).isEmpty }
    }

    func payload(sessionId: Int) -> IntradialyticReadingCreate {
        IntradialyticReadingCreate(
            sessionId: sessionId,
            // nil, not "00:00" — a blank time is unknown, not midnight.
            readingTime: normalisedTime,
            systolicBp: Int(systolicBp), diastolicBp: Int(diastolicBp),
            pulse: Int(pulse),
            meanArterialPressure: Double(meanArterialPressure),
            dialysateRate: Double(dialysateRate),
            dialysateVolumeRemaining: Double(dialysateVolumeRemaining),
            ufRate: Double(ufRate), ufVolumeRemoved: Double(ufVolumeRemoved),
            bloodFlowRate: Double(bloodFlowRate),
            arterialPressure: Double(arterialPressure),
            venousPressure: Double(venousPressure),
            effluentPressure: Double(effluentPressure),
            accessState: accessState.isEmpty ? nil : accessState,
            salineAmount: salineAmount.isEmpty ? nil : salineAmount,
            remarks: remarks.isEmpty ? nil : remarks)
    }

    private static func clock(_ value: String?) -> String {
        guard let value, !value.isEmpty else { return "" }
        return String(value.prefix(5))
    }

    private static func num(_ value: Double?) -> String {
        guard let value else { return "" }
        return value == value.rounded() ? String(Int(value)) : String(value)
    }
}
