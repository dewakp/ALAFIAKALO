import Foundation

// MARK: - Telehealth Session

struct TelehealthSession: Codable, Identifiable {
    let id: Int
    let sessionCode: String
    let title: String?
    let sessionType: String
    let status: String

    let scheduledStart: Date
    let scheduledEnd: Date?
    let actualStart: Date?
    let actualEnd: Date?
    let durationMinutes: Int?

    let createdById: Int
    let providerId: Int?

    let reasonForVisit: String?
    let chiefComplaint: String?
    let specialty: String?
    let priority: String?

    let recordingEnabled: Bool
    let transcriptionEnabled: Bool
    let screenSharingEnabled: Bool
    let chatEnabled: Bool
    let waitingRoomEnabled: Bool

    let connectionQuality: String?
    let patientSatisfaction: Int?
    let cancellationReason: String?
    let cancelledById: Int?

    let followUpNeeded: Bool
    let followUpNotes: String?
    let followUpDate: String?

    let participants: [SessionParticipant]?
    let createdAt: Date
    let updatedAt: Date

    enum CodingKeys: String, CodingKey {
        case id, title, status, priority, specialty, participants
        case sessionCode = "session_code"
        case sessionType = "session_type"
        case scheduledStart = "scheduled_start"
        case scheduledEnd = "scheduled_end"
        case actualStart = "actual_start"
        case actualEnd = "actual_end"
        case durationMinutes = "duration_minutes"
        case createdById = "created_by_id"
        case providerId = "provider_id"
        case reasonForVisit = "reason_for_visit"
        case chiefComplaint = "chief_complaint"
        case recordingEnabled = "recording_enabled"
        case transcriptionEnabled = "transcription_enabled"
        case screenSharingEnabled = "screen_sharing_enabled"
        case chatEnabled = "chat_enabled"
        case waitingRoomEnabled = "waiting_room_enabled"
        case connectionQuality = "connection_quality"
        case patientSatisfaction = "patient_satisfaction"
        case cancellationReason = "cancellation_reason"
        case cancelledById = "cancelled_by_id"
        case followUpNeeded = "follow_up_needed"
        case followUpNotes = "follow_up_notes"
        case followUpDate = "follow_up_date"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    var displayTitle: String { title ?? reasonForVisit ?? "Telehealth Visit" }

    var isJoinable: Bool {
        ["scheduled", "waiting", "in_progress"].contains(status)
    }
}

// MARK: - Participant

struct SessionParticipant: Codable, Identifiable {
    let id: Int
    let sessionId: Int
    let userId: Int
    let role: String
    let status: String
    let cameraEnabled: Bool
    let microphoneEnabled: Bool
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, role, status
        case sessionId = "session_id"
        case userId = "user_id"
        case cameraEnabled = "camera_enabled"
        case microphoneEnabled = "microphone_enabled"
        case createdAt = "created_at"
    }
}

// MARK: - Session Note

struct SessionNote: Codable, Identifiable {
    let id: Int
    let sessionId: Int
    let authorId: Int
    let noteType: String
    let content: String
    let diagnosisCodes: String?
    let procedureCodes: String?
    let isPrivate: Bool
    let createdAt: Date
    let updatedAt: Date

    enum CodingKeys: String, CodingKey {
        case id, content
        case sessionId = "session_id"
        case authorId = "author_id"
        case noteType = "note_type"
        case diagnosisCodes = "diagnosis_codes"
        case procedureCodes = "procedure_codes"
        case isPrivate = "is_private"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

// MARK: - Transcript

struct SessionTranscript: Codable, Identifiable {
    let id: Int
    let sessionId: Int
    let speakerId: Int?
    let content: String
    let language: String
    let confidence: Double?
    let sequenceNumber: Int
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, content, language, confidence
        case sessionId = "session_id"
        case speakerId = "speaker_id"
        case sequenceNumber = "sequence_number"
        case createdAt = "created_at"
    }
}

// MARK: - RTC Config

struct RTCConfig: Codable {
    let iceServers: [ICEServer]
    let sessionCode: String
    let userId: Int
    let role: String

    enum CodingKeys: String, CodingKey {
        case role
        case iceServers = "ice_servers"
        case sessionCode = "session_code"
        case userId = "user_id"
    }
}

struct ICEServer: Codable {
    let urls: [String]
    let username: String?
    let credential: String?
}

// MARK: - Create / Update DTOs

struct SessionCreate: Encodable {
    var sessionType: String = "video"
    var title: String?
    var scheduledStart: String
    var scheduledEnd: String?
    var reasonForVisit: String?
    var chiefComplaint: String?
    var specialty: String?
    var priority: String = "routine"
    var providerId: Int?
    var transcriptionEnabled: Bool = true
    var chatEnabled: Bool = true
    var recordingEnabled: Bool = false
    var waitingRoomEnabled: Bool = true

    enum CodingKeys: String, CodingKey {
        case title, specialty, priority
        case sessionType = "session_type"
        case scheduledStart = "scheduled_start"
        case scheduledEnd = "scheduled_end"
        case reasonForVisit = "reason_for_visit"
        case chiefComplaint = "chief_complaint"
        case providerId = "provider_id"
        case transcriptionEnabled = "transcription_enabled"
        case chatEnabled = "chat_enabled"
        case recordingEnabled = "recording_enabled"
        case waitingRoomEnabled = "waiting_room_enabled"
    }
}

struct NoteCreate: Encodable {
    var noteType: String = "general"
    var content: String

    enum CodingKeys: String, CodingKey {
        case content
        case noteType = "note_type"
    }
}

struct SessionStatusUpdate: Encodable {
    let status: String
}
