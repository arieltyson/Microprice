# Markout and adverse-selection analysis of strategy fills.
#
# Input columns: variant, side (+1 bought, -1 sold), price, qty, forecast,
# imbalance, sentiment and mid_after_<h> for each horizon h in seconds.

markout_columns <- function(fills) {
  grep("^mid_after_[0-9]+$", names(fills), value = TRUE)
}

horizons_of <- function(fills) {
  as.integer(sub("mid_after_", "", markout_columns(fills)))
}

# Quantity-weighted average move in our favour, in ticks per share, by variant and horizon.
markout_curve <- function(fills) {
  rows <- list()
  for (variant in sort(unique(fills$variant))) {
    f <- fills[fills$variant == variant, ]
    for (column in markout_columns(f)) {
      move <- f$side * (f[[column]] - f$price)
      ok <- is.finite(move)
      rows[[length(rows) + 1]] <- data.frame(
        variant = variant,
        horizon_s = as.integer(sub("mid_after_", "", column)),
        markout = stats::weighted.mean(move[ok], f$qty[ok]),
        fills = sum(ok)
      )
    }
  }
  out <- do.call(rbind, rows)
  out[order(out$variant, out$horizon_s), ]
}

# Regresses the 10-second markout on each signal, signed in the direction of the
# fill. A positive coefficient means fills that agree with the signal do better;
# a negative intercept is the adverse selection left after the signals.
adverse_selection <- function(fills, horizon = 10L) {
  column <- paste0("mid_after_", horizon)
  d <- data.frame(
    markout = fills$side * (fills[[column]] - fills$price),
    forecast = fills$side * fills$forecast,
    imbalance = fills$side * fills$imbalance,
    sentiment = fills$side * fills$sentiment,
    qty = fills$qty
  )
  d <- d[stats::complete.cases(d), ]
  model <- stats::lm(markout ~ forecast + imbalance + sentiment, data = d, weights = qty)
  s <- summary(model)$coefficients
  list(
    horizon_s = horizon,
    n = nrow(d),
    r_squared = summary(model)$r.squared,
    coefficients = lapply(seq_len(nrow(s)), function(i) {
      list(term = rownames(s)[i], estimate = unname(s[i, 1]), std_error = unname(s[i, 2]),
           t_value = unname(s[i, 3]), p_value = unname(s[i, 4]))
    })
  )
}

plot_markouts <- function(curve, path) {
  grDevices::png(path, width = 900, height = 520, res = 120)
  on.exit(grDevices::dev.off())
  variants <- unique(curve$variant)
  styles <- seq_along(variants)
  graphics::plot(range(curve$horizon_s), range(c(0, curve$markout)), type = "n", log = "x",
                 xlab = "Seconds after fill", ylab = "Markout (ticks per share)",
                 main = "Post-fill mid-price move in the strategy's favour")
  graphics::abline(h = 0, col = "grey60")
  for (i in seq_along(variants)) {
    v <- curve[curve$variant == variants[i], ]
    graphics::lines(v$horizon_s, v$markout, lty = styles[i], lwd = 2)
    graphics::points(v$horizon_s, v$markout, pch = 14 + i)
  }
  graphics::legend("bottomleft", legend = variants, lty = styles, pch = 14 + seq_along(variants), lwd = 2, bty = "n")
}
