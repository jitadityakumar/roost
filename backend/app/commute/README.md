# Commute data attribution

`stations.csv` (station name/lat/lon/CRS code lookup) is copied from the
`london-commuter-stations` project, which sources it from
[`davwheat/uk-railway-stations`](https://github.com/davwheat/uk-railway-stations)
on GitHub. That dataset is licensed under the [Open Database License
(ODbL)](https://opendatacommons.org/licenses/odbl/) and requires attribution
to Trainline EU.

Static, National-Rail-only station list — used only to resolve a station
name (from Rightmove's `nearest_stations_raw`) to a CRS code before calling
the `london-commuter-stations` journey-time API. Not otherwise modified.
