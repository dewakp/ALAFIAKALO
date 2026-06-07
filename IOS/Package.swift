// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "ALAFIA",
    platforms: [.iOS(.v17)],
    products: [
        .library(name: "ALAFIA", targets: ["ALAFIA"])
    ],
    dependencies: [
        .package(url: "https://github.com/Alamofire/Alamofire.git", from: "5.9.0"),
        .package(url: "https://github.com/onevcat/Kingfisher.git", from: "7.10.0"),
    ],
    targets: [
        .target(
            name: "ALAFIA",
            dependencies: ["Alamofire", "Kingfisher"]
        ),
        .testTarget(
            name: "ALAFIATests",
            dependencies: ["ALAFIA"]
        )
    ]
)
