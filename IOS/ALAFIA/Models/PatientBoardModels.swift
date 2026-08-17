import Foundation

/// A board/table value that the API may send as a string, number, bool or null.
///
/// Summary items and table cells are deliberately heterogeneous — a lab value is
/// "4.2" or "NEG", a count is an Int, `danger` is a Bool — so a single concrete
/// Swift type would fail to decode half the payload. This keeps both a display
/// string and the underlying bool so a flag can still be read as a flag.
struct FlexValue: Codable, Hashable {
    let text: String?
    let number: Double?
    let flag: Bool?

    var display: String? {
        if let text { return text }
        if let number {
            return number == number.rounded()
                ? String(Int(number))
                : String(format: "%.2f", number).replacingOccurrences(of: #"0+$"#,
                                                                      with: "",
                                                                      options: .regularExpression)
        }
        if let flag { return flag ? "yes" : "no" }
        return nil
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() {
            text = nil; number = nil; flag = nil
        } else if let b = try? c.decode(Bool.self) {
            text = nil; number = nil; flag = b
        } else if let d = try? c.decode(Double.self) {
            text = nil; number = d; flag = nil
        } else if let s = try? c.decode(String.self) {
            text = s; number = nil; flag = nil
        } else {
            text = nil; number = nil; flag = nil
        }
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        if let text { try c.encode(text) } else if let number { try c.encode(number) }
        else if let flag { try c.encode(flag) } else { try c.encodeNil() }
    }
}

struct BoardItem: Codable, Hashable {
    let label: String
    let value: FlexValue?
    let unit: String?
    let danger: Bool?
    let note: String?

    var valueWithUnit: String? {
        guard let v = value?.display else { return nil }
        guard let unit, !unit.isEmpty else { return v }
        return "\(v) \(unit)"
    }
}

struct BoardCard: Codable, Identifiable, Hashable {
    var id: String { key }
    let key: String
    let label: String
    let icon: String
    let shared: Bool
    let items: [BoardItem]
    let count: Int?
    let lastUpdated: String?
    let emptyReason: String?

    enum CodingKeys: String, CodingKey {
        case key, label, icon, shared, items, count
        case lastUpdated = "last_updated"
        case emptyReason = "empty_reason"
    }
}

struct BoardPatient: Codable, Hashable {
    let userId: Int
    let fullName: String?
    let email: String?

    enum CodingKeys: String, CodingKey {
        case userId = "user_id"
        case fullName = "full_name"
        case email
    }
}

struct PatientBoardResponse: Codable {
    let patient: BoardPatient
    let permissions: [String]
    let cards: [BoardCard]
}

struct TrendPoint: Codable, Hashable {
    let date: String
    let value: Double?
}

struct TrendSeries: Codable, Hashable, Identifiable {
    var id: String { label }
    let label: String
    let unit: String?
    let points: [TrendPoint]
    /// Whether this measure's axis should start at zero. Decided server-side,
    /// because only the server knows what the measure IS. Absent = true, which
    /// is the conservative default: a zero-based axis is cramped but honest,
    /// while a fitted one can exaggerate a trend.
    let zeroBaseline: Bool?

    enum CodingKeys: String, CodingKey {
        case label, unit, points
        case zeroBaseline = "zero_baseline"
    }
}

struct BoardColumn: Codable, Hashable, Identifiable {
    var id: String { key }
    let key: String
    let label: String
}

/// One item on a category card. `danger` is advisory — the note says why, so
/// the flag is never carried by colour alone.
struct CardItem: Codable, Hashable {
    let label: String
    let value: FlexValue?
    let unit: String?
    let danger: Bool?
    let note: String?

    var valueWithUnit: String {
        let v = value?.display ?? "—"
        guard let unit, !unit.isEmpty else { return v }
        return "\(v) \(unit)"
    }
}

/// A category's own summary card, computed server-side. The client never
/// re-derives a clinical number — two implementations of "average potassium" is
/// one too many.
struct BoardDetailCard: Codable, Hashable, Identifiable {
    var id: String { label }
    let label: String
    let items: [CardItem]
    let note: String?
}

struct PatientCategoryResponse: Codable {
    let patient: BoardPatient
    let key: String
    let label: String
    let icon: String
    let days: Int
    let series: [TrendSeries]
    let columns: [BoardColumn]
    let rows: [[String: FlexValue]]
    let cards: [BoardDetailCard]?
}
