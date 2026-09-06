import Foundation

/// Centralized API client for all network requests
actor APIClient {
    static let shared = APIClient()

    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    private init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        // Standard system TLS validation (App Transport Security + the OS trust
        // store) secures every request. We deliberately do NOT certificate-pin:
        // api.alafia.app is served by Cloud Run behind Google-managed certificates
        // that auto-rotate, so a hardcoded leaf pin would break the app on every
        // rotation (it did — a stale placeholder pin surfaced as URLError.cancelled).
        // If pinning is ever required, pin the Google Trust Services *intermediate*
        // SPKI (stable for years), never the auto-rotated leaf, and ship pin updates
        // ahead of CA migrations.
        self.session = URLSession(configuration: config)

        self.decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let dateStr = try container.decode(String.self)
            // Delegate to AppDate.parse, which handles ISO8601 (with/without
            // fractional seconds and zone), NAIVE datetimes with no timezone
            // (e.g. "2026-04-20T16:45:35.544021" — what the backend emits for
            // created_at/updated_at), and date-only strings. The previous inline
            // strategy only accepted zoned ISO8601, so naive timestamps threw
            // dataCorrupted ("data couldn't be read because it isn't in the
            // correct format") and broke every screen with a Date field.
            if let date = AppDate.parse(dateStr) { return date }
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Cannot decode date: \(dateStr)")
        }
        
        self.encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .custom { date, encoder in
            var container = encoder.singleValueContainer()
            let df = DateFormatter()
            df.dateFormat = "yyyy-MM-dd"
            try container.encode(df.string(from: date))
        }
    }

    // MARK: - CSRF

    /// Non-throwing wrapper: the body below already falls back to a generated
    /// token, so a caller should never have to handle a failure it cannot get.
    private func fetchCsrfTokenOrGenerated() async -> String {
        (try? await fetchCsrfToken()) ?? UUID().uuidString
    }

    private func fetchCsrfToken() async throws -> String {
        var request = buildRequest(path: "/auth/csrf-cookie", method: "GET")
        request.httpBody = nil

        do {
            let (_, response) = try await session.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse else {
                throw APIError.invalidResponse
            }

            let headers = httpResponse.value(forHTTPHeaderField: "Set-Cookie") ?? ""
            let parts = headers.split(separator: ";").map { String($0).trimmingCharacters(in: .whitespaces) }
            let tokenPart = parts.first { $0.hasPrefix("csrf_token=") }

            if let token = tokenPart?.split(separator: "=", maxSplits: 1).last, !token.isEmpty {
                return String(token)
            }
        } catch {
            // Fall through to generated token.
        }

        // Some backend variants do not expose a dedicated csrf-cookie route.
        // Sending matching cookie + header still satisfies double-submit CSRF checks.
        return UUID().uuidString
    }
    
    // MARK: - Token Management
    
    private var cachedToken: String?

    private var token: String? {
        cachedToken ?? KeychainHelper.get(key: AppConfig.tokenKey)
    }

    func setToken(_ token: String?) {
        cachedToken = token
    }

    // MARK: - Auto-refresh on 401 (parity with Android's TokenAuthenticator)

    private static let refreshTokenKey = "alafia_refresh_token"
    private var isRefreshing = false

    /// Sends a request and, on a 401, transparently refreshes the access token once
    /// and retries — so short-lived hybrid EdDSA+ML-DSA access tokens never surface
    /// as spurious mid-session auth failures.
    private func send(_ request: URLRequest) async throws -> (Data, URLResponse) {
        let (data, response) = try await session.data(for: request)
        guard (response as? HTTPURLResponse)?.statusCode == 401,
              !(request.url?.path.hasSuffix("/auth/refresh") ?? false),
              await attemptRefresh() else {
            return (data, response)
        }
        var retry = request
        if let newToken = token {
            retry.setValue("Bearer \(newToken)", forHTTPHeaderField: "Authorization")
        }
        return try await session.data(for: retry)
    }

    /// Refreshes the access token from the stored refresh token (body-based ⇒ no CSRF
    /// needed for non-cookie clients). Returns true on success.
    private func attemptRefresh() async -> Bool {
        guard !isRefreshing else { return false }
        guard let refresh = KeychainHelper.get(key: Self.refreshTokenKey) else { return false }
        isRefreshing = true
        defer { isRefreshing = false }
        guard let url = URL(string: "\(AppConfig.baseURL)/auth/refresh") else { return false }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(withJSONObject: ["refresh_token": refresh])
        guard let (data, response) = try? await session.data(for: req),
              (response as? HTTPURLResponse)?.statusCode == 200,
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let access = json["access_token"] as? String else {
            return false
        }
        KeychainHelper.save(key: AppConfig.tokenKey, value: access)
        cachedToken = access
        if let newRefresh = json["refresh_token"] as? String {
            KeychainHelper.save(key: Self.refreshTokenKey, value: newRefresh)
        }
        return true
    }

    // MARK: - Request Building
    
    private func buildRequest(
        path: String,
        method: String,
        body: Data? = nil,
        contentType: String = "application/json",
        timeout: TimeInterval? = nil
    ) -> URLRequest {
        let url = URL(string: "\(AppConfig.baseURL)\(path)")!
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue(contentType, forHTTPHeaderField: "Content-Type")
        // The device knows what day it is where the patient is; the server runs
        // UTC and does not. Without this, "what did I eat today?" asked in the
        // evening in the Americas queries tomorrow and finds nothing.
        request.setValue(TimeZone.current.identifier, forHTTPHeaderField: "X-Client-Timezone")
        if let timeout { request.timeoutInterval = timeout }

        if let token = token {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        
        request.httpBody = body
        return request
    }
    
    // MARK: - Generic Request Methods
    
    func get<T: Decodable>(_ path: String) async throws -> T {
        let request = buildRequest(path: path, method: "GET")
        let (data, response) = try await send(request)
        try validateResponse(response, data: data)
        let decoded = try decoder.decode(T.self, from: data)
        return decoded
    }

    /// GET with transparent offline cache fallback.
    /// On success the response is cached; on network failure the last cached value is returned.
    func getWithCache<T: Codable>(_ path: String) async throws -> T {
        do {
            let result: T = try await get(path)
            OfflineCache.shared.store(result, for: path)
            return result
        } catch {
            if let cached: T = OfflineCache.shared.load(for: path) {
                return cached
            }
            throw error
        }
    }
    
    func post<T: Decodable, B: Encodable>(_ path: String, body: B, timeout: TimeInterval? = nil) async throws -> T {
        let bodyData = try encoder.encode(body)
        var request = buildRequest(path: path, method: "POST", body: bodyData, timeout: timeout)
        await attachCSRFIfUnauthenticated(&request)
        let (data, response) = try await send(request)
        try validateResponse(response, data: data)
        return try decoder.decode(T.self, from: data)
    }

    /// Attach a double-submit CSRF pair when the request carries no Bearer token.
    ///
    /// This mirrors the server's own rule rather than a list of paths. `main.py`
    /// exempts a request whose credential is explicit and non-ambient — anything
    /// with `Authorization: Bearer` — and enforces CSRF on everything else. The
    /// endpoints with no Bearer token are exactly the ones a user reaches when
    /// they cannot log in: **register, and password reset**.
    ///
    /// Those were sent as plain JSON with no CSRF pair and the server answered
    /// 403, which the Reset Password screen rendered verbatim as
    /// "CSRF token missing or invalid" — to a user who had merely forgotten
    /// their password. Login escaped it only because it happens to use
    /// `postFormWithCSRF`; the CSRF-aware path existed and the JSON one never
    /// got it.
    ///
    /// Deriving the condition from the Authorization header, instead of naming
    /// the affected routes, is what stops the next unauthenticated endpoint from
    /// shipping broken the same way.
    private func attachCSRFIfUnauthenticated(_ request: inout URLRequest) async {
        guard request.value(forHTTPHeaderField: "Authorization") == nil else { return }
        // Never throws: falls back to a generated token, and double-submit only
        // requires that the header and the cookie MATCH.
        let csrfToken = await fetchCsrfTokenOrGenerated()
        request.setValue(csrfToken, forHTTPHeaderField: "X-CSRF-Token")
        request.setValue("csrf_token=\(csrfToken)", forHTTPHeaderField: "Cookie")
    }
    
    /// Encode a form body for `application/x-www-form-urlencoded`.
    ///
    /// This used `.urlQueryAllowed`, which is a set for query STRINGS and
    /// therefore leaves `& = + ; $` untouched — they are legal there. In a form
    /// BODY `&` separates fields, so a password containing one was cut short at
    /// it. `f8&$dfUHa%fg9R_SA@qK` reached the server as `f8`, the API answered
    /// 401 "Incorrect email or password", and the app rendered that as
    /// "Please log in again" — with the correct password on screen.
    ///
    /// `+` was worse: it survives the trip and decodes server-side to a SPACE,
    /// so the password is wrong in a way nothing on either end reports.
    ///
    /// Only RFC 3986 unreserved characters are left as-is; everything else is
    /// percent-encoded.
    static func formURLEncoded(_ fields: [String: String]) -> String {
        var unreserved = CharacterSet.alphanumerics
        unreserved.insert(charactersIn: "-._~")
        return fields.map { key, value in
            let k = key.addingPercentEncoding(withAllowedCharacters: unreserved) ?? key
            let v = value.addingPercentEncoding(withAllowedCharacters: unreserved) ?? value
            return "\(k)=\(v)"
        }.joined(separator: "&")
    }

    func postForm<T: Decodable>(_ path: String, formData: [String: String]) async throws -> T {
        let body = Self.formURLEncoded(formData)
        let request = buildRequest(
            path: path,
            method: "POST",
            body: body.data(using: .utf8),
            contentType: "application/x-www-form-urlencoded"
        )
        let (data, response) = try await send(request)
        try validateResponse(response, data: data)
        return try decoder.decode(T.self, from: data)
    }

    func postFormWithCSRF<T: Decodable>(_ path: String, formData: [String: String]) async throws -> T {
        let csrfToken = try await fetchCsrfToken()
        let body = Self.formURLEncoded(formData)

        var request = buildRequest(
            path: path,
            method: "POST",
            body: body.data(using: .utf8),
            contentType: "application/x-www-form-urlencoded"
        )
        request.setValue(csrfToken, forHTTPHeaderField: "X-CSRF-Token")
        request.setValue("csrf_token=\(csrfToken)", forHTTPHeaderField: "Cookie")

        let (data, response) = try await send(request)
        try validateResponse(response, data: data)
        return try decoder.decode(T.self, from: data)
    }
    
    /// POSTs one or more JPEGs as `multipart/form-data`, plus optional text fields.
    ///
    /// Every image is sent under the same field name in a single request, which is
    /// what `/ai/vision` expects for "several shots of one subject": the backend
    /// analyses them together and returns one combined result.
    func postImages<T: Decodable>(
        _ path: String,
        images: [Data],
        fieldName: String = "files",
        fields: [String: String] = [:],
        timeout: TimeInterval = 180
    ) async throws -> T {
        let boundary = "Boundary-\(UUID().uuidString)"
        var body = Data()

        func append(_ string: String) {
            body.append(string.data(using: .utf8)!)
        }

        for (key, value) in fields {
            append("--\(boundary)\r\n")
            append("Content-Disposition: form-data; name=\"\(key)\"\r\n\r\n")
            append("\(value)\r\n")
        }
        for (index, image) in images.enumerated() {
            append("--\(boundary)\r\n")
            append("Content-Disposition: form-data; name=\"\(fieldName)\"; filename=\"image\(index).jpg\"\r\n")
            append("Content-Type: image/jpeg\r\n\r\n")
            body.append(image)
            append("\r\n")
        }
        append("--\(boundary)--\r\n")

        let request = buildRequest(
            path: path,
            method: "POST",
            body: body,
            contentType: "multipart/form-data; boundary=\(boundary)",
            timeout: timeout
        )
        let (data, response) = try await send(request)
        try validateResponse(response, data: data)
        return try decoder.decode(T.self, from: data)
    }

    func patch<T: Decodable, B: Encodable>(_ path: String, body: B) async throws -> T {
        let bodyData = try encoder.encode(body)
        let request = buildRequest(path: path, method: "PATCH", body: bodyData)
        let (data, response) = try await send(request)
        try validateResponse(response, data: data)
        return try decoder.decode(T.self, from: data)
    }
    
    func put<T: Decodable, B: Encodable>(_ path: String, body: B) async throws -> T {
        let bodyData = try encoder.encode(body)
        let request = buildRequest(path: path, method: "PUT", body: bodyData)
        let (data, response) = try await send(request)
        try validateResponse(response, data: data)
        return try decoder.decode(T.self, from: data)
    }
    
    func putNoBody<T: Decodable>(_ path: String) async throws -> T {
        let request = buildRequest(path: path, method: "PUT")
        let (data, response) = try await send(request)
        try validateResponse(response, data: data)
        return try decoder.decode(T.self, from: data)
    }
    
    func delete(_ path: String) async throws {
        let request = buildRequest(path: path, method: "DELETE")
        let (data, response) = try await send(request)
        let httpResponse = response as! HTTPURLResponse
        if httpResponse.statusCode != 204 {
            try validateResponse(response, data: data)
        }
    }

    // MARK: - Streaming (SSE)

    /// Posts `body` to `path` and returns an `AsyncThrowingStream` that yields
    /// individual content tokens as they arrive from the Ollama SSE endpoint.
    func streamPost<B: Encodable>(_ path: String, body: B) -> AsyncThrowingStream<StreamEvent, Error> {
        AsyncThrowingStream { continuation in
            Task {
                do {
                    let csrfToken = try await fetchCsrfToken()
                    let bodyData = try encoder.encode(body)
                    var request = buildRequest(path: path, method: "POST", body: bodyData)
                    // The AI stream runs a tool loop before it can say anything,
                    // and a cold Ollama fallback is ~250s all in. 120 cut off
                    // requests the server would have completed. Kept below the
                    // documented ladder: client 285 < OLLAMA_TIMEOUT 290 <
                    // Cloud Run 300, and no two rungs equal.
                    request.timeoutInterval = 285
                    request.setValue(csrfToken, forHTTPHeaderField: "X-CSRF-Token")
                    request.setValue("csrf_token=\(csrfToken)", forHTTPHeaderField: "Cookie")

                    let (bytes, response) = try await session.bytes(for: request)

                    if let httpResponse = response as? HTTPURLResponse,
                       httpResponse.statusCode != 200 {
                        continuation.finish(throwing: APIError.unknown(httpResponse.statusCode))
                        return
                    }

                    for try await line in bytes.lines {
                        if line.hasPrefix("data: ") {
                            let payload = String(line.dropFirst(6))
                            if payload == "[DONE]" { break }
                            guard let data = payload.data(using: .utf8) else { continue }
                            // Decoded as a whole frame rather than [String: String]:
                            // the status frame carries a nested object, which that
                            // decode silently dropped along with anything else new.
                            if let frame = try? JSONDecoder().decode(StreamFrame.self, from: data) {
                                if let step = frame.status {
                                    continuation.yield(.status(step))
                                }
                                if let dropped = frame.retract, dropped > 0 {
                                    continuation.yield(.retract(dropped))
                                }
                                if let content = frame.content, !content.isEmpty {
                                    continuation.yield(.content(content))
                                }
                            }
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }
    
    // MARK: - Validation
    
    /// Paths where a 401 is an answer to the user, not a dead session.
    private static func isSignInPath(_ path: String?) -> Bool {
        guard let path else { return false }
        return ["/auth/login", "/auth/register", "/auth/refresh", "/auth/verify",
                "/auth/forgot-password", "/auth/reset-password"]
            .contains { path.hasSuffix($0) }
    }

    private func validateResponse(_ response: URLResponse, data: Data) throws {
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }
        
        switch httpResponse.statusCode {
        case 200...299:
            return
        case 401:
            // This 401 has already survived one transparent refresh (see `send`),
            // so the session is dead rather than stale. Announce it, or the
            // entitlement gate parks in `.unknown` and renders a spinner that
            // never resolves — the indefinite load App Review reported.
            //
            // Sign-in endpoints are excluded on purpose: a wrong password is a
            // 401 the login form shows itself, not a reason to tear down a
            // session that never existed.
            if !Self.isSignInPath(httpResponse.url?.path) {
                NotificationCenter.default.post(name: .alafiaUnauthorized, object: nil)
            }
            throw APIError.unauthorized
        case 402:
            // The app-wide paywall. Broadcast it so the entitlement gate closes
            // wherever the user happens to be, not only at launch.
            NotificationCenter.default.post(name: .alafiaPaymentRequired, object: nil)
            if let detail = try? JSONDecoder().decode(ErrorDetail.self, from: data) {
                throw APIError.paymentRequired(detail.detail)
            }
            throw APIError.paymentRequired("An active ALAFIA Membership is required.")
        case 400...499:
            if let detail = try? JSONDecoder().decode(ErrorDetail.self, from: data) {
                throw APIError.clientError(detail.detail)
            }
            // `detail` is not always a string. The medication dose guard answers
            // 422 with an OBJECT — the findings that name what it refused and
            // the field that overrides it — and the string decode above simply
            // fails on that, so the user was shown "Request failed (422)" while
            // the server had already written the reason AND the fix. Keep the
            // body so the caller can read the fields it knows about, and use
            // the server's own sentence in the meantime.
            if let structured = try? JSONDecoder().decode(StructuredErrorDetail.self, from: data),
               let message = structured.detail.message {
                throw APIError.structured(message: message,
                                          status: httpResponse.statusCode,
                                          body: data)
            }
            // FastAPI's own validation errors are a LIST of field problems. Left
            // undecoded they fell through to "Request failed (422)" — which is
            // what the Reset Password screen showed for an empty email, telling
            // the user a status code instead of which field is wrong.
            if let invalid = try? JSONDecoder().decode(ValidationErrorDetail.self, from: data),
               let readable = invalid.readableMessage {
                throw APIError.clientError(readable)
            }
            throw APIError.clientError("Request failed (\(httpResponse.statusCode))")
        case 500...599:
            throw APIError.serverError
        default:
            throw APIError.unknown(httpResponse.statusCode)
        }
    }
}

// MARK: - Error Types

enum APIError: LocalizedError {
    case invalidResponse
    case unauthorized
    case paymentRequired(String)
    case clientError(String)
    /// A 4xx whose `detail` is an object rather than a string. `body` is the raw
    /// response so the caller can decode the extra fields — the dose guard's
    /// `findings` and `override_with` are why this exists.
    case structured(message: String, status: Int, body: Data)
    case serverError
    case unknown(Int)
    
    var errorDescription: String? {
        switch self {
        case .invalidResponse: return "Invalid server response"
        case .unauthorized: return "Please log in again"
        case .paymentRequired(let msg): return msg
        case .clientError(let msg): return msg
        case .structured(let msg, _, _): return msg
        case .serverError: return "Server error — try again later"
        case .unknown(let code): return "Unexpected error (\(code))"
        }
    }
}

struct ErrorDetail: Decodable {
    let detail: String
}

/// `{"detail": {"message": "...", ...}}` — the object form of a FastAPI error.
struct StructuredErrorDetail: Decodable {
    struct Body: Decodable { let message: String? }
    let detail: Body
}

/// `{"detail": [{"loc": ["body","email"], "msg": "..."}]}` — pydantic's form.
struct ValidationErrorDetail: Decodable {
    struct Item: Decodable {
        let loc: [String]?
        let msg: String?

        /// "email" out of ["body", "email"] — the field the user must fix.
        var field: String? {
            guard let last = loc?.last, last != "body" else { return nil }
            return last.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }
    let detail: [Item]

    /// One line the user can act on. Several problems are joined rather than
    /// showing only the first, or fixing one reveals the next on the next tap.
    var readableMessage: String? {
        let parts: [String] = detail.compactMap { item in
            guard let msg = item.msg, !msg.isEmpty else { return nil }
            if let field = item.field { return "\(field): \(msg)" }
            return msg
        }
        return parts.isEmpty ? nil : parts.joined(separator: "\n")
    }
}

extension ValidationErrorDetail.Item {
    private enum CodingKeys: String, CodingKey { case loc, msg }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.msg = try? c.decode(String.self, forKey: .msg)
        // `loc` mixes strings and integers (a list index). Decode leniently
        // rather than failing the whole message over an array position.
        if var arr = try? c.nestedUnkeyedContainer(forKey: .loc) {
            var parts: [String] = []
            while !arr.isAtEnd {
                if let s = try? arr.decode(String.self) { parts.append(s) }
                else if let i = try? arr.decode(Int.self) { parts.append(String(i)) }
                else { _ = try? arr.decode(AnyCodableSkip.self) }
            }
            self.loc = parts
        } else {
            self.loc = nil
        }
    }
}

/// Consumes one unknown element so a mixed `loc` array cannot stall decoding.
private struct AnyCodableSkip: Decodable {
    init(from decoder: Decoder) throws { _ = try decoder.singleValueContainer() }
}

// MARK: - Local date/time display

/// Render server timestamps in the device's LOCAL timezone + locale.
///
/// The backend stores UTC. Slicing an ISO string (`iso.prefix(16)`) shows the raw UTC
/// clock, which races ahead of the user's time; and `ISO8601DateFormatter` defaults to
/// UTC, so using it for "today" can roll to tomorrow. `AppDate` parses (naive strings
/// assumed UTC) and formats with `TimeZone.current`.
enum AppDate {
    /// Parse a server value to a Date. Naive (no-offset) strings are treated as UTC.
    static func parse(_ s: String?) -> Date? {
        guard let s, !s.isEmpty else { return nil }
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = iso.date(from: s) { return d }
        iso.formatOptions = [.withInternetDateTime]
        if let d = iso.date(from: s) { return d }
        // naive datetime (no zone) → assume UTC
        let naive = DateFormatter()
        naive.locale = Locale(identifier: "en_US_POSIX")
        naive.timeZone = TimeZone(identifier: "UTC")
        naive.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        if s.count >= 19, let d = naive.date(from: String(s.prefix(19))) { return d }
        // date-only → local midnight
        let dOnly = DateFormatter()
        dOnly.locale = Locale(identifier: "en_US_POSIX")
        dOnly.timeZone = .current
        dOnly.dateFormat = "yyyy-MM-dd"
        if s.count >= 10, let d = dOnly.date(from: String(s.prefix(10))) { return d }
        return nil
    }

    /// Today's date, LOCAL, as "yyyy-MM-dd" (for date fields sent to the backend).
    static func localToday() -> String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = .current
        f.dateFormat = "yyyy-MM-dd"
        return f.string(from: Date())
    }

    /// Localized date + time in the device timezone.
    static func dateTime(_ s: String?) -> String {
        guard let d = parse(s) else { return s ?? "" }
        let f = DateFormatter(); f.timeZone = .current; f.dateStyle = .medium; f.timeStyle = .short
        return f.string(from: d)
    }

    /// Localized date only.
    static func date(_ s: String?) -> String {
        guard let d = parse(s) else { return s ?? "" }
        let f = DateFormatter(); f.timeZone = .current; f.dateStyle = .medium
        return f.string(from: d)
    }

    /// Local time only (HH:mm).
    static func time(_ s: String?) -> String {
        guard let d = parse(s) else { return s ?? "" }
        let f = DateFormatter(); f.timeZone = .current; f.timeStyle = .short
        return f.string(from: d)
    }
}

// MARK: - AI chat stream frames

/// One step the server reports while it reads the record.
///
/// The tool rounds take tens of seconds and cannot stream (the model must read
/// each result before it knows what to ask next), so without these the patient
/// watches an empty bubble for the whole wait. The label is written by the
/// BACKEND so iOS, Android and web cannot drift apart, and so a new tool does
/// not need three app releases to get a name.
struct ChatStatusStep: Decodable, Equatable {
    let label: String
    /// e.g. "6 found" / "nothing recorded". Absent where there is no result yet.
    let detail: String?
    /// "thinking" | "tool" | "tool_done" | "composing".
    let phase: String?
}

/// A decoded SSE frame. Every field is optional — a frame carries one of them.
///
/// This replaces a `[String: String]` decode that silently dropped every frame
/// whose value was not a string, which is why the status frames (a nested
/// object) and `interaction_id` (an Int) were invisible to this client.
struct StreamFrame: Decodable {
    let content: String?
    let status: ChatStatusStep?
    /// Characters to take back: that text came from a round that turned out to
    /// be a data fetch, not the answer. Models narrate ("Let me check your food
    /// log…") before calling a tool, and leaving it splices the preamble onto
    /// the front of an answer it was never part of.
    let retract: Int?
    let error: String?
    let interaction_id: Int?
}

/// What `streamPost` hands back.
enum StreamEvent {
    case content(String)
    case status(ChatStatusStep)
    case retract(Int)
}
