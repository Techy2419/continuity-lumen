// Lightweight markdown renderer -- handles what Continuity's reports
// actually use (bold, headers, bullet lists, numbered lists, inline
// code, line breaks). Not a full markdown parser, just enough to stop
// raw ** and # showing up literally in the chat.
function renderMarkdown(text) {
  let escaped = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  const lines = escaped.split("\n");
  let html = "";
  let inList = false;

  for (let line of lines) {
    const bulletMatch = line.match(/^\s*[-*]\s+(.*)/);
    const numberedMatch = line.match(/^\s*\d+\.\s+(.*)/);
    const headerMatch = line.match(/^(#{1,4})\s+(.*)/);

    if (bulletMatch || numberedMatch) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li>${inlineMarkdown(bulletMatch ? bulletMatch[1] : numberedMatch[1])}</li>`;
      continue;
    }
    if (inList) { html += "</ul>"; inList = false; }

    if (headerMatch) {
      const level = Math.min(headerMatch[1].length + 3, 6); // map to h4-h6ish
      html += `<div style="font-weight:700;margin-top:6px;">${inlineMarkdown(headerMatch[2])}</div>`;
    } else if (line.trim() === "") {
      html += "<br>";
    } else {
      html += `<div>${inlineMarkdown(line)}</div>`;
    }
  }
  if (inList) html += "</ul>";
  return html;
}

function inlineMarkdown(text) {
  return text
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`(.+?)`/g, "<code>$1</code>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>");
}
