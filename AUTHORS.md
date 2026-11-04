# Authors

Authorship of the **software** is recorded here. Authorship of the article that
describes it is listed in the paper and in `CITATION.cff` under
`preferred-citation`; the two lists are related but not identical, which is
normal and deliberate.

## Copyright holders

- **Yuri Parra Castilho** — Department of Soil Science, Luiz de Queiroz College
  of Agriculture, University of São Paulo, Piracicaba, Brazil.
  <yuri.castilho@usp.br>
- **Maurício Sibulski** — Polytechnic School, Pontifical Catholic University of
  Rio Grande do Sul, Porto Alegre, Brazil.

## Contributions

| | |
|---|---|
| Yuri Parra Castilho | Conception; scientific core — scoring equations, parameter resolution, unit handling, validation, weighting and aggregation; desktop interface; test suite; verification against the original SMAF spreadsheet; packaging. |
| Maurício Sibulski | Interface design and front-end development of the earlier web version of eSMAF, from which this application's workflow descends. |

## The method

eSMAF implements a published framework; it does not originate it. SMAF was
developed by the USDA Agricultural Research Service and the Natural Resources
Conservation Service, and the scoring equations, factor tables and indicator
definitions used here come from:

- Andrews, S.S., Karlen, D.L., Cambardella, C.A. (2004). The Soil Management
  Assessment Framework. *Soil Science Society of America Journal* 68, 1945–1962.
  https://doi.org/10.2136/sssaj2004.1945
- Wienhold, B.J., Karlen, D.L., Andrews, S.S., Stott, D.E. (2009). Protocol for
  indicator scoring in the soil management assessment framework (SMAF).
  *Renewable Agriculture and Food Systems* 24, 260–266.
  https://doi.org/10.1017/S1742170509990093
- Stott, D.E., Andrews, S.S., Liebig, M.A., Wienhold, B.J., Karlen, D.L. (2010).
  Evaluation of β-glucosidase activity as a soil quality indicator for the soil
  management assessment framework. *Soil Science Society of America Journal* 74,
  107–119. https://doi.org/10.2136/sssaj2009.0029

Adaptations made for Brazilian conditions — the potassium curve after IAC
Boletim 100, the organic matter class equivalence with the Brazilian Soil
Classification System, and the added Brazilian crops and native vegetation
types — are described in the article and recorded in the calculation model
rather than written into the equations.

## Contributing

Requests to add a crop, a parameter set or a laboratory unit preset are welcome
and are best sent to the address above. Note that the licence permits
modification for noncommercial purposes but does not permit a modified version
to be distributed under the name eSMAF; see `LICENSE.md`.
