import Foundation

/// Sent to the backend to represent a single message in conversation history.
struct HistoryMessage: Encodable {
    let role: String    // "user" or "assistant"
    let content: String
}

struct AIQueryRequest: Encodable {
    let query: String
    var contextModule: String?
    var includeHistory: Bool = false
    var persona: String?
    /// Conversation history so Ollama gets full context
    var messages: [HistoryMessage]?

    enum CodingKeys: String, CodingKey {
        case query
        case contextModule = "context_module"
        case includeHistory = "include_history"
        case persona
        case messages
    }
}

struct AIQueryResponse: Decodable {
    let response: String
    let module: String?
    let confidence: Double?
    let persona: String?
}

struct NutritionDailySummaryResponse: Decodable {
    let date: String
    let totalCalories: Double
    let totalProteinG: Double
    let totalCarbsG: Double
    let totalFatG: Double
    let mealCount: Int

    enum CodingKeys: String, CodingKey {
        case date
        case totalCalories = "total_calories"
        case totalProteinG = "total_protein_g"
        case totalCarbsG = "total_carbs_g"
        case totalFatG = "total_fat_g"
        case mealCount = "meal_count"
    }
}

struct ChatMessage: Identifiable {
    let id: UUID
    let role: Role
    /// Mutable so tokens can be appended during streaming
    var content: String
    let timestamp: Date

    enum Role {
        case user, assistant
    }

    init(role: Role, content: String) {
        self.id = UUID()
        self.role = role
        self.content = content
        self.timestamp = Date()
    }
}

struct AIPersona: Decodable, Identifiable {
    var id: String { key }
    let key: String
    let title: String
    let origin: String
    let region: String
    let greeting: String
    let description: String
}
