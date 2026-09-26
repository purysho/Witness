// Placeholder paths in the form the current platform uses, so macOS and Linux
// users are not shown a Windows drive path. The engine expands "~".
const platform =
  typeof navigator === "undefined" ? "" : `${navigator.platform} ${navigator.userAgent}`;
const isWindows = /Win32|Win64|Windows/.test(platform);

export function examplePath(...parts: string[]): string {
  return isWindows ? `C:\\${parts.join("\\")}` : `~/${parts.join("/")}`;
}
