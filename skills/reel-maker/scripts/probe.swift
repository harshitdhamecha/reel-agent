import AVFoundation
let a = AVURLAsset(url: URL(fileURLWithPath: CommandLine.arguments[1]))
for t in a.tracks {
  print(t.mediaType.rawValue, t.naturalSize, t.preferredTransform, t.nominalFrameRate)
}
print(CMTimeGetSeconds(a.duration))
