/** Wire format shared with the backend's binary document/image decoders. */
const BINARY_EXTENSIONS = new Set([
  "zip", "docx", "pdf", "pptx", "xlsx", "epub", "png", "jpg", "jpeg", "webp", "gif",
]);

export function isBinaryAttachment(filename: string): boolean {
  const extension = filename.slice(filename.lastIndexOf(".") + 1).toLowerCase();
  return BINARY_EXTENSIONS.has(extension);
}
