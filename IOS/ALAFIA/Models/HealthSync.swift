import Foundation

// MARK: - Sync Connection

struct SyncConnection: Codable, Identifiable {
    let id: Int
    let platform: String
    let isActive: Bool
    var enabledDataTypes: [String]?
    let lastSyncAt: Date?
    let lastSyncStatus: String?
    let lastSyncRecords: Int?
    let lastSyncDuplicates: Int?
    let createdAt: Date
    let updatedAt: Date

    enum CodingKeys: String, CodingKey {
        case id, platform
        case isActive = "is_active"
        case enabledDataTypes = "enabled_data_types"
        case lastSyncAt = "last_sync_at"
        case lastSyncStatus = "last_sync_status"
        case lastSyncRecords = "last_sync_records"
        case lastSyncDuplicates = "last_sync_duplicates"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct SyncConnectionCreate: Codable {
    let platform: String
    var enabledDataTypes: [String]?

    enum CodingKeys: String, CodingKey {
        case platform
        case enabledDataTypes = "enabled_data_types"
    }
}

// MARK: - Batch Sync

struct SyncRecord: Codable {
    let externalId: String
    let dataType: String
    let sourceTimestamp: Date
    let data: [String: AnyCodable]

    enum CodingKeys: String, CodingKey {
        case externalId = "external_id"
        case dataType = "data_type"
        case sourceTimestamp = "source_timestamp"
        case data
    }
}

struct SyncBatchRequest: Codable {
    let platform: String
    let records: [SyncRecord]
}

struct SyncRecordResult: Codable, Identifiable {
    var id: String { externalId }
    let externalId: String
    let status: String
    let targetTable: String?
    let targetRecordId: Int?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case externalId = "external_id"
        case status
        case targetTable = "target_table"
        case targetRecordId = "target_record_id"
        case error
    }
}

struct SyncBatchResponse: Codable {
    let total: Int
    let created: Int
    let duplicates: Int
    let errors: Int
    let results: [SyncRecordResult]
}

struct SyncStatusResponse: Codable {
    let platform: String
    let isActive: Bool
    let lastSyncAt: Date?
    let lastSyncStatus: String?
    let lastSyncRecords: Int?
    let lastSyncDuplicates: Int?
    let totalSyncedRecords: Int
    let recordsByType: [String: Int]

    enum CodingKeys: String, CodingKey {
        case platform
        case isActive = "is_active"
        case lastSyncAt = "last_sync_at"
        case lastSyncStatus = "last_sync_status"
        case lastSyncRecords = "last_sync_records"
        case lastSyncDuplicates = "last_sync_duplicates"
        case totalSyncedRecords = "total_synced_records"
        case recordsByType = "records_by_type"
    }
}

// MARK: - AnyCodable helper for freeform data dict

struct AnyCodable: Codable {
    let value: Any

    init(_ value: Any) { self.value = value }

    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { value = NSNull() }
        else if let b = try? c.decode(Bool.self) { value = b }
        else if let i = try? c.decode(Int.self) { value = i }
        else if let d = try? c.decode(Double.self) { value = d }
        else if let s = try? c.decode(String.self) { value = s }
        else if let a = try? c.decode([AnyCodable].self) { value = a.map(\.value) }
        else if let d = try? c.decode([String: AnyCodable].self) { value = d.mapValues(\.value) }
        else { throw DecodingError.dataCorruptedError(in: c, debugDescription: "Unsupported type") }
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch value {
        case is NSNull: try c.encodeNil()
        case let b as Bool: try c.encode(b)
        case let i as Int: try c.encode(i)
        case let d as Double: try c.encode(d)
        case let s as String: try c.encode(s)
        case let a as [Any]: try c.encode(a.map { AnyCodable($0) })
        case let d as [String: Any]: try c.encode(d.mapValues { AnyCodable($0) })
        default: try c.encodeNil()
        }
    }
}
