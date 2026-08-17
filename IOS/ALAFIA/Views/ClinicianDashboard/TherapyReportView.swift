import Charts
import SwiftUI

/// The physician's dialysis view: session reports, the intradialytic curve, and
/// sign-off.
///
/// Therapies used to fall through to the generic records table, whose Detail and
/// Session columns were mostly em-dashes on a patient with 2005 sessions. This
/// mirrors the patient's own Session Reports screen so both sides read the same
/// artifact, and adds the two things only a clinician does.
struct TherapyReportView: View {
    let patientId: Int
    let rows: [[String: FlexValue]]
    let days: Int

    /// Only haemodialysis rows carry a session_id; peritoneal has its own screen.
    private var sessions: [[String: FlexValue]] {
        rows.filter { ($0["session_id"]?.number) != nil }
    }

    /// Counted in SQL. The client mean below is only a fallback — averaging the
    /// page makes the tile a function of the page size.
    @State private var summary: TherapySummary?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if sessions.isEmpty {
                Text("No therapy sessions in this period.")
                    .font(.callout).foregroundStyle(.secondary)
            } else {
                statTiles
                Text(windowNote)
                    .font(.caption).foregroundStyle(.secondary)
                ForEach(Array(sessions.enumerated()), id: \.offset) { _, row in
                    NavigationLink {
                        SessionReportView(patientId: patientId,
                                          sessionId: Int(row["session_id"]?.number ?? 0))
                    } label: {
                        sessionCard(row)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .task(id: days) { await loadSummary() }
    }

    /// Says what the window is HIDING. 36 of 2005 sessions is a different
    /// clinical picture from 36 of 36, and the list looks identical.
    private var windowNote: String {
        let shown = sessions.count
        guard let s = summary, s.totalSessionsAllTime > s.totalSessions else {
            return "^[\(shown) session](inflect: true) in this period"
        }
        return "^[\(shown) session](inflect: true) in this period — "
             + "\(s.totalSessionsAllTime) on record since \(s.earliestSession ?? "—")"
    }

    private func loadSummary() async {
        summary = try? await APIClient.shared.get(
            "/clinician-dashboard/patient/\(patientId)/therapy-summary?days=\(days)")
    }

    // MARK: - Tiles

    private func avg(_ key: String) -> Double? {
        let values = sessions.compactMap { $0[key]?.number }
        guard !values.isEmpty else { return nil }
        return values.reduce(0, +) / Double(values.count)
    }

    private var statTiles: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 10) {
                tile("Sessions", "\(summary?.totalSessions ?? sessions.count)", .blue)
                tile("Avg Pre Wt", fmt(summary?.avgPreWeightKg ?? avg("pre_weight_kg"), 1, "kg"), .green)
                tile("Avg Post Wt", fmt(summary?.avgPostWeightKg ?? avg("post_weight_kg"), 1, "kg"), .green)
                tile("Avg UF", fmt(summary?.avgFluidRemovedMl ?? avg("fluid_removed_ml"), 0, "mL"), .orange)
                tile("Avg Duration", fmt(summary?.avgDurationMin ?? avg("duration_minutes"), 0, "min"), .purple)
            }
        }
    }

    /// A missing value is excluded from the mean, never counted as zero — a
    /// session with no recorded duration must not drag the average toward 0.
    private func fmt(_ value: Double?, _ digits: Int, _ unit: String) -> String {
        guard let value else { return "—" }
        return "\(String(format: "%.\(digits)f", value)) \(unit)"
    }

    private func tile(_ label: String, _ value: String, _ tone: Color) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(value).font(.headline).foregroundStyle(tone)
            Text(label).font(.caption2).foregroundStyle(.secondary)
        }
        .padding(10)
        .frame(minWidth: 104, alignment: .leading)
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 10))
        .overlay(alignment: .top) { Rectangle().fill(tone).frame(height: 3) }
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    // MARK: - Session card

    private func sessionCard(_ row: [String: FlexValue]) -> some View {
        let reviewed = row["flowsheet_status"]?.text == "reviewed"
            || row["reviewed_at"]?.display != nil
        return VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Text(row["date"]?.display ?? "—").font(.subheadline.bold())
                if let status = row["status"]?.display {
                    chip(status, .accentColor)
                }
                if reviewed { chip("reviewed", .green) }
                Spacer()
                if let pre = row["pre_weight_kg"]?.number,
                   let post = row["post_weight_kg"]?.number {
                    Text("\(String(format: "%.1f", pre)) → \(String(format: "%.1f", post)) kg")
                        .font(.caption.bold())
                }
            }
            HStack(spacing: 12) {
                if let uf = row["fluid_removed_ml"]?.number {
                    Text("\(String(format: "%.0f", uf)) mL").font(.caption).foregroundStyle(.orange)
                }
                if let dur = row["duration_minutes"]?.number {
                    Text("\(String(format: "%.0f", dur)) min").font(.caption).foregroundStyle(.purple)
                }
                if let n = row["readings"]?.number, n > 0 {
                    Text("^[\(Int(n)) reading](inflect: true)").font(.caption).foregroundStyle(.secondary)
                }
            }
            if row["pre_bp"]?.display != nil || row["post_bp"]?.display != nil {
                Text("BP: Pre \(row["pre_bp"]?.display ?? "—") → Post \(row["post_bp"]?.display ?? "—")")
                    .font(.caption2).foregroundStyle(.secondary)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 10))
    }

    private func chip(_ text: String, _ tone: Color) -> some View {
        Text(text)
            .font(.caption2.bold())
            .padding(.horizontal, 8).padding(.vertical, 2)
            .background(tone.opacity(0.15), in: Capsule())
            .foregroundStyle(tone)
    }
}

// MARK: - One session

struct SessionReportView: View {
    let patientId: Int
    let sessionId: Int

    @State private var report: TherapySessionReport?
    @State private var error: String?
    @State private var actionError: String?
    @State private var busy = false
    @State private var signoff: SessionSignoff?
    @State private var addedNotes: [TherapySessionNote] = []
    @State private var noteText = ""
    @State private var noteBusy = false
    @State private var integrity: SessionIntegrity?
    @State private var integrityError: String?

    /// Same fixed-order palette as the web charts and PatientCategoryView.
    private static let palette: [Color] = [
        Color(red: 0.16, green: 0.47, blue: 0.84),
        Color(red: 0.92, green: 0.41, blue: 0.20),
        Color(red: 0.11, green: 0.69, blue: 0.48),
    ]

    var body: some View {
        Group {
            if let error {
                // A failed load is an error, never an empty state.
                ContentUnavailableView("Unavailable", systemImage: "lock.shield",
                                       description: Text(error))
            } else if let report {
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        facts(report.session)
                        charts(report.readings)
                        readingsTable(report.readings)
                        notesCard(report.notes + addedNotes)
                        integrityCard()
                        signOffCard(signoff ?? report.signoff)
                    }
                    .padding(12)
                }
            } else {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .navigationTitle(report?.session.date ?? "Session")
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
    }

    private func load() async {
        do {
            report = try await APIClient.shared.get(
                "/clinician-dashboard/patient/\(patientId)/therapy-sessions/\(sessionId)")
        } catch {
            self.error = error.localizedDescription.contains("403")
                ? "This patient has not shared therapies."
                : "Could not load this session."
        }
    }

    private func signOff() async {
        busy = true
        actionError = nil
        defer { busy = false }
        do {
            let res: SessionReviewResponse = try await APIClient.shared.post(
                "/clinician-dashboard/patient/\(patientId)/therapy-sessions/\(sessionId)/review",
                body: EmptyBody())
            signoff = res.signoff
        } catch {
            actionError = "Sign-off failed."
        }
    }

    private struct EmptyBody: Encodable {}

    // MARK: cards

    private func facts(_ s: TherapySessionDetail) -> some View {
        let items: [(String, String?)] = [
            ("Therapy", s.name ?? s.therapy?.replacingOccurrences(of: "_", with: " ")),
            ("Facility", s.facilityName),
            ("Access", s.dialysisAccessType),
            ("Attending", s.attendingPhysician),
            ("Nurse", s.attendingNurse),
            ("Duration", s.durationMinutes.map { "\($0) min" }),
            ("Pre weight", s.preDialysisWeightKg.map { String(format: "%.1f kg", $0) }),
            ("Post weight", s.postDialysisWeightKg.map { String(format: "%.1f kg", $0) }),
            ("Dry weight", s.dryWeightKg.map { String(format: "%.1f kg", $0) }),
            ("Fluid removed", s.fluidRemovedMl.map { String(format: "%.0f mL", $0) }),
            ("Blood flow", s.bloodFlowRate.map { String(format: "%.0f mL/min", $0) }),
            ("Pre BP", s.preSystolicBp.flatMap { sys in s.preDiastolicBp.map { "\(sys)/\($0)" } }),
            ("Post BP", s.postSystolicBp.flatMap { sys in s.postDiastolicBp.map { "\(sys)/\($0)" } }),
            ("Pre HR", s.preHeartRate.map(String.init)),
            ("Post HR", s.postHeartRate.map(String.init)),
            ("Tolerance", s.patientTolerance),
        ].filter { $0.1?.isEmpty == false }

        return VStack(alignment: .leading, spacing: 8) {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 140), alignment: .leading)],
                      alignment: .leading, spacing: 10) {
                ForEach(items, id: \.0) { key, value in
                    VStack(alignment: .leading, spacing: 1) {
                        Text(key.uppercased()).font(.caption2).foregroundStyle(.secondary)
                        Text(value ?? "—").font(.subheadline.weight(.semibold))
                    }
                }
            }
            if let c = s.complications, !c.isEmpty {
                Text("Complications: \(c)").font(.caption).foregroundStyle(.red)
            }
            if let a = s.adverseReactions, !a.isEmpty {
                Text("Adverse reactions: \(a)").font(.caption).foregroundStyle(.red)
            }
            if let n = s.patientNotes, !n.isEmpty {
                Text("Patient notes: \(n)").font(.caption)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 10))
    }

    /// The intradialytic curve. Grouped by unit — BP, pulse and UF never share
    /// an axis, and there is never a second y-axis.
    @ViewBuilder
    private func charts(_ readings: [IntradialyticReading]) -> some View {
        let usable = readings.filter { !($0.readingTime ?? "").isEmpty }
        if usable.count < 2 {
            Text(usable.isEmpty
                 ? "No intradialytic readings were recorded for this session."
                 : "Only one intradialytic reading — not enough to plot a curve.")
                .font(.callout).foregroundStyle(.secondary)
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 10))
        } else {
            chartCard("Blood pressure (mmHg)", usable, [
                ("Systolic", { $0.systolicBp.map(Double.init) }),
                ("Diastolic", { $0.diastolicBp.map(Double.init) }),
                ("MAP", { $0.meanArterialPressure }),
            ])
            chartCard("Pulse (bpm)", usable, [("Pulse", { $0.pulse.map(Double.init) })])
            chartCard("UF removed (mL)", usable, [("UF removed", { $0.ufVolumeRemoved })])
        }
    }

    /// Zero belongs on a volume, not on a blood pressure.
    private static func readingDomain(
        _ measures: [(String, (IntradialyticReading) -> Double?)],
        _ readings: [IntradialyticReading],
        unit title: String
    ) -> ClosedRange<Double> {
        let values = readings.flatMap { r in measures.compactMap { $0.1(r) } }
        guard let lo = values.min(), let hi = values.max() else { return 0...1 }
        // UF removed is a cumulative volume: zero is where the session started.
        let zeroBased = title.contains("mL") || title.lowercased().contains("uf")
        if zeroBased { return 0...(hi > 0 ? hi * 1.05 : 1) }
        let span = hi - lo
        let pad = span > 0 ? span * 0.15 : max(abs(hi) * 0.05, 1)
        return (lo - pad)...(hi + pad)
    }

    @ViewBuilder
    private func chartCard(_ title: String,
                           _ readings: [IntradialyticReading],
                           _ measures: [(String, (IntradialyticReading) -> Double?)]) -> some View {
        let present = measures.filter { m in readings.contains { m.1($0) != nil } }
        if !present.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                Text(title).font(.subheadline.bold())
                Chart {
                    ForEach(Array(present.enumerated()), id: \.offset) { idx, m in
                        ForEach(readings) { r in
                            if let v = m.1(r) {
                                let t = r.readingTime ?? "—"
                                LineMark(x: .value("Time", t), y: .value(m.0, v))
                                    .foregroundStyle(by: .value("Measure", m.0))
                                PointMark(x: .value("Time", t), y: .value(m.0, v))
                                    .foregroundStyle(by: .value("Measure", m.0))
                            }
                        }
                        .foregroundStyle(Self.palette[idx % Self.palette.count])
                    }
                }
                .chartLegend(.visible)
                // Same rule as the category charts: BP and pulse are bounded
                // measures whose variation IS the finding — an intradialytic
                // systolic falling 158 -> 105 is the hypotension a nephrologist
                // is looking for, and a 0-based axis flattens it. UF volume is a
                // real quantity, so zero belongs there.
                .chartYScale(domain: Self.readingDomain(present, readings, unit: title))
                .frame(height: 190)
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 10))
        }
    }

    /// The intradialytic readings as a TABLE — the same columns the patient's own
    /// expanded card shows. Charts without the numbers underneath are a summary,
    /// not a record: a clinician checking one 12:12 reading cannot read it off a
    /// line.
    @ViewBuilder
    private func readingsTable(_ readings: [IntradialyticReading]) -> some View {
        let usable = readings.filter { !($0.readingTime ?? "").isEmpty }
        if !usable.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                Text("Intradialytic Readings (\(usable.count))")
                    .font(.subheadline.bold())
                ScrollView(.horizontal, showsIndicators: true) {
                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 12) {
                            ForEach(["Time", "BP", "Pulse", "MAP", "BFR", "UFR", "UF Vol", "Art P", "Ven P"], id: \.self) {
                                Text($0).font(.caption2.bold()).frame(width: 54, alignment: .leading)
                            }
                        }
                        Divider()
                        ForEach(usable) { r in
                            HStack(spacing: 12) {
                                cell(r.readingTime ?? "—")
                                cell(r.systolicBp != nil && r.diastolicBp != nil
                                     ? "\(r.systolicBp!)/\(r.diastolicBp!)" : "—")
                                cell(r.pulse.map(String.init) ?? "—")
                                cell(r.meanArterialPressure.map { String(format: "%.0f", $0) } ?? "—")
                                cell(r.bloodFlowRate.map { String(format: "%.0f", $0) } ?? "—")
                                cell(r.ufRate.map { String(format: "%.0f", $0) } ?? "—")
                                cell(r.ufVolumeRemoved.map { String(format: "%.0f", $0) } ?? "—")
                                cell(r.arterialPressure.map { String(format: "%.0f", $0) } ?? "—")
                                cell(r.venousPressure.map { String(format: "%.0f", $0) } ?? "—")
                            }
                        }
                    }
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 10))
        }
    }

    private func cell(_ text: String) -> some View {
        Text(text).font(.caption2).frame(width: 54, alignment: .leading)
    }

    /// Comment. Signing a record you cannot annotate attests that you read it and
    /// nothing about what you concluded — so the note sits above the signature.
    private func notesCard(_ notes: [TherapySessionNote]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Clinical notes").font(.subheadline.bold())
            if notes.isEmpty {
                Text("No notes on this session yet.").font(.caption).foregroundStyle(.secondary)
            }
            ForEach(notes) { n in
                VStack(alignment: .leading, spacing: 2) {
                    Text([n.authorRole ?? "clinician", n.noteType ?? "general"].joined(separator: " · "))
                        .font(.caption2).foregroundStyle(.secondary)
                    Text(n.noteText).font(.callout)
                }
            }
            TextField("Add a clinical note…", text: $noteText, axis: .vertical)
                .lineLimit(2...5)
                .textFieldStyle(.roundedBorder)
            Button {
                Task { await addNote() }
            } label: {
                if noteBusy { ProgressView() } else { Text("Add note") }
            }
            .buttonStyle(.bordered)
            .disabled(noteBusy || noteText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 10))
    }

    private func addNote() async {
        let text = noteText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        noteBusy = true
        defer { noteBusy = false }
        do {
            let n: TherapySessionNote = try await APIClient.shared.post(
                "/clinician-dashboard/patient/\(patientId)/therapy-sessions/\(sessionId)/notes",
                body: NoteBody(note_text: text, note_type: "clinical"))
            addedNotes.append(n)
            noteText = ""
        } catch {
            actionError = "Could not save the note."
        }
    }

    private struct NoteBody: Encodable { let note_text: String; let note_type: String }

    /// Tamper-evidence, recomputed rather than displayed. A truncated hash on
    /// screen proves nothing — it is a string the view was handed.
    @ViewBuilder
    private func integrityCard() -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Record integrity", systemImage: "checkmark.shield").font(.subheadline.bold())
            if let integrityError {
                Text(integrityError).font(.caption).foregroundStyle(.red)
            }
            if let i = integrity {
                Text(i.payloadMatches == nil ? "Signed content: never signed — nothing to check"
                     : (i.payloadMatches! ? "Signed content: unchanged since sign-off"
                                          : "Signed content: DOES NOT MATCH the signed hash"))
                    .font(.caption)
                    .foregroundStyle(i.payloadMatches == false ? .red : .secondary)
                Text("Ledger: \(i.chainIntact == true ? "intact" : (i.chainIntact == false ? "BROKEN" : "no entries")) · \(i.anchoredCount) of \(i.trail.count) anchored")
                    .font(.caption).foregroundStyle(i.chainIntact == false ? .red : .secondary)
                ForEach(i.trail, id: \.blockUid) { t in
                    Text("#\(t.index) \(t.event ?? t.action) · \(t.anchored ? "block \(t.blockNumber ?? 0)" : "not anchored")")
                        .font(.caption2).foregroundStyle(.secondary)
                }
            } else {
                Button("Verify this record") { Task { await verify() } }
                    .buttonStyle(.bordered)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 10))
    }

    private func verify() async {
        do {
            integrity = try await APIClient.shared.get(
                "/clinician-dashboard/patient/\(patientId)/therapy-sessions/\(sessionId)/integrity")
        } catch {
            integrityError = "Could not verify this record."
        }
    }

    private func signOffCard(_ so: SessionSignoff) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Sign-off", systemImage: "signature").font(.subheadline.bold())
            Group {
                Text("Patient signature: \(so.signedAt ?? "not signed")")
                Text("Nurse countersignature: \(so.countersignedAt ?? "none")")
                Text("Physician review: \(so.reviewedAt ?? "not reviewed")")
                if let h = so.payloadHash {
                    Text("Integrity hash: \(String(h.prefix(32)))…")
                }
            }
            .font(.caption).foregroundStyle(.secondary)

            if let actionError {
                Text(actionError).font(.caption).foregroundStyle(.red)
            }
            if so.isReviewed {
                Label("Reviewed and anchored", systemImage: "checkmark.seal.fill")
                    .font(.caption.bold()).foregroundStyle(.green)
            } else {
                Button {
                    Task { await signOff() }
                } label: {
                    if busy { ProgressView() } else { Text("Sign off on this session") }
                }
                .buttonStyle(.borderedProminent)
                .disabled(busy)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 10))
    }
}
