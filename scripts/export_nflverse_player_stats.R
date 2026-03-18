options(nflreadr.prefer = "csv")

suppressPackageStartupMessages({
  library(nflreadr)
  library(readr)
  library(dplyr)
})

seasons <- 2015:2025
output_path <- "data/raw/nflverse_player_stats_week_2015_2025_raw.csv"

player_stats <- load_player_stats(seasons = seasons, summary_level = "week", file_type = "csv")
player_stats <- as_tibble(player_stats)

write_csv(player_stats, output_path)
cat(sprintf("Wrote %s rows to %s\n", nrow(player_stats), output_path))