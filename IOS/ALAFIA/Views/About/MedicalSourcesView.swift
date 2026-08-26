import SwiftUI

/// Where ALAFIA's health information comes from.
///
/// App Review guideline 1.4.1 requires that an app presenting medical
/// recommendations, calculations or references cite its sources, and that those
/// citations be easy for the user to find. Everything listed here is a source
/// the app actually reads — the nutrient targets, the food data, the condition
/// codes and the drug names each trace to one of these. Nothing is listed for
/// appearance: if a source stops being used, it comes off this screen.
struct MedicalSourcesView: View {

    struct Source: Identifiable {
        let id = UUID()
        let title: String
        let publisher: String
        /// What in the app is derived from it — the reason it is cited.
        let usedFor: String
        let url: URL?
    }

    private let sources: [Source] = [
        Source(
            title: "KDOQI Clinical Practice Guideline for Nutrition in CKD: 2020 Update",
            publisher: "National Kidney Foundation",
            usedFor: "Protein, potassium, phosphorus and sodium targets for chronic kidney "
                   + "disease and dialysis, including the individualised protein range "
                   + "(≈1.0–1.2 g/kg/day on dialysis).",
            url: URL(string: "https://www.kidney.org/professionals/guidelines/guidelines_commentaries/nutrition-ckd")
        ),
        Source(
            title: "KDIGO Clinical Practice Guidelines",
            publisher: "Kidney Disease: Improving Global Outcomes",
            usedFor: "Staging and management context for chronic kidney disease.",
            url: URL(string: "https://kdigo.org/guidelines/")
        ),
        Source(
            title: "FoodData Central",
            publisher: "U.S. Department of Agriculture, Agricultural Research Service",
            usedFor: "Nutrient composition for foods and branded products — the calories, "
                   + "protein, potassium and phosphorus shown for a logged meal.",
            url: URL(string: "https://fdc.nal.usda.gov/")
        ),
        Source(
            title: "Dietary Reference Intakes (DRI)",
            publisher: "National Academies of Sciences, Engineering, and Medicine",
            usedFor: "Baseline daily nutrient reference values for adults without a "
                   + "condition-specific target.",
            url: URL(string: "https://www.nationalacademies.org/our-work/summary-report-of-the-dietary-reference-intakes")
        ),
        Source(
            title: "RxNorm / RxNav",
            publisher: "U.S. National Library of Medicine",
            usedFor: "Whether a medication name is a real drug, its recognised spelling, "
                   + "and the dose strengths in which it is actually supplied — used to "
                   + "flag an implausible dose before it is recorded.",
            url: URL(string: "https://www.nlm.nih.gov/research/umls/rxnorm/index.html")
        ),
        Source(
            title: "ICD-11 for Mortality and Morbidity Statistics",
            publisher: "World Health Organization",
            usedFor: "The codes and official titles for conditions on your problem list.",
            url: URL(string: "https://icd.who.int/browse11")
        ),
        Source(
            title: "Open Food Facts",
            publisher: "Open Food Facts contributors (open database)",
            usedFor: "Packaged product details where a barcode is scanned and the product "
                   + "is not in FoodData Central.",
            url: URL(string: "https://world.openfoodfacts.org/")
        ),
    ]

    var body: some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: 10) {
                    Text("ALAFIA is not a medical device and does not diagnose, treat or "
                         + "prescribe.")
                        .font(.subheadline.weight(.semibold))
                    Text("The targets, estimates and explanations in this app are derived "
                         + "from the published sources below. They are general guidance and "
                         + "cannot account for everything your own clinician knows about "
                         + "you. Always follow your care team's instructions, and speak to "
                         + "them before changing your diet, fluid intake or medication.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                .padding(.vertical, 4)
            }

            Section("Sources") {
                ForEach(sources) { source in
                    VStack(alignment: .leading, spacing: 6) {
                        Text(source.title).font(.subheadline.weight(.semibold))
                        Text(source.publisher).font(.caption).foregroundStyle(.secondary)
                        Text(source.usedFor).font(.caption)
                        if let url = source.url {
                            Link(destination: url) {
                                Label("Open source", systemImage: "arrow.up.right.square")
                                    .font(.caption)
                            }
                            .padding(.top, 2)
                        }
                    }
                    .padding(.vertical, 4)
                }
            }

            Section {
                Text("Emergencies are not handled by this app. If you think you are having "
                     + "a medical emergency, contact your local emergency number.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Sources & Citations")
        .navigationBarTitleDisplayMode(.inline)
    }
}

#Preview {
    NavigationStack { MedicalSourcesView() }
}
