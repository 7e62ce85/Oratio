const imageRegex = /^https?:\/\/[^"']*\.(?:jpg|jpeg|gif|png|svg|webp)(?:\?.*)?$/i;

export default function isImage(url: string) {
  const result = imageRegex.test(url);
  // console.log("=== IS IMAGE DEBUG ===");
  // console.log("url:", url);
  // console.log("regex test result:", result);
  // console.log("====================");
  return result;
}
