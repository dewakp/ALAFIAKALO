import Foundation
import HealthKit

/// Reads data from Apple HealthKit and syncs it one-way into ALAFIA.
/// Uses external sample UUIDs as dedup keys — the backend rejects duplicates.
@Observable
final class HealthKitSyncManager {
    static let shared = HealthKitSyncManager()

    // MARK: - State

    var isAvailable: Bool { HKHealthStore.isHealthDataAvailable() }
    var isAuthorized = false
    var isSyncing = false
    var lastSyncResult: SyncBatchResponse?
    var syncError: String?
    var connection: SyncConnection?
    var syncStatus: SyncStatusResponse?

    private let store = HKHealthStore()
    private let batchSize = 200

    // Data types we read
    static let allDataTypes: [(key: String, label: String, icon: String)] = [
        ("steps", "Steps", "figure.walk"),
        ("heart_rate", "Heart Rate", "heart.fill"),
        ("workout", "Workouts", "figure.run"),
        ("sleep", "Sleep Analysis", "bed.double.fill"),
        ("weight", "Body Mass", "scalemass.fill"),
        ("blood_pressure", "Blood Pressure", "heart.text.clipboard"),
        ("blood_oxygen", "Blood Oxygen", "lungs.fill"),
        ("body_temperature", "Body Temperature", "thermometer.medium"),
        ("nutrition", "Nutrition", "fork.knife"),
        ("mindfulness", "Mindfulness", "brain.head.profile"),
    ]

    private let hkTypes: [String: HKSampleType] = {
        var map: [String: HKSampleType] = [:]
        map["steps"] = HKQuantityType(.stepCount)
        map["heart_rate"] = HKQuantityType(.heartRate)
        map["workout"] = HKWorkoutType.workoutType()
        map["sleep"] = HKCategoryType(.sleepAnalysis)
        map["weight"] = HKQuantityType(.bodyMass)
        map["blood_pressure"] = HKQuantityType(.bloodPressureSystolic)
        map["blood_oxygen"] = HKQuantityType(.oxygenSaturation)
        map["body_temperature"] = HKQuantityType(.bodyTemperature)
        map["nutrition"] = HKQuantityType(.dietaryEnergyConsumed)
        map["mindfulness"] = HKCategoryType(.mindfulSession)
        return map
    }()

    // MARK: - Authorization

    func requestAuthorization() async {
        guard isAvailable else { return }

        var readTypes = Set<HKObjectType>()
        for (_, type) in hkTypes {
            readTypes.insert(type)
        }
        // Also request diastolic BP since systolic is the primary key
        readTypes.insert(HKQuantityType(.bloodPressureDiastolic))

        do {
            try await store.requestAuthorization(toShare: [], read: readTypes)
            isAuthorized = true
        } catch {
            syncError = "HealthKit authorization failed: \(error.localizedDescription)"
        }
    }

    // MARK: - Connection Management

    func ensureConnection(enabledTypes: [String]) async {
        do {
            let existing: [SyncConnection] = try await APIClient.shared.get("/sync/connections")
            if let hk = existing.first(where: { $0.platform == "healthkit" }) {
                connection = hk
            } else {
                let body = SyncConnectionCreate(platform: "healthkit", enabledDataTypes: enabledTypes)
                let created: SyncConnection = try await APIClient.shared.post("/sync/connections", body: body)
                connection = created
            }
        } catch {
            syncError = "Connection error: \(error.localizedDescription)"
        }
    }

    func loadStatus() async {
        do {
            syncStatus = try await APIClient.shared.get("/sync/status/healthkit")
        } catch {
            // Connection may not exist yet — that's okay
        }
    }

    // MARK: - Full Sync

    func performSync(dataTypes: [String]) async {
        guard isAvailable, isAuthorized else {
            syncError = "HealthKit not available or not authorized"
            return
        }

        isSyncing = true
        syncError = nil
        lastSyncResult = nil

        // Use last sync time as the anchor — only fetch new data
        let sinceDate = connection?.lastSyncAt ?? Calendar.current.date(byAdding: .month, value: -3, to: Date())!

        var allRecords: [SyncRecord] = []

        for dataType in dataTypes {
            guard let hkType = hkTypes[dataType] else { continue }
            do {
                let records = try await fetchSamples(type: hkType, dataType: dataType, since: sinceDate)
                allRecords.append(contentsOf: records)
            } catch {
                print("Error fetching \(dataType): \(error)")
            }
        }

        guard !allRecords.isEmpty else {
            isSyncing = false
            lastSyncResult = SyncBatchResponse(total: 0, created: 0, duplicates: 0, errors: 0, results: [])
            return
        }

        // Send in batches
        var totalCreated = 0, totalDups = 0, totalErrors = 0
        var allResults: [SyncRecordResult] = []

        for chunk in allRecords.chunked(into: batchSize) {
            do {
                let batch = SyncBatchRequest(platform: "healthkit", records: chunk)
                let resp: SyncBatchResponse = try await APIClient.shared.post("/sync/ingest", body: batch)
                totalCreated += resp.created
                totalDups += resp.duplicates
                totalErrors += resp.errors
                allResults.append(contentsOf: resp.results)
            } catch {
                syncError = "Sync error: \(error.localizedDescription)"
                totalErrors += chunk.count
            }
        }

        lastSyncResult = SyncBatchResponse(
            total: allRecords.count,
            created: totalCreated,
            duplicates: totalDups,
            errors: totalErrors,
            results: allResults
        )

        await loadStatus()
        isSyncing = false
    }

    // MARK: - HealthKit Queries

    private func fetchSamples(type: HKSampleType, dataType: String, since: Date) async throws -> [SyncRecord] {
        let predicate = HKQuery.predicateForSamples(withStart: since, end: Date(), options: .strictStartDate)
        let limit = 500

        return try await withCheckedThrowingContinuation { continuation in
            let query = HKSampleQuery(
                sampleType: type,
                predicate: predicate,
                limit: limit,
                sortDescriptors: [NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: false)]
            ) { _, samples, error in
                if let error {
                    continuation.resume(throwing: error)
                    return
                }
                let records = (samples ?? []).compactMap { sample in
                    Self.mapSample(sample, dataType: dataType)
                }
                continuation.resume(returning: records)
            }
            store.execute(query)
        }
    }

    private static func mapSample(_ sample: HKSample, dataType: String) -> SyncRecord? {
        let externalId = sample.uuid.uuidString
        let timestamp = sample.startDate

        var data: [String: AnyCodable] = [
            "start_date": AnyCodable(ISO8601DateFormatter().string(from: sample.startDate)),
        ]

        switch dataType {
        case "steps":
            guard let q = sample as? HKQuantitySample else { return nil }
            data["count"] = AnyCodable(Int(q.quantity.doubleValue(for: .count())))
            data["date"] = AnyCodable(dateString(sample.startDate))

        case "heart_rate":
            guard let q = sample as? HKQuantitySample else { return nil }
            data["bpm"] = AnyCodable(Int(q.quantity.doubleValue(for: HKUnit.count().unitDivided(by: .minute()))))
            data["date"] = AnyCodable(dateString(sample.startDate))

        case "workout":
            guard let w = sample as? HKWorkout else { return nil }
            data["workout_type"] = AnyCodable(w.workoutActivityType.name)
            data["activity_type"] = AnyCodable(w.workoutActivityType.name)
            data["duration_minutes"] = AnyCodable(Int(w.duration / 60))
            if let cal = w.totalEnergyBurned {
                data["active_energy_burned"] = AnyCodable(cal.doubleValue(for: .kilocalorie()))
            }
            if let dist = w.totalDistance {
                data["distance_km"] = AnyCodable(dist.doubleValue(for: .meterUnit(with: .kilo)))
            }
            data["date"] = AnyCodable(dateString(sample.startDate))

        case "sleep":
            guard sample is HKCategorySample else { return nil }
            let hours = sample.endDate.timeIntervalSince(sample.startDate) / 3600
            data["duration_hours"] = AnyCodable(round(hours * 10) / 10)
            data["date"] = AnyCodable(dateString(sample.endDate))

        case "weight":
            guard let q = sample as? HKQuantitySample else { return nil }
            data["value_kg"] = AnyCodable(round(q.quantity.doubleValue(for: .gramUnit(with: .kilo)) * 10) / 10)
            data["date"] = AnyCodable(dateString(sample.startDate))

        case "blood_pressure":
            // BP comes as a correlation; for quantity samples, just use systolic
            guard let q = sample as? HKQuantitySample else { return nil }
            data["systolic"] = AnyCodable(Int(q.quantity.doubleValue(for: .millimeterOfMercury())))
            data["date"] = AnyCodable(dateString(sample.startDate))

        case "blood_oxygen":
            guard let q = sample as? HKQuantitySample else { return nil }
            data["percentage"] = AnyCodable(round(q.quantity.doubleValue(for: .percent()) * 1000) / 10)
            data["date"] = AnyCodable(dateString(sample.startDate))

        case "body_temperature":
            guard let q = sample as? HKQuantitySample else { return nil }
            data["value_celsius"] = AnyCodable(round(q.quantity.doubleValue(for: .degreeCelsius()) * 10) / 10)
            data["date"] = AnyCodable(dateString(sample.startDate))

        case "nutrition":
            guard let q = sample as? HKQuantitySample else { return nil }
            data["energy_kcal"] = AnyCodable(round(q.quantity.doubleValue(for: .kilocalorie())))
            data["food_name"] = AnyCodable("HealthKit import")
            data["date"] = AnyCodable(dateString(sample.startDate))

        case "mindfulness":
            guard sample is HKCategorySample else { return nil }
            let minutes = Int(sample.endDate.timeIntervalSince(sample.startDate) / 60)
            data["duration_minutes"] = AnyCodable(minutes)
            data["session_type"] = AnyCodable("mindfulness")
            data["date"] = AnyCodable(dateString(sample.startDate))

        default:
            return nil
        }

        return SyncRecord(
            externalId: externalId,
            dataType: dataType,
            sourceTimestamp: timestamp,
            data: data
        )
    }

    private static func dateString(_ date: Date) -> String {
        let df = DateFormatter()
        df.dateFormat = "yyyy-MM-dd"
        return df.string(from: date)
    }
}

// MARK: - Array chunking

extension Array {
    func chunked(into size: Int) -> [[Element]] {
        stride(from: 0, to: count, by: size).map {
            Array(self[$0..<Swift.min($0 + size, count)])
        }
    }
}

// MARK: - Workout type name

extension HKWorkoutActivityType {
    var name: String {
        switch self {
        case .running: return "running"
        case .cycling: return "cycling"
        case .swimming: return "swimming"
        case .walking: return "walking"
        case .hiking: return "hiking"
        case .yoga: return "yoga"
        case .functionalStrengthTraining, .traditionalStrengthTraining: return "weightlifting"
        case .highIntensityIntervalTraining: return "hiit"
        case .dance: return "dance"
        case .elliptical: return "elliptical"
        case .rowing: return "rowing"
        case .stairClimbing: return "stair_climbing"
        case .crossTraining: return "cross_training"
        case .pilates: return "pilates"
        case .tennis: return "tennis"
        case .basketball: return "basketball"
        case .soccer: return "soccer"
        default: return "other"
        }
    }
}
