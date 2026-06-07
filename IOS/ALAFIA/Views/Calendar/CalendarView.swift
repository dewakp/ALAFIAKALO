import SwiftUI

struct CalendarView: View {
    @State private var events: [CalendarEvent] = []
    @State private var viewDate = Date()
    @State private var selectedDate = Date()
    @State private var showForm = false
    @State private var editEvent: CalendarEvent?
    @State private var filterCategory = ""
    @State private var isLoading = false
    @State private var errorMessage = ""

    private var year: Int { Calendar.current.component(.year, from: viewDate) }
    private var month: Int { Calendar.current.component(.month, from: viewDate) }

    private var monthLabel: String {
        let df = DateFormatter()
        df.dateFormat = "MMMM yyyy"
        return df.string(from: viewDate)
    }

    private var selectedDateStr: String { Self.dateStr(selectedDate) }

    private var eventsOnDate: [CalendarEvent] {
        var filtered = events.filter { $0.eventDate == selectedDateStr }
        if !filterCategory.isEmpty { filtered = filtered.filter { $0.category == filterCategory } }
        return filtered
    }

    private var eventCountByDate: [String: Int] {
        var m: [String: Int] = [:]
        events.forEach { m[$0.eventDate, default: 0] += 1 }
        return m
    }

    static func dateStr(_ date: Date) -> String {
        let df = DateFormatter()
        df.dateFormat = "yyyy-MM-dd"
        return df.string(from: date)
    }

    var body: some View {
            ScrollView {
                VStack(spacing: 16) {
                    // Month nav
                    monthNavigator
                    // Calendar grid
                    calendarGrid
                    // Category filters
                    categoryFilters
                    // Day header
                    dayHeader
                    // Events list
                    eventsList
                }
                .padding()
            }
            .navigationTitle("Calendar")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { openCreate() } label: {
                        Image(systemName: "plus.circle.fill")
                    }
                }
            }
            .sheet(isPresented: $showForm) {
                EventFormSheet(
                    editEvent: editEvent,
                    defaultDate: selectedDateStr,
                    onSave: { loadMonth() },
                    onDismiss: { showForm = false; editEvent = nil }
                )
            }
            .task { loadMonth() }
            .onChange(of: viewDate) { loadMonth() }
    }

    // MARK: - Subviews

    private var monthNavigator: some View {
        HStack {
            Button { changeMonth(-1) } label: { Image(systemName: "chevron.left") }
            Spacer()
            Text(monthLabel).font(.title2).fontWeight(.semibold)
            Spacer()
            Button { changeMonth(1) } label: { Image(systemName: "chevron.right") }
        }
        .padding(.horizontal, 4)
    }

    private var calendarGrid: some View {
        let grid = computeGrid()
        let todayStr = Self.dateStr(Date())
        let weekdays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

        return VStack(spacing: 4) {
            HStack {
                ForEach(weekdays, id: \.self) { d in
                    Text(d).font(.caption2).foregroundStyle(.secondary).frame(maxWidth: .infinity)
                }
            }
            ForEach(grid.indices, id: \.self) { wi in
                HStack(spacing: 0) {
                    ForEach(0..<7, id: \.self) { di in
                        let day = grid[wi][di]
                        if day > 0 {
                            let ds = dateStrForDay(day)
                            let isToday = ds == todayStr
                            let isSelected = ds == selectedDateStr
                            let count = eventCountByDate[ds] ?? 0
                            Button {
                                selectedDate = dateFromStr(ds)
                            } label: {
                                VStack(spacing: 2) {
                                    Text("\(day)")
                                        .font(.callout)
                                        .fontWeight(isToday ? .bold : .regular)
                                        .frame(width: 34, height: 34)
                                        .background(
                                            isSelected ? Color.green :
                                            isToday ? Color.green.opacity(0.2) :
                                            Color.clear
                                        )
                                        .foregroundStyle(isSelected ? .white : isToday ? .green : .primary)
                                        .clipShape(Circle())
                                    Circle()
                                        .fill(count > 0 ? Color.green : Color.clear)
                                        .frame(width: 5, height: 5)
                                }
                            }
                            .frame(maxWidth: .infinity)
                        } else {
                            Color.clear.frame(maxWidth: .infinity, minHeight: 40)
                        }
                    }
                }
            }
        }
        .padding(12)
        .background(Color(.systemGray6))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private var categoryFilters: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                filterChip(label: "All", key: "")
                ForEach(EventCategory.all, id: \.key) { cat in
                    filterChip(label: cat.label, key: cat.key, color: cat.swiftColor)
                }
            }
        }
    }

    private func filterChip(label: String, key: String, color: Color = .green) -> some View {
        let active = filterCategory == key
        return Button {
            filterCategory = active ? "" : key
        } label: {
            Text(label)
                .font(.caption)
                .fontWeight(.medium)
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(active ? color : Color(.systemGray5))
                .foregroundStyle(active ? .white : .primary)
                .clipShape(Capsule())
        }
    }

    private var dayHeader: some View {
        let df = DateFormatter()
        df.dateFormat = "EEEE, MMMM d"
        return HStack {
            Text(df.string(from: selectedDate)).font(.headline)
            Spacer()
            Text("\(eventsOnDate.count) event\(eventsOnDate.count == 1 ? "" : "s")")
                .font(.caption).foregroundStyle(.secondary)
        }
    }

    private var eventsList: some View {
        Group {
            if eventsOnDate.isEmpty {
                VStack(spacing: 8) {
                    Text("No events on this day")
                        .foregroundStyle(.secondary)
                    Button("Add Event") { openCreate() }
                        .buttonStyle(.borderedProminent)
                        .tint(.green)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 30)
            } else {
                ForEach(eventsOnDate) { ev in
                    EventCard(event: ev, onComplete: { completeEvent(ev.id) },
                              onEdit: { openEdit(ev) }, onDelete: { deleteEvent(ev.id) })
                }
            }
        }
    }

    // MARK: - Helpers

    private func changeMonth(_ delta: Int) {
        viewDate = Calendar.current.date(byAdding: .month, value: delta, to: viewDate) ?? viewDate
    }

    private func computeGrid() -> [[Int]] {
        let cal = Calendar.current
        let comps = cal.dateComponents([.year, .month], from: viewDate)
        let first = cal.date(from: comps)!
        let firstWeekday = cal.component(.weekday, from: first)
        let range = cal.range(of: .day, in: .month, for: first)!

        var rows: [[Int]] = []
        var day = 1 - (firstWeekday - 1)
        while day <= range.count {
            var week: [Int] = []
            for _ in 0..<7 {
                week.append(day >= 1 && day <= range.count ? day : 0)
                day += 1
            }
            rows.append(week)
        }
        return rows
    }

    private func dateStrForDay(_ day: Int) -> String {
        String(format: "%04d-%02d-%02d", year, month, day)
    }

    private func dateFromStr(_ str: String) -> Date {
        let df = DateFormatter()
        df.dateFormat = "yyyy-MM-dd"
        return df.date(from: str) ?? Date()
    }

    private func openCreate() {
        editEvent = nil
        showForm = true
    }

    private func openEdit(_ ev: CalendarEvent) {
        editEvent = ev
        showForm = true
    }

    // MARK: - API

    private func loadMonth() {
        Task {
            isLoading = true
            let daysInMonth = Calendar.current.range(of: .day, in: .month, for: viewDate)!.count
            let start = String(format: "%04d-%02d-01", year, month)
            let end = String(format: "%04d-%02d-%02d", year, month, daysInMonth)
            do {
                let result: [CalendarEvent] = try await APIClient.shared.get(
                    "/calendar/?start_date=\(start)&end_date=\(end)&limit=500"
                )
                await MainActor.run { events = result; isLoading = false }
            } catch {
                await MainActor.run { errorMessage = error.localizedDescription; isLoading = false }
            }
        }
    }

    private func completeEvent(_ id: Int) {
        Task {
            do {
                let _: CalendarEvent = try await APIClient.shared.patch(
                    "/calendar/\(id)/complete", body: EmptyBody()
                )
                loadMonth()
            } catch { }
        }
    }

    private func deleteEvent(_ id: Int) {
        Task {
            do {
                try await APIClient.shared.delete("/calendar/\(id)")
                loadMonth()
            } catch { }
        }
    }
}

// MARK: - Event Card

struct EventCard: View {
    let event: CalendarEvent
    let onComplete: () -> Void
    let onEdit: () -> Void
    let onDelete: () -> Void

    private var cat: EventCategory { EventCategory.find(event.category) }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            RoundedRectangle(cornerRadius: 3)
                .fill(cat.swiftColor)
                .frame(width: 4)

            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text(cat.label)
                        .font(.caption2).fontWeight(.semibold)
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(cat.swiftColor).foregroundStyle(.white)
                        .clipShape(Capsule())
                    if let p = event.priority {
                        Text(p)
                            .font(.caption2).fontWeight(.semibold)
                            .padding(.horizontal, 6).padding(.vertical, 2)
                            .background(p == "high" ? .red : p == "medium" ? .orange : .gray)
                            .foregroundStyle(.white).clipShape(Capsule())
                    }
                    if event.status != "scheduled" {
                        Text(event.status)
                            .font(.caption2).fontWeight(.semibold)
                            .padding(.horizontal, 6).padding(.vertical, 2)
                            .background(event.status == "completed" ? .green : .red)
                            .foregroundStyle(.white).clipShape(Capsule())
                    }
                }

                Text(event.title)
                    .font(.body).fontWeight(.semibold)
                    .strikethrough(event.status == "completed")

                if let desc = event.description, !desc.isEmpty {
                    Text(desc).font(.caption).foregroundStyle(.secondary)
                }

                HStack(spacing: 10) {
                    if event.allDay {
                        Label("All day", systemImage: "clock").font(.caption2).foregroundStyle(.secondary)
                    } else if let st = event.startTime {
                        let display = st.prefix(5) + (event.endTime.map { " – " + $0.prefix(5) } ?? "")
                        Label(display, systemImage: "clock").font(.caption2).foregroundStyle(.secondary)
                    }
                    if let loc = event.location, !loc.isEmpty {
                        Label(loc, systemImage: "mappin").font(.caption2).foregroundStyle(.secondary)
                    }
                    if let r = event.recurrence {
                        Label(r, systemImage: "repeat").font(.caption2).foregroundStyle(.secondary)
                    }
                }

                if let n = event.notes, !n.isEmpty {
                    Text(n).font(.caption).italic().foregroundStyle(.secondary).padding(.top, 2)
                }
            }

            Spacer()

            VStack(spacing: 6) {
                if event.status == "scheduled" {
                    Button { onComplete() } label: {
                        Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
                    }
                }
                Button { onEdit() } label: {
                    Image(systemName: "pencil.circle.fill").foregroundStyle(.blue)
                }
                Button { onDelete() } label: {
                    Image(systemName: "trash.circle.fill").foregroundStyle(.red)
                }
            }
            .font(.title3)
        }
        .padding()
        .background(Color(.systemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .shadow(color: .black.opacity(0.06), radius: 4, y: 2)
        .opacity(event.status == "cancelled" ? 0.5 : 1)
    }
}

// MARK: - Event Form Sheet

struct EventFormSheet: View {
    let editEvent: CalendarEvent?
    let defaultDate: String
    let onSave: () -> Void
    let onDismiss: () -> Void

    @State private var title = ""
    @State private var desc = ""
    @State private var category = "appointment"
    @State private var eventDate = Date()
    @State private var startTime = Date()
    @State private var endTime = Date()
    @State private var hasStartTime = false
    @State private var hasEndTime = false
    @State private var allDay = false
    @State private var recurrence = "none"
    @State private var recurrenceEnd = Date()
    @State private var hasRecurrenceEnd = false
    @State private var location = ""
    @State private var priority = ""
    @State private var notes = ""
    @State private var reminderMin = ""
    @State private var saving = false
    @State private var errMsg = ""

    private var isEdit: Bool { editEvent != nil }
    private let df: DateFormatter = {
        let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"; return f
    }()
    private let tf: DateFormatter = {
        let f = DateFormatter(); f.dateFormat = "HH:mm:ss"; return f
    }()
    private let tfShort: DateFormatter = {
        let f = DateFormatter(); f.dateFormat = "HH:mm"; return f
    }()

    var body: some View {
        NavigationStack {
            Form {
                Section("Details") {
                    TextField("Title", text: $title)
                    Picker("Category", selection: $category) {
                        ForEach(EventCategory.all, id: \.key) { c in
                            Text(c.label).tag(c.key)
                        }
                    }
                    TextField("Description", text: $desc, axis: .vertical)
                        .lineLimit(2...4)
                }

                Section("Date & Time") {
                    DatePicker("Date", selection: $eventDate, displayedComponents: .date)
                    Toggle("All Day", isOn: $allDay)
                    if !allDay {
                        Toggle("Set Start Time", isOn: $hasStartTime)
                        if hasStartTime {
                            DatePicker("Start", selection: $startTime, displayedComponents: .hourAndMinute)
                        }
                        Toggle("Set End Time", isOn: $hasEndTime)
                        if hasEndTime {
                            DatePicker("End", selection: $endTime, displayedComponents: .hourAndMinute)
                        }
                    }
                }

                Section("Recurrence") {
                    Picker("Repeat", selection: $recurrence) {
                        Text("No repeat").tag("none")
                        Text("Daily").tag("daily")
                        Text("Weekly").tag("weekly")
                        Text("Biweekly").tag("biweekly")
                        Text("Monthly").tag("monthly")
                        Text("Yearly").tag("yearly")
                    }
                    if recurrence != "none" {
                        Toggle("Set End Date", isOn: $hasRecurrenceEnd)
                        if hasRecurrenceEnd {
                            DatePicker("Until", selection: $recurrenceEnd, displayedComponents: .date)
                        }
                    }
                }

                Section("Additional") {
                    TextField("Location", text: $location)
                    Picker("Priority", selection: $priority) {
                        Text("None").tag("")
                        Text("Low").tag("low")
                        Text("Medium").tag("medium")
                        Text("High").tag("high")
                    }
                    TextField("Reminder (min before)", text: $reminderMin)
                        .keyboardType(.numberPad)
                    TextField("Notes", text: $notes, axis: .vertical)
                        .lineLimit(2...4)
                }

                if !errMsg.isEmpty {
                    Section {
                        Text(errMsg).foregroundStyle(.red).font(.caption)
                    }
                }
            }
            .navigationTitle(isEdit ? "Edit Event" : "New Event")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { onDismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(isEdit ? "Save" : "Create") { save() }
                        .disabled(saving || title.isEmpty)
                        .fontWeight(.semibold)
                }
            }
            .onAppear { populate() }
        }
    }

    private func populate() {
        if let ev = editEvent {
            title = ev.title
            desc = ev.description ?? ""
            category = ev.category
            eventDate = df.date(from: ev.eventDate) ?? Date()
            allDay = ev.allDay
            if let st = ev.startTime {
                hasStartTime = true
                startTime = tf.date(from: st) ?? tfShort.date(from: String(st.prefix(5))) ?? Date()
            }
            if let et = ev.endTime {
                hasEndTime = true
                endTime = tf.date(from: et) ?? tfShort.date(from: String(et.prefix(5))) ?? Date()
            }
            recurrence = ev.recurrence ?? "none"
            if let re = ev.recurrenceEndDate {
                hasRecurrenceEnd = true
                recurrenceEnd = df.date(from: re) ?? Date()
            }
            location = ev.location ?? ""
            priority = ev.priority ?? ""
            notes = ev.notes ?? ""
            if let rm = ev.reminderMinutes { reminderMin = "\(rm)" }
        } else {
            eventDate = df.date(from: defaultDate) ?? Date()
        }
    }

    private func save() {
        saving = true
        errMsg = ""
        Task {
            do {
                let dateStr = df.string(from: eventDate)
                let st: String? = (!allDay && hasStartTime) ? tfShort.string(from: startTime) + ":00" : nil
                let et: String? = (!allDay && hasEndTime) ? tfShort.string(from: endTime) + ":00" : nil
                let rec: String? = recurrence == "none" ? nil : recurrence
                let recEnd: String? = (rec != nil && hasRecurrenceEnd) ? df.string(from: recurrenceEnd) : nil
                let rm: Int? = Int(reminderMin)
                let pr: String? = priority.isEmpty ? nil : priority

                if isEdit {
                    let body = CalendarEventUpdate(
                        title: title, description: desc.isEmpty ? nil : desc,
                        category: category, eventDate: dateStr,
                        startTime: st, endTime: et, allDay: allDay,
                        recurrence: rec, status: nil, location: location.isEmpty ? nil : location,
                        reminderMinutes: rm, priority: pr,
                        notes: notes.isEmpty ? nil : notes, color: nil
                    )
                    let _: CalendarEvent = try await APIClient.shared.patch(
                        "/calendar/\(editEvent!.id)", body: body
                    )
                } else {
                    let body = CalendarEventCreate(
                        title: title, description: desc.isEmpty ? nil : desc,
                        category: category, eventDate: dateStr,
                        startTime: st, endTime: et, allDay: allDay,
                        recurrence: rec, recurrenceEndDate: recEnd,
                        location: location.isEmpty ? nil : location,
                        reminderMinutes: rm, priority: pr,
                        notes: notes.isEmpty ? nil : notes, color: nil
                    )
                    let _: CalendarEvent = try await APIClient.shared.post("/calendar/", body: body)
                }
                await MainActor.run { onSave(); onDismiss() }
            } catch {
                await MainActor.run { errMsg = error.localizedDescription; saving = false }
            }
        }
    }
}
