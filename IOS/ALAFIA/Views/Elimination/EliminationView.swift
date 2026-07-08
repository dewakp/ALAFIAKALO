import SwiftUI
import PhotosUI

// MARK: - Analyze-photo control (shared by the three log sheets)

/// "Analyze photo" button: picks an image, runs it through the vision model
/// (`elimination-from-image`) for the given `eventType`, hands the suggested
/// fields back via `onResult`, and renders any attention flags + disclaimer.
/// AI visual estimate — not a diagnosis.
struct AnalyzeEliminationPhotoButton: View {
    let eventType: String
    let onResult: (EliminationFromImageResponse) -> Void

    @State private var photoItem: PhotosPickerItem?
    @State private var analyzing = false
    @State private var flags: [String] = []
    @State private var errorMessage: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            PhotosPicker(selection: $photoItem, matching: .images) {
                HStack {
                    if analyzing { ProgressView() } else { Image(systemName: "camera.viewfinder") }
                    Text(analyzing ? "Analyzing photo…" : "Analyze photo")
                }
            }
            .disabled(analyzing)
            .onChange(of: photoItem) { _, item in
                guard let item else { return }
                Task { await analyze(item) }
            }
            ForEach(flags, id: \.self) { f in
                Label(f, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption).foregroundStyle(.orange)
            }
            if let e = errorMessage {
                Text(e).font(.caption).foregroundStyle(.red)
            }
        }
    }

    private func analyze(_ item: PhotosPickerItem) async {
        guard let data = try? await item.loadTransferable(type: Data.self) else { return }
        analyzing = true; errorMessage = nil; flags = []
        struct Body: Encodable { let event_type: String; let image_base64: String }
        do {
            let body = Body(event_type: eventType,
                            image_base64: "data:image/jpeg;base64," + data.base64EncodedString())
            let res: EliminationFromImageResponse = try await APIClient.shared.post(
                "/image-ai/elimination-from-image", body: body, timeout: 180)
            onResult(res)
            flags = res.flags + [res.disclaimer].compactMap { $0 }
        } catch {
            errorMessage = error.localizedDescription
        }
        analyzing = false
    }
}

// MARK: - ViewModels

@Observable
final class BowelViewModel {
    var entries: [BowelMovement] = []
    var isLoading = false
    var errorMessage: String?

    func fetch() async {
        isLoading = true
        errorMessage = nil
        do {
            entries = try await APIClient.shared.get("/elimination/bowel?limit=100")
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }

    func add(_ entry: BowelMovementCreate) async -> Bool {
        do {
            let _: BowelMovement = try await APIClient.shared.post("/elimination/bowel", body: entry)
            await fetch()
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    func delete(id: Int) async {
        do {
            try await APIClient.shared.delete("/elimination/bowel/\(id)")
            entries.removeAll { $0.id == id }
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

@Observable
final class VomitingViewModel {
    var entries: [VomitingLog] = []
    var isLoading = false
    var errorMessage: String?

    func fetch() async {
        isLoading = true
        errorMessage = nil
        do {
            entries = try await APIClient.shared.get("/elimination/vomiting?limit=100")
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }

    func add(_ entry: VomitingLogCreate) async -> Bool {
        do {
            let _: VomitingLog = try await APIClient.shared.post("/elimination/vomiting", body: entry)
            await fetch()
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    func delete(id: Int) async {
        do {
            try await APIClient.shared.delete("/elimination/vomiting/\(id)")
            entries.removeAll { $0.id == id }
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

@Observable
final class UrinationViewModel {
    var entries: [UrinationLog] = []
    var isLoading = false
    var errorMessage: String?

    func fetch() async {
        isLoading = true
        errorMessage = nil
        do {
            entries = try await APIClient.shared.get("/elimination/urination?limit=100")
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }

    func add(_ entry: UrinationLogCreate) async -> Bool {
        do {
            let _: UrinationLog = try await APIClient.shared.post("/elimination/urination", body: entry)
            await fetch()
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    func delete(id: Int) async {
        do {
            try await APIClient.shared.delete("/elimination/urination/\(id)")
            entries.removeAll { $0.id == id }
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

// MARK: - Main View

struct EliminationView: View {
    @State private var selectedTab = 0

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                Picker("Type", selection: $selectedTab) {
                    Text("💩 Bowel").tag(0)
                    Text("🤮 Vomiting").tag(1)
                    Text("💧 Urination").tag(2)
                }
                .pickerStyle(.segmented)
                .padding(.horizontal)
                .padding(.vertical, 8)

                switch selectedTab {
                case 1:  VomitingListView()
                case 2:  UrinationListView()
                default: BowelListView()
                }
            }
            .navigationTitle("Elimination")
        }
    }
}

// MARK: - Bowel Movement List + Add

struct BowelListView: View {
    @State private var vm = BowelViewModel()
    @State private var showAdd = false

    var body: some View {
        Group {
            if vm.isLoading {
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if vm.entries.isEmpty {
                EmptyStateView(icon: "hare", title: "No Records", message: "Tap + to log a bowel movement")
            } else {
                List {
                    ForEach(vm.entries) { entry in
                        BowelRow(entry: entry)
                    }
                    .onDelete { idx in
                        Task {
                            for i in idx { await vm.delete(id: vm.entries[i].id) }
                        }
                    }
                }
            }
        }
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { showAdd = true } label: { Image(systemName: "plus") }
            }
        }
        .sheet(isPresented: $showAdd) { AddBowelSheet(vm: vm) }
        .task { await vm.fetch() }
    }
}

struct BowelRow: View {
    let entry: BowelMovement

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text("💩")
                    .font(.title2)
                VStack(alignment: .leading) {
                    Text(entry.logDate)
                        .font(.headline)
                    if let t = entry.logTime {
                        Text(t)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                Spacer()
                if let b = entry.bristolScale {
                    VStack(alignment: .trailing) {
                        Text("Bristol \(b)")
                            .font(.caption)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(.blue.opacity(0.15))
                            .clipShape(Capsule())
                    }
                }
            }
            if entry.bloodPresent == true {
                Label("Blood present", systemImage: "exclamationmark.triangle.fill")
                    .font(.caption)
                    .foregroundStyle(.red)
            }
            if let notes = entry.notes, !notes.isEmpty {
                Text(notes)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
        .padding(.vertical, 4)
    }
}

struct AddBowelSheet: View {
    @Bindable var vm: BowelViewModel
    @Environment(\.dismiss) var dismiss

    @State private var bristolScale: Double = 4
    @State private var bloodPresent = false
    @State private var mucusPresent = false
    @State private var straining = false
    @State private var urgency = false
    @State private var painLevel: Double = 0
    @State private var notes = ""
    @State private var saving = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    AnalyzeEliminationPhotoButton(eventType: "bowel") { res in
                        let s = res.suggested
                        if let b = s.bristolScale { bristolScale = Double(b) }
                        if s.bloodPresent == true { bloodPresent = true }
                        if s.mucusPresent == true { mucusPresent = true }
                        var bits: [String] = []
                        if let b = s.bristolScale { bits.append("Bristol type \(b)") }
                        if let c = s.consistency { bits.append(c) }
                        if let c = s.color { bits.append("\(c) color") }
                        if s.bloodPresent == true { bits.append("possible blood") }
                        if s.mucusPresent == true { bits.append("possible mucus") }
                        notes = bits.isEmpty ? res.description : "\(bits.joined(separator: ", ")) — \(res.description)"
                    }
                } header: { Text("Analyze Photo (Optional)") }

                Section("Bristol Stool Scale") {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Type \(Int(bristolScale))")
                            .font(.headline)
                        Text(bristolDescription(Int(bristolScale)))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Slider(value: $bristolScale, in: 1...7, step: 1)
                            .tint(.brown)
                    }
                }

                Section("Symptoms") {
                    Toggle("Blood present", isOn: $bloodPresent)
                        .tint(.red)
                    Toggle("Mucus present", isOn: $mucusPresent)
                        .tint(.orange)
                    Toggle("Straining", isOn: $straining)
                    Toggle("Urgency", isOn: $urgency)
                    VStack(alignment: .leading) {
                        Text("Pain level: \(Int(painLevel))/10")
                        Slider(value: $painLevel, in: 0...10, step: 1)
                            .tint(.red)
                    }
                }

                Section("Notes") {
                    TextField("Any additional details…", text: $notes, axis: .vertical)
                        .lineLimit(3...6)
                }
            }
            .navigationTitle("Log Bowel Movement")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        Task {
                            saving = true
                            let entry = BowelMovementCreate(
                                logDate: ISO8601DateFormatter().string(from: Date()).prefix(10).description,
                                bristolScale: Int(bristolScale),
                                bloodPresent: bloodPresent,
                                mucusPresent: mucusPresent,
                                painLevel: Int(painLevel) > 0 ? Int(painLevel) : nil,
                                straining: straining,
                                urgency: urgency,
                                notes: notes.isEmpty ? nil : notes
                            )
                            if await vm.add(entry) { dismiss() }
                            saving = false
                        }
                    }
                    .disabled(saving)
                }
            }
        }
    }

    private func bristolDescription(_ type: Int) -> String {
        switch type {
        case 1: return "Separate hard lumps"
        case 2: return "Lumpy sausage shape"
        case 3: return "Sausage with cracks"
        case 4: return "Smooth, soft sausage"
        case 5: return "Soft blobs, clear edges"
        case 6: return "Fluffy pieces, mushy"
        case 7: return "Entirely liquid"
        default: return ""
        }
    }
}

// MARK: - Vomiting List + Add

struct VomitingListView: View {
    @State private var vm = VomitingViewModel()
    @State private var showAdd = false

    var body: some View {
        Group {
            if vm.isLoading {
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if vm.entries.isEmpty {
                EmptyStateView(icon: "facemask", title: "No Records", message: "Tap + to log a vomiting episode")
            } else {
                List {
                    ForEach(vm.entries) { entry in
                        VomitingRow(entry: entry)
                    }
                    .onDelete { idx in
                        Task { for i in idx { await vm.delete(id: vm.entries[i].id) } }
                    }
                }
            }
        }
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { showAdd = true } label: { Image(systemName: "plus") }
            }
        }
        .sheet(isPresented: $showAdd) { AddVomitingSheet(vm: vm) }
        .task { await vm.fetch() }
    }
}

struct VomitingRow: View {
    let entry: VomitingLog

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text("🤮")
                    .font(.title2)
                VStack(alignment: .leading) {
                    Text(entry.logDate)
                        .font(.headline)
                    if let t = entry.logTime { Text(t).font(.caption).foregroundStyle(.secondary) }
                }
                Spacer()
                if entry.containsBlood == true {
                    Label("Blood", systemImage: "exclamationmark.triangle.fill")
                        .font(.caption)
                        .foregroundStyle(.red)
                }
            }
            if let trigger = entry.trigger, !trigger.isEmpty {
                Text("Trigger: \(trigger)")
                    .font(.caption)
                    .foregroundStyle(.orange)
            }
            if let notes = entry.notes, !notes.isEmpty {
                Text(notes)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
        .padding(.vertical, 4)
    }
}

struct AddVomitingSheet: View {
    @Bindable var vm: VomitingViewModel
    @Environment(\.dismiss) var dismiss

    @State private var containsFood = false
    @State private var containsBile = false
    @State private var containsBlood = false
    @State private var nauseaBefore = false
    @State private var nauseaAfter = false
    @State private var projectile = false
    @State private var reliefAfter = false
    @State private var fever = false
    @State private var dizziness = false
    @State private var trigger = ""
    @State private var notes = ""
    @State private var saving = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    AnalyzeEliminationPhotoButton(eventType: "vomiting") { res in
                        if res.suggested.bloodPresent == true { containsBlood = true }
                        notes = res.description
                    }
                } header: { Text("Analyze Photo (Optional)") }

                Section("Contents") {
                    Toggle("Contains food", isOn: $containsFood)
                    Toggle("Contains bile (yellow/green)", isOn: $containsBile).tint(.yellow)
                    Toggle("Contains blood", isOn: $containsBlood).tint(.red)
                    Toggle("Projectile", isOn: $projectile).tint(.orange)
                }

                Section("Symptoms") {
                    Toggle("Nausea before", isOn: $nauseaBefore)
                    Toggle("Nausea after", isOn: $nauseaAfter)
                    Toggle("Relief after vomiting", isOn: $reliefAfter).tint(.green)
                    Toggle("Fever", isOn: $fever).tint(.red)
                    Toggle("Dizziness", isOn: $dizziness).tint(.purple)
                }

                Section("Details") {
                    TextField("Trigger (e.g. food, smell, motion…)", text: $trigger)
                    TextField("Additional notes…", text: $notes, axis: .vertical)
                        .lineLimit(3...6)
                }
            }
            .navigationTitle("Log Vomiting Episode")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        Task {
                            saving = true
                            let today = ISO8601DateFormatter().string(from: Date()).prefix(10).description
                            let entry = VomitingLogCreate(
                                logDate: today,
                                containsFood: containsFood,
                                containsBile: containsBile,
                                containsBlood: containsBlood,
                                nauseaBefore: nauseaBefore,
                                nauseaAfter: nauseaAfter,
                                projectile: projectile,
                                trigger: trigger.isEmpty ? nil : trigger,
                                reliefAfter: reliefAfter,
                                fever: fever,
                                dizziness: dizziness,
                                notes: notes.isEmpty ? nil : notes
                            )
                            if await vm.add(entry) { dismiss() }
                            saving = false
                        }
                    }
                    .disabled(saving)
                }
            }
        }
    }
}

// MARK: - Urination List + Add

struct UrinationListView: View {
    @State private var vm = UrinationViewModel()
    @State private var showAdd = false

    var body: some View {
        Group {
            if vm.isLoading {
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if vm.entries.isEmpty {
                EmptyStateView(icon: "drop", title: "No Records", message: "Tap + to log urination")
            } else {
                List {
                    ForEach(vm.entries) { entry in
                        UrinationRow(entry: entry)
                    }
                    .onDelete { idx in
                        Task { for i in idx { await vm.delete(id: vm.entries[i].id) } }
                    }
                }
            }
        }
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { showAdd = true } label: { Image(systemName: "plus") }
            }
        }
        .sheet(isPresented: $showAdd) { AddUrinationSheet(vm: vm) }
        .task { await vm.fetch() }
    }
}

struct UrinationRow: View {
    let entry: UrinationLog

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text("💧")
                    .font(.title2)
                VStack(alignment: .leading) {
                    Text(entry.logDate)
                        .font(.headline)
                    if let t = entry.logTime { Text(t).font(.caption).foregroundStyle(.secondary) }
                }
                Spacer()
                if let vol = entry.volumeMl {
                    Text("\(vol) mL")
                        .font(.caption)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(.blue.opacity(0.15))
                        .clipShape(Capsule())
                }
            }
            HStack(spacing: 8) {
                if let color = entry.color { Text("Color: \(color)").font(.caption).foregroundStyle(.secondary) }
                if entry.bloodPresent == true {
                    Label("Blood", systemImage: "exclamationmark.triangle.fill")
                        .font(.caption)
                        .foregroundStyle(.red)
                }
                if entry.burningSensation == true {
                    Text("Burning").font(.caption).foregroundStyle(.orange)
                }
            }
            if let notes = entry.notes, !notes.isEmpty {
                Text(notes).font(.caption).foregroundStyle(.secondary).lineLimit(2)
            }
        }
        .padding(.vertical, 4)
    }
}

struct AddUrinationSheet: View {
    @Bindable var vm: UrinationViewModel
    @Environment(\.dismiss) var dismiss

    @State private var volumeStr = ""
    @State private var color = ""
    @State private var clarity = ""
    @State private var bloodPresent = false
    @State private var burningSensation = false
    @State private var urgency = false
    @State private var nighttime = false
    @State private var painLevel: Double = 0
    @State private var notes = ""
    @State private var saving = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    AnalyzeEliminationPhotoButton(eventType: "urination") { res in
                        let s = res.suggested
                        if let c = s.color { color = c }
                        if s.bloodPresent == true { bloodPresent = true }
                        var bits: [String] = []
                        if let c = s.color { bits.append("\(c) color") }
                        if s.bloodPresent == true { bits.append("possible blood") }
                        notes = bits.isEmpty ? res.description : "\(bits.joined(separator: ", ")) — \(res.description)"
                    }
                } header: { Text("Analyze Photo (Optional)") }

                Section("Measurement") {
                    TextField("Volume (mL)", text: $volumeStr)
                        .keyboardType(.numberPad)
                    TextField("Color (pale, yellow, amber, dark…)", text: $color)
                    TextField("Clarity (clear, cloudy, foamy…)", text: $clarity)
                }

                Section("Symptoms") {
                    Toggle("Blood present", isOn: $bloodPresent).tint(.red)
                    Toggle("Burning sensation", isOn: $burningSensation).tint(.orange)
                    Toggle("Urgency", isOn: $urgency)
                    Toggle("Nighttime (nocturia)", isOn: $nighttime).tint(.indigo)
                    VStack(alignment: .leading) {
                        Text("Pain level: \(Int(painLevel))/10")
                        Slider(value: $painLevel, in: 0...10, step: 1).tint(.red)
                    }
                }

                Section("Notes") {
                    TextField("Additional details…", text: $notes, axis: .vertical)
                        .lineLimit(3...6)
                }
            }
            .navigationTitle("Log Urination")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        Task {
                            saving = true
                            let today = ISO8601DateFormatter().string(from: Date()).prefix(10).description
                            let entry = UrinationLogCreate(
                                logDate: today,
                                color: color.isEmpty ? nil : color,
                                clarity: clarity.isEmpty ? nil : clarity,
                                volumeMl: Int(volumeStr),
                                painLevel: Int(painLevel) > 0 ? Int(painLevel) : nil,
                                burningSensation: burningSensation,
                                urgency: urgency,
                                bloodPresent: bloodPresent,
                                nighttime: nighttime,
                                notes: notes.isEmpty ? nil : notes
                            )
                            if await vm.add(entry) { dismiss() }
                            saving = false
                        }
                    }
                    .disabled(saving)
                }
            }
        }
    }
}
