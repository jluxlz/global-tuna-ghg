# Global tuna-fishery greenhouse gas emissions

Scientific models, frozen inputs and outputs for **Harvest control rules shape the emission benefits of fuel transition in global tuna fisheries**.

**[Download the complete code and data package](https://github.com/jluxlz/global-tuna-ghg/releases/latest).** Extract the single ZIP, install the dependencies, then run:

```sh
python restore_data.py --verify
python reproduce.py verify
python reproduce.py figures
```

The November fuel revision uses vessel-class operating days, engine hours and loads. The historical inventory covers 1950–2025. Its paired sensitivity compares results with and without direct refrigerant leakage and across specified R22 GWP100 values. Saved scenarios include 1,944 primary C/F/T simulations, 1,620 full sensitivity reruns, 486 Indian Ocean bigeye runs and 27 matched-catch rule comparisons. Only the earlier comparisons explicitly used as supplementary evidence retain their original assumptions.

The ZIP includes supplied vessel inputs; live scraping is optional. It includes data and R renderers for all 35 quantitative figures, excluding the two conceptual Extended Data diagrams. Manuscripts, editorial files and superseded output copies are not distributed. See [REPRODUCING.md](REPRODUCING.md) for instructions and [the source inventory](data/source_inputs.csv) for attribution. Third-party terms apply.
