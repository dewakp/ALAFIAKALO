import Foundation

struct LabResult: Codable, Identifiable {
    let id: Int
    let userId: Int
    let testDate: String
    let testName: String
    let loincCode: String?
    let category: String?
    let value: Double?
    let valueString: String?
    let unit: String?
    let referenceRangeLow: Double?
    let referenceRangeHigh: Double?
    let isAbnormal: Bool?
    let status: String
    let orderingProvider: String?
    let performingLab: String?
    let notes: String?
    let createdAt: Date
    
    enum CodingKeys: String, CodingKey {
        case id, value, unit, status, category, notes
        case userId = "user_id"
        case testDate = "test_date"
        case testName = "test_name"
        case loincCode = "loinc_code"
        case valueString = "value_string"
        case referenceRangeLow = "reference_range_low"
        case referenceRangeHigh = "reference_range_high"
        case isAbnormal = "is_abnormal"
        case orderingProvider = "ordering_provider"
        case performingLab = "performing_lab"
        case createdAt = "created_at"
    }
    
    var displayValue: String {
        if let v = value {
            return "\(v) \(unit ?? "")"
        }
        return valueString ?? "-"
    }
    
    var referenceRange: String? {
        guard let low = referenceRangeLow, let high = referenceRangeHigh else { return nil }
        return "\(low) - \(high) \(unit ?? "")"
    }
}

struct LabResultCreate: Encodable {
    let testDate: String
    let testName: String
    var loincCode: String?
    var category: String?
    var value: Double?
    var unit: String?
    var referenceRangeLow: Double?
    var referenceRangeHigh: Double?
    var isAbnormal: Bool?
    var performingLab: String?
    var notes: String?
    
    enum CodingKeys: String, CodingKey {
        case testDate = "test_date"
        case testName = "test_name"
        case loincCode = "loinc_code"
        case category, value, unit, notes
        case referenceRangeLow = "reference_range_low"
        case referenceRangeHigh = "reference_range_high"
        case isAbnormal = "is_abnormal"
        case performingLab = "performing_lab"
    }
}
