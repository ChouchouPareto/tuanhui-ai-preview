import Foundation
import Vision
import ImageIO

// Local macOS OCR only: no network, no model billing, no image mutation.
guard CommandLine.arguments.count == 2 else { exit(2) }
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.recognitionLanguages = ["zh-Hans", "en-US"]
request.usesLanguageCorrection = false
let handler = VNImageRequestHandler(url: URL(fileURLWithPath: CommandLine.arguments[1]), options: [:])
do {
    try handler.perform([request])
    let output: [[String: Any]] = (request.results ?? []).compactMap { result in
        guard let text = result.topCandidates(1).first else { return nil }
        let box = result.boundingBox
        return ["text": text.string, "confidence": text.confidence,
                "box": [box.origin.x, 1 - box.origin.y - box.height, box.width, box.height]]
    }
    let data = try JSONSerialization.data(withJSONObject: output)
    FileHandle.standardOutput.write(data)
} catch {
    FileHandle.standardError.write(Data("Local OCR failed".utf8))
    exit(1)
}
