import type { Asset } from "./types";

export const libraryActions = [
  { id: "normalize", label: "Нормализация", movesMedia: true },
  { id: "quarantine", label: "Карантина", movesMedia: true },
  { id: "delete", label: "Изтриване", movesMedia: true },
  { id: "subtitles", label: "Субтитри / версии", movesMedia: false },
  { id: "identity", label: "Идентификация / колекция", movesMedia: false },
] as const;
export type LibraryAction = (typeof libraryActions)[number]["id"];

// UI hints only. Absence of a recorded dependency never grants write permission;
// the server still analyzes the exact plan and enforces every existing gate.
export function actionUnavailable(
  action: (typeof libraryActions)[number],
  asset: Asset & { availability?: string },
  busy: boolean,
): string | undefined {
  if (busy) return "Изчакайте текущата заявка.";
  if (!action.movesMedia) return;
  if (asset.data.dependencies?.length)
    return "Torrent зависимост блокира тази операция.";
  if (asset.availability !== "AVAILABLE")
    return "Файлът не е наличен в библиотеката. Обследвайте я отново.";
}
