import SwiftUI

@Observable
final class AIChatViewModel {
    var messages: [ChatMessage] = []
    var inputText = ""
    var isLoading = false
    var errorMessage: String?
    
    // Persona
    var personas: [AIPersona] = []
    var selectedPersona: AIPersona?
    var showPersonaPicker = false   // opt-in — we default to the device locale

    init() {
        Task { await loadPersonas() }
    }

    private func isYesterdayNutritionQuery(_ text: String) -> Bool {
        let t = text.lowercased()
        return t.contains("nutrition") && t.contains("yesterday")
    }

    private func buildYesterdaySummaryText(_ s: NutritionDailySummaryResponse) -> String {
        let calories = Int(s.totalCalories)
        let protein = String(format: "%.1f", s.totalProteinG)
        let carbs = String(format: "%.1f", s.totalCarbsG)
        let fat = String(format: "%.1f", s.totalFatG)
        return "Yesterday, you logged \(s.mealCount) meal(s): \(calories) kcal, protein \(protein) g, carbs \(carbs) g, fat \(fat) g."
    }

    private func fetchYesterdayNutritionSummaryText() async throws -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        let yesterday = Calendar.current.date(byAdding: .day, value: -1, to: Date()) ?? Date()
        let dateParam = formatter.string(from: yesterday)
        let summary: NutritionDailySummaryResponse = try await APIClient.shared.get("/nutrition/daily-summary?date=\(dateParam)")
        return buildYesterdaySummaryText(summary)
    }
    
    func loadPersonas() async {
        do {
            personas = try await APIClient.shared.get("/ai/personas")
        } catch {
            // The persona roster is backend-owned (AI stays server-driven — no
            // named guides baked into the app). If the fetch fails, fall back to
            // a single neutral assistant so chat still works offline.
            personas = [
                AIPersona(key: "assistant", title: "Assistant", origin: "", region: "specialist",
                          greeting: "Welcome", description: "Your personal health guide.", opening: nil)
            ]
        }
        applyDefaultPersona()
    }

    /// Land the user straight in the chat with a sensible default rather than
    /// forcing the picker: match the device language to a guide, else the general
    /// practitioner, else the first specialist. The user can still change it.
    private func applyDefaultPersona() {
        guard selectedPersona == nil, !personas.isEmpty else { return }
        let code = Locale.current.language.languageCode?.identifier ?? ""
        let langEN = Locale(identifier: "en_US").localizedString(forLanguageCode: code)?.lowercased() ?? ""
        let match = (langEN.isEmpty ? nil : personas.first { $0.origin.lowercased().hasPrefix(langEN) })
            ?? personas.first { $0.key == "general_practitioner" }
            ?? personas.first { $0.region == "specialist" }
            ?? personas.first
        if let match { selectPersona(match) }
    }
    
    func selectPersona(_ persona: AIPersona) {
        selectedPersona = persona
        showPersonaPicker = false
        // Opening line comes from the backend (persona.opening) so the AI's voice
        // is server-controlled; only fall back to a neutral generic if absent.
        messages = [
            ChatMessage(role: .assistant,
                        content: persona.opening ?? "Welcome — how can I help with your health today?")
        ]
    }
    
    func sendMessage() async {
        let text = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }

        // Capture history before appending the new user message
        let history = messages.map {
            HistoryMessage(role: $0.role == .user ? "user" : "assistant", content: $0.content)
        }

        messages.append(ChatMessage(role: .user, content: text))
        inputText = ""
        isLoading = true

        // Placeholder assistant message that tokens will fill in
        let placeholder = ChatMessage(role: .assistant, content: "")
        messages.append(placeholder)
        let idx = messages.endIndex - 1

        do {
            let query = AIQueryRequest(query: text, persona: selectedPersona?.key, messages: history)
            var receivedToken = false
            do {
                for try await token in await APIClient.shared.streamPost("/ai/chat/stream", body: query) {
                    receivedToken = true
                    messages[idx].content += token
                }
            } catch APIError.unknown(let code) where code == 404 || code == 405 {
                let response: AIQueryResponse = try await APIClient.shared.post("/ai/chat", body: query)
                messages[idx].content = response.response
                receivedToken = true
            }

            if !receivedToken {
                let response: AIQueryResponse = try await APIClient.shared.post("/ai/chat", body: query)
                messages[idx].content = response.response
            }

            if messages[idx].content.contains("Custom LLM integration coming soon"), isYesterdayNutritionQuery(text) {
                if let summaryText = try? await fetchYesterdayNutritionSummaryText() {
                    messages[idx].content = summaryText
                }
            }
        } catch {
            if isYesterdayNutritionQuery(text), let summaryText = try? await fetchYesterdayNutritionSummaryText() {
                messages[idx].content = summaryText
            } else {
                messages[idx].content = "Sorry, I couldn't process your request. Please try again."
            }
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }
}

struct AIChatView: View {
    @State private var vm = AIChatViewModel()
    @State private var speech = SpeechRecognizer()
    @FocusState private var isFocused: Bool
    
    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Messages
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(spacing: 12) {
                            ForEach(vm.messages) { msg in
                                ChatBubble(message: msg)
                                    .id(msg.id)
                            }
                            
                            if vm.isLoading {
                                HStack {
                                    TypingIndicator()
                                    Spacer()
                                }
                                .padding(.horizontal)
                                .id("typing")
                            }
                        }
                        .padding(.vertical, 12)
                    }
                    .onChange(of: vm.messages.count) {
                        withAnimation {
                            proxy.scrollTo(vm.messages.last?.id, anchor: .bottom)
                        }
                    }
                    .onChange(of: vm.isLoading) {
                        withAnimation {
                            proxy.scrollTo("typing", anchor: .bottom)
                        }
                    }
                }
                
                Divider()
                
                // Input
                HStack(spacing: 12) {
                    TextField(speech.isRecording ? "Listening… speak your question" : "Ask about your health...",
                              text: $vm.inputText, axis: .vertical)
                        .lineLimit(1...4)
                        .textFieldStyle(.plain)
                        .focused($isFocused)
                        .onSubmit { sendIfReady() }
                        .disabled(vm.selectedPersona == nil)

                    // Voice input (parity with the web chat mic) — speak your question.
                    Button {
                        toggleVoice()
                    } label: {
                        Image(systemName: speech.isRecording ? "mic.fill" : "mic")
                            .font(.title2)
                            .foregroundStyle(speech.isRecording ? .red : (vm.selectedPersona == nil ? .gray : .green))
                    }
                    .disabled(vm.isLoading || vm.selectedPersona == nil)

                    Button {
                        sendIfReady()
                    } label: {
                        Image(systemName: "arrow.up.circle.fill")
                            .font(.title2)
                            .foregroundStyle(
                                vm.inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || vm.selectedPersona == nil
                                ? .gray : .green
                            )
                    }
                    .disabled(vm.inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || vm.isLoading || vm.selectedPersona == nil)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                .background(.ultraThinMaterial)
                // Live transcript into the field while speaking.
                .onChange(of: speech.transcript) { _, t in
                    if speech.isRecording { vm.inputText = t }
                }
                // When recording ends, send the final transcript to the agent.
                .onChange(of: speech.isRecording) { wasRecording, nowRecording in
                    if wasRecording && !nowRecording {
                        let text = speech.transcript.trimmingCharacters(in: .whitespacesAndNewlines)
                        guard !text.isEmpty else { return }
                        vm.inputText = text
                        Task { await vm.sendMessage() }
                    }
                }
            }
            .navigationTitle("AI Assistant")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        vm.showPersonaPicker = true
                    } label: {
                        HStack(spacing: 4) {
                            if let p = vm.selectedPersona {
                                Text(p.title)
                                    .font(.caption)
                                    .foregroundStyle(.green)
                            }
                            Image(systemName: "person.crop.circle")
                        }
                    }
                }
            }
            .sheet(isPresented: $vm.showPersonaPicker) {
                PersonaPickerSheet(vm: vm)
            }
        }
    }
    
    private func sendIfReady() {
        Task { await vm.sendMessage() }
    }

    private func toggleVoice() {
        if speech.isRecording {
            speech.stop()
        } else {
            Task {
                if await speech.authorize() {
                    try? speech.start()
                }
            }
        }
    }
}

// MARK: - Persona Picker Sheet

struct PersonaPickerSheet: View {
    @Bindable var vm: AIChatViewModel
    @Environment(\.dismiss) private var dismiss
    // Rolled up per region: specialists open, cultural regions collapsed.
    @State private var expanded: Set<String> = ["specialist"]

    private let regionOrder = ["specialist", "africa", "middle_east", "south_asia", "europe", "north_america"]
    private let regionLabels: [String: String] = [
        "specialist": "🏥 Specialist Agents",
        "africa": "🌍 Africa",
        "middle_east": "🕌 Middle East",
        "south_asia": "🕉 South Asia",
        "europe": "🏰 Europe",
        "north_america": "🗽 North America",
    ]

    private var grouped: [(String, [AIPersona])] {
        let dict = Dictionary(grouping: vm.personas, by: { $0.region })
        return regionOrder.compactMap { region in
            guard let items = dict[region], !items.isEmpty else { return nil }
            return (region, items)
        }
    }

    var body: some View {
        NavigationStack {
            List {
                Text("Optional — close this to keep your device-language guide, or pick another.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .listRowBackground(Color.clear)

                ForEach(grouped, id: \.0) { region, personas in
                    DisclosureGroup(isExpanded: Binding(
                        get: { expanded.contains(region) },
                        set: { if $0 { expanded.insert(region) } else { expanded.remove(region) } }
                    )) {
                        ForEach(personas) { persona in
                            let isSelected = vm.selectedPersona?.key == persona.key
                            Button {
                                vm.selectPersona(persona)
                                dismiss()
                            } label: {
                                HStack {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(persona.title).font(.subheadline).fontWeight(.medium)
                                        Text(persona.origin).font(.caption).foregroundStyle(.secondary)
                                    }
                                    Spacer()
                                    if isSelected {
                                        Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
                                    }
                                }
                            }
                            .buttonStyle(.plain)
                        }
                    } label: {
                        HStack {
                            Text(regionLabels[region] ?? region).font(.headline)
                            Spacer()
                            Text("\(personas.count)").font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
            }
            .navigationTitle("Choose Your Guide")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) { Button("Done") { dismiss() } }
            }
        }
    }
}

struct ChatBubble: View {
    let message: ChatMessage
    
    var isUser: Bool { message.role == .user }
    
    var body: some View {
        HStack {
            if isUser { Spacer(minLength: 60) }
            
            VStack(alignment: isUser ? .trailing : .leading, spacing: 4) {
                if !isUser {
                    HStack(spacing: 4) {
                        Image(systemName: "brain.head.profile")
                            .font(.caption)
                            .foregroundStyle(.green)
                        Text("ALAFIA AI")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
                
                Text(message.content)
                    .font(.body)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .background(isUser ? Color.green : Color(.systemGray6))
                    .foregroundStyle(isUser ? .white : .primary)
                    .clipShape(RoundedRectangle(cornerRadius: 18))
            }
            
            if !isUser { Spacer(minLength: 60) }
        }
        .padding(.horizontal)
    }
}

struct TypingIndicator: View {
    @State private var phase = 0.0
    
    var body: some View {
        HStack(spacing: 4) {
            ForEach(0..<3, id: \.self) { i in
                Circle()
                    .fill(Color.gray)
                    .frame(width: 8, height: 8)
                    .opacity(0.4 + 0.6 * sin(phase + Double(i) * .pi / 3))
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .background(Color(.systemGray6))
        .clipShape(RoundedRectangle(cornerRadius: 18))
        .onAppear {
            withAnimation(.linear(duration: 1.0).repeatForever(autoreverses: false)) {
                phase = .pi * 2
            }
        }
    }
}
