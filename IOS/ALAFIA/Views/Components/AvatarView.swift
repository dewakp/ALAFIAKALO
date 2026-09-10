import SwiftUI

/// One avatar, used by every screen that shows a person.
///
/// Web grew a shared `Avatar` for the same reason: the clinician grid drew its
/// own initials circle and nothing else drew anything, so a photo uploaded in
/// Profile would have appeared in exactly one place.
///
/// The photo arrives as a `data:` URI on the user payload rather than as a URL
/// to fetch — it is already small (the server crops and re-encodes to 256 px),
/// and one fewer authenticated round-trip per face matters in a list.
struct AvatarView: View {
    let urlString: String?
    let name: String?
    let userId: Int
    var size: CGFloat = 44

    /// Deterministic tint, so a person keeps their colour between launches and
    /// a list stays scannable. Matches the web palette.
    private static let tints: [Color] = [
        Color(red: 0.055, green: 0.647, blue: 0.914),
        Color(red: 0.545, green: 0.361, blue: 0.965),
        Color(red: 0.961, green: 0.620, blue: 0.043),
        Color(red: 0.063, green: 0.725, blue: 0.506),
        Color(red: 0.937, green: 0.267, blue: 0.267),
        Color(red: 0.388, green: 0.400, blue: 0.945),
    ]

    private var tint: Color { Self.tints[abs(userId) % Self.tints.count] }

    private var initials: String {
        let words = (name ?? "").split(separator: " ").prefix(2)
        let letters = words.compactMap { $0.first }.map(String.init).joined().uppercased()
        return letters.isEmpty ? "?" : letters
    }

    /// Decodes a `data:image/…;base64,…` URI. Anything else — including a real
    /// http URL, which this app does not currently receive — falls through to
    /// initials rather than showing a broken image.
    private var image: UIImage? {
        guard let s = urlString,
              let comma = s.firstIndex(of: ","),
              s.hasPrefix("data:image"),
              let data = Data(base64Encoded: String(s[s.index(after: comma)...]))
        else { return nil }
        return UIImage(data: data)
    }

    var body: some View {
        Group {
            if let ui = image {
                Image(uiImage: ui)
                    .resizable()
                    .scaledToFill()
            } else {
                ZStack {
                    tint
                    Text(initials)
                        .font(.system(size: max(11, size * 0.36), weight: .bold))
                        .foregroundStyle(.white)
                }
            }
        }
        .frame(width: size, height: size)
        .clipShape(Circle())
        // A name, not "avatar" — a list of twenty "image" announcements tells a
        // VoiceOver user nothing.
        .accessibilityLabel(name.map { "\($0)" } ?? "Profile photo")
    }
}
