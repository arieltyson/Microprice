#!/usr/bin/env Rscript
# Usage: Rscript analysis/run.R results/holdout_fills.csv results/analysis
suppressPackageStartupMessages(library(jsonlite))
args <- commandArgs(trailingOnly = TRUE)
input <- if (length(args) >= 1) args[1] else "results/holdout_fills.csv"
out <- if (length(args) >= 2) args[2] else "results/analysis"
dir.create(out, recursive = TRUE, showWarnings = FALSE)
here <- dirname(sub("--file=", "", grep("--file=", commandArgs(FALSE), value = TRUE)))
source(file.path(here, "R", "markouts.R"))

fills <- utils::read.csv(input)
curve <- markout_curve(fills)
utils::write.csv(curve, file.path(out, "markouts.csv"), row.names = FALSE)
plot_markouts(curve, file.path(out, "markouts.png"))
regressions <- lapply(split(fills, fills$variant), adverse_selection)
write_json(list(markouts = curve, adverse_selection = regressions), file.path(out, "analysis.json"),
           auto_unbox = TRUE, digits = 6, pretty = TRUE)
cat(sprintf("%-10s %5ds  %+.3f ticks/share\n", curve$variant, curve$horizon_s, curve$markout), sep = "")
