const videoRegex = /^https?:\/\/[^"']*\.(?:mp4|webm)(?:\?.*)?$/i;

export default function isVideo(url: string) {
  const result = videoRegex.test(url);
  // console.log("=== IS VIDEO DEBUG ===");
  // console.log("url:", url);
  // console.log("regex test result:", result);
  // console.log("====================");
  return result;
}
