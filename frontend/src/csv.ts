// CSV para Excel en español (spec 004, decisión 3): separador ";", coma decimal y BOM UTF-8
// para que abra bien las tildes. Los números van sin separador de miles.

const BOM = String.fromCharCode(0xfeff);

/** Número que llega de la API como texto ("1200100.00"): se escribe con coma decimal. */
export class Num {
  constructor(public value: string) {}
}

export const num = (value: string | number) => new Num(String(value));

export type Cell = string | number | Num | null;

export interface Section {
  title?: string;
  head: string[];
  rows: Cell[][];
}

export function csvCell(cell: Cell): string {
  if (cell == null) return "";
  if (cell instanceof Num || typeof cell === "number") {
    return String(cell instanceof Num ? cell.value : cell).replace(".", ",");
  }
  let text = cell;
  // Un texto que empieza por = + - @ Excel lo toma como fórmula (inyección en CSV): se neutraliza.
  if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`;
  if (/[;"\n\r]/.test(text)) text = `"${text.replace(/"/g, '""')}"`;
  return text;
}

/** Varias tablas en un archivo, separadas por una línea en blanco y con su título. */
export function toCsv(sections: Section[]): string {
  const lines: string[] = [];
  sections.forEach((section, i) => {
    if (i > 0) lines.push("");
    if (section.title) lines.push(csvCell(section.title));
    for (const row of [section.head, ...section.rows]) lines.push(row.map(csvCell).join(";"));
  });
  return `${BOM}${lines.join("\r\n")}\r\n`;
}

export function downloadCsv(filename: string, content: string): void {
  const url = URL.createObjectURL(new Blob([content], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
