import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import { join } from "node:path";
const require = createRequire(import.meta.url);
const modulePath = process.env.PASTPORT_PLAYWRIGHT_MODULE_ROOT;
const { chromium } = modulePath
  ? await import(pathToFileURL(join(modulePath, "playwright/index.mjs")))
  : require("playwright");
const base = process.env.PASTPORT_BROWSER_URL;
if (!base?.startsWith("http://127.0.0.1:"))
  throw new Error("A synthetic localhost browser service is required");
const token = process.env.PASTPORT_BROWSER_TOKEN;
const outsider = process.env.PASTPORT_BROWSER_OUTSIDER;
const artifacts = process.env.PASTPORT_BROWSER_ARTIFACTS;

async function waitText(locator, pattern, timeout = 12000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (pattern.test(await locator.textContent())) return;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  assert.match(await locator.textContent(), pattern);
}
async function connect(page, value = token) {
  await page.locator("#token").fill(value);
  await page.locator("#connect").click();
  await page.locator("#workspace").waitFor({ state: "visible" });
}
async function section(page, name) {
  await page.locator(`nav button[data-section="${name}"]`).click();
}
async function refresh(page, pattern, status = "waiting_review") {
  const deadline = Date.now() + 12000;
  const statusLine = page
    .locator("#runSummary p")
    .filter({ hasText: /^Status:/ });
  while (Date.now() < deadline) {
    await section(page, "overview");
    await page.locator("#refresh").click();
    await new Promise((resolve) => setTimeout(resolve, 200));
    // The worker can enter a stage before committing its stable review state.
    if (
      pattern.test(await page.locator("#runSummary").textContent()) &&
      (await statusLine.textContent()) === `Status: ${status}`
    )
      return;
  }
  assert.match(await page.locator("#runSummary").textContent(), pattern);
  assert.equal(await statusLine.textContent(), `Status: ${status}`);
}
async function approve(page) {
  await section(page, "review");
  // A stage name can appear before the worker has created its review targets.
  await page.locator("#reviews select").first().waitFor({ state: "visible" });
  const decisions = await page.locator("#reviews select").all();
  assert.ok(decisions.length > 0);
  for (const select of decisions) await select.selectOption("approved");
  for (const input of await page.locator("#reviews input").all())
    await input.fill("Explicit synthetic browser review");
  await page.locator("#saveReviews").click();
  await new Promise((resolve) => setTimeout(resolve, 150));
}

// One serial scenario preserves real workflow causality; no routes or save results are faked.
test(
  "real workflow, sources, draft play/recovery, revisions, approvals and private release",
  { timeout: 120000 },
  async () => {
    const browser = await chromium.launch({
      headless: true,
      ...(process.env.PASTPORT_CHROMIUM_EXECUTABLE
        ? { executablePath: process.env.PASTPORT_CHROMIUM_EXECUTABLE }
        : {}),
    });
    const context = await browser.newContext({
      viewport: { width: 1280, height: 950 },
    });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    try {
      await page.goto(base);
      await connect(page);
      await page.locator("#projectId").fill("browser-project");
      await page.locator("#projectName").fill("Synthetic browser chapter");
      await page.locator("#folderId").fill("browser-fixture");
      await page.locator("#createProject").click();
      await waitText(page.locator("#message"), /Saved/);
      await page.locator("#createRun").click();
      await waitText(page.locator("#runSummary"), /select_candidate/);
      await page
        .getByRole("textbox", { name: /Reason for choosing/ })
        .fill("Compare a synthetic heritage direction");
      await page.getByRole("button", { name: "Choose direction" }).click();
      await refresh(page, /evidence_review/);
      await section(page, "evidence");
      await page.locator("#claims button").first().click();
      await waitText(page.locator("#sourceContent"), /No saved original text/);
      assert.match(
        await page.locator("#sourceContent").textContent(),
        /Source hash/,
      );
      await approve(page);
      await refresh(page, /narrative_review/);
      const runId = await page.locator("#runId").inputValue();
      await section(page, "play");
      await page.locator("#newPreview").click();
      await waitText(page.locator("#playerBinding"), /TEST/);
      let previewId = await page.locator("#previewId").inputValue();
      const inspectImage = page.locator(".image-stage img");
      await inspectImage.evaluate((image) => image.decode());
      const imageBounds = await inspectImage.boundingBox();
      const hotspotBounds = await page
        .locator(".hotspot")
        .first()
        .boundingBox();
      assert.ok(imageBounds && hotspotBounds);
      assert.ok(hotspotBounds.x >= imageBounds.x);
      assert.ok(
        hotspotBounds.x + hotspotBounds.width <=
          imageBounds.x + imageBounds.width,
      );
      assert.ok(hotspotBounds.y >= imageBounds.y);
      assert.ok(
        hotspotBounds.y + hotspotBounds.height <=
          imageBounds.y + imageBounds.height,
      );
      await page.screenshot({
        path: join(artifacts, "player-inspect.png"),
        fullPage: true,
      });
      await page
        .locator("#playerContent button")
        .filter({ hasText: /Observe:/ })
        .first()
        .focus();
      await page.keyboard.press("Enter");
      await waitText(page.locator("#playerStatus"), /Saved · revision 1/);
      // Simulate a network failure only. The retry still reaches the real server with the same action.
      let dropped = false;
      await page.route("**/previews/*/actions", async (route) => {
        if (!dropped) {
          dropped = true;
          await route.fetch(); // Commit succeeds; only the response is lost.
          await route.abort("failed");
        } else await route.continue();
      });
      await page.locator('#playerContent [data-option-id="help"]').click();
      await waitText(page.locator("#playerStatus"), /result unknown/);
      await page.locator("#retryPlayer").click();
      await waitText(page.locator("#playerStatus"), /Saved · revision 2/);
      await page.unroute("**/previews/*/actions");
      assert.match(
        await page.locator("#playerContent").textContent(),
        /2 minutes/,
      );
      await page
        .getByText("Legal replay and branch comparison", { exact: true })
        .click();
      await page.locator("#replayLength").fill("1");
      await page.locator("#forkPreview").click();
      await waitText(
        page.locator("#branchDifference"),
        /Original story time: 2/,
      );
      await page.locator('#playerContent [data-option-id="hurry"]').click();
      await waitText(page.locator("#playerStatus"), /Saved · revision 2/);
      assert.match(
        await page.locator("#branchDifference").textContent(),
        /Current story time: 0/,
      );
      previewId = await page.locator("#previewId").inputValue();
      await page.locator("#gameLanguage").selectOption("zh");
      assert.match(await page.locator("#playerBinding").textContent(), /TEST/);
      await page.locator("#gameLanguage").selectOption("en");
      await page
        .locator("#playerContent button")
        .filter({ hasText: /Continue:/ })
        .click();
      await waitText(page.locator("#playerStatus"), /Saved · revision 3/);
      await page.locator("#playerContent input[type=checkbox]").check();
      await page
        .getByRole("button", { name: "Submit evidence", exact: true })
        .click();
      await waitText(page.locator("#playerStatus"), /Saved · revision 4/);
      await waitText(page.locator("#playerContent"), /Chapter complete/);
      await page.screenshot({
        path: join(artifacts, "player-desktop.png"),
        fullPage: true,
      });
      // Refresh loses the token intentionally; re-authentication restores only an explicitly named session.
      await page.reload();
      assert.equal(await page.locator("#token").inputValue(), "");
      await connect(page);
      await page.locator("#runId").fill(runId);
      await page.locator("#refresh").click();
      await waitText(page.locator("#runSummary"), /narrative_review/);
      await section(page, "play");
      await page.locator("#previewId").fill(previewId);
      await page.locator("#restorePreview").click();
      await waitText(page.locator("#playerContent"), /Chapter complete/);
      await page.locator("#newPreview").click();
      await waitText(page.locator("#playerContent"), /Observe:/);
      await section(page, "story");
      const editor = page.locator("#storyEditor textarea").first();
      await editor.locator("..").locator("..").locator("summary").click();
      const savedText = await editor.inputValue();
      await editor.fill(savedText + " Unsaved text to discard");
      await page.locator("#reloadDraft").click();
      assert.equal(await editor.inputValue(), savedText);
      await editor.fill(savedText + " Browser revision");
      await page
        .locator("#editReason")
        .fill("Clarify the synthetic introduction");
      await page.locator("#saveStory").click();
      await waitText(page.locator("#storyContent"), /edit-/);
      await page.locator("#compareChanges").click();
      await waitText(page.locator("#changeImpact"), /uncertain/);
      assert.match(
        await page.locator("#changeImpact").textContent(),
        /Browser revision/,
      );
      await section(page, "play");
      assert.equal(await page.locator("#playerBinding").textContent(), "");
      await approve(page);
      await refresh(page, /publish_review/);
      await approve(page);
      await refresh(page, /published/, "published");
      await section(page, "play");
      await page.locator("#openRelease").click();
      await waitText(page.locator("#playerBinding"), /PRIVATE RELEASE/);
      await section(page, "activity");
      assert.match(
        await page.locator("#budgetSummary").textContent(),
        /Unknown outcomes/,
      );
      await page.setViewportSize({ width: 390, height: 844 });
      await page.screenshot({
        path: join(artifacts, "workbench-mobile.png"),
        fullPage: true,
      });
      assert.equal(
        await page.evaluate(
          () => document.documentElement.scrollWidth > window.innerWidth,
        ),
        false,
      );
      assert.equal(
        await page.evaluate(() => Object.keys(localStorage).length),
        0,
      );
      await page.locator("#disconnect").click();
      assert.equal(await page.locator("#playerBinding").textContent(), "");
      await connect(page, outsider);
      await section(page, "overview");
      await page.locator("#runId").fill(runId);
      await page.locator("#refresh").click();
      await waitText(page.locator("#message"), /FORBIDDEN/);
      assert.equal(await page.locator("#playerBinding").textContent(), "");
      assert.deepEqual(errors, []);
    } catch (error) {
      await page.screenshot({
        path: join(artifacts, "failure.png"),
        fullPage: true,
      });
      console.error(
        "Visible status:",
        await page.locator("#message").textContent(),
      );
      console.error(
        "Workflow status:",
        await page.locator("#runSummary").textContent(),
      );
      throw error;
    } finally {
      await context.close();
      await browser.close();
    }
  },
);
