import XCTest
@testable import ALAFIA

final class OfflineCacheTests: XCTestCase {

    private var cache: OfflineCache!

    override func setUp() {
        super.setUp()
        cache = OfflineCache.shared
        cache.clear()
    }

    override func tearDown() {
        cache.clear()
        super.tearDown()
    }

    func testStoreAndLoadRoundTrip() {
        let items = ["apple", "banana", "cherry"]
        cache.store(items, for: "/test/fruits")

        let loaded: [String]? = cache.load(for: "/test/fruits")
        XCTAssertEqual(loaded, items)
    }

    func testLoadReturnNilForMissingKey() {
        let result: [String]? = cache.load(for: "/nonexistent/path")
        XCTAssertNil(result)
    }

    func testRemoveDeletesCachedEntry() {
        cache.store(["data"], for: "/test/remove")
        cache.remove(for: "/test/remove")

        let result: [String]? = cache.load(for: "/test/remove")
        XCTAssertNil(result)
    }

    func testClearRemovesAllEntries() {
        cache.store(["a"], for: "/test/one")
        cache.store(["b"], for: "/test/two")
        cache.clear()

        let one: [String]? = cache.load(for: "/test/one")
        let two: [String]? = cache.load(for: "/test/two")
        XCTAssertNil(one)
        XCTAssertNil(two)
    }

    func testOverwriteExistingKey() {
        cache.store(["old"], for: "/test/overwrite")
        cache.store(["new"], for: "/test/overwrite")

        let result: [String]? = cache.load(for: "/test/overwrite")
        XCTAssertEqual(result, ["new"])
    }

    func testPathSanitization() {
        // Paths with special characters should still work
        cache.store(42, for: "/api/v1/labs?user_id=1&page=2")
        let result: Int? = cache.load(for: "/api/v1/labs?user_id=1&page=2")
        XCTAssertEqual(result, 42)
    }
}
