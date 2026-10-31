// Запуск Streamlit-сервера для предпросмотра.
// Пробрасывает порт/хост из аргументов командной строки или переменных окружения.
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");

function argValue(name) {
  const idx = process.argv.indexOf(name);
  if (idx !== -1 && process.argv[idx + 1]) return process.argv[idx + 1];
  const inline = process.argv.find((a) => a.startsWith(name + "="));
  return inline ? inline.split("=")[1] : undefined;
}

const port =
  argValue("--port") || argValue("-p") || process.env.PORT || "7100";
const host =
  argValue("--host") || process.env.HOST || "localhost";

const venvStreamlit = path.join(
  __dirname,
  ".venv",
  "Scripts",
  process.platform === "win32" ? "streamlit.exe" : "streamlit"
);
const streamlit = fs.existsSync(venvStreamlit) ? venvStreamlit : "streamlit";

const child = spawn(
  streamlit,
  [
    "run",
    "app.py",
    "--server.port",
    String(port),
    "--server.address",
    String(host),
    "--server.headless",
    "true",
  ],
  { stdio: "inherit", cwd: __dirname }
);

child.on("exit", (code) => process.exit(code ?? 0));
process.on("SIGINT", () => child.kill("SIGINT"));
process.on("SIGTERM", () => child.kill("SIGTERM"));
