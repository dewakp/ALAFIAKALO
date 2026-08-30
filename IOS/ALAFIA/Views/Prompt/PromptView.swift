import SwiftUI
import PhotosUI

// Prompt Hub (Basis: "Mobile starts with a Prompt Page"). Text, voice, and camera
// all resolve to the matching existing screen — parity with the web hub.

struct AIRouteRequest: Encodable {
    let text: String
    let modality: String
    let hasAttachment: Bool

    enum CodingKeys: String, CodingKey {
        case text, modality
        case hasAttachment = "has_attachment"
    }

    init(text: String, modality: String = "text", hasAttachment: Bool = false) {
        self.text = text
        self.modality = modality
        self.hasAttachment = hasAttachment
    }
}

struct AIRouteResponse: Decodable {
    let intent: String
    let confidence: Double
    let route: String
    let action: String
    let assistantMessage: String

    enum CodingKeys: String, CodingKey {
        case intent, confidence, route, action
        case assistantMessage = "assistant_message"
    }
}

struct VisionItem: Decodable { let name: String? }

struct AIVisionResponse: Decodable {
    let items: [VisionItem]?
    let notes: String?
}

/// Maps a routed intent to an existing screen (Basis: reuse current UIs).
enum PromptDestination: Identifiable {
    case nutrition, medications, fitness, elimination, mood, mentalHealth
    case lifestyle, labs, trends, imageAI
    /// Carries the question the user asked, so the chat can send it on arrival
    /// instead of making them type it again.
    case chat(query: String?)

    var id: String {
        if case .chat = self { return "chat" }
        return String(describing: self)
    }

    /// `query` is the user's original text. It matters only for `.chat`, which
    /// is where an unrouted question ends up — every other destination is a form
    /// the user fills in, not a question to answer.
    static func from(intent: String, query: String? = nil) -> PromptDestination {
        switch intent {
        case "log_meal": return .nutrition
        case "log_medication": return .medications
        case "log_activity": return .fitness
        case "log_elimination": return .elimination
        case "journal": return .mood
        case "log_symptom": return .mentalHealth
        case "log_sleep": return .lifestyle
        case "view_labs": return .labs
        case "view_trends": return .trends
        case "vision_capture": return .imageAI
        default: return .chat(query: query)
        }
    }

    @ViewBuilder var view: some View {
        switch self {
        case .nutrition: NutritionView()
        case .medications: MedicationsView()
        case .fitness: FitnessView()
        case .elimination: EliminationView()
        case .mood: MoodView()
        case .mentalHealth: MentalHealthView()
        case .lifestyle: LifestyleView()
        case .labs: LabsView()
        case .trends: ChartDashboardView()
        case .imageAI: ImageAIView()
        case .chat(let query): AIChatView(initialQuery: query)
        }
    }
}

@Observable
final class PromptViewModel {
    var input = ""
    var status = ""
    var busy = false

    @MainActor
    func route(onRouted: @escaping (PromptDestination) -> Void) async {
        let text = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !busy else { return }
        busy = true
        status = "Understanding…"
        defer { busy = false }
        do {
            let res: AIRouteResponse = try await APIClient.shared.post(
                "/ai/route", body: AIRouteRequest(text: text)
            )
            status = res.assistantMessage
            onRouted(PromptDestination.from(intent: res.intent, query: text))
        } catch {
            status = "Couldn't understand that. Try the AI assistant."
        }
    }

    /// A voice transcript behaves exactly like typed text.
    @MainActor
    func submit(transcript: String, onRouted: @escaping (PromptDestination) -> Void) async {
        input = transcript
        await route(onRouted: onRouted)
    }

    /// Upload a photo to /ai/vision; route to Nutrition when food is detected.
    @MainActor
    func analyzeImage(_ imageData: Data, onRouted: @escaping (PromptDestination) -> Void) async {
        guard !busy else { return }
        busy = true
        status = "Looking at your photo…"
        defer { busy = false }
        do {
            let res: AIVisionResponse = try await uploadImage(imageData, to: "/ai/vision")
            if let items = res.items, !items.isEmpty {
                onRouted(.nutrition)
            } else {
                status = "No food detected — opening Image AI."
                onRouted(.imageAI)
            }
        } catch {
            status = "Image AI unavailable — opening Image AI."
            onRouted(.imageAI)
        }
    }

    private func uploadImage<T: Decodable>(_ imageData: Data, to path: String) async throws -> T {
        let boundary = UUID().uuidString
        let url = URL(string: "\(AppConfig.baseURL)\(path)")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 180
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        if let token = KeychainHelper.get(key: AppConfig.tokenKey) {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        var body = Data()
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"image.jpg\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: image/jpeg\r\n\r\n".data(using: .utf8)!)
        body.append(imageData)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
        request.httpBody = body

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
        return try JSONDecoder().decode(T.self, from: data)
    }
}

struct PromptView: View {
    @State private var vm = PromptViewModel()
    @State private var speech = SpeechRecognizer()
    @State private var destination: PromptDestination?

    private func send() {
        Task { await vm.route { destination = $0 } }
    }

    private func toggleVoice() {
        if speech.isRecording {
            speech.stop()
            let text = speech.transcript.trimmingCharacters(in: .whitespacesAndNewlines)
            if !text.isEmpty {
                Task { await vm.submit(transcript: text) { destination = $0 } }
            }
        } else {
            Task {
                guard await speech.authorize() else {
                    vm.status = "Microphone or speech permission denied. You can type instead."
                    return
                }
                do { try speech.start(); vm.status = "Listening… tap the mic again when done." }
                catch { vm.status = "Voice input isn't available right now." }
            }
        }
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 16) {
                Spacer()

                Text("How are you doing today?")
                    .font(.title2).bold()
                    .multilineTextAlignment(.center)

                Text("Tell ALAFIA what you ate, took, or how you feel — it'll take you to the right place.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal)

                HStack(spacing: 8) {
                    Button(action: toggleVoice) {
                        Image(systemName: speech.isRecording ? "stop.circle.fill" : "mic.fill")
                            .font(.title2)
                            .foregroundStyle(speech.isRecording ? .red : .accentColor)
                    }
                    .disabled(vm.busy)

                    PhotoCaptureButton { data in
                        Task { await vm.analyzeImage(data) { destination = $0 } }
                    } label: {
                        Image(systemName: "camera.fill").font(.title2)
                    }
                    .disabled(vm.busy)

                    TextField("e.g. I ate jollof rice and took my 10mg lisinopril", text: $vm.input)
                        .textFieldStyle(.roundedBorder)
                        .disabled(vm.busy)
                        .onSubmit(send)

                    if vm.busy {
                        ProgressView().frame(width: 30)
                    } else {
                        Button(action: send) {
                            Image(systemName: "arrow.up.circle.fill").font(.title)
                        }
                        .disabled(vm.input.trimmingCharacters(in: .whitespaces).isEmpty)
                    }
                }
                .padding(.horizontal)

                if !vm.status.isEmpty {
                    Text(vm.status)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                }

                Spacer()
            }
            .padding()
            .navigationTitle("Ask ALAFIA")
            .navigationBarTitleDisplayMode(.inline)
            .sheet(item: $destination) { dest in
                NavigationStack { dest.view }
            }
        }
    }
}
