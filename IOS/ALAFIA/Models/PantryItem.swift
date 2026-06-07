import Foundation

struct PantryItem: Codable, Identifiable {
    let id: Int
    let userId: Int
    let name: String
    let category: String
    let quantity: Double
    let unit: String
    let location: String
    let expirationDate: String?
    let notes: String?
    let autoReplenish: Bool
    let lowThreshold: Double?
    let createdAt: Date
    let updatedAt: Date

    enum CodingKeys: String, CodingKey {
        case id, name, category, quantity, unit, location, notes
        case userId = "user_id"
        case expirationDate = "expiration_date"
        case autoReplenish = "auto_replenish"
        case lowThreshold = "low_threshold"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct PantryItemCreate: Encodable {
    let name: String
    let category: String
    let quantity: Double
    let unit: String
    let location: String
    let expirationDate: String?
    let notes: String?

    enum CodingKeys: String, CodingKey {
        case name, category, quantity, unit, location, notes
        case expirationDate = "expiration_date"
    }
}
