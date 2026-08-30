import SwiftUI

// MARK: - ViewModel

@Observable
final class HemodialysisViewModel {
    var sessions: [TherapySession] = []
    var summary: HDSummary?
    var isLoading = false
    var errorMessage: String?
    var showAddSheet = false
    var isSaving = false
    var periodDays = 90
    var editingSession: TherapySession?

    // Form state
    var scheduledDate = Date()
    var status = "COMPLETED"
    var dayOfWeek = ""
    var dialysisAccessType = "AV Fistula"
    var facilityName = ""
    var attendingPhysician = ""
    var rnReviewer = ""
    // Weights
    var dryWeightKg = ""
    var previousPostWeightKg = ""
    var preDialysisWeightKg = ""
    var postDialysisWeightKg = ""
    var fluidRemovedMl = ""
    var fluidToRemoveKg = ""
    // Flow rates
    var bloodFlowRate = ""
    var dialysateFlowRate = ""
    var durationMinutes = ""
    // Wall clocks in the form, datetimes on the wire. Two treatments in one day
    // are told apart by these, so they are what makes a same-day session
    // identifiable rather than a suspected duplicate.
    var startClock = ""
    var endClock = ""
    /// The intradialytic grid. Rows that came from the server keep their id, so
    /// saving updates them in place instead of appending duplicates.
    var readingRows: [EditableReading] = []
    var removedReadingIds: [Int] = []

    /// The clock part of a stored session timestamp.
    static func clock(of value: String?) -> String {
        guard let value, !value.isEmpty else { return "" }
        guard let r = value.range(of: #"T([01]\d|2[0-3]):([0-5]\d)"#, options: .regularExpression)
        else { return "" }
        return String(value[r].dropFirst())
    }

    /// "HH:MM" combined with the SESSION's date — editing a 2013 flowsheet must
    /// not restamp it with today. nil when the clock is not a valid time.
    static func iso(day: String, clock: String) -> String? {
        let t = clock.trimmingCharacters(in: .whitespaces)
        guard t.range(of: #"^([01]\d|2[0-3]):([0-5]\d)$"#, options: .regularExpression) != nil
        else { return nil }
        return "\(day)T\(t):00"
    }

    /// Minutes between two wall clocks, crossing midnight: 21:00 → 01:00 is four
    /// hours, not minus twenty.
    static func minutes(from start: String, to end: String) -> Int? {
        func mins(_ s: String) -> Int? {
            let parts = s.trimmingCharacters(in: .whitespaces).split(separator: ":")
            guard parts.count == 2, let h = Int(parts[0]), let m = Int(parts[1]),
                  (0...23).contains(h), (0...59).contains(m) else { return nil }
            return h * 60 + m
        }
        guard let a = mins(start), let b = mins(end) else { return nil }
        var d = b - a
        if d < 0 { d += 24 * 60 }
        return d
    }

    func deriveDuration() {
        if let m = Self.minutes(from: startClock, to: endClock) {
            durationMinutes = String(m)
        }
    }
    // Dialysate prescription
    var dialysateVolumeLiters = ""
    var dialysateLactateMeq = ""
    var dialysatePotassiumMeq = ""
    var sakNumber = ""
    var needleGauge = "15G"
    var needleLength = ""
    var buttonholeTechnique = false
    // Vitals
    var preSystolicBp = ""
    var preDiastolicBp = ""
    var preHeartRate = ""
    var preTemperature = ""
    var postSystolicBp = ""
    var postDiastolicBp = ""
    var postHeartRate = ""
    var postTemperature = ""
    var oxygenSaturation = ""
    // Standing BP
    var preStandingSystolicBp = ""
    var preStandingDiastolicBp = ""
    var preStandingHeartRate = ""
    var postStandingSystolicBp = ""
    var postStandingDiastolicBp = ""
    var postStandingHeartRate = ""
    // Pre-treatment symptoms
    var preShortnessOfBreath = false
    var preSwelling = false
    var preChangeInMobility = false
    var preDigestionProblems = false
    var preHospErSinceLast = false
    var accessThrillBruit = true
    var accessRednessDrainage = false
    // Equipment
    var cartridgeLot = ""
    var sakLot = ""
    var cyclerNumber = ""
    var warmerSerial = ""
    // Post-treatment totals
    var totalDialysateLiters = ""
    var totalUfLiters = ""
    var totalBloodVolumeProcessed = ""
    var dialyzerAppearance = ""
    var postBleedingStopTime = ""
    var postBruising = false
    var postInfiltration = false
    var postShortnessOfBreath = false
    var postSwelling = false
    var postDigestionProblems = false
    var postAccessThrillBruit = true
    // Machine maintenance
    var purificationPakChange = false
    var airFilterCleaned = false
    var wasteLineBleachDisinfection = false
    var alarmTestCompleted = false
    var sakUseNumber = ""
    var totalChloramineLevel = ""
    var labTubesDrawn = ""
    // Notes
    var sideEffects = ""
    var drugsAdministered = ""
    var clinicalNotes = ""
    var patientNotes = ""

    static let accessTypes = ["AV Fistula", "AV Graft", "Central Catheter", "Buttonhole"]

    /// Pre-fill from the last treatment, and which fields this access supports.
    var defaults: FlowsheetDefaults?

    /// Mirrors `classify_access` in app/services/flowsheet_defaults.py.
    ///
    /// A catheter has no needles and no bruit. A **graft is cannulated like a
    /// fistula**, so needle fields still apply to it. Anything unrecognised
    /// disables nothing — wrongly greying out a field stops the patient
    /// recording what actually happened.
    var isCatheterAccess: Bool {
        let text = dialysisAccessType.lowercased()
        if text.contains("fistula") || text.contains("graft")
            || text.contains("avf") || text.contains("avg") || text.contains("buttonhole") {
            return false
        }
        return text.contains("catheter") || text.contains("cather")
            || text.contains("cvc") || text.contains("permcath")
            || text.contains("perm-cath") || text.contains("tunnel")
    }

    /// Load what the last treatment already told us. A failure here means an
    /// empty form, never a blocked one.
    func loadDefaults() async {
        do {
            let d: FlowsheetDefaults = try await APIClient.shared.get(
                "/chronic/therapy-sessions/defaults"
            )
            defaults = d
            if let target = d.targetWeightKg, dryWeightKg.isEmpty {
                dryWeightKg = String(target)
            }
            if let access = d.carriedForward?.dialysisAccessType, !access.isEmpty {
                dialysisAccessType = access
            }
            if let physician = d.carriedForward?.attendingPhysician { attendingPhysician = physician }
            if let nurse = d.carriedForward?.attendingNurse { rnReviewer = nurse }
            if let volume = d.carriedForward?.dialysateVolumeLiters {
                dialysateVolumeLiters = String(volume)
            }
            if let potassium = d.carriedForward?.dialysatePotassiumMeq {
                dialysatePotassiumMeq = String(potassium)
            }
            if let sak = d.carriedForward?.sakNumber { sakNumber = String(sak) }

            // These were decoded and then dropped on the floor — the patient
            // re-typed a cycler and warmer serial the record already held.
            if let weight = d.carriedForward?.previousPostWeightKg, previousPostWeightKg.isEmpty {
                previousPostWeightKg = String(weight)
            }
            if let lot = d.carriedForward?.cartridgeLot, cartridgeLot.isEmpty { cartridgeLot = lot }
            if let lot = d.carriedForward?.sakLot, sakLot.isEmpty { sakLot = lot }
            if let cycler = d.carriedForward?.cyclerNumber, cyclerNumber.isEmpty { cyclerNumber = cycler }
            if let warmer = d.carriedForward?.warmerSerial, warmerSerial.isEmpty { warmerSerial = warmer }
            if let flow = d.carriedForward?.bloodFlowRate, bloodFlowRate.isEmpty {
                bloodFlowRate = String(flow)
            }
        } catch {
            defaults = nil
        }
    }
    static let statusOptions = ["SCHEDULED", "IN_PROGRESS", "COMPLETED", "CANCELLED"]
    static let needleGauges = ["15G", "16G", "17G"]
    static let daysOfWeek = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    func load() async {
        isLoading = true; errorMessage = nil
        do {
            sessions = try await APIClient.shared.get("/chronic/therapy-sessions?therapy_type=HEMODIALYSIS&limit=500")
            let cutoff = Calendar.current.date(byAdding: .day, value: -periodDays, to: Date()) ?? Date()
            let df = DateFormatter(); df.dateFormat = "yyyy-MM-dd"
            sessions = sessions.filter { s in
                guard let d = df.date(from: String(s.scheduledDate.prefix(10))) else { return true }
                return d >= cutoff
            }
        } catch { errorMessage = error.localizedDescription }
        isLoading = false
    }

    func loadSummary() async {
        do {
            summary = try await APIClient.shared.get("/chronic/hd-summary?days=\(periodDays)")
        } catch { /* silent */ }
    }

    func deleteSession(id: Int) async {
        do {
            try await APIClient.shared.delete("/chronic/therapy-sessions/\(id)")
            sessions.removeAll { $0.id == id }
        } catch { errorMessage = error.localizedDescription }
    }

    // MARK: - Flowsheet Lifecycle

    func submitFlowsheet(id: Int) async {
        do {
            let _: FlowsheetActionResponse = try await APIClient.shared.post("/chronic/therapy-sessions/\(id)/submit", body: EmptyBody())
            await load()
        } catch { errorMessage = error.localizedDescription }
    }

    func signFlowsheet(id: Int) async {
        do {
            let _: FlowsheetActionResponse = try await APIClient.shared.post("/chronic/therapy-sessions/\(id)/sign", body: FlowsheetSignRequest(signatureImage: ""))
            await load()
        } catch { errorMessage = error.localizedDescription }
    }

    func countersignFlowsheet(id: Int) async {
        do {
            let _: FlowsheetActionResponse = try await APIClient.shared.post("/chronic/therapy-sessions/\(id)/countersign", body: FlowsheetSignRequest(signatureImage: ""))
            await load()
        } catch { errorMessage = error.localizedDescription }
    }

    func reviewFlowsheet(id: Int) async {
        do {
            let _: FlowsheetActionResponse = try await APIClient.shared.post("/chronic/therapy-sessions/\(id)/review", body: EmptyBody())
            await load()
        } catch { errorMessage = error.localizedDescription }
    }

    func lockFlowsheet(id: Int) async {
        do {
            let _: FlowsheetActionResponse = try await APIClient.shared.post("/chronic/therapy-sessions/\(id)/lock", body: EmptyBody())
            await load()
        } catch { errorMessage = error.localizedDescription }
    }

    func resetForm() {
        editingSession = nil
        scheduledDate = Date()
        status = "COMPLETED"
        let wd = Calendar.current.component(.weekday, from: Date())
        dayOfWeek = Self.daysOfWeek[(wd + 5) % 7]
        dialysisAccessType = "AV Fistula"; facilityName = ""; attendingPhysician = ""; rnReviewer = ""
        dryWeightKg = ""; previousPostWeightKg = ""; preDialysisWeightKg = ""
        postDialysisWeightKg = ""; fluidRemovedMl = ""; fluidToRemoveKg = ""
        bloodFlowRate = ""; dialysateFlowRate = ""; durationMinutes = ""
        startClock = ""; endClock = ""
        readingRows = []; removedReadingIds = []
        dialysateVolumeLiters = ""; dialysateLactateMeq = ""; dialysatePotassiumMeq = ""
        sakNumber = ""; needleGauge = "15G"; needleLength = ""; buttonholeTechnique = false
        preSystolicBp = ""; preDiastolicBp = ""; preHeartRate = ""; preTemperature = ""
        postSystolicBp = ""; postDiastolicBp = ""; postHeartRate = ""; postTemperature = ""
        oxygenSaturation = ""
        preStandingSystolicBp = ""; preStandingDiastolicBp = ""; preStandingHeartRate = ""
        postStandingSystolicBp = ""; postStandingDiastolicBp = ""; postStandingHeartRate = ""
        preShortnessOfBreath = false; preSwelling = false; preChangeInMobility = false
        preDigestionProblems = false; preHospErSinceLast = false
        accessThrillBruit = true; accessRednessDrainage = false
        cartridgeLot = ""; sakLot = ""; cyclerNumber = ""; warmerSerial = ""
        totalDialysateLiters = ""; totalUfLiters = ""; totalBloodVolumeProcessed = ""
        dialyzerAppearance = ""; postBleedingStopTime = ""
        postBruising = false; postInfiltration = false; postShortnessOfBreath = false
        postSwelling = false; postDigestionProblems = false; postAccessThrillBruit = true
        purificationPakChange = false; airFilterCleaned = false
        wasteLineBleachDisinfection = false; alarmTestCompleted = false
        sakUseNumber = ""; totalChloramineLevel = ""; labTubesDrawn = ""
        sideEffects = ""; clinicalNotes = ""; patientNotes = ""
        drugsAdministered = ""
        isSaving = false
    }

    func populateForm(from s: TherapySession) {
        editingSession = s
        let df = DateFormatter(); df.dateFormat = "yyyy-MM-dd"
        scheduledDate = df.date(from: String(s.scheduledDate.prefix(10))) ?? Date()
        status = s.status; dayOfWeek = s.dayOfWeek ?? ""
        dialysisAccessType = s.dialysisAccessType ?? "AV Fistula"
        facilityName = s.facilityName ?? ""; attendingPhysician = s.attendingPhysician ?? ""
        rnReviewer = s.rnReviewer ?? ""
        dryWeightKg = s.dryWeightKg.map { String($0) } ?? ""
        previousPostWeightKg = s.previousPostWeightKg.map { String($0) } ?? ""
        preDialysisWeightKg = s.preDialysisWeightKg.map { String($0) } ?? ""
        postDialysisWeightKg = s.postDialysisWeightKg.map { String($0) } ?? ""
        fluidRemovedMl = s.fluidRemovedMl.map { String(Int($0)) } ?? ""
        fluidToRemoveKg = s.fluidToRemoveKg.map { String($0) } ?? ""
        bloodFlowRate = s.bloodFlowRate.map { String(Int($0)) } ?? ""
        dialysateFlowRate = s.dialysateFlowRate.map { String(Int($0)) } ?? ""
        durationMinutes = s.durationMinutes.map { String($0) } ?? ""
        startClock = Self.clock(of: s.actualStartTime)
        endClock = Self.clock(of: s.actualEndTime)
        readingRows = (s.intradialyticReadings ?? []).map(EditableReading.init(from:))
        removedReadingIds = []
        dialysateVolumeLiters = s.dialysateVolumeLiters.map { String($0) } ?? ""
        dialysateLactateMeq = s.dialysateLactateMeq.map { String($0) } ?? ""
        dialysatePotassiumMeq = s.dialysatePotassiumMeq.map { String($0) } ?? ""
        sakNumber = s.sakNumber.map { String($0) } ?? ""
        needleGauge = s.needleGauge ?? "15G"
        needleLength = s.needleLength.map { String($0) } ?? ""
        buttonholeTechnique = s.buttonholeTechnique ?? false
        preSystolicBp = s.preSystolicBp.map { String($0) } ?? ""
        preDiastolicBp = s.preDiastolicBp.map { String($0) } ?? ""
        preHeartRate = s.preHeartRate.map { String($0) } ?? ""
        preTemperature = s.preTemperature.map { String($0) } ?? ""
        postSystolicBp = s.postSystolicBp.map { String($0) } ?? ""
        postDiastolicBp = s.postDiastolicBp.map { String($0) } ?? ""
        postHeartRate = s.postHeartRate.map { String($0) } ?? ""
        postTemperature = s.postTemperature.map { String($0) } ?? ""
        oxygenSaturation = s.oxygenSaturation.map { String($0) } ?? ""
        preStandingSystolicBp = s.preStandingSystolicBp.map { String($0) } ?? ""
        preStandingDiastolicBp = s.preStandingDiastolicBp.map { String($0) } ?? ""
        preStandingHeartRate = s.preStandingHeartRate.map { String($0) } ?? ""
        postStandingSystolicBp = s.postStandingSystolicBp.map { String($0) } ?? ""
        postStandingDiastolicBp = s.postStandingDiastolicBp.map { String($0) } ?? ""
        postStandingHeartRate = s.postStandingHeartRate.map { String($0) } ?? ""
        preShortnessOfBreath = s.preShortnessOfBreath ?? false
        preSwelling = s.preSwelling ?? false; preChangeInMobility = s.preChangeInMobility ?? false
        preDigestionProblems = s.preDigestionProblems ?? false
        preHospErSinceLast = s.preHospErSinceLast ?? false
        accessThrillBruit = s.accessThrillBruit ?? true
        accessRednessDrainage = s.accessRednessDrainage ?? false
        cartridgeLot = s.cartridgeLot ?? ""; sakLot = s.sakLot ?? ""
        cyclerNumber = s.cyclerNumber ?? ""; warmerSerial = s.warmerSerial ?? ""
        totalDialysateLiters = s.totalDialysateLiters.map { String($0) } ?? ""
        totalUfLiters = s.totalUfLiters.map { String($0) } ?? ""
        totalBloodVolumeProcessed = s.totalBloodVolumeProcessed.map { String($0) } ?? ""
        dialyzerAppearance = s.dialyzerAppearance ?? ""
        postBleedingStopTime = s.postBleedingStopTime ?? ""
        postBruising = s.postBruising ?? false; postInfiltration = s.postInfiltration ?? false
        postShortnessOfBreath = s.postShortnessOfBreath ?? false
        postSwelling = s.postSwelling ?? false; postDigestionProblems = s.postDigestionProblems ?? false
        postAccessThrillBruit = s.postAccessThrillBruit ?? true
        purificationPakChange = s.purificationPakChange ?? false
        airFilterCleaned = s.airFilterCleaned ?? false
        wasteLineBleachDisinfection = s.wasteLineBleachDisinfection ?? false
        alarmTestCompleted = s.alarmTestCompleted ?? false
        sakUseNumber = s.sakUseNumber.map { String($0) } ?? ""
        totalChloramineLevel = s.totalChloramineLevel.map { String($0) } ?? ""
        labTubesDrawn = s.labTubesDrawn ?? ""
        sideEffects = s.sideEffects ?? ""; clinicalNotes = s.clinicalNotes ?? ""
        drugsAdministered = s.drugsAdministered ?? ""
        patientNotes = s.patientNotes ?? ""
    }

    /// Writes the grid: existing rows are UPDATED, new rows created, rows the
    /// user deleted removed.
    ///
    /// Re-POSTing an existing row is what made editing a session grow its
    /// flowsheet on web — the corrected row differs from the stored one, so it
    /// landed as an extra reading. And a deleted row that is never DELETEd
    /// simply reappears on the next load.
    private func saveReadings(sessionId: Int) async throws {
        for id in removedReadingIds {
            try await APIClient.shared.delete("/chronic/readings/\(id)")
        }
        removedReadingIds = []

        for row in readingRows where !row.isBlank {
            let payload = row.payload(sessionId: sessionId)
            if let serverId = row.serverId {
                let _: IntradialyticReading = try await APIClient.shared.put(
                    "/chronic/readings/\(serverId)", body: payload)
            } else {
                let _: IntradialyticReading = try await APIClient.shared.post(
                    "/chronic/therapy-sessions/\(sessionId)/readings", body: payload)
            }
        }
    }

    func submit() async {
        isSaving = true
        let df = DateFormatter(); df.dateFormat = "yyyy-MM-dd"

        var body = TherapySessionCreate(
            therapyType: "HEMODIALYSIS",
            scheduledDate: df.string(from: scheduledDate),
            status: status
        )
        body.dialysisAccessType = dialysisAccessType
        if !dayOfWeek.isEmpty { body.dayOfWeek = dayOfWeek }
        if !facilityName.isEmpty { body.facilityName = facilityName }
        if !attendingPhysician.isEmpty { body.attendingPhysician = attendingPhysician }
        if !rnReviewer.isEmpty { body.rnReviewer = rnReviewer }
        body.dryWeightKg = Double(dryWeightKg)
        body.previousPostWeightKg = Double(previousPostWeightKg)
        body.preDialysisWeightKg = Double(preDialysisWeightKg)
        body.postDialysisWeightKg = Double(postDialysisWeightKg)
        body.fluidRemovedMl = Double(fluidRemovedMl)
        body.fluidToRemoveKg = Double(fluidToRemoveKg)
        body.bloodFlowRate = Double(bloodFlowRate)
        body.dialysateFlowRate = Double(dialysateFlowRate)
        body.durationMinutes = Int(durationMinutes)
        let day = df.string(from: scheduledDate).prefix(10)
        body.actualStartTime = Self.iso(day: String(day), clock: startClock)
        body.actualEndTime = Self.iso(day: String(day), clock: endClock)
        body.dialysateVolumeLiters = Double(dialysateVolumeLiters)
        body.dialysateLactateMeq = Double(dialysateLactateMeq)
        body.dialysatePotassiumMeq = Double(dialysatePotassiumMeq)
        body.sakNumber = Int(sakNumber)
        if !needleGauge.isEmpty { body.needleGauge = needleGauge }
        body.needleLength = Double(needleLength)
        body.buttonholeTechnique = buttonholeTechnique
        body.preSystolicBp = Int(preSystolicBp); body.preDiastolicBp = Int(preDiastolicBp)
        body.preHeartRate = Int(preHeartRate); body.preTemperature = Double(preTemperature)
        body.postSystolicBp = Int(postSystolicBp); body.postDiastolicBp = Int(postDiastolicBp)
        body.postHeartRate = Int(postHeartRate); body.postTemperature = Double(postTemperature)
        body.oxygenSaturation = Int(oxygenSaturation)
        body.preStandingSystolicBp = Int(preStandingSystolicBp)
        body.preStandingDiastolicBp = Int(preStandingDiastolicBp)
        body.preStandingHeartRate = Int(preStandingHeartRate)
        body.postStandingSystolicBp = Int(postStandingSystolicBp)
        body.postStandingDiastolicBp = Int(postStandingDiastolicBp)
        body.postStandingHeartRate = Int(postStandingHeartRate)
        body.preShortnessOfBreath = preShortnessOfBreath
        body.preSwelling = preSwelling; body.preChangeInMobility = preChangeInMobility
        body.preDigestionProblems = preDigestionProblems
        body.preHospErSinceLast = preHospErSinceLast
        body.accessThrillBruit = accessThrillBruit
        body.accessRednessDrainage = accessRednessDrainage
        if !cartridgeLot.isEmpty { body.cartridgeLot = cartridgeLot }
        if !sakLot.isEmpty { body.sakLot = sakLot }
        if !cyclerNumber.isEmpty { body.cyclerNumber = cyclerNumber }
        if !warmerSerial.isEmpty { body.warmerSerial = warmerSerial }
        body.totalDialysateLiters = Double(totalDialysateLiters)
        body.totalUfLiters = Double(totalUfLiters)
        body.totalBloodVolumeProcessed = Double(totalBloodVolumeProcessed)
        if !dialyzerAppearance.isEmpty { body.dialyzerAppearance = dialyzerAppearance }
        if !postBleedingStopTime.isEmpty { body.postBleedingStopTime = postBleedingStopTime }
        body.postBruising = postBruising; body.postInfiltration = postInfiltration
        body.postShortnessOfBreath = postShortnessOfBreath
        body.postSwelling = postSwelling; body.postDigestionProblems = postDigestionProblems
        body.postAccessThrillBruit = postAccessThrillBruit
        body.purificationPakChange = purificationPakChange
        body.airFilterCleaned = airFilterCleaned
        body.wasteLineBleachDisinfection = wasteLineBleachDisinfection
        body.alarmTestCompleted = alarmTestCompleted
        body.sakUseNumber = Int(sakUseNumber); body.totalChloramineLevel = Double(totalChloramineLevel)
        if !labTubesDrawn.isEmpty { body.labTubesDrawn = labTubesDrawn }
        if !sideEffects.isEmpty { body.sideEffects = sideEffects }
        if !drugsAdministered.isEmpty { body.drugsAdministered = drugsAdministered }
        if !clinicalNotes.isEmpty { body.clinicalNotes = clinicalNotes }
        if !patientNotes.isEmpty { body.patientNotes = patientNotes }

        do {
            let sessionId: Int
            if let editing = editingSession {
                let _: TherapySession = try await APIClient.shared.put("/chronic/therapy-sessions/\(editing.id)", body: body)
                sessionId = editing.id
            } else {
                let created: TherapySession = try await APIClient.shared.post("/chronic/therapy-sessions", body: body)
                sessionId = created.id
            }
            try await saveReadings(sessionId: sessionId)
            resetForm(); showAddSheet = false
            await load(); await loadSummary()
        } catch { errorMessage = error.localizedDescription }
        isSaving = false
    }
}

// MARK: - View

struct HemodialysisView: View {
    @State private var vm = HemodialysisViewModel()
    @State private var expandedId: Int?

    var body: some View {
        Group {
            if vm.isLoading {
                ProgressView("Loading…")
            } else {
                sessionList
            }
        }
        .navigationTitle("Hemodialysis")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                        vm.resetForm()
                        vm.showAddSheet = true
                        Task { await vm.loadDefaults() }
                    } label: { Image(systemName: "plus") }
            }
        }
        .task { await vm.load(); await vm.loadSummary() }
        .refreshable { await vm.load(); await vm.loadSummary() }
        .sheet(isPresented: $vm.showAddSheet) { addSessionSheet }
        .alert("Error", isPresented: .constant(vm.errorMessage != nil)) {
            Button("OK") { vm.errorMessage = nil }
        } message: { Text(vm.errorMessage ?? "") }
    }

    // MARK: - Session List

    private var sessionList: some View {
        List {
            if let s = vm.summary, s.totalSessions > 0 {
                Section("Summary (\(periodLabel))") {
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                        HDStatCard(title: "Sessions", value: "\(s.totalSessions)", color: .blue)
                        HDStatCard(title: "Avg Pre Wt", value: s.avgPreWeightKg.map { String(format: "%.1f kg", $0) } ?? "—", color: .green)
                        HDStatCard(title: "Avg Post Wt", value: s.avgPostWeightKg.map { String(format: "%.1f kg", $0) } ?? "—", color: .green)
                        HDStatCard(title: "Avg UF", value: s.avgFluidRemovedMl.map { "\(Int($0)) mL" } ?? "—", color: .orange)
                        HDStatCard(title: "Avg Duration", value: s.avgDurationMin.map { "\(Int($0)) min" } ?? "—", color: .purple)
                        HDStatCard(title: "w/ Readings", value: s.sessionsWithReadings.map { "\($0)" } ?? "—", color: .blue)
                    }
                }
            }

            Section {
                Picker("Period", selection: $vm.periodDays) {
                    Text("30d").tag(30); Text("90d").tag(90); Text("180d").tag(180)
                    Text("1y").tag(365); Text("All").tag(3650)
                }
                .pickerStyle(.segmented)
                .onChange(of: vm.periodDays) { _, _ in Task { await vm.load(); await vm.loadSummary() } }
            }

            if vm.sessions.isEmpty {
                Section {
                    ContentUnavailableView("No Sessions", systemImage: "waveform.path.ecg",
                        description: Text("No hemodialysis sessions in this period."))
                }
            } else {
                Section("\(vm.sessions.count) Sessions") {
                    ForEach(vm.sessions) { session in
                        sessionCard(session)
                    }
                    .onDelete { indexSet in
                        Task { for i in indexSet { await vm.deleteSession(id: vm.sessions[i].id) } }
                    }
                }
            }
        }
    }

    private var periodLabel: String {
        switch vm.periodDays {
        case 30: return "30 days"; case 90: return "90 days"; case 180: return "180 days"
        case 365: return "1 year"; default: return "All time"
        }
    }

    // MARK: - Session Card

    private func sessionCard(_ s: TherapySession) -> some View {
        let isExpanded = expandedId == s.id
        let readings = s.intradialyticReadings ?? []

        return VStack(alignment: .leading, spacing: 8) {
            HStack {
                VStack(alignment: .leading) {
                    HStack(spacing: 6) {
                        Text(formatDate(s.scheduledDate)).font(.headline)
                        if let dow = s.dayOfWeek, !dow.isEmpty {
                            Text(dow).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    if let dur = s.durationMinutes {
                        Text("\(dur) min").font(.caption).foregroundStyle(.secondary)
                    }
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 4) {
                    Text(s.status.replacingOccurrences(of: "_", with: " ").capitalized)
                        .font(.caption).bold()
                        .padding(.horizontal, 10).padding(.vertical, 3)
                        .background(statusColor(s.status).opacity(0.15))
                        .foregroundStyle(statusColor(s.status))
                        .clipShape(Capsule())
                    if let fs = s.flowsheetStatus, !fs.isEmpty {
                        Text("FS: \(fs.uppercased())")
                            .font(.system(size: 10)).bold()
                            .padding(.horizontal, 8).padding(.vertical, 2)
                            .background(flowsheetColor(fs).opacity(0.15))
                            .foregroundStyle(flowsheetColor(fs))
                            .clipShape(Capsule())
                    }
                }
            }

            Divider()

            HStack(spacing: 14) {
                HDInfoPill(label: "Access", value: s.dialysisAccessType ?? "—")
                HDInfoPill(label: "Pre Wt", value: fmtKg(s.preDialysisWeightKg))
                HDInfoPill(label: "Post Wt", value: fmtKg(s.postDialysisWeightKg))
                if let fr = s.fluidRemovedMl { HDInfoPill(label: "UF", value: "\(Int(fr)) mL") }
            }

            if s.preSystolicBp != nil || s.postSystolicBp != nil {
                HStack(spacing: 14) {
                    HDInfoPill(label: "Pre BP", value: fmtBP(s.preSystolicBp, s.preDiastolicBp))
                    HDInfoPill(label: "Post BP", value: fmtBP(s.postSystolicBp, s.postDiastolicBp))
                    if let hr = s.preHeartRate { HDInfoPill(label: "HR", value: "\(hr)") }
                }
            }

            if !readings.isEmpty {
                Text("\(readings.count) intradialytic readings")
                    .font(.caption2).foregroundStyle(.blue).bold()
            }

            if isExpanded {
                Divider()

                if s.preStandingSystolicBp != nil || s.postStandingSystolicBp != nil {
                    HStack(spacing: 14) {
                        HDInfoPill(label: "Pre Stand BP", value: fmtBP(s.preStandingSystolicBp, s.preStandingDiastolicBp))
                        HDInfoPill(label: "Post Stand BP", value: fmtBP(s.postStandingSystolicBp, s.postStandingDiastolicBp))
                    }
                }

                if s.dialysateVolumeLiters != nil || s.bloodFlowRate != nil {
                    HStack(spacing: 14) {
                        if let bfr = s.bloodFlowRate { HDInfoPill(label: "BFR", value: "\(Int(bfr))") }
                        if let dfr = s.dialysateFlowRate { HDInfoPill(label: "DFR", value: "\(Int(dfr))") }
                        if let v = s.dialysateVolumeLiters { HDInfoPill(label: "Dialysate", value: "\(v) L") }
                    }
                }

                if s.totalDialysateLiters != nil || s.totalUfLiters != nil {
                    HStack(spacing: 14) {
                        if let v = s.totalDialysateLiters { HDInfoPill(label: "Total Dial", value: "\(v) L") }
                        if let v = s.totalUfLiters { HDInfoPill(label: "Total UF", value: "\(v) L") }
                        if let v = s.totalBloodVolumeProcessed { HDInfoPill(label: "Blood Vol", value: "\(v) L") }
                    }
                }

                if !readings.isEmpty {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Intradialytic Readings").font(.caption).bold().foregroundStyle(.blue)
                        ForEach(Array(readings.enumerated()), id: \.offset) { idx, r in
                            HStack(spacing: 8) {
                                Text(fmtTime(r.readingTime ?? "")).font(.caption2).bold().frame(width: 44, alignment: .leading)
                                Text("BP \(fmtBP(r.systolicBp, r.diastolicBp))").font(.caption2).frame(width: 70, alignment: .leading)
                                if let p = r.pulse { Text("P \(p)").font(.caption2).frame(width: 30, alignment: .leading) }
                                if let bfr = r.bloodFlowRate { Text("BFR \(Int(bfr))").font(.caption2) }
                                if let uf = r.ufVolumeRemoved { Text("UF \(Int(uf))").font(.caption2) }
                            }
                            .padding(.vertical, 1)
                            if idx < readings.count - 1 { Divider() }
                        }
                    }
                    .padding(8)
                    .background(Color.blue.opacity(0.05))
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                }

                if let se = s.sideEffects, !se.isEmpty {
                    Label(se, systemImage: "exclamationmark.triangle").font(.caption).foregroundStyle(.red)
                }
                if let cn = s.clinicalNotes, !cn.isEmpty {
                    Text(cn).font(.caption).foregroundStyle(.secondary).lineLimit(3)
                }
                if let fac = s.facilityName, !fac.isEmpty {
                    Label(fac, systemImage: "mappin").font(.caption2).foregroundStyle(.secondary)
                }

                Button {
                    vm.populateForm(from: s); vm.showAddSheet = true
                } label: {
                    Label("Edit Session", systemImage: "pencil").font(.caption).bold()
                }
                .buttonStyle(.bordered).tint(.blue).padding(.top, 4)

                // ── Flowsheet Lifecycle Actions ──────────────────────────
                Divider().padding(.top, 6)
                Text("Flowsheet").font(.caption).bold().foregroundStyle(.primary)

                let fsStatus = FlowsheetStatus(rawValue: s.flowsheetStatus ?? "")
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        if fsStatus == nil || fsStatus == .draft {
                            Button("Submit") { Task { await vm.submitFlowsheet(id: s.id) } }
                                .buttonStyle(.borderedProminent).controlSize(.small)
                        }
                        if fsStatus == .submitted {
                            Button("Sign") { Task { await vm.signFlowsheet(id: s.id) } }
                                .buttonStyle(.borderedProminent).controlSize(.small)
                        }
                        if fsStatus == .signed {
                            Button("Countersign") { Task { await vm.countersignFlowsheet(id: s.id) } }
                                .buttonStyle(.borderedProminent).controlSize(.small)
                        }
                        if fsStatus == .countersigned {
                            Button("Review") { Task { await vm.reviewFlowsheet(id: s.id) } }
                                .buttonStyle(.borderedProminent).controlSize(.small)
                        }
                        if fsStatus == .reviewed {
                            Button("Lock") { Task { await vm.lockFlowsheet(id: s.id) } }
                                .buttonStyle(.borderedProminent).controlSize(.small)
                        }
                        if fsStatus == .locked {
                            Label("Locked", systemImage: "lock.fill")
                                .font(.caption).bold().foregroundStyle(.green)
                        }
                    }
                }

                // ── Clinical Notes ───────────────────────────────────────
                if let notes = s.clinicalNotesList, !notes.isEmpty {
                    Text("Clinical Notes (\(notes.count))").font(.caption).bold().foregroundStyle(.blue)
                    ForEach(notes, id: \.id) { note in
                        VStack(alignment: .leading, spacing: 2) {
                            HStack {
                                Text(note.noteType).font(.caption2).bold()
                                Spacer()
                                Text(AppDate.dateTime(note.createdAt)).font(.system(size: 9)).foregroundStyle(.secondary)
                            }
                            Text(note.noteText).font(.caption).lineLimit(3)
                        }
                        .padding(8)
                        .background(Color.blue.opacity(0.05))
                        .clipShape(RoundedRectangle(cornerRadius: 6))
                    }
                }
            }
        }
        .padding(.vertical, 4)
        .contentShape(Rectangle())
        .onTapGesture { withAnimation { expandedId = isExpanded ? nil : s.id } }
    }

    // MARK: - Add/Edit Sheet

    private var addSessionSheet: some View {
        NavigationStack {
            Form {
                Section("Session Info") {
                    DatePicker("Date", selection: $vm.scheduledDate, displayedComponents: .date)
                    Picker("Status", selection: $vm.status) {
                        ForEach(HemodialysisViewModel.statusOptions, id: \.self) { Text($0.replacingOccurrences(of: "_", with: " ").capitalized) }
                    }
                    Picker("Day of Week", selection: $vm.dayOfWeek) {
                        Text("—").tag("")
                        ForEach(HemodialysisViewModel.daysOfWeek, id: \.self) { Text($0) }
                    }
                    HStack {
                        VStack(alignment: .leading) {
                            Text("Start Time").font(.caption)
                            TextField("08:00", text: $vm.startClock)
                                .onChange(of: vm.startClock) { _, _ in vm.deriveDuration() }
                        }
                        VStack(alignment: .leading) {
                            Text("End Time").font(.caption)
                            TextField("11:30", text: $vm.endClock)
                                .onChange(of: vm.endClock) { _, _ in vm.deriveDuration() }
                        }
                        VStack(alignment: .leading) { Text("Duration (min)").font(.caption); TextField("240", text: $vm.durationMinutes).keyboardType(.numberPad) }
                    }
                }

                // The grid a patient records DURING treatment. iOS could show
                // these and never capture one — the model existed and nothing
                // called the endpoint.
                Section("Intradialytic Readings") {
                    IntradialyticEditor(rows: $vm.readingRows, removedIds: $vm.removedReadingIds)
                }

                Section("Vascular Access") {
                    Picker("Access Type", selection: $vm.dialysisAccessType) {
                        ForEach(HemodialysisViewModel.accessTypes, id: \.self) { Text($0) }
                    }
                    Picker("Needle Gauge", selection: $vm.needleGauge) {
                        ForEach(HemodialysisViewModel.needleGauges, id: \.self) { Text($0) }
                    }
                    .disabled(vm.isCatheterAccess)
                    HStack {
                        VStack(alignment: .leading) { Text("Needle Length (mm)").font(.caption); TextField("mm", text: $vm.needleLength).keyboardType(.decimalPad) }
                    }
                    Toggle("Buttonhole Technique", isOn: $vm.buttonholeTechnique)
                        .disabled(vm.isCatheterAccess)
                }

                Section("Weights (kg)") {
                    HStack {
                        VStack(alignment: .leading) { Text("Dry").font(.caption); TextField("kg", text: $vm.dryWeightKg).keyboardType(.decimalPad) }
                        VStack(alignment: .leading) { Text("Prev Post").font(.caption); TextField("kg", text: $vm.previousPostWeightKg).keyboardType(.decimalPad) }
                    }
                    HStack {
                        VStack(alignment: .leading) { Text("Pre").font(.caption); TextField("kg", text: $vm.preDialysisWeightKg).keyboardType(.decimalPad) }
                        VStack(alignment: .leading) { Text("Post").font(.caption); TextField("kg", text: $vm.postDialysisWeightKg).keyboardType(.decimalPad) }
                    }
                    HStack {
                        VStack(alignment: .leading) { Text("To Remove (kg)").font(.caption); TextField("kg", text: $vm.fluidToRemoveKg).keyboardType(.decimalPad) }
                        VStack(alignment: .leading) { Text("Removed (mL)").font(.caption); TextField("mL", text: $vm.fluidRemovedMl).keyboardType(.decimalPad) }
                    }
                }

                Section("Dialysate Prescription") {
                    HStack {
                        VStack(alignment: .leading) { Text("BFR (mL/min)").font(.caption); TextField("300", text: $vm.bloodFlowRate).keyboardType(.decimalPad) }
                        VStack(alignment: .leading) { Text("DFR (mL/min)").font(.caption); TextField("500", text: $vm.dialysateFlowRate).keyboardType(.decimalPad) }
                    }
                    HStack {
                        VStack(alignment: .leading) { Text("Volume (L)").font(.caption); TextField("L", text: $vm.dialysateVolumeLiters).keyboardType(.decimalPad) }
                        VStack(alignment: .leading) { Text("SAK #").font(.caption); TextField("#", text: $vm.sakNumber).keyboardType(.numberPad) }
                    }
                    HStack {
                        VStack(alignment: .leading) { Text("Lactate (mEq)").font(.caption); TextField("mEq", text: $vm.dialysateLactateMeq).keyboardType(.decimalPad) }
                        VStack(alignment: .leading) { Text("K⁺ (mEq)").font(.caption); TextField("mEq", text: $vm.dialysatePotassiumMeq).keyboardType(.decimalPad) }
                    }
                    HStack {
                        VStack(alignment: .leading) { Text("SpO₂ (%)").font(.caption); TextField("%", text: $vm.oxygenSaturation).keyboardType(.numberPad) }
                    }
                }

                Section("Pre-Treatment Vitals") {
                    HStack {
                        VStack(alignment: .leading) { Text("Sitting Sys").font(.caption); TextField("mmHg", text: $vm.preSystolicBp).keyboardType(.numberPad) }
                        VStack(alignment: .leading) { Text("Sitting Dia").font(.caption); TextField("mmHg", text: $vm.preDiastolicBp).keyboardType(.numberPad) }
                    }
                    HStack {
                        VStack(alignment: .leading) { Text("HR").font(.caption); TextField("bpm", text: $vm.preHeartRate).keyboardType(.numberPad) }
                        VStack(alignment: .leading) { Text("Temp (°F)").font(.caption); TextField("°F", text: $vm.preTemperature).keyboardType(.decimalPad) }
                    }
                    HStack {
                        VStack(alignment: .leading) { Text("Stand Sys").font(.caption); TextField("mmHg", text: $vm.preStandingSystolicBp).keyboardType(.numberPad) }
                        VStack(alignment: .leading) { Text("Stand Dia").font(.caption); TextField("mmHg", text: $vm.preStandingDiastolicBp).keyboardType(.numberPad) }
                        VStack(alignment: .leading) { Text("Stand HR").font(.caption); TextField("bpm", text: $vm.preStandingHeartRate).keyboardType(.numberPad) }
                    }
                }

                Section("Pre-Treatment Assessment") {
                    Toggle("Shortness of Breath", isOn: $vm.preShortnessOfBreath)
                    Toggle("Swelling / Edema", isOn: $vm.preSwelling)
                    Toggle("Change in Mobility", isOn: $vm.preChangeInMobility)
                    Toggle("Digestion Problems", isOn: $vm.preDigestionProblems)
                    Toggle("Hospital/ER Since Last", isOn: $vm.preHospErSinceLast)
                    Toggle("Access Thrill/Bruit ✓", isOn: $vm.accessThrillBruit)
                    Toggle("Access Redness/Drainage", isOn: $vm.accessRednessDrainage)
                }

                Section("Post-Treatment Vitals") {
                    HStack {
                        VStack(alignment: .leading) { Text("Sitting Sys").font(.caption); TextField("mmHg", text: $vm.postSystolicBp).keyboardType(.numberPad) }
                        VStack(alignment: .leading) { Text("Sitting Dia").font(.caption); TextField("mmHg", text: $vm.postDiastolicBp).keyboardType(.numberPad) }
                    }
                    HStack {
                        VStack(alignment: .leading) { Text("HR").font(.caption); TextField("bpm", text: $vm.postHeartRate).keyboardType(.numberPad) }
                        VStack(alignment: .leading) { Text("Temp (°F)").font(.caption); TextField("°F", text: $vm.postTemperature).keyboardType(.decimalPad) }
                    }
                    HStack {
                        VStack(alignment: .leading) { Text("Stand Sys").font(.caption); TextField("mmHg", text: $vm.postStandingSystolicBp).keyboardType(.numberPad) }
                        VStack(alignment: .leading) { Text("Stand Dia").font(.caption); TextField("mmHg", text: $vm.postStandingDiastolicBp).keyboardType(.numberPad) }
                        VStack(alignment: .leading) { Text("Stand HR").font(.caption); TextField("bpm", text: $vm.postStandingHeartRate).keyboardType(.numberPad) }
                    }
                }

                Section("Post-Treatment Totals") {
                    HStack {
                        VStack(alignment: .leading) { Text("Total Dial (L)").font(.caption); TextField("L", text: $vm.totalDialysateLiters).keyboardType(.decimalPad) }
                        VStack(alignment: .leading) { Text("Total UF (L)").font(.caption); TextField("L", text: $vm.totalUfLiters).keyboardType(.decimalPad) }
                    }
                    HStack {
                        VStack(alignment: .leading) { Text("Blood Vol (L)").font(.caption); TextField("L", text: $vm.totalBloodVolumeProcessed).keyboardType(.decimalPad) }
                        VStack(alignment: .leading) { Text("Dialyzer").font(.caption); TextField("Appearance", text: $vm.dialyzerAppearance) }
                    }
                    VStack(alignment: .leading) { Text("Bleed Stop Time").font(.caption); TextField("Time", text: $vm.postBleedingStopTime) }
                    Toggle("Bruising", isOn: $vm.postBruising)
                    Toggle("Infiltration", isOn: $vm.postInfiltration)
                    Toggle("SOB", isOn: $vm.postShortnessOfBreath)
                    Toggle("Swelling", isOn: $vm.postSwelling)
                    Toggle("GI Issues", isOn: $vm.postDigestionProblems)
                    Toggle("Access Thrill/Bruit ✓", isOn: $vm.postAccessThrillBruit)
                }

                Section("Equipment") {
                    HStack {
                        VStack(alignment: .leading) { Text("Cartridge Lot").font(.caption); TextField("Lot #", text: $vm.cartridgeLot) }
                        VStack(alignment: .leading) { Text("SAK Lot").font(.caption); TextField("Lot #", text: $vm.sakLot) }
                    }
                    HStack {
                        VStack(alignment: .leading) { Text("Cycler #").font(.caption); TextField("#", text: $vm.cyclerNumber) }
                        VStack(alignment: .leading) { Text("Warmer Serial").font(.caption); TextField("Serial", text: $vm.warmerSerial) }
                    }
                }

                Section("Machine Maintenance") {
                    Toggle("Purification Pak Change", isOn: $vm.purificationPakChange)
                    Toggle("Air Filter Cleaned", isOn: $vm.airFilterCleaned)
                    Toggle("Waste Line Bleach", isOn: $vm.wasteLineBleachDisinfection)
                    Toggle("Alarm Test Complete", isOn: $vm.alarmTestCompleted)
                    HStack {
                        VStack(alignment: .leading) { Text("SAK Use #").font(.caption); TextField("#", text: $vm.sakUseNumber).keyboardType(.numberPad) }
                        VStack(alignment: .leading) { Text("Chloramine (ppm)").font(.caption); TextField("ppm", text: $vm.totalChloramineLevel).keyboardType(.decimalPad) }
                    }
                    VStack(alignment: .leading) { Text("Lab Tubes Drawn").font(.caption); TextField("e.g. EDTA, SST", text: $vm.labTubesDrawn) }
                }

                Section("Facility & Staff") {
                    TextField("Facility Name", text: $vm.facilityName)
                    TextField("Physician", text: $vm.attendingPhysician)
                    TextField("RN Reviewer", text: $vm.rnReviewer)
                }

                // This screen had no drugs field at all; a decade of Epogene,
                // Venofer and Doxercalciferol arrived only by import (§3aa).
                Section("Drugs Given This Session") {
                    DrugsAdministeredEditor(text: $vm.drugsAdministered)
                }

                Section("Notes") {
                    TextField("Side Effects", text: $vm.sideEffects, axis: .vertical).lineLimit(2...4)
                    TextField("Clinical Notes", text: $vm.clinicalNotes, axis: .vertical).lineLimit(2...4)
                    TextField("Patient Notes", text: $vm.patientNotes, axis: .vertical).lineLimit(2...4)
                }
            }
            .navigationTitle(vm.editingSession != nil ? "Edit HD Session" : "New HD Session")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { vm.showAddSheet = false } }
                ToolbarItem(placement: .confirmationAction) {
                    Button(vm.editingSession != nil ? "Update" : "Save") { Task { await vm.submit() } }
                        .disabled(vm.isSaving)
                }
            }
        }
    }

    // MARK: - Helpers

    private func formatDate(_ s: String) -> String {
        let df = DateFormatter(); df.dateFormat = "yyyy-MM-dd"
        guard let date = df.date(from: String(s.prefix(10))) else { return s }
        df.dateStyle = .medium; return df.string(from: date)
    }

    private func fmtKg(_ v: Double?) -> String {
        guard let v else { return "—" }; return String(format: "%.1f kg", v)
    }

    private func fmtBP(_ s: Int?, _ d: Int?) -> String {
        guard let s, let d else { return "—" }; return "\(s)/\(d)"
    }

    private func fmtTime(_ t: String) -> String { String(t.prefix(5)) }

    private func statusColor(_ s: String) -> Color {
        switch s.lowercased() {
        case "completed": return .green; case "in_progress": return .blue
        case "scheduled": return .orange; case "cancelled": return .red
        default: return .secondary
        }
    }

    private func flowsheetColor(_ s: String) -> Color {
        switch s.lowercased() {
        case "draft": return .gray
        case "submitted": return .blue
        case "signed": return .teal
        case "countersigned": return .purple
        case "reviewed": return .orange
        case "locked": return .green
        default: return .secondary
        }
    }
}

// MARK: - Reusable subviews

private struct HDStatCard: View {
    let title: String; let value: String; let color: Color
    var body: some View {
        VStack(spacing: 2) {
            Text(value).font(.callout).bold().foregroundStyle(color)
            Text(title).font(.system(size: 10)).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity).padding(8)
        .background(color.opacity(0.08)).clipShape(RoundedRectangle(cornerRadius: 8))
    }
}

private struct HDInfoPill: View {
    let label: String; let value: String
    var body: some View {
        VStack(spacing: 2) {
            Text(label).font(.system(size: 10)).foregroundStyle(.secondary)
            Text(value).font(.caption).bold()
        }
    }
}
