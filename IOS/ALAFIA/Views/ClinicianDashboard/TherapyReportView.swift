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

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if sessions.isEmpty {
                Text("No therapy sessions in this period.")
                    .font(.callout).foregroundStyle(.secondary)
            } else {
                statTiles
                Text("^[\(sessions.count) session](inflect: true) in the last \(days) days")
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
                tile("Sessions", "\(sessions.count)", .blue)
                tile("Avg Pre Wt", fmt(avg("pre_weight_kg"), 1, "kg"), .green)
                tile("Avg Post Wt", fmt(avg("post_weight_kg"), 1, "kg"), .green)
                tile("Avg UF", fmt(avg("fluid_removed_ml"), 0, "mL"), .orange)
                tile("Avg Duration", fmt(avg("duration_minutes"), 0, "min"), .purple)
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
                        if !report.notes.isEmpty { notesCard(report.notes) }
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
        let usable = readings.filter { !$0.readingTime.isEmpty }
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
                                let t = r.readingTime
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
                .frame(height: 190)
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 10))
        }
    }

    private func notesCard(_ notes: [TherapySessionNote]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Clinical notes").font(.subheadline.bold())
            ForEach(notes) { n in
                VStack(alignment: .leading, spacing: 2) {
                    Text([n.authorRole ?? "clinician", n.noteType ?? "general"].joined(separator: " · "))
                        .font(.caption2).foregroundStyle(.secondary)
                    Text(n.noteText).font(.callout)
                }
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 10))
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
