# Start here

1. Download **global-tuna-ghg-complete.zip** from the current complete release. Do not combine older archives.
2. Extract it and open a terminal in the `global-tuna-ghg` folder.
3. Run `python restore_data.py --verify`, then `python reproduce.py verify` to check all supplied files and frozen model inputs.
4. Install Python packages from `requirements.txt` and R packages with `install_r_dependencies.R`.
5. Run `python reproduce.py figures` to render saved numerical results, or follow `REPRODUCING.md` to recalculate model stages.

Live scraping is optional. The accepted vessel registry, saved query results and stock-fit inputs are included. Model recalculation can take hours. Downloading or redrawing saved results is not a fresh scientific fit.

If using Git instead of the complete ZIP, run `python restore_data.py --download --verify` first. It retrieves the same single complete archive from the same release.
