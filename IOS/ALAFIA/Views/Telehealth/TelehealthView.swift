import SwiftUI
import WebKit

// MARK: - ViewModel

@Observable
final class TelehealthViewModel {
    var sessions: [TelehealthSession] = []
    var notes: [SessionNote] = []
    var transcripts: [SessionTranscript] = []
    var isLoading = false
    var errorMessage: String?

    func fetchSessions() async {
        isLoading = true; errorMessage = nil
        do {
            sessions = try await APIClient.shared.get("/telehealth/sessions?limit=100")
            isLoading = false
        } catch {
            errorMessage = error.localizedDescription; isLoading = false
        }
    }

    func createSession(_ payload: SessionCreate) async -> Bool {
        do {
            let _: TelehealthSession = try await APIClient.shared.post("/telehealth/sessions", body: payload)
            await fetchSessions()
            return true
        } catch {
            errorMessage = error.localizedDescription; return false
        }
    }

    func cancelSession(id: Int) async {
        do {
            let _: TelehealthSession = try await APIClient.shared.patch(
                "/telehealth/sessions/\(id)", body: SessionStatusUpdate(status: "cancelled"))
            await fetchSessions()
        } catch { errorMessage = error.localizedDescription }
    }

    func joinSession(id: Int) async {
        do {
            let _: SessionParticipant = try await APIClient.shared.patch(
                "/telehealth/sessions/\(id)/join", body: EmptyBody())
        } catch { /* may already be joined */ }
    }

    func startSession(id: Int) async {
        do {
            let _: TelehealthSession = try await APIClient.shared.patch(
                "/telehealth/sessions/\(id)/start", body: EmptyBody())
        } catch { /* ignore */ }
    }

    func endSession(id: Int) async {
        do {
            let _: TelehealthSession = try await APIClient.shared.patch(
                "/telehealth/sessions/\(id)/end", body: EmptyBody())
        } catch { /* ignore */ }
    }

    func leaveSession(id: Int) async {
        do {
            let _: SessionParticipant = try await APIClient.shared.patch(
                "/telehealth/sessions/\(id)/leave", body: EmptyBody())
        } catch { /* ignore */ }
    }

    func fetchNotes(sessionId: Int) async {
        do {
            notes = try await APIClient.shared.get("/telehealth/sessions/\(sessionId)/notes")
        } catch { errorMessage = error.localizedDescription }
    }

    func addNote(sessionId: Int, content: String, type: String) async -> Bool {
        do {
            let _: SessionNote = try await APIClient.shared.post(
                "/telehealth/sessions/\(sessionId)/notes",
                body: NoteCreate(noteType: type, content: content))
            await fetchNotes(sessionId: sessionId)
            return true
        } catch {
            errorMessage = error.localizedDescription; return false
        }
    }

    func deleteNote(sessionId: Int, noteId: Int) async {
        do {
            try await APIClient.shared.delete("/telehealth/sessions/\(sessionId)/notes/\(noteId)")
            notes.removeAll { $0.id == noteId }
        } catch { errorMessage = error.localizedDescription }
    }

    func fetchTranscripts(sessionId: Int) async {
        do {
            transcripts = try await APIClient.shared.get("/telehealth/sessions/\(sessionId)/transcripts")
        } catch { errorMessage = error.localizedDescription }
    }

    func getRTCConfig(sessionId: Int) async -> RTCConfig? {
        do {
            let config: RTCConfig = try await APIClient.shared.get(
                "/telehealth/sessions/\(sessionId)/rtc-config")
            return config
        } catch {
            errorMessage = error.localizedDescription; return nil
        }
    }
}

struct EmptyBody: Encodable {}

// MARK: - Main View

struct TelehealthView: View {
    @State private var vm = TelehealthViewModel()
    @State private var showCreate = false
    @State private var selectedSession: TelehealthSession?
    @State private var showCall = false
    @State private var filter: String = "all"

    private var filtered: [TelehealthSession] {
        switch filter {
        case "upcoming": return vm.sessions.filter { $0.status == "scheduled" }
        case "past": return vm.sessions.filter { $0.status == "completed" }
        case "cancelled": return vm.sessions.filter { $0.status == "cancelled" }
        default: return vm.sessions
        }
    }

    var body: some View {
            Group {
                if vm.isLoading {
                    ProgressView()
                } else if vm.sessions.isEmpty {
                    EmptyStateView(icon: "video.fill",
                                   title: "No Telehealth Sessions",
                                   message: "Schedule a telehealth visit to get started")
                } else {
                    VStack(spacing: 0) {
                        filterBar
                        sessionList
                    }
                }
            }
            .navigationTitle("Telehealth")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showCreate = true } label: {
                        Image(systemName: "plus")
                    }
                }
            }
            .sheet(isPresented: $showCreate) {
                CreateSessionSheet(vm: vm)
            }
            .sheet(item: $selectedSession) { session in
                SessionDetailSheet(session: session, vm: vm, onJoinCall: {
                    selectedSession = nil
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                        showCall = true
                    }
                })
            }
            .fullScreenCover(isPresented: $showCall) {
                if let s = vm.sessions.first(where: { $0.isJoinable }) ?? vm.sessions.first {
                    VideoCallView(session: s, vm: vm, onDismiss: {
                        showCall = false
                        Task { await vm.fetchSessions() }
                    })
                }
            }
            .task { await vm.fetchSessions() }
            .refreshable { await vm.fetchSessions() }
    }

    private var filterBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(["all", "upcoming", "past", "cancelled"], id: \.self) { f in
                    Button {
                        filter = f
                    } label: {
                        Text(f.capitalized)
                            .font(.caption).fontWeight(.semibold)
                            .padding(.horizontal, 14).padding(.vertical, 6)
                            .background(filter == f ? Color.green : Color(.systemGray5))
                            .foregroundStyle(filter == f ? .white : .primary)
                            .clipShape(Capsule())
                    }
                }
            }
            .padding(.horizontal).padding(.vertical, 8)
        }
    }

    private var sessionList: some View {
        List(filtered) { session in
            SessionRow(session: session, onTap: {
                selectedSession = session
            }, onJoin: {
                selectedSession = nil
                Task {
                    await vm.joinSession(id: session.id)
                    if session.status == "scheduled" {
                        await vm.startSession(id: session.id)
                    }
                    showCall = true
                }
            })
        }
        .listStyle(.plain)
    }
}

// MARK: - Session Row

struct SessionRow: View {
    let session: TelehealthSession
    let onTap: () -> Void
    let onJoin: () -> Void

    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 12) {
                // Icon
                Image(systemName: iconName)
                    .font(.title2)
                    .foregroundStyle(statusColor)
                    .frame(width: 40)

                VStack(alignment: .leading, spacing: 4) {
                    Text(session.displayTitle)
                        .font(.headline).lineLimit(1)

                    HStack(spacing: 6) {
                        SessionBadge(text: session.sessionType.capitalized, color: typeColor)
                        SessionBadge(text: statusLabel, color: statusColor)
                        if let p = session.priority, p != "routine" {
                            SessionBadge(text: p.capitalized, color: p == "urgent" ? .orange : .red)
                        }
                    }

                    HStack(spacing: 4) {
                        Image(systemName: "calendar")
                            .font(.caption2)
                        Text(session.scheduledStart, style: .date)
                            .font(.caption)
                        Text(session.scheduledStart, style: .time)
                            .font(.caption)
                    }
                    .foregroundStyle(.secondary)

                    if let spec = session.specialty {
                        HStack(spacing: 4) {
                            Image(systemName: "stethoscope")
                                .font(.caption2)
                            Text(spec).font(.caption)
                        }
                        .foregroundStyle(.secondary)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                if session.isJoinable {
                    Button(action: onJoin) {
                        Image(systemName: "video.fill")
                            .font(.title3)
                            .foregroundStyle(.white)
                            .padding(8)
                            .background(Color.green)
                            .clipShape(Circle())
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.vertical, 4)
        }
        .buttonStyle(.plain)
    }

    private var iconName: String {
        switch session.sessionType {
        case "video": return "video.fill"
        case "voice": return "phone.fill"
        case "chat": return "message.fill"
        default: return "video.fill"
        }
    }

    private var typeColor: Color {
        switch session.sessionType {
        case "video": return .blue
        case "voice": return .green
        case "chat": return .purple
        default: return .gray
        }
    }

    private var statusColor: Color {
        switch session.status {
        case "scheduled": return .blue
        case "waiting": return .orange
        case "in_progress": return .green
        case "completed": return .gray
        case "cancelled": return .red
        case "no_show": return .brown
        default: return .gray
        }
    }

    private var statusLabel: String {
        session.status.replacingOccurrences(of: "_", with: " ").capitalized
    }
}

struct SessionBadge: View {
    let text: String
    let color: Color

    var body: some View {
        Text(text)
            .font(.system(size: 10, weight: .semibold))
            .padding(.horizontal, 6).padding(.vertical, 2)
            .background(color.opacity(0.15))
            .foregroundStyle(color)
            .clipShape(Capsule())
    }
}

// MARK: - Create Session Sheet

struct CreateSessionSheet: View {
    @Environment(\.dismiss) var dismiss
    let vm: TelehealthViewModel

    @State private var sessionType = "video"
    @State private var title = ""
    @State private var scheduledStart = Date().addingTimeInterval(3600)
    @State private var scheduledEnd = Date().addingTimeInterval(5400)
    @State private var reasonForVisit = ""
    @State private var chiefComplaint = ""
    @State private var specialty = ""
    @State private var priority = "routine"
    @State private var transcription = true
    @State private var chat = true
    @State private var recording = false
    @State private var waitingRoom = true
    @State private var submitting = false

    private static let specialties = [
        "", "General Practice", "Cardiology", "Dermatology", "Endocrinology",
        "Gastroenterology", "Neurology", "Oncology", "Orthopedics",
        "Pediatrics", "Psychiatry", "Pulmonology", "Urology",
    ]

    var body: some View {
        NavigationStack {
            Form {
                // Type picker
                Section("Visit Type") {
                    Picker("Type", selection: $sessionType) {
                        Label("Video", systemImage: "video.fill").tag("video")
                        Label("Voice", systemImage: "phone.fill").tag("voice")
                        Label("Chat", systemImage: "message.fill").tag("chat")
                    }
                    .pickerStyle(.segmented)
                }

                // Schedule
                Section("Schedule") {
                    DatePicker("Start", selection: $scheduledStart, in: Date()...)
                    DatePicker("End", selection: $scheduledEnd, in: scheduledStart...)
                }

                // Clinical
                Section("Visit Details") {
                    TextField("Title (optional)", text: $title)
                    TextField("Reason for Visit", text: $reasonForVisit)
                    TextField("Chief Complaint", text: $chiefComplaint, axis: .vertical)
                        .lineLimit(2...4)
                    Picker("Specialty", selection: $specialty) {
                        ForEach(Self.specialties, id: \.self) { s in
                            Text(s.isEmpty ? "— None —" : s).tag(s)
                        }
                    }
                    Picker("Priority", selection: $priority) {
                        Text("Routine").tag("routine")
                        Text("Urgent").tag("urgent")
                        Text("Emergency").tag("emergency")
                    }
                }

                // Features
                Section("Features") {
                    Toggle("Live Transcription", isOn: $transcription)
                    Toggle("In-Session Chat", isOn: $chat)
                    Toggle("Recording", isOn: $recording)
                    Toggle("Waiting Room", isOn: $waitingRoom)
                }
            }
            .navigationTitle("Schedule Visit")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Schedule") {
                        Task { await submit() }
                    }
                    .disabled(submitting)
                }
            }
        }
    }

    private func submit() async {
        submitting = true
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        let payload = SessionCreate(
            sessionType: sessionType,
            title: title.isEmpty ? nil : title,
            scheduledStart: formatter.string(from: scheduledStart),
            scheduledEnd: formatter.string(from: scheduledEnd),
            reasonForVisit: reasonForVisit.isEmpty ? nil : reasonForVisit,
            chiefComplaint: chiefComplaint.isEmpty ? nil : chiefComplaint,
            specialty: specialty.isEmpty ? nil : specialty,
            priority: priority,
            transcriptionEnabled: transcription,
            chatEnabled: chat,
            recordingEnabled: recording,
            waitingRoomEnabled: waitingRoom
        )
        let ok = await vm.createSession(payload)
        submitting = false
        if ok { dismiss() }
    }
}

// MARK: - Session Detail Sheet

struct SessionDetailSheet: View {
    let session: TelehealthSession
    let vm: TelehealthViewModel
    let onJoinCall: () -> Void

    @Environment(\.dismiss) var dismiss
    @State private var tab = 0
    @State private var noteText = ""
    @State private var noteType = "general"

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Status strip
                HStack(spacing: 8) {
                    SessionBadge(text: session.sessionType.capitalized,
                                 color: session.sessionType == "video" ? .blue :
                                        session.sessionType == "voice" ? .green : .purple)
                    SessionBadge(text: session.status.replacingOccurrences(of: "_", with: " ").capitalized,
                                 color: statusColor)
                    if let p = session.priority {
                        SessionBadge(text: p.capitalized,
                                     color: p == "urgent" ? .orange : p == "emergency" ? .red : .gray)
                    }
                    Spacer()
                    Text(session.sessionCode.prefix(8) + "…")
                        .font(.caption).foregroundStyle(.secondary)
                }
                .padding(.horizontal).padding(.vertical, 8)

                Picker("Tab", selection: $tab) {
                    Text("Info").tag(0)
                    Text("Notes").tag(1)
                    Text("Transcripts").tag(2)
                    Text("Participants").tag(3)
                }
                .pickerStyle(.segmented)
                .padding(.horizontal)

                Divider()

                ScrollView {
                    switch tab {
                    case 0: infoTab
                    case 1: notesTab
                    case 2: transcriptsTab
                    case 3: participantsTab
                    default: EmptyView()
                    }
                }
            }
            .navigationTitle(session.displayTitle)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { dismiss() }
                }
                if session.isJoinable {
                    ToolbarItem(placement: .confirmationAction) {
                        Button { onJoinCall() } label: {
                            Label("Join", systemImage: "video.fill")
                        }
                    }
                }
            }
            .task {
                await vm.fetchNotes(sessionId: session.id)
                await vm.fetchTranscripts(sessionId: session.id)
            }
        }
    }

    private var statusColor: Color {
        switch session.status {
        case "scheduled": return .blue
        case "waiting": return .orange
        case "in_progress": return .green
        case "completed": return .gray
        case "cancelled": return .red
        default: return .gray
        }
    }

    // Tab: Info
    private var infoTab: some View {
        VStack(alignment: .leading, spacing: 16) {
            infoRow("Scheduled Start", value: session.scheduledStart.formatted(date: .abbreviated, time: .shortened))
            if let end = session.scheduledEnd {
                infoRow("Scheduled End", value: end.formatted(date: .abbreviated, time: .shortened))
            }
            if let start = session.actualStart {
                infoRow("Actual Start", value: start.formatted(date: .abbreviated, time: .shortened))
            }
            if let end = session.actualEnd {
                infoRow("Actual End", value: end.formatted(date: .abbreviated, time: .shortened))
            }
            if let d = session.durationMinutes {
                infoRow("Duration", value: "\(d) min")
            }
            if let s = session.specialty {
                infoRow("Specialty", value: s)
            }
            if let r = session.reasonForVisit {
                infoRow("Reason", value: r)
            }
            if let c = session.chiefComplaint {
                infoRow("Chief Complaint", value: c)
            }
            if session.followUpNeeded {
                GroupBox {
                    VStack(alignment: .leading, spacing: 4) {
                        Label("Follow-up Needed", systemImage: "arrow.turn.down.right")
                            .font(.subheadline).fontWeight(.semibold)
                        if let d = session.followUpDate {
                            Text("Date: \(d)").font(.caption)
                        }
                        if let n = session.followUpNotes {
                            Text(n).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
            }

            if !session.isJoinable && session.status != "cancelled" {
                // Cancel button
            } else if session.status != "cancelled" && session.status != "completed" {
                Button(role: .destructive) {
                    Task {
                        await vm.cancelSession(id: session.id)
                        dismiss()
                    }
                } label: {
                    Label("Cancel Session", systemImage: "xmark.circle")
                }
            }
        }
        .padding()
    }

    private func infoRow(_ label: String, value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(.caption).foregroundStyle(.secondary)
            Text(value).font(.subheadline).fontWeight(.medium)
        }
    }

    // Tab: Notes
    private var notesTab: some View {
        VStack(spacing: 12) {
            // Add note
            GroupBox {
                VStack(spacing: 8) {
                    Picker("Type", selection: $noteType) {
                        ForEach(["general", "subjective", "objective", "assessment", "plan", "follow_up"], id: \.self) { t in
                            Text(t.replacingOccurrences(of: "_", with: " ").capitalized).tag(t)
                        }
                    }
                    .pickerStyle(.menu)

                    HStack {
                        TextField("Add a note…", text: $noteText, axis: .vertical)
                            .lineLimit(2...4)
                        Button {
                            guard !noteText.isEmpty else { return }
                            Task {
                                let ok = await vm.addNote(sessionId: session.id, content: noteText, type: noteType)
                                if ok { noteText = "" }
                            }
                        } label: {
                            Image(systemName: "paperplane.fill")
                                .foregroundStyle(.green)
                        }
                    }
                }
            }

            if vm.notes.isEmpty {
                ContentUnavailableView("No Notes", systemImage: "doc.text",
                                       description: Text("Add clinical notes above"))
            } else {
                ForEach(vm.notes) { note in
                    GroupBox {
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                SessionBadge(text: note.noteType.replacingOccurrences(of: "_", with: " ").capitalized, color: .blue)
                                Spacer()
                                Text(note.createdAt, style: .date)
                                    .font(.caption2).foregroundStyle(.secondary)
                                Button {
                                    Task { await vm.deleteNote(sessionId: session.id, noteId: note.id) }
                                } label: {
                                    Image(systemName: "trash")
                                        .font(.caption).foregroundStyle(.red)
                                }
                            }
                            Text(note.content).font(.subheadline)
                            if let d = note.diagnosisCodes {
                                Text("ICD: \(d)").font(.caption).foregroundStyle(.secondary)
                            }
                            if let p = note.procedureCodes {
                                Text("CPT: \(p)").font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
        }
        .padding()
    }

    // Tab: Transcripts
    private var transcriptsTab: some View {
        VStack(spacing: 8) {
            if vm.transcripts.isEmpty {
                ContentUnavailableView("No Transcripts", systemImage: "waveform",
                                       description: Text("Transcripts appear after a call"))
            } else {
                ForEach(vm.transcripts) { t in
                    HStack(alignment: .top, spacing: 8) {
                        Image(systemName: "person.circle.fill")
                            .font(.title3).foregroundStyle(.secondary)
                        VStack(alignment: .leading, spacing: 2) {
                            HStack {
                                Text("Speaker #\(t.speakerId ?? 0)")
                                    .font(.caption).foregroundStyle(.secondary)
                                Spacer()
                                if let c = t.confidence {
                                    Text("\(Int(c * 100))%")
                                        .font(.caption2).foregroundStyle(.secondary)
                                }
                            }
                            Text(t.content).font(.subheadline)
                        }
                    }
                    .padding(.vertical, 4)
                    Divider()
                }
            }
        }
        .padding()
    }

    // Tab: Participants
    private var participantsTab: some View {
        VStack(spacing: 8) {
            if let parts = session.participants, !parts.isEmpty {
                ForEach(parts) { p in
                    HStack {
                        Image(systemName: p.role == "provider" ? "stethoscope" : "person.fill")
                            .font(.title3)
                            .foregroundStyle(p.role == "provider" ? .blue : .green)
                            .frame(width: 36)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("User #\(p.userId)").font(.subheadline).fontWeight(.medium)
                            Text("\(p.role.capitalized) — \(p.status.replacingOccurrences(of: "_", with: " ").capitalized)")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer()
                        HStack(spacing: 6) {
                            Image(systemName: p.cameraEnabled ? "video.fill" : "video.slash.fill")
                                .foregroundStyle(p.cameraEnabled ? .green : .gray)
                            Image(systemName: p.microphoneEnabled ? "mic.fill" : "mic.slash.fill")
                                .foregroundStyle(p.microphoneEnabled ? .green : .gray)
                        }
                        .font(.caption)
                    }
                    .padding(.vertical, 4)
                    Divider()
                }
            } else {
                ContentUnavailableView("No Participants", systemImage: "person.2",
                                       description: Text("Participants will appear when they join"))
            }
        }
        .padding()
    }
}

// MARK: - Video Call View

struct VideoCallView: View {
    let session: TelehealthSession
    let vm: TelehealthViewModel
    let onDismiss: () -> Void

    @State private var callState: CallState = .connecting
    @State private var elapsed: Int = 0
    @State private var cameraOn = true
    @State private var micOn = true
    @State private var chatOpen = false
    @State private var chatMessages: [ChatMsg] = []
    @State private var chatInput = ""
    @State private var transcripts: [LiveTranscript] = []
    private let timer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

    enum CallState { case connecting, waiting, active, ended }

    struct ChatMsg: Identifiable {
        let id = UUID()
        let userId: Int
        let content: String
        let timestamp: Date
        let isMine: Bool
    }

    struct LiveTranscript: Identifiable {
        let id = UUID()
        let speakerId: Int?
        let content: String
    }

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            VStack(spacing: 0) {
                // Top bar
                topBar

                // Main area
                ZStack {
                    // Remote video placeholder
                    if session.sessionType == "video" {
                        RoundedRectangle(cornerRadius: 12)
                            .fill(Color(.systemGray6).opacity(0.2))
                            .overlay {
                                if callState == .waiting {
                                    waitingOverlay
                                } else if callState == .connecting {
                                    connectingOverlay
                                } else {
                                    Image(systemName: "person.circle.fill")
                                        .font(.system(size: 80))
                                        .foregroundStyle(.white.opacity(0.3))
                                }
                            }
                            .padding(8)
                    } else {
                        // Voice call
                        VStack(spacing: 16) {
                            if callState == .waiting {
                                waitingOverlay
                            } else if callState == .connecting {
                                connectingOverlay
                            } else {
                                Image(systemName: "phone.fill")
                                    .font(.system(size: 60))
                                    .foregroundStyle(.white.opacity(0.3))
                                Text("Voice Call")
                                    .font(.title2).foregroundStyle(.white.opacity(0.7))
                                Text(elapsedString)
                                    .font(.system(.title, design: .monospaced))
                                    .foregroundStyle(.white)
                            }
                        }
                    }

                    // Local video PIP
                    if session.sessionType == "video" {
                        VStack {
                            Spacer()
                            HStack {
                                Spacer()
                                RoundedRectangle(cornerRadius: 12)
                                    .fill(Color(.systemGray4).opacity(0.5))
                                    .frame(width: 120, height: 90)
                                    .overlay {
                                        if cameraOn {
                                            Image(systemName: "person.fill")
                                                .font(.title)
                                                .foregroundStyle(.white.opacity(0.5))
                                        } else {
                                            Image(systemName: "video.slash.fill")
                                                .foregroundStyle(.white.opacity(0.5))
                                        }
                                    }
                                    .padding(12)
                            }
                        }
                        .padding(.bottom, 60)
                    }

                    // Live transcription overlay
                    if session.transcriptionEnabled && !transcripts.isEmpty {
                        VStack {
                            Spacer()
                            VStack(alignment: .leading, spacing: 4) {
                                ForEach(transcripts.suffix(3)) { t in
                                    HStack(spacing: 4) {
                                        Text("Speaker #\(t.speakerId ?? 0):")
                                            .font(.caption2).foregroundStyle(.white.opacity(0.5))
                                        Text(t.content)
                                            .font(.caption).foregroundStyle(.white)
                                    }
                                }
                            }
                            .padding(8)
                            .background(.black.opacity(0.6))
                            .clipShape(RoundedRectangle(cornerRadius: 8))
                            .padding(.horizontal)
                            .padding(.bottom, 70)
                        }
                    }

                    // Chat panel
                    if chatOpen {
                        chatPanel
                    }
                }

                // Bottom controls
                bottomControls
            }
        }
        .onReceive(timer) { _ in
            if callState == .active { elapsed += 1 }
        }
        .task {
            await initCall()
        }
        .statusBarHidden()
    }

    private var elapsedString: String {
        let m = elapsed / 60
        let s = elapsed % 60
        return String(format: "%02d:%02d", m, s)
    }

    // MARK: - Top Bar
    private var topBar: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(session.displayTitle)
                    .font(.headline).foregroundStyle(.white).lineLimit(1)
                HStack(spacing: 6) {
                    Circle()
                        .fill(callState == .active ? .green : callState == .waiting ? .orange : .gray)
                        .frame(width: 8, height: 8)
                    Text(callState == .active ? "Live" : callState == .waiting ? "Waiting" : "Connecting")
                        .font(.caption).foregroundStyle(.white.opacity(0.7))
                }
            }
            Spacer()
            HStack(spacing: 10) {
                Image(systemName: "clock")
                    .font(.caption).foregroundStyle(.white.opacity(0.7))
                Text(elapsedString)
                    .font(.system(.subheadline, design: .monospaced))
                    .foregroundStyle(.white)
            }
        }
        .padding(.horizontal).padding(.vertical, 8)
        .background(.black.opacity(0.4))
    }

    // MARK: - Overlays
    private var waitingOverlay: some View {
        VStack(spacing: 16) {
            ProgressView().tint(.white).scaleEffect(1.5)
            Text("Waiting Room")
                .font(.title2).fontWeight(.semibold).foregroundStyle(.white)
            Text("Please wait while the provider admits you")
                .font(.subheadline).foregroundStyle(.white.opacity(0.7))
                .multilineTextAlignment(.center)
        }
    }

    private var connectingOverlay: some View {
        VStack(spacing: 16) {
            ProgressView().tint(.white).scaleEffect(1.5)
            Text("Connecting…")
                .font(.title3).foregroundStyle(.white)
        }
    }

    // MARK: - Chat
    private var chatPanel: some View {
        HStack(spacing: 0) {
            Spacer()
            VStack(spacing: 0) {
                HStack {
                    Text("Chat").font(.headline).foregroundStyle(.white)
                    Spacer()
                    Button { chatOpen = false } label: {
                        Image(systemName: "xmark").foregroundStyle(.white)
                    }
                }
                .padding(10)
                .background(.black.opacity(0.5))

                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 8) {
                            ForEach(chatMessages) { msg in
                                HStack {
                                    if msg.isMine { Spacer() }
                                    VStack(alignment: msg.isMine ? .trailing : .leading, spacing: 2) {
                                        if !msg.isMine {
                                            Text("User #\(msg.userId)")
                                                .font(.caption2).foregroundStyle(.white.opacity(0.5))
                                        }
                                        Text(msg.content)
                                            .font(.subheadline).foregroundStyle(.white)
                                            .padding(8)
                                            .background(msg.isMine ? Color.green : Color.white.opacity(0.15))
                                            .clipShape(RoundedRectangle(cornerRadius: 12))
                                    }
                                    if !msg.isMine { Spacer() }
                                }
                                .id(msg.id)
                            }
                        }
                        .padding(8)
                    }
                    .onChange(of: chatMessages.count) { _, _ in
                        if let last = chatMessages.last {
                            proxy.scrollTo(last.id, anchor: .bottom)
                        }
                    }
                }

                HStack(spacing: 8) {
                    TextField("Message…", text: $chatInput)
                        .textFieldStyle(.roundedBorder)
                        .foregroundStyle(.white)
                    Button {
                        guard !chatInput.isEmpty else { return }
                        chatMessages.append(ChatMsg(userId: 0, content: chatInput,
                                                    timestamp: Date(), isMine: true))
                        chatInput = ""
                    } label: {
                        Image(systemName: "paperplane.fill").foregroundStyle(.green)
                    }
                }
                .padding(8)
                .background(.black.opacity(0.5))
            }
            .frame(width: 280)
            .background(.black.opacity(0.7))
        }
    }

    // MARK: - Controls
    private var bottomControls: some View {
        HStack(spacing: 20) {
            if session.sessionType == "video" {
                callButton(icon: cameraOn ? "video.fill" : "video.slash.fill",
                          active: cameraOn) { cameraOn.toggle() }
            }
            callButton(icon: micOn ? "mic.fill" : "mic.slash.fill",
                       active: micOn) { micOn.toggle() }
            if session.chatEnabled {
                callButton(icon: "message.fill",
                           active: chatOpen, tint: chatOpen ? .blue : nil) { chatOpen.toggle() }
            }

            // End call
            Button(action: endCall) {
                Image(systemName: "phone.down.fill")
                    .font(.title2).foregroundStyle(.white)
                    .frame(width: 56, height: 56)
                    .background(Color.red)
                    .clipShape(Circle())
                    .shadow(color: .red.opacity(0.4), radius: 6)
            }
        }
        .padding(.vertical, 12)
        .padding(.horizontal)
        .background(.black.opacity(0.5))
    }

    private func callButton(icon: String, active: Bool, tint: Color? = nil, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.title3).foregroundStyle(.white)
                .frame(width: 48, height: 48)
                .background(tint ?? (active ? Color.white.opacity(0.15) : Color.white.opacity(0.08)))
                .clipShape(Circle())
                .overlay(Circle().stroke(.white.opacity(0.15)))
        }
    }

    // MARK: - Call lifecycle
    private func initCall() async {
        await vm.joinSession(id: session.id)
        if session.status == "scheduled" {
            await vm.startSession(id: session.id)
        }
        // Get RTC config
        if let _ = await vm.getRTCConfig(sessionId: session.id) {
            callState = session.waitingRoomEnabled ? .waiting : .active
            // In a full implementation, WebRTC peer connection would be
            // established here using the native WebRTC framework.
            // For now we simulate the call state transition.
            try? await Task.sleep(for: .seconds(2))
            if callState == .waiting {
                callState = .active
            }
        } else {
            callState = .ended
        }
    }

    private func endCall() {
        Task {
            await vm.endSession(id: session.id)
            await vm.leaveSession(id: session.id)
            callState = .ended
            onDismiss()
        }
    }
}
