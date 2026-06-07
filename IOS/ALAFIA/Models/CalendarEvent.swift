import Foundation

struct CalendarEvent: Codable, Identifiable {
    let id: Int
    let userId: Int
    var title: String
    var description: String?
    var category: String
    var eventDate: String
    var startTime: String?
    var endTime: String?
    var allDay: Bool
    var recurrence: String?
    var recurrenceEndDate: String?
    var recurrenceDays: String?
    var status: String
    var location: String?
    var reminderMinutes: Int?
    var metadataJson: String?
    var linkedMedicationId: Int?
    var linkedConditionId: Int?
    var linkedFitnessId: Int?
    var color: String?
    var priority: String?
    var notes: String?
    var completedAt: Date?
    let createdAt: Date
    let updatedAt: Date

    enum CodingKeys: String, CodingKey {
        case id, title, description, category, status, location, color, priority, notes, recurrence
        case userId = "user_id"
        case eventDate = "event_date"
        case startTime = "start_time"
        case endTime = "end_time"
        case allDay = "all_day"
        case recurrenceEndDate = "recurrence_end_date"
        case recurrenceDays = "recurrence_days"
        case reminderMinutes = "reminder_minutes"
        case metadataJson = "metadata_json"
        case linkedMedicationId = "linked_medication_id"
        case linkedConditionId = "linked_condition_id"
        case linkedFitnessId = "linked_fitness_id"
        case completedAt = "completed_at"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct CalendarEventCreate: Encodable {
    var title: String
    var description: String?
    var category: String = "appointment"
    var eventDate: String
    var startTime: String?
    var endTime: String?
    var allDay: Bool = false
    var recurrence: String?
    var recurrenceEndDate: String?
    var location: String?
    var reminderMinutes: Int?
    var priority: String?
    var notes: String?
    var color: String?

    enum CodingKeys: String, CodingKey {
        case title, description, category, location, recurrence, priority, notes, color
        case eventDate = "event_date"
        case startTime = "start_time"
        case endTime = "end_time"
        case allDay = "all_day"
        case recurrenceEndDate = "recurrence_end_date"
        case reminderMinutes = "reminder_minutes"
    }
}

struct CalendarEventUpdate: Encodable {
    var title: String?
    var description: String?
    var category: String?
    var eventDate: String?
    var startTime: String?
    var endTime: String?
    var allDay: Bool?
    var recurrence: String?
    var status: String?
    var location: String?
    var reminderMinutes: Int?
    var priority: String?
    var notes: String?
    var color: String?

    enum CodingKeys: String, CodingKey {
        case title, description, category, location, recurrence, status, priority, notes, color
        case eventDate = "event_date"
        case startTime = "start_time"
        case endTime = "end_time"
        case allDay = "all_day"
        case reminderMinutes = "reminder_minutes"
    }
}

struct EventCategory {
    let key: String
    let label: String
    let icon: String
    let color: String

    static let all: [EventCategory] = [
        .init(key: "appointment", label: "Appointment", icon: "stethoscope", color: "#2196F3"),
        .init(key: "meal", label: "Meal", icon: "fork.knife", color: "#4CAF50"),
        .init(key: "medication", label: "Medication", icon: "pills.fill", color: "#FF9800"),
        .init(key: "exercise", label: "Exercise", icon: "figure.run", color: "#E91E63"),
        .init(key: "meditation", label: "Meditation", icon: "brain.head.profile", color: "#9C27B0"),
        .init(key: "therapy", label: "Therapy", icon: "heart.fill", color: "#00BCD4"),
        .init(key: "lab", label: "Lab / Test", icon: "flask.fill", color: "#795548"),
        .init(key: "wellness", label: "Wellness", icon: "sparkles", color: "#607D8B"),
        .init(key: "custom", label: "Custom", icon: "calendar", color: "#9E9E9E"),
    ]

    static func find(_ key: String) -> EventCategory {
        all.first(where: { $0.key == key }) ?? all.last!
    }

    var swiftColor: Color {
        Color(hex: color)
    }
}

import SwiftUI

extension Color {
    init(hex: String) {
        let h = hex.trimmingCharacters(in: CharacterSet(charactersIn: "#"))
        var rgb: UInt64 = 0
        Scanner(string: h).scanHexInt64(&rgb)
        self.init(
            red: Double((rgb >> 16) & 0xFF) / 255,
            green: Double((rgb >> 8) & 0xFF) / 255,
            blue: Double(rgb & 0xFF) / 255
        )
    }
}
