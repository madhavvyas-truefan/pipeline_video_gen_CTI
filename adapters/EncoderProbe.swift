import AVFoundation
import Foundation

// Reports whether the installed AVFoundation stack accepts each codec for a
// QuickTime intermediate. It intentionally does not encode user media.
let temporary = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("pipeline-video-gen-probe.mov")
try? FileManager.default.removeItem(at: temporary)
let writer = try! AVAssetWriter(outputURL: temporary, fileType: .mov)
let codecs: [(String, AVVideoCodecType)] = [
  ("h264", .h264), ("hevc", .hevc), ("proRes422", .proRes422), ("proRes4444", .proRes4444)
]
var supported: [String: Bool] = [:]
for (name, codec) in codecs {
  let input = AVAssetWriterInput(mediaType: .video, outputSettings: [
    AVVideoCodecKey: codec,
    AVVideoWidthKey: 1080,
    AVVideoHeightKey: 1350
  ])
  supported[name] = writer.canAdd(input)
}
let output: [String: Any] = [
  "platform": ProcessInfo.processInfo.operatingSystemVersionString,
  "container": "mov",
  "supported": supported,
  "policy": "Choose ProRes for intermediates; require h264 or hevc for delivery."
]
let data = try! JSONSerialization.data(withJSONObject: output, options: [.prettyPrinted, .sortedKeys])
print(String(data: data, encoding: .utf8)!)
