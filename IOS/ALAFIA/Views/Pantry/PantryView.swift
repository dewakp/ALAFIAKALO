import SwiftUI

// MARK: - ViewModel

@Observable
final class PantryViewModel {
    var items: [PantryItem] = []
    var isLoading = false
    var errorMessage: String?
    var filterLocation: String? = nil

    func fetchItems() async {
        isLoading = true
        errorMessage = nil
        do {
            let all: [PantryItem] = try await APIClient.shared.get("/pantry/")
            if let loc = filterLocation {
                items = all.filter { $0.location == loc }
            } else {
                items = all
            }
            isLoading = false
        } catch {
            errorMessage = error.localizedDescription
            isLoading = false
        }
    }

    func addItem(_ item: PantryItemCreate) async -> Bool {
        do {
            let _: PantryItem = try await APIClient.shared.post("/pantry/", body: item)
            await fetchItems()
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    func deleteItem(id: Int) async {
        do {
            try await APIClient.shared.delete("/pantry/\(id)")
            items.removeAll { $0.id == id }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    var refrigeratorItems: [PantryItem] { items.filter { $0.location == "refrigerator" } }
    var freezerItems: [PantryItem] { items.filter { $0.location == "freezer" } }
    var pantryItems: [PantryItem] { items.filter { $0.location == "pantry" } }
}

// MARK: - Main View

struct PantryView: View {
    @State private var vm = PantryViewModel()
    @State private var showAdd = false

    var body: some View {
        Group {
            if vm.isLoading {
                ProgressView()
            } else if vm.items.isEmpty {
                EmptyStateView(
                    icon: "refrigerator.fill",
                    title: "Pantry Empty",
                    message: "Tap + to add items from your refrigerator, freezer, or pantry"
                )
            } else {
                List {
                    if !vm.refrigeratorItems.isEmpty {
                        Section("Refrigerator") {
                            ForEach(vm.refrigeratorItems) { item in
                                PantryItemRow(item: item)
                            }
                            .onDelete { indexSet in
                                Task {
                                    for i in indexSet {
                                        await vm.deleteItem(id: vm.refrigeratorItems[i].id)
                                    }
                                }
                            }
                        }
                    }
                    if !vm.freezerItems.isEmpty {
                        Section("Freezer") {
                            ForEach(vm.freezerItems) { item in
                                PantryItemRow(item: item)
                            }
                            .onDelete { indexSet in
                                Task {
                                    for i in indexSet {
                                        await vm.deleteItem(id: vm.freezerItems[i].id)
                                    }
                                }
                            }
                        }
                    }
                    if !vm.pantryItems.isEmpty {
                        Section("Pantry") {
                            ForEach(vm.pantryItems) { item in
                                PantryItemRow(item: item)
                            }
                            .onDelete { indexSet in
                                Task {
                                    for i in indexSet {
                                        await vm.deleteItem(id: vm.pantryItems[i].id)
                                    }
                                }
                            }
                        }
                    }

                    // Future feature note
                    Section {
                        HStack(spacing: 12) {
                            Image(systemName: "cart.fill")
                                .foregroundStyle(.secondary)
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Auto-Replenish")
                                    .font(.subheadline)
                                    .fontWeight(.semibold)
                                Text("Coming soon — connect to grocery services for automatic reordering when items run low.")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .padding(.vertical, 4)
                    }
                }
            }
        }
        .navigationTitle("Pantry & Fridge")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { showAdd = true } label: {
                    Image(systemName: "plus")
                }
            }
        }
        .sheet(isPresented: $showAdd) {
            AddPantryItemView { item in
                Task {
                    let ok = await vm.addItem(item)
                    if ok { showAdd = false }
                }
            }
        }
        .task { await vm.fetchItems() }
    }
}

// MARK: - Row

struct PantryItemRow: View {
    let item: PantryItem

    private var isExpiringSoon: Bool {
        guard let exp = item.expirationDate else { return false }
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        guard let date = formatter.date(from: exp) else { return false }
        let days = Calendar.current.dateComponents([.day], from: Date(), to: date).day ?? 999
        return days >= 0 && days <= 3
    }

    private var isExpired: Bool {
        guard let exp = item.expirationDate else { return false }
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        guard let date = formatter.date(from: exp) else { return false }
        return date < Date()
    }

    private var locationIcon: String {
        switch item.location {
        case "refrigerator": return "refrigerator.fill"
        case "freezer": return "snowflake"
        default: return "cabinet.fill"
        }
    }

    private var categoryColor: Color {
        switch item.category {
        case "produce": return .green
        case "dairy": return .blue
        case "meat", "seafood": return .red
        case "grains", "baking": return .brown
        case "frozen": return .cyan
        case "beverages": return .purple
        case "condiments", "spices": return .orange
        case "snacks": return .yellow
        default: return .gray
        }
    }

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: locationIcon)
                .foregroundStyle(categoryColor)
                .frame(width: 28)

            VStack(alignment: .leading, spacing: 2) {
                Text(item.name)
                    .fontWeight(.semibold)
                HStack(spacing: 8) {
                    Text("\(item.quantity, specifier: "%.1f") \(item.unit)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text(item.category.capitalized)
                        .font(.caption2)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(categoryColor.opacity(0.15))
                        .clipShape(Capsule())
                }
            }

            Spacer()

            if let exp = item.expirationDate {
                VStack(alignment: .trailing, spacing: 2) {
                    if isExpired {
                        Label("Expired", systemImage: "exclamationmark.triangle.fill")
                            .font(.caption2)
                            .foregroundStyle(.red)
                    } else if isExpiringSoon {
                        Label("Expiring", systemImage: "exclamationmark.triangle.fill")
                            .font(.caption2)
                            .foregroundStyle(.orange)
                    }
                    Text(exp)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }
}

// MARK: - Add Item Sheet

struct AddPantryItemView: View {
    let onSave: (PantryItemCreate) -> Void
    @Environment(\.dismiss) private var dismiss

    @State private var name = ""
    @State private var category = "other"
    @State private var quantity = "1"
    @State private var unit = "pieces"
    @State private var location = "pantry"
    @State private var expirationDate = Date()
    @State private var hasExpiration = false
    @State private var notes = ""

    private let categories = [
        "produce", "dairy", "meat", "seafood", "grains", "canned",
        "frozen", "beverages", "condiments", "snacks", "baking", "spices", "other"
    ]
    private let units = ["pieces", "lbs", "oz", "kg", "g", "liters", "ml", "cups", "gallons", "bags", "boxes", "cans", "bottles"]
    private let locations = [
        ("refrigerator", "Refrigerator", "refrigerator.fill"),
        ("freezer", "Freezer", "snowflake"),
        ("pantry", "Pantry", "cabinet.fill"),
    ]

    var body: some View {
        NavigationStack {
            Form {
                Section("Item Details") {
                    TextField("Item Name", text: $name)
                    Picker("Category", selection: $category) {
                        ForEach(categories, id: \.self) { c in
                            Text(c.capitalized).tag(c)
                        }
                    }
                }

                Section("Quantity") {
                    HStack {
                        TextField("Qty", text: $quantity)
                            .keyboardType(.decimalPad)
                            .frame(width: 80)
                        Picker("Unit", selection: $unit) {
                            ForEach(units, id: \.self) { u in
                                Text(u).tag(u)
                            }
                        }
                    }
                }

                Section("Location") {
                    Picker("Storage", selection: $location) {
                        ForEach(locations, id: \.0) { loc in
                            Label(loc.1, systemImage: loc.2).tag(loc.0)
                        }
                    }
                    .pickerStyle(.segmented)
                }

                Section("Expiration") {
                    Toggle("Has Expiration Date", isOn: $hasExpiration)
                    if hasExpiration {
                        DatePicker("Expires", selection: $expirationDate, displayedComponents: .date)
                    }
                }

                Section("Notes") {
                    TextField("Notes (optional)", text: $notes, axis: .vertical)
                        .lineLimit(2...4)
                }

                // Future feature callout
                Section {
                    HStack(spacing: 10) {
                        Image(systemName: "cart.badge.plus")
                            .foregroundStyle(.secondary)
                        VStack(alignment: .leading) {
                            Text("Auto-Replenish (Coming Soon)")
                                .font(.footnote)
                                .fontWeight(.medium)
                            Text("Connect to Instacart, Kroger, Walmart, etc. for automatic reordering.")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
            .navigationTitle("Add Pantry Item")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        let formatter = DateFormatter()
                        formatter.dateFormat = "yyyy-MM-dd"
                        let item = PantryItemCreate(
                            name: name,
                            category: category,
                            quantity: Double(quantity) ?? 1,
                            unit: unit,
                            location: location,
                            expirationDate: hasExpiration ? formatter.string(from: expirationDate) : nil,
                            notes: notes.isEmpty ? nil : notes
                        )
                        onSave(item)
                    }
                    .disabled(name.isEmpty)
                }
            }
        }
    }
}
