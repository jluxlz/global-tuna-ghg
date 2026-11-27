# Software submission guide

This guide supplements the existing scientific README and REPRODUCING.md. It
provides a small offline example, tested dependencies, installation and runtime
measurements, and license terms for the Nature software submission checklist.
The scientific model files and published numerical results are unchanged.

## Software and data access

Repository: https://github.com/jluxlz/global-tuna-ghg

The scientific source snapshot used for this addition is release v2026.11.18,
commit 002d0cba0139b31fa0c08ba43ecded5608bc7bec. The local publication record
verifies the 631.2 Mt historical total and 40.3/28.2/27.8 percent median fuel
reductions associated with the submitted manuscript. This addition does not
replace the complete scientific data release or change those estimates.

The small demo below needs only this source tree and its synthetic CSV inputs.
Full scientific reproduction uses the inputs, source attributions and manifests
in the complete release. Consult its data-access terms before redistributing
third-party records. Live RFMO or GISIS queries are not needed for the demo.

## System requirements and tested versions

The offline demo was tested on 64-bit Windows 11, build 26200, using Python
3.13.0. It uses two unmodified production modules:

- `scenario/harvest_control_rules.py`: C/F/T target calculation.
- `scenario/fishery_coupling.py`: annual production, finite harvest, effort
  demand, physical capacity, realized catches and next-year biomass.

`requirements-demo.txt` pins the complete pip dependency set verified in a fresh
package directory: NumPy 2.3.1, pandas 2.2.3, python-dateutil 4.0.0, pytz 2026.6
and tzdata 2026.6. An additional test used the existing research environment,
whose date/time dependencies differ; both passed the expected-output check.
The exact verification environment and source/input checksums are in
`software_submission/environment.json` and `software_submission/verification.json`.

No R installation, JAGS, GPU, browser, database account, third-party vessel
microdata, or network connection is required to RUN the installed demo. Internet
access may be needed to install its dependencies. Tests ran on a machine with
approximately 32 GiB RAM; this is the test-machine specification, not a minimum
memory requirement. Linux and macOS were not tested in this task.

The full scientific workflow additionally uses R 4.5.2 for figures and the
Python/R dependencies in the existing `requirements.txt` and
`install_r_dependencies.R`. Stock refitting additionally requires JAGS and JABBA.
The current R library inventory includes JABBA 2.3.7 (upstream commit
c62db86c99dc5b5a0e115fd53fdd40f7c882b7c9), R2jags 0.8-9, rjags 4-17,
ggplot2 4.0.2, sf 1.1-0 and dplyr 1.2.0. A JAGS-4.3.2 installation directory
is present, but JAGS was not runtime-tested in this task. R package versions were
read from installed DESCRIPTION files, not inferred from unpinned install commands.
The full inventory is preserved in `software_submission/environment.json`.
Do not interpret this current inventory as a reconstruction of every historical
execution environment.

Live GISIS collection is separate. The retained Edge WebDriver is
148.0.3967.96; the original Selenium package and Edge browser versions were not
recorded. Current installed Selenium versions are not historical evidence.

## Installation guide

Install Python 3.13, then open a terminal at the repository root. A standard
virtual environment is recommended:

```powershell
python -m venv .venv-demo
.\.venv-demo\Scripts\python.exe -m pip install --only-binary=:all: --no-compile -r requirements-demo.txt
.\.venv-demo\Scripts\python.exe demo/run_demo.py
```

The recorded isolation test used a fresh pip target and disabled automatic
site-package loading, so existing research packages could not satisfy missing
dependencies. To repeat that exact method from the repository root:

```powershell
python -m pip install --only-binary=:all: --no-compile --target .demo-packages -r requirements-demo.txt
python -I -S -c "import sys,runpy; sys.path.insert(0,'.demo-packages'); runpy.run_path('demo/run_demo.py',run_name='__main__')"
```

Use a new/empty target directory for a fresh installation. Do not copy these
packages into the research environment. The first command is not needed again
for repeated demo runs.

Measured dependency installation took **6.84 seconds** into a fresh directory
with pip's wheel cache already populated, with Python preinstalled. It excludes
installing Python, R/JAGS, downloading the full scientific data and compiling
bytecode (`--no-compile`). Uncached network installation takes longer and depends
on connectivity. Full optional-environment installation was not timed here.
See `software_submission/verification.json` for the exact measurement scope.

For the full workflow, use a separate environment and the existing release's
dependency installers and REPRODUCING.md. R/JAGS are unnecessary for this demo.

## Demo inputs and procedure

Run `demo/run_demo.py` from any working directory. By default it reads:

- `demo/input/stocks.csv`: two fictitious stocks, with r in year^-1 and
  carrying capacity, beginning-of-2024 biomass and 2024 catch in Mt.
- `demo/input/fleet.csv`: two fictitious vessels, with installed power in kW,
  reference annual days and accounting weights.
- `demo/input/allocation.csv`: stock-specific allocation shares over organization
  and gear; shares sum to one for each stock.

The example runs C, F and T separately over 2025-2030, with fixed fleet capacity,
a 280-day bound, 1 percent annual catchability increase and a neutral fuel-cost
response. T uses trigger/closure proxies of 0.4/0.1 of K. It uses no random
sampling, so no random seed is necessary. Annual removals update stock biomass.
The production modules are imported directly rather than copied or reimplemented.

Outputs are written only to `demo/output/` by default. Supply `--output <folder>`
to choose another location. Production results are not overwritten. Supply
`--input <folder>` to use other CSVs with the same schemas. The expected-summary
comparison and the hand-calculated first-year checks are intentionally skipped
for custom inputs. Conservation, quota and physical-capacity checks still run.
Other datasets must retain the documented units, schema and assumptions. This
small example is not a general-purpose stock-assessment tool.

## Expected output and runtime

The console reports PASS. Files are:

| File | Expected contents |
| --- | --- |
| `stocks.csv` | 36 stock-year-rule records, with biomass, growth, target and realized catch |
| `effort.csv` | 36 organization-gear-year-rule records, with requested, realized and capacity kW-days |
| `summary.csv` | Three rows; cumulative realized catch and minimum beginning-year B/BMSY |
| `verification.json` | Checks, input/model hashes, environment versions and runtime |

For the supplied data, cumulative realized catch (Mt) is approximately
0.505640704510 for C, 0.505608935377 for F and 0.506624279305 for T. All three
have minimum beginning-year B/BMSY of 0.498. Reference values are preserved in
`demo/expected/summary.csv` and compared within floating-point tolerances.
The first-year DEMO_A biomass is independently checked at 0.249 Mt; its C/F/T
targets are checked at 0.1/0.0498/0.024734 Mt. Checks also cover biomass balance,
quota and capacity ceilings, closure, and equivalence of untriggered T and F.
The reference summary is a saved computational reference, not independent
biological validation.

Three repeat runs in the existing environment took **1.20-1.21 seconds** each,
including interpreter startup. The first run with a freshly installed isolated
dependency directory took **13.35 seconds**. Allow approximately **1-15 seconds**
on the tested machine, with slower first imports possible. Installation and data
download are excluded. This example is a deterministic mechanism demonstration,
not a new empirical result, full fleet simulation or reconstruction of the paper's
GHG inventory. No GHG results or figures are produced by this small example.

## Full scientific use

The existing complete-release instructions remain in REPRODUCING.md. Obtain its
documented source inputs and verify the retained inputs before recalculation.
The historical inventory uses `GHG_Calculation/ghg_lca.py`; the projected fleet
interface is `scenario/fleet_model.py`. Current HCR experiment drivers are under
`analysis/hcr_revision_20261020/`. Stock refits and full scenario runs can take
hours. Their run time is distinct from the short demo time above.

The existing release's `reproduce.py` and manifest verification support saved
inputs and current output locations. Do not use outdated model entry names from
older workspace documentation, and do not run production entry points merely to
try the demo. This addition has not rerun the 500-draw inventory or 1,944-scenario
ensemble. Its two imported scientific modules were byte-identical to the
v2026.11.18 source snapshot before and after testing.

## License and reporting

Author-developed code and its software documentation are released under the
MIT License; see LICENSE. Third-party code, artwork and source datasets retain
their original terms; see THIRD_PARTY_NOTICES.md. Synthetic demo CSVs contain no
real vessel identities and are supplied under the MIT terms with the demo.

`software_submission/CHECKLIST_GUIDE.txt` maps the supplied materials to the
Nature checklist. Check an item only after these additions are included in the
repository or submitted package that reviewers can actually access. No unfamiliar
colleague installation test is claimed. A repository link does not by itself
prove that the latest local files have been uploaded.
