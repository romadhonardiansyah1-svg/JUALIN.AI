// @ts-check
const { test, expect } = require("@playwright/test");

/**
 * Real-stack evidence only. No page.route, request mocking, or provider calls.
 * The guarded Python orchestrator supplies synthetic disposable fixtures.
 */
const sellerA = process.env.E2E_SELLER_A_EMAIL;
const sellerB = process.env.E2E_SELLER_B_EMAIL;
const password = process.env.E2E_SELLER_PASSWORD;
const orderId = process.env.E2E_ORDER_ID;
const capabilityToken = process.env.E2E_CAPABILITY_TOKEN;

for (const [name, value] of Object.entries({
  E2E_SELLER_A_EMAIL: sellerA,
  E2E_SELLER_B_EMAIL: sellerB,
  E2E_SELLER_PASSWORD: password,
  E2E_ORDER_ID: orderId,
  E2E_CAPABILITY_TOKEN: capabilityToken,
})) {
  if (!value) throw new Error(`${name} is required from the disposable orchestrator`);
}

async function login(page, email) {
  await page.goto("/login");
  await page.getByPlaceholder("email@tokoku.com").fill(email);
  await page.getByPlaceholder("Masukkan password").fill(password);
  await page.getByRole("button", { name: "Masuk →" }).click();
  await expect(page).toHaveURL(/\/dashboard(?:\/|$)/);
}

function authCookieNames(cookies) {
  return cookies
    .filter((cookie) => /jualin_(access|refresh|csrf)$/.test(cookie.name))
    .map((cookie) => cookie.name);
}

test.describe("real disposable browser/backend integration", () => {
  test("real auth tenant switch clears A before B", async ({ page, context }) => {
    await login(page, sellerA);
    await expect(page.getByText("Toko E2E A", { exact: false }).first()).toBeVisible();

    const cookiesA = await context.cookies();
    const access = cookiesA.find((cookie) => cookie.name.endsWith("jualin_access"));
    const refresh = cookiesA.find((cookie) => cookie.name.endsWith("jualin_refresh"));
    const csrf = cookiesA.find((cookie) => cookie.name.endsWith("jualin_csrf"));
    expect(access?.httpOnly).toBe(true);
    expect(refresh?.httpOnly).toBe(true);
    expect(csrf?.httpOnly).toBe(false);

    await page.evaluate(async (accountA) => {
      localStorage.setItem("jualin_token", "legacy-test-token");
      localStorage.setItem("jualin_user", JSON.stringify({ email: accountA }));
      const cache = await caches.open("jualin-e2e-sensitive");
      await cache.put("/synthetic-static", new Response(accountA));
    }, sellerA);

    await page.getByTitle("Logout").click();
    await expect(page).toHaveURL(/\/login$/);
    const loggedOutProbe = await page.request.get("/api/auth/me");
    expect(loggedOutProbe.status()).toBe(401);
    expect(authCookieNames(await context.cookies())).toEqual([]);

    await login(page, sellerB);
    await page.goto("/dashboard/settings");
    await expect(page.getByDisplayValue(sellerB)).toBeVisible();
    await expect(page.getByText(sellerA, { exact: false })).toHaveCount(0);

    const legacyState = await page.evaluate(() => ({
      token: localStorage.getItem("jualin_token"),
      user: localStorage.getItem("jualin_user"),
    }));
    expect(legacyState).toEqual({ token: null, user: null });
    await expect
      .poll(async () => (await page.evaluate(() => caches.keys())).includes("jualin-e2e-sensitive"))
      .toBe(false);
  });

  test("real public capability exchange establishes an HttpOnly session", async ({ page, context }) => {
    const networkUrls = [];
    page.on("request", (request) => networkUrls.push(request.url()));

    await page.goto(`/pay/${orderId}#token=${encodeURIComponent(capabilityToken)}`);
    await expect(page.getByText("Total Pembayaran")).toBeVisible();
    await expect.poll(() => new URL(page.url()).hash).toBe("");
    await expect(page.getByRole("document")).not.toContainText(capabilityToken);
    expect(networkUrls.some((url) => url.includes(capabilityToken))).toBe(false);

    const capabilityCookie = (await context.cookies()).find(
      (cookie) => cookie.name === "payment_capability_session"
    );
    expect(capabilityCookie?.httpOnly).toBe(true);
    expect(capabilityCookie?.path).toBe(`/api/public/payments/${orderId}`);

    const status = await page.request.get(`/api/public/payments/${orderId}/status`);
    expect(status.status()).toBe(200);
    expect(status.headers()["cache-control"]).toContain("no-store");
  });

  test("real approval creates a durable dispatch", async ({ page }) => {
    await login(page, sellerA);
    await page.goto("/dashboard/recovery");
    await expect(page.getByRole("heading", { level: 1, name: "Jualin Santai" })).toBeVisible();

    await page.getByRole("button", { name: new RegExp(`ORD-${orderId}`) }).click();
    const approve = page.getByRole("button", { name: "Setujui & jadwalkan" });
    await expect(approve).toBeEnabled();
    const responsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        response.url().includes(`/api/recovery/opportunities/`) &&
        response.url().endsWith("/approve")
    );
    await approve.click();
    const response = await responsePromise;

    expect(response.status()).toBe(202);
    await expect(page.getByText("Disetujui, menunggu pemeriksaan terakhir.")).toBeVisible();
  });
});
