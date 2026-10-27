source(file.path("..", "..", "R", "markouts.R"))

fills <- data.frame(
  variant = c("a", "a", "b"),
  side = c(1, -1, 1),
  price = c(100, 101, 100),
  qty = c(100, 300, 100),
  forecast = c(0.5, -0.5, -1),
  imbalance = c(0.2, -0.1, 0.0),
  sentiment = c(0, 0, 0.1),
  mid_after_1 = c(101, 100, 99),
  mid_after_10 = c(102, 102, 99)
)

test_that("horizons are read from column names", {
  expect_equal(horizons_of(fills), c(1L, 10L))
})

test_that("markouts are quantity weighted and signed by side", {
  curve <- markout_curve(fills)
  a1 <- curve[curve$variant == "a" & curve$horizon_s == 1, "markout"]
  expect_equal(a1, (100 * 1 + 300 * 1) / 400)
  a10 <- curve[curve$variant == "a" & curve$horizon_s == 10, "markout"]
  expect_equal(a10, (100 * 2 + 300 * -1) / 400)
  expect_equal(curve[curve$variant == "b" & curve$horizon_s == 10, "markout"], -1)
})

test_that("adverse selection regression reports every term", {
  set.seed(1)
  n <- 400
  side <- sample(c(-1, 1), n, replace = TRUE)
  forecast <- rnorm(n)
  big <- data.frame(variant = "x", side = side, price = 100, qty = 100, forecast = forecast,
                    imbalance = rnorm(n), sentiment = rnorm(n, sd = 0.1))
  big$mid_after_10 <- 100 + forecast + rnorm(n, sd = 0.1)
  fit <- adverse_selection(big)
  terms <- vapply(fit$coefficients, function(x) x$term, "")
  expect_equal(terms, c("(Intercept)", "forecast", "imbalance", "sentiment"))
  expect_gt(fit$coefficients[[2]]$estimate, 0.9)
})
