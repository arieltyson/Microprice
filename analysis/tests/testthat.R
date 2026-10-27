library(testthat)
test_dir(file.path(dirname(sub("--file=", "", grep("--file=", commandArgs(FALSE), value = TRUE))), "testthat"),
         stop_on_failure = TRUE)
