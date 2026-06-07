import SwiftUI
import HealthKit

struct HealthSyncView: View {
    @State private var hkManager = HealthKitSyncManager.shared
    @State private var enabledTypes: Set<String> = Set(HealthKitSyncManager.allDataTypes.map(\.key))
    @State private var showResult = false

    var body: some View {
        List {
            // ── Status Section ───────────────────────
            Section {
                HStack {
                    Image(systemName: "heart.fill")
                        .foregroundStyle(.red)
                        .font(.title2)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Apple Health")
                            .font(.headline)
                        Text(hkManager.isAvailable ? (hkManager.isAuthorized ? "Connected" : "Not connected") : "Not available")
                            .font(.caption)
                            .foregroundStyle(hkManager.isAuthorized ? .green : .secondary)
                    }
                    Spacer()
                    if !hkManager.isAuthorized && hkManager.isAvailable {
                        Button("Connect") {
                            Task { await hkManager.requestAuthorization() }
                        }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.small)
                    }
                }

                if let status = hkManager.syncStatus {
                    HStack {
                        Label("\(status.totalSyncedRecords) records synced", systemImage: "arrow.triangle.2.circlepath")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Spacer()
                        if let lastSync = status.lastSyncAt {
                            Text(lastSync, style: .relative)
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }

                    if let st = status.lastSyncStatus {
                        HStack {
                            Circle()
                                .fill(st == "success" ? .green : (st == "partial" ? .orange : .red))
                                .frame(width: 8, height: 8)
                            Text("Last sync: \(st)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            if let created = status.lastSyncRecords, let dups = status.lastSyncDuplicates {
                                Spacer()
                                Text("\(created) new, \(dups) skipped")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }

            // ── Data Types ───────────────────────────
            Section("Data Types") {
                ForEach(HealthKitSyncManager.allDataTypes, id: \.key) { item in
                    Toggle(isOn: Binding(
                        get: { enabledTypes.contains(item.key) },
                        set: { enabled in
                            if enabled { enabledTypes.insert(item.key) }
                            else { enabledTypes.remove(item.key) }
                        }
                    )) {
                        Label(item.label, systemImage: item.icon)
                    }
                }
            }

            // ── Sync Records Breakdown ───────────────
            if let status = hkManager.syncStatus, !status.recordsByType.isEmpty {
                Section("Synced Records") {
                    ForEach(status.recordsByType.sorted(by: { $0.value > $1.value }), id: \.key) { type, count in
                        HStack {
                            Text(type.replacingOccurrences(of: "_", with: " ").capitalized)
                                .font(.subheadline)
                            Spacer()
                            Text("\(count)")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }

            // ── Sync Button ──────────────────────────
            Section {
                Button {
                    Task { await sync() }
                } label: {
                    HStack {
                        Spacer()
                        if hkManager.isSyncing {
                            ProgressView()
                                .padding(.trailing, 8)
                            Text("Syncing...")
                        } else {
                            Image(systemName: "arrow.triangle.2.circlepath")
                            Text("Sync Now")
                        }
                        Spacer()
                    }
                    .font(.headline)
                    .padding(.vertical, 4)
                }
                .disabled(!hkManager.isAuthorized || hkManager.isSyncing || enabledTypes.isEmpty)
            }

            // ── Result ───────────────────────────────
            if let result = hkManager.lastSyncResult, showResult {
                Section("Last Sync Result") {
                    LabeledContent("Total Records", value: "\(result.total)")
                    LabeledContent("Created", value: "\(result.created)")
                        .foregroundStyle(.green)
                    LabeledContent("Duplicates Skipped", value: "\(result.duplicates)")
                        .foregroundStyle(.orange)
                    if result.errors > 0 {
                        LabeledContent("Errors", value: "\(result.errors)")
                            .foregroundStyle(.red)
                    }
                }
            }

            if let error = hkManager.syncError {
                Section {
                    Label(error, systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(.red)
                        .font(.caption)
                }
            }

            // ── Info ─────────────────────────────────
            Section {
                VStack(alignment: .leading, spacing: 8) {
                    Label("One-way sync", systemImage: "arrow.right")
                    Text("Data flows from Apple Health → ALAFIA only. We never write to Apple Health.")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    Label("Deduplication", systemImage: "shield.checkmark")
                    Text("Each health record has a unique ID. Re-syncing the same data will not create duplicates.")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    Label("EHR & Apps", systemImage: "stethoscope")
                    Text("Any app or EHR system that writes to Apple Health will be automatically included in the sync.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .padding(.vertical, 4)
            }
        }
        .navigationTitle("Health Sync")
        .task {
            if hkManager.isAvailable {
                await hkManager.requestAuthorization()
                await hkManager.ensureConnection(enabledTypes: Array(enabledTypes))
                await hkManager.loadStatus()
            }
        }
    }

    private func sync() async {
        showResult = false
        await hkManager.ensureConnection(enabledTypes: Array(enabledTypes))
        await hkManager.performSync(dataTypes: Array(enabledTypes))
        showResult = true
    }
}
