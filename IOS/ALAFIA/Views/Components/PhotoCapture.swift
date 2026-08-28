import SwiftUI
import UIKit
import PhotosUI

/// Takes a photo with the CAMERA, falling back to the library only when there
/// isn't one.
///
/// Every photo entry point in this app used `PhotosPicker`, which opens the
/// library and nothing else — behind a camera icon. A patient photographing the
/// meal in front of them, or the label on the bottle in their hand, was sent to
/// pick an old picture instead. The subject of every one of these is physically
/// present at the moment of tapping, so the camera is the right default and the
/// library is the exception.
///
/// The library is still reachable: long-press the same control. That keeps the
/// capability for "I photographed the label yesterday" without spending the
/// primary tap on it.
struct CameraPicker: UIViewControllerRepresentable {
    /// JPEG bytes, to match what every existing caller already sends upstream.
    let onCapture: (Data) -> Void
    @Environment(\.dismiss) private var dismiss

    /// A simulator has no camera. Asking for one there throws, so callers use
    /// this to decide, rather than discovering it at runtime.
    static var isAvailable: Bool {
        UIImagePickerController.isSourceTypeAvailable(.camera)
    }

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = Self.isAvailable ? .camera : .photoLibrary
        picker.cameraCaptureMode = .photo
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ picker: UIImagePickerController, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        private let parent: CameraPicker
        init(_ parent: CameraPicker) { self.parent = parent }

        func imagePickerController(
            _ picker: UIImagePickerController,
            didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]
        ) {
            let image = (info[.editedImage] as? UIImage) ?? (info[.originalImage] as? UIImage)
            // 0.8 keeps a label legible to the vision model without sending a
            // 12-megapixel original over a phone connection.
            if let data = image?.jpegData(compressionQuality: 0.8) {
                parent.onCapture(data)
            }
            parent.dismiss()
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            parent.dismiss()
        }
    }
}

/// A control that photographs something. Tap for the camera, long-press to pick
/// an existing photo.
/// `Content`, not `Label` — a generic named `Label` shadows SwiftUI's own
/// `Label` view, so `Label("…", systemImage:)` inside the body stops compiling.
struct PhotoCaptureButton<Content: View>: View {
    let onImage: (Data) -> Void
    @ViewBuilder var label: () -> Content

    @State private var showCamera = false
    @State private var libraryItem: PhotosPickerItem?
    @State private var showLibrary = false

    var body: some View {
        Button { showCamera = true } label: { label() }
            .contextMenu {
                Button {
                    showLibrary = true
                } label: {
                    Label("Choose from Library", systemImage: "photo.on.rectangle")
                }
            }
            .sheet(isPresented: $showCamera) {
                CameraPicker(onCapture: onImage).ignoresSafeArea()
            }
            .photosPicker(isPresented: $showLibrary, selection: $libraryItem, matching: .images)
            .onChange(of: libraryItem) { _, item in
                guard let item else { return }
                Task {
                    if let data = try? await item.loadTransferable(type: Data.self) {
                        onImage(data)
                    }
                    libraryItem = nil
                }
            }
    }
}
