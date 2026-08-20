import SwiftUI

/// One patient, as a board of data-category cards.
///
/// Opening a patient shows every category they share — latest values per
/// category plus their current wellness score — and opening a card gives the
/// trends and the records behind it. Categories the patient did NOT share are
/// still listed, greyed and locked: omitting them silently reads as "no data",
/// which is a different clinical fact.
struct PatientBoardView: View {
    let patientId: Int
    let patientName: String

    @State private var board: PatientBoardResponse?
    @State private var error: String?

    private let columns = [GridItem(.adaptive(minimum: 250), spacing: 12)]

    var body: some View {
        Group {
            if let error {
                ContentUnavailableView("Unavailable", systemImage: "lock.shield",
                                       description: Text(error))
            } else if let board {
                ScrollView {
                    VStack(alignment: .leading, spacing: 12) {
                        shareBanner(board)
                        LazyVGrid(columns: columns, spacing: 12) {
                            ForEach(board.cards) { card in
                                if card.shared {
                                    NavigationLink {
                                        PatientCategoryView(patientId: patientId,
                                                            categoryKey: card.key,
                                                            categoryLabel: card.label)
                                    } label: {
                                        CategoryCardView(card: card)
                                    }
                                    .buttonStyle(.plain)
                                } else {
                                    CategoryCardView(card: card)
                                }
                            }
                        }
                    }
                    .padding(12)
                }
            } else {
                ProgressView("Loading patient…")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .navigationTitle(patientName)
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
    }

    @ViewBuilder
    private func shareBanner(_ board: PatientBoardResponse) -> some View {
        HStack(spacing: 6) {
            Image(systemName: "lock.fill").font(.caption2)
            Text(board.permissions.contains("all")
                 ? "This patient shares all of their data with you."
                 : "Shared with you: \(board.permissions.joined(separator: ", "))")
                .font(.caption)
        }
        .foregroundStyle(.secondary)
    }

    private func load() async {
        do {
            board = try await APIClient.shared.get("/clinician-dashboard/patient/\(patientId)/board")
        } catch let loadError {
            error = loadError.localizedDescription.contains("403")
                ? "This patient has revoked access."
                : "Could not load this patient."
        }
    }
}

struct CategoryCardView: View {
    let card: BoardCard

    private var symbol: String {
        switch card.icon {
        case "gauge": return "gauge.with.dots.needle.67percent"
        case "heart-pulse": return "heart.fill"
        case "flask": return "flask.fill"
        case "pill": return "pills.fill"
        case "activity": return "waveform.path.ecg"
        case "apple": return "leaf.fill"
        case "dumbbell": return "figure.run"
        case "droplets": return "drop.fill"
        case "brain": return "brain"
        case "book": return "book.fill"
        case "link": return "link"
        case "thermometer": return "thermometer.medium"
        case "cross": return "cross.case.fill"
        case "heart": return "heart.text.square"
        case "message-square": return "message.fill"
        default: return "square.grid.2x2"
        }
    }

    private var accent: Color {
        switch card.key {
        case "score": return .orange
        case "vitals": return .red
        case "labs": return .purple
        case "medications": return .orange
        case "conditions": return .pink
        case "nutrition": return .green
        case "fitness": return .teal
        case "elimination": return .brown
        case "mood": return .pink
        case "journal": return .indigo
        case "symptoms": return .orange
        case "dialysis": return .teal
        case "messages": return .cyan
        case "lifestyle": return .mint
        default: return .blue
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: symbol).font(.footnote).foregroundStyle(accent)
                Text(card.label).font(.subheadline).fontWeight(.semibold)
                Spacer()
                if let count = card.count {
                    Text("\(count)").font(.caption2).foregroundStyle(.secondary)
                }
                Image(systemName: card.shared ? "chevron.right" : "lock.fill")
                    .font(.caption2).foregroundStyle(.secondary)
            }

            if card.items.isEmpty {
                Text(card.emptyReason ?? "Nothing recorded.")
                    .font(.caption).foregroundStyle(.secondary)
            } else {
                ForEach(Array(card.items.prefix(5).enumerated()), id: \.offset) { _, item in
                    HStack(alignment: .firstTextBaseline) {
                        Text(item.label)
                            .font(.caption).lineLimit(1)
                        Spacer(minLength: 8)
                        if let v = item.valueWithUnit {
                            Text(v).font(.caption).fontWeight(.semibold).lineLimit(1)
                        }
                    }
                    .foregroundStyle(item.danger == true ? Color.red : Color.primary)
                }
            }

            if let updated = card.lastUpdated {
                Text("Updated \(updated.prefix(10))")
                    .font(.caption2).foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(Color(.secondarySystemGroupedBackground))
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .opacity(card.shared ? 1 : 0.55)
    }
}
