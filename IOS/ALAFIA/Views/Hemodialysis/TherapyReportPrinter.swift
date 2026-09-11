import SwiftUI
import UIKit

/// Print or save a treatment report as PDF.
///
/// The document is rendered SERVER-SIDE and fetched as HTML, so the patient's
/// copy, the clinician's copy and the web copy are the same document. Three
/// templates would drift, and the one that drifted would be the one a clinician
/// was reading.
///
/// `UIMarkupTextPrintFormatter` hands the HTML to iOS's own print pipeline,
/// which gives AirPrint, "Save to Files" and "Save as PDF" for free — the
/// affordances a bundled PDF library would have taken away.
enum TherapyReportPrinter {

    /// Fetch and present the print sheet. Returns an error message on failure.
    ///
    /// `patientId` is set when a CLINICIAN is printing; the backend re-checks
    /// the sharing grant on that route, so passing an id is a destination and
    /// never an authorisation.
    @MainActor
    static func present(sessionId: Int, patientId: Int? = nil) async -> String? {
        let path = patientId.map {
            "/clinician-dashboard/patient/\($0)/therapy-sessions/\(sessionId)/report.html"
        } ?? "/chronic/therapy-sessions/\(sessionId)/report.html"

        let html: String
        do {
            html = try await APIClient.shared.getHTML(path)
        } catch {
            // Named, not swallowed. A print button that silently does nothing
            // is indistinguishable from one that is not wired at all.
            return error.localizedDescription
        }

        let info = UIPrintInfo(dictionary: nil)
        info.outputType = .general
        info.jobName = "ALAFIA Treatment Report"

        let controller = UIPrintInteractionController.shared
        controller.printInfo = info
        controller.printFormatter = UIMarkupTextPrintFormatter(markupText: html)

        return await withCheckedContinuation { continuation in
            controller.present(animated: true) { _, _, error in
                continuation.resume(returning: error?.localizedDescription)
            }
        }
    }
}
