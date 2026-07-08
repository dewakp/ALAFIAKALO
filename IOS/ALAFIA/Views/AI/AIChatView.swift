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
    var showPersonaPicker = true
    
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
            let loaded: [AIPersona] = try await APIClient.shared.get("/ai/personas")
            personas = loaded
        } catch {
            // Fallback
            personas = [
                AIPersona(key: "babalawo", title: "Babalawo", origin: "Yoruba · Nigeria", region: "africa", greeting: "Ẹ kú àárọ̀", description: "Your personal health guide."),
                AIPersona(key: "dibia", title: "Dibia", origin: "Igbo · Nigeria", region: "africa", greeting: "Nnọọ", description: "Your personal health guide."),
                AIPersona(key: "boka", title: "Boka", origin: "Hausa · Nigeria", region: "africa", greeting: "Sannu", description: "Your personal health guide."),
                AIPersona(key: "sage", title: "Sage", origin: "English · UK / Ireland", region: "europe", greeting: "Welcome", description: "Your personal health guide."),
                AIPersona(key: "medicine_keeper", title: "Medicine Keeper", origin: "Native American · United States / Canada", region: "north_america", greeting: "Aho", description: "Your personal health guide."),
            ]
        }
    }
    
    func selectPersona(_ persona: AIPersona) {
        selectedPersona = persona
        showPersonaPicker = false
        messages = [
            ChatMessage(role: .assistant, content: "Welcome! I'm \(persona.title) — think of me as your personal wellness guide. What's on your mind?")
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
    
    private let regionOrder = ["africa", "middle_east", "south_asia", "europe", "north_america"]
    private let regionLabels: [String: String] = [
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
                Text("Pick the name you'd like your health assistant to go by")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .listRowBackground(Color.clear)
                
                ForEach(grouped, id: \.0) { region, personas in
                    Section(regionLabels[region] ?? region) {
                        ForEach(personas) { persona in
                            let isSelected = vm.selectedPersona?.key == persona.key
                            Button {
                                vm.selectPersona(persona)
                                dismiss()
                            } label: {
                                HStack {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(persona.title)
                                            .font(.headline)
                                        Text(persona.origin)
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                    Spacer()
                                    if isSelected {
                                        Image(systemName: "checkmark.circle.fill")
                                            .foregroundStyle(.green)
                                    }
                                }
                                .padding(.vertical, 4)
                            }
                            .buttonStyle(.plain)
                            .listRowBackground(
                                isSelected ? Color.green.opacity(0.08) : nil
                            )
                        }
                    }
                }
            }
            .navigationTitle("Choose Your Guide")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                if vm.selectedPersona != nil {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button("Done") { dismiss() }
                    }
                }
            }
            .interactiveDismissDisabled(vm.selectedPersona == nil)
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
