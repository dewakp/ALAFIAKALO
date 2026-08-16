import SwiftUI
import PhotosUI

/// Reusable styled text field
struct LKTextField: View {
    let title: String
    @Binding var text: String
    var keyboardType: UIKeyboardType = .default
    var isSecure: Bool = false

    /// Whether a secure field is currently showing its contents.
    @State private var revealed = false
    /// Swapping SecureField ⇄ TextField destroys the old view, so the keyboard
    /// dismisses mid-typing unless focus is explicitly moved to the replacement.
    @FocusState private var focused: Bool

    /// Fields whose content is never a sentence. Derived from the keyboard type
    /// so every caller gets it right without remembering to ask.
    private var neverCapitalise: Bool {
        keyboardType == .emailAddress || keyboardType == .URL
    }

    /// This used to be hard-coded to `.sentences` for anything not secure, and
    /// because it is applied INSIDE this wrapper it overrode the caller's own
    /// `.autocapitalization(.none)`. The result shipped: typing an address into
    /// the login form produced "Deji.adesida@alafia.app" and the API answered
    /// 401, which the app showed as "Please log in again". Signup and password
    /// reset use the same field, so both were affected too.
    private var capitalisation: TextInputAutocapitalization {
        (isSecure || neverCapitalise) ? .never : .sentences
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.caption)
                .fontWeight(.medium)
                .foregroundStyle(.secondary)

            HStack(spacing: 8) {
                Group {
                    if isSecure && !revealed {
                        SecureField(title, text: $text)
                            .focused($focused)
                            // Stated explicitly rather than relied upon: the
                            // first character of a password must never be
                            // capitalised for the user.
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                    } else {
                        TextField(title, text: $text)
                            .focused($focused)
                            .keyboardType(isSecure ? .default : keyboardType)
                            // A revealed password must not be autocapitalised,
                            // autocorrected or spell-checked — iOS would happily
                            // "fix" it into something the user never typed.
                            .textInputAutocapitalization(capitalisation)
                            .autocorrectionDisabled(isSecure || neverCapitalise)
                    }
                }

                if isSecure {
                    Button {
                        revealed.toggle()
                        // Restore focus after the field is rebuilt, so toggling
                        // does not close the keyboard mid-entry.
                        DispatchQueue.main.async { focused = true }
                    } label: {
                        Image(systemName: revealed ? "eye.slash" : "eye")
                            .foregroundStyle(.secondary)
                            .frame(width: 24, height: 24)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(revealed ? "Hide password" : "Show password")
                    .accessibilityAddTraits(revealed ? .isSelected : [])
                }
            }
            .padding(12)
            .background(Color(.systemGray6))
            .cornerRadius(10)
        }
    }
}

/// Reusable styled number field
struct LKNumberField: View {
    let title: String
    @Binding var value: String
    var unit: String? = nil
    
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.caption)
                .fontWeight(.medium)
                .foregroundStyle(.secondary)
            
            HStack {
                TextField("0", text: $value)
                    .keyboardType(.decimalPad)
                    .padding(12)
                    .background(Color(.systemGray6))
                    .cornerRadius(10)
                
                if let unit {
                    Text(unit)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }
}

/// Primary action button
struct LKButton: View {
    let title: String
    var isLoading: Bool = false
    let action: () -> Void
    
    var body: some View {
        Button(action: action) {
            Group {
                if isLoading {
                    ProgressView()
                        .tint(.white)
                } else {
                    Text(title)
                        .fontWeight(.semibold)
                }
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 14)
            .background(Color.green)
            .foregroundStyle(.white)
            .cornerRadius(12)
        }
        .disabled(isLoading)
    }
}

/// Stat card for dashboard
struct StatCard: View {
    let icon: String
    let title: String
    let subtitle: String
    let color: Color
    
    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: icon)
                .font(.title2)
                .foregroundStyle(color)
                .frame(width: 48, height: 48)
                .background(color.opacity(0.12))
                .cornerRadius(12)
            
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.subheadline)
                    .fontWeight(.semibold)
                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            
            Spacer()
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(16)
        .shadow(color: .black.opacity(0.04), radius: 8, y: 2)
    }
}

/// Empty state placeholder
struct EmptyStateView: View {
    let icon: String
    let title: String
    let message: String
    
    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: icon)
                .font(.system(size: 48))
                .foregroundStyle(.secondary)
            Text(title)
                .font(.headline)
            Text(message)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding(40)
    }
}

/// Date formatting helpers
extension String {
    static func todayISO() -> String {
        let df = DateFormatter()
        df.dateFormat = "yyyy-MM-dd"
        return df.string(from: Date())
    }
}

/// Multi-image picker using PHPickerViewController
struct ImagePickerView: UIViewControllerRepresentable {
    @Binding var images: [UIImage]
    var maxCount: Int = 3
    @Environment(\.dismiss) private var dismiss

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeUIViewController(context: Context) -> PHPickerViewController {
        var config = PHPickerConfiguration()
        config.selectionLimit = maxCount - images.count
        config.filter = .images
        let picker = PHPickerViewController(configuration: config)
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ uiViewController: PHPickerViewController, context: Context) {}

    class Coordinator: NSObject, PHPickerViewControllerDelegate {
        let parent: ImagePickerView
        init(_ parent: ImagePickerView) { self.parent = parent }

        func picker(_ picker: PHPickerViewController, didFinishPicking results: [PHPickerResult]) {
            picker.dismiss(animated: true)
            let remaining = parent.maxCount - parent.images.count
            for result in results.prefix(remaining) {
                if result.itemProvider.canLoadObject(ofClass: UIImage.self) {
                    result.itemProvider.loadObject(ofClass: UIImage.self) { [weak self] image, _ in
                        if let ui = image as? UIImage {
                            DispatchQueue.main.async { self?.parent.images.append(ui) }
                        }
                    }
                }
            }
        }
    }
}
