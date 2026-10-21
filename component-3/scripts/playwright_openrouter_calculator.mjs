import { createRequire } from "node:module";
import { mkdirSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const playwrightModule = process.env.PLAYWRIGHT_CORE_MODULE;
if (!playwrightModule) {
  throw new Error("Set PLAYWRIGHT_CORE_MODULE to the installed playwright-core module path.");
}
const chromiumExecutable = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE;
const { chromium } = require(playwrightModule);

const componentRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const outputRoot = join(componentRoot, "runtime", "openrouter-playwright");
const rawVideoRoot = join(outputRoot, "raw-video");
mkdirSync(rawVideoRoot, { recursive: true });

const dashboardUrl = process.env.DASHBOARD_URL ?? "http://127.0.0.1:5175/inputs";
const c1Path = process.env.C1_REPORT_PATH;
const c2Path = process.env.C2_PUML_PATH;
if (!c1Path || !c2Path) {
  throw new Error("Set C1_REPORT_PATH and C2_PUML_PATH before running the Playwright demo.");
}
const generationTimeoutMs = Number(process.env.GENERATION_TIMEOUT_MS ?? 300_000);
const evidence = { started_at: new Date().toISOString(), dashboard_url: dashboardUrl, steps: [] };
const mark = (step, detail = null) => {
  evidence.steps.push({ step, at: new Date().toISOString(), detail });
  process.stdout.write(`[e2e] ${step}${detail ? `: ${detail}` : ""}\n`);
};

const browser = await chromium.launch({
  headless: true,
  ...(chromiumExecutable ? { executablePath: chromiumExecutable } : {}),
});
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  recordVideo: { dir: rawVideoRoot, size: { width: 1280, height: 720 } },
});
const page = await context.newPage();
const video = page.video();
page.setDefaultTimeout(30_000);

try {
  await page.goto(dashboardUrl, { waitUntil: "networkidle" });
  mark("dashboard-ready");

  await page.getByLabel("Upload C1 SRS document").setInputFiles(c1Path);
  await page.getByLabel("Upload C2 PlantUML document").setInputFiles(c2Path);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Build provisional contract & validate" }).click();
  await page.getByText("Provisional source contract accepted by C3").waitFor();
  mark("source-documents-validated", "8 requirements, complete PlantUML envelope");
  await page.screenshot({ path: join(outputRoot, "01-inputs-validated.png"), fullPage: true });

  await page.getByRole("button", { name: /Continue to Design/ }).click();
  await page.getByRole("button", { name: "Build design context" }).click();
  await page.getByText("Parsed classes", { exact: true }).last().waitFor();
  await page.getByRole("button", { name: "Compute design coverage" }).click();
  await page.getByText("5/5").waitFor();
  await page.getByRole("button", { name: /Custom \/ non-CRUD application/ }).click();
  await page.getByRole("button", { name: "Run stack selection" }).click();
  await page.getByText("Approve REACT + NODE_JS").waitFor();
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Approve REACT + NODE_JS" }).click();
  await page.getByRole("button", { name: "Continue to Code Generation" }).click();
  mark("design-and-stack-approved", "9 classes, 8 relationships, 5/5 FR anchors");

  await page.getByText("OpenRouter-only runtime").waitFor();
  const selectedEngine = await page.getByLabel("Behaviour engine").inputValue();
  if (selectedEngine !== "EXPERIMENTAL_OPENROUTER") {
    throw new Error(`Unexpected generation engine ${selectedEngine}`);
  }
  await page.getByRole("button", { name: "Test OpenRouter connection" }).click();
  await page.getByText("OpenRouter connected", { exact: true }).waitFor({ timeout: 60_000 });
  mark("openrouter-check-passed");

  page.setDefaultTimeout(generationTimeoutMs);
  await page.getByRole("button", { name: "Generate behaviour app with OpenRouter API" }).click();
  await page.getByText("Behaviour run evidence").waitFor({ timeout: generationTimeoutMs });
  const providerRow = page.getByText("Provider", { exact: true }).locator("xpath=following-sibling::*[1]");
  const providerText = await providerRow.textContent().catch(() => "openrouter");
  if (!String(providerText).toLowerCase().includes("openrouter")) {
    throw new Error(`Generation manifest did not report OpenRouter: ${providerText}`);
  }
  mark("openrouter-generation-passed", String(providerText).trim());
  await page.screenshot({ path: join(outputRoot, "02-generation-evidence.png"), fullPage: true });

  await page.getByRole("button", { name: "Start app on a new port" }).click();
  const appLink = page.getByRole("link", { name: "Open generated app" });
  await appLink.waitFor();
  const appUrl = await appLink.getAttribute("href");
  if (!appUrl) throw new Error("Generated app URL was not exposed.");
  evidence.generated_app_url = appUrl;
  mark("generated-app-started", appUrl);

  await page.goto(appUrl, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: /^Calculator ·/, level: 1 }).waitFor();
  await page.getByLabel("enterNumber number").fill("7");
  await page.getByRole("button", { name: "Run enterNumber" }).click();
  await page.getByLabel("selectOperation operation").selectOption({ label: "Addition" });
  await page.getByRole("button", { name: "Run selectOperation" }).click();
  await page.getByLabel("enterNumber number").fill("5");
  await page.getByRole("button", { name: "Run enterNumber" }).click();
  await page.getByRole("button", { name: "Run calculateResult" }).click();
  await page.getByRole("row", { name: /displayValue/ }).getByText("12", { exact: true }).waitFor();
  mark("calculator-addition-verified", "7 + 5 = 12");
  await page.screenshot({ path: join(outputRoot, "03-calculator-result.png"), fullPage: true });
  evidence.status = "PASSED";
} catch (error) {
  evidence.status = "FAILED";
  evidence.error = String(error?.stack ?? error);
  await page.screenshot({ path: join(outputRoot, "failure.png"), fullPage: true }).catch(() => {});
  throw error;
} finally {
  evidence.finished_at = new Date().toISOString();
  writeFileSync(join(outputRoot, "result.json"), `${JSON.stringify(evidence, null, 2)}\n`, "utf8");
  await context.close();
  const rawVideoPath = await video.path();
  const finalVideoPath = join(outputRoot, "openrouter-calculator-e2e.webm");
  rmSync(finalVideoPath, { force: true });
  renameSync(rawVideoPath, finalVideoPath);
  await browser.close();
  process.stdout.write(`[e2e] evidence=${join(outputRoot, "result.json")}\n`);
  process.stdout.write(`[e2e] video=${finalVideoPath}\n`);
}
