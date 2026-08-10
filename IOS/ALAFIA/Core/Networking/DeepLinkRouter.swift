import Foundation
import Combine

/// Handles deep links from URL schemes (`alafia://`) and Universal Links.
///
/// Usage in views:
/// ```
/// @EnvironmentObject var deepLinkRouter: DeepLinkRouter
/// .onChange(of: deepLinkRouter.pendingRoute) { _, route in
///     if let route { navigate(to: route) }
/// }
/// ```
final class DeepLinkRouter: ObservableObject {
    /// The route the app should navigate to.
    @Published var pendingRoute: Route?

    enum Route: Equatable {
        case dashboard
        case labs
        case medications
        case fitness
        case nutrition
        case mood
        case wellness
        case telehealth
        case messaging
        case insurance
        case calendar
        case aiChat
        case profile
        case passwordReset(token: String)
        case unknown(path: String)
    }

    /// Parse an incoming URL and set `pendingRoute`.
    func handle(url: URL) {
        // Support both custom scheme and universal links:
        //   alafia://labs
        //   https://alafia.app/app/labs
        let path: String
        if url.scheme == AppConfig.urlScheme {
            // alafia://labs/...  → host is the first segment
            path = url.host ?? url.path
        } else {
            // Universal link: strip /app prefix
            path = url.path
                .replacingOccurrences(of: "/app/", with: "")
                .replacingOccurrences(of: "/app", with: "")
        }

        pendingRoute = route(for: path.lowercased(), queryItems: URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems)
    }

    func clearRoute() {
        pendingRoute = nil
    }

    // MARK: - Private

    private func route(for path: String, queryItems: [URLQueryItem]?) -> Route {
        switch path {
        case "", "dashboard", "home":       return .dashboard
        case "labs":                         return .labs
        case "medications":                  return .medications
        case "fitness":                      return .fitness
        case "nutrition":                    return .nutrition
        case "mood":                         return .mood
        case "wellness":                     return .wellness
        case "telehealth":                   return .telehealth
        case "messaging", "messages":        return .messaging
        case "insurance":                    return .insurance
        case "calendar":                     return .calendar
        case "ai", "ai-chat":               return .aiChat
        case "profile":                      return .profile
        case "password-reset", "reset-password":
            let token = queryItems?.first(where: { $0.name == "token" })?.value ?? ""
            return .passwordReset(token: token)
        default:
            return .unknown(path: path)
        }
    }
}
