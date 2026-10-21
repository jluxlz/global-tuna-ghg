# Fig. 1 artwork

The figure renderer reads the author's existing artwork rather than exporting
replacement assets over it. The manually edited `Fig1.png` remains read-only.

Panel c uses the supplied NOAA-labelled PNGs in `Icon/`, matching the five
species labels. The supplied Bluefin illustration is a schematic bluefin icon
for SBT, not a species-identification image or an observation. Artwork size is
fixed; bubble area alone encodes CEI. Transparent margins are cropped in memory.

Panel d uses the author's five PDFs in `RFMO_Icons/`. These are coloured RFMO
boundary silhouettes. Their aspect ratios are preserved. Poppler renders copies
to `Icon_Render_Cache/` for embedding; the original PDFs are never overwritten.
The organisation abbreviations and gear colour legend remain explicit.

Implementation: `Fig1_Icon_Assets.r`, called by `Fig1_Multi_Dimensional.r`.
The data behind the bubbles, bars and uncertainty whiskers are unchanged.
