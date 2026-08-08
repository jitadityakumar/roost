import { expect, test } from "@playwright/test";

test("health check responds ok", async ({ request }) => {
  const resp = await request.get("/api/health");
  expect(resp.ok()).toBeTruthy();
  expect(await resp.json()).toEqual({ status: "ok" });
});

test("home page shows the three entry points", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("link", { name: /add property/i })).toBeVisible();
  await expect(page.getByRole("link", { name: /active/i })).toBeVisible();
  await expect(page.getByRole("link", { name: /in.review/i })).toBeVisible();
});

test("active and in-review pages load directly via URL (client-side routing)", async ({ page }) => {
  await page.goto("/active");
  await expect(page).toHaveURL(/\/active$/);

  await page.goto("/in-review");
  await expect(page).toHaveURL(/\/in-review$/);
});

test("submitting a non-Rightmove URL shows a validation error, no scrape attempted", async ({ page }) => {
  await page.goto("/add");
  await page.getByRole("textbox").fill("https://www.zoopla.co.uk/for-sale/details/1");
  await page.getByRole("button", { name: /add/i }).click();

  await expect(page.locator(".error")).toContainText(/rightmove/i);
});
