/* eslint-env jest */
import { isBinaryAttachment } from "../attachments";

describe("attachment wire encoding", () => {
  test.each(["book.xlsx", "book.epub", "image.png", "image.JPG", "image.jpeg", "image.webp", "image.gif", "project.zip", "report.pdf", "text.docx", "slides.pptx"])(
    "%s preserves binary bytes as base64", (filename) => {
      expect(isBinaryAttachment(filename)).toBe(true);
    },
  );
  test.each(["index.html", "style.css", "code.tsx", "icon.svg", "README.md"])(
    "%s remains plain text", (filename) => {
      expect(isBinaryAttachment(filename)).toBe(false);
    },
  );
});
