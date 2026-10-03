"""Discriminate legacy custom DMI formulas without claiming historical origin."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pyne_runtime as pn

ROOT = Path(__file__).resolve().parents[1]
NAME = "legacy_dmi_wrapper_discriminator"
CASES = (("advanced", "ta_advanced_indicators", 3, 3),
         ("trend", "ta_trend_switch_indicators", 4, 3),
         ("tuple", "ta_tuple_outputs_indicators", 5, 4))
SOURCE_SHA = "c6c5997559cb2f2a245cddf2a2dac11e8e8bb8670623b7b04f8d919add3d0066"


def build_diagnostic(root=ROOT):
    spec = importlib.util.spec_from_file_location("legacy_dmi_reporter", root / "scripts/official_alignment_report.py")
    reporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reporter)
    folder = root / "tests/workloads"
    capture = json.loads((folder / (NAME + ".tradingview.json")).read_text(encoding="utf-8"))
    reporter.verify_evidence(folder, NAME, capture)
    titles = [f"{title} {field}" for title, _, _, _ in CASES for field in
              ("high", "low", "close", "oldPlus", "oldMinus", "oldADX", "strictPlus", "strictMinus", "strictADX")]
    if (capture.get("scriptSha256") != SOURCE_SHA or capture.get("columns") != titles
            or len(capture["rows"]) != 24 or capture.get("diagnosticOnly") is not True
            or capture.get("missingValueToken") != "NA" or capture.get("tolerance") != 1e-7
            or capture.get("sourceExpressionClass") != "legacy_custom_dmi_discriminator"):
        raise ValueError("Incomplete or incorrectly qualified native legacy DMI discrimination")
    columns = {title: [row["values"][n] for row in capture["rows"]] for n, title in enumerate(titles)}
    cases = []
    reproduced = 0
    for title, fixture_name, period, adx_period in CASES:
        fixture = json.loads((root / "tests/golden" / (fixture_name + ".json")).read_text(encoding="utf-8"))
        legacy = fixture["external_capture"]
        bars = legacy["bars"]
        expected_selection = dict(title=title, fixture=fixture_name, rows=len(bars), period=period,
            adxPeriod=adx_period, inputBarsSha256=hashlib.sha256(
                json.dumps(bars, sort_keys=True, separators=(",", ":")).encode()).hexdigest())
        if expected_selection not in capture.get("selection", []):
            raise ValueError("Legacy DMI source selection identity differs")
        for field in ("high", "low", "close"):
            values = [bar[field] for bar in bars] + [None] * (24 - len(bars))
            if columns[title + " " + field] != values:
                raise ValueError("Native custom DMI source differs from supplied legacy OHLCV")
        script = f'''indicator("Strict DMI wrapper control")
p,m,a=ta.dmi({period},{adx_period})
plot(p,"Plus")
plot(m,"Minus")
plot(a,"ADX")
plot(p-m,"Spread")
'''
        runtime = pn.run(script, bars, executor_mode="inline")
        if not runtime.ok:
            raise ValueError("Strict DMI source control failed")
        values = {line["name"]: {p["time"]:p["value"] for p in line["data"]} for line in runtime.lines}
        indices = {bar["time"]:i for i, bar in enumerate(bars)}
        results = []
        differences = 0
        for plot, points in legacy["series"].items():
            if not (plot.startswith("Plus DI") or plot.startswith("Minus DI") or plot.startswith("DI Spread")):
                continue
            field = "Plus" if plot.startswith("Plus") else "Minus" if plot.startswith("Minus") else "Spread"
            old = columns[title + " old" + field] if field != "Spread" else [
                None if a is None or b is None else a-b
                for a,b in zip(columns[title + " oldPlus"], columns[title + " oldMinus"], strict=True)]
            strict = columns[title + " strict" + field] if field != "Spread" else [
                None if a is None or b is None else a-b
                for a,b in zip(columns[title + " strictPlus"], columns[title + " strictMinus"], strict=True)]
            affected = []
            for index, point in enumerate(points):
                position = indices[point["time"]]
                if old[position] != point["value"]:
                    raise ValueError("Native legacy wrapper does not exactly reproduce an imported DI value")
                reproduced += 1
                strict_value = strict[position]
                runtime_value = values[field].get(point["time"])
                if strict_value is None or runtime_value is None or abs(strict_value-runtime_value) > 1e-7:
                    raise ValueError("Strict native wrapper differs from current source computation")
                if abs(strict_value-point["value"]) > legacy.get("tolerance", 1e-7):
                    affected.append(index)
            differences += len(affected)
            annotations = [item for item in legacy.get("known_differences", [])
                           if item.get("plot") == plot and item.get("classification") == "legacy_custom_formula_reference"]
            if len(annotations) != len(affected):
                raise ValueError("Legacy DMI annotation population differs from exact native witnesses")
            for index in affected:
                point = points[index]
                witness = dict(fixture=fixture_name, plot=plot, originalPointIndex=index,
                    nativeLegacyValue=point["value"], historicalOriginProved=False)
                observed = dict(time=point["time"], value=values[field][point["time"]])
                matched = [item for item in annotations if item.get("tradingview") == point
                           and item.get("pyne") == observed and item.get("wrapperWitness") == witness
                           and item.get("reason") and NAME in item.get("evidence", "")]
                if len(matched) != 1:
                    raise ValueError("Disclosed legacy DMI discrepancy lacks its exact native witness")
            results.append(dict(plot=plot, importedPointsExactlyReproduced=len(points),
                                strictFormulaDifferentPointIndices=affected))
        cases.append(dict(fixture=fixture_name, rows=len(bars), results=results,
                          rawFormulaDifferences=differences))
    if reproduced != 115 or sum(case["rawFormulaDifferences"] for case in cases) != 111:
        raise ValueError("Legacy custom DMI discrepancy population changed")
    return dict(schema="pyne.native-legacy-dmi-wrapper-diagnostic/1", cases=cases,
        nativeControlledRows=24, nativeControlledOutputCells=432, sourceInputCellsVerified=216,
        importedDiPointsExactlyReproduced=115, strictFormulaDifferentPoints=111,
        currentRuntimeMatchesStrictNativeControl=True, historicalCaptureOriginProved=False,
        countedAsAdditionalRuntimeAgreement=False, acceptanceProved=False,
        qualification="The explicitly evaluated old formula exactly reproduces 115 imported DI values; the strict formula differs at 111 points and matches current supplied-data computation. Original historical provenance remains unverified. These custom formulas do not qualify native built-in DMI or add runtime parity cells; independent initial monthly/weekly built-in captures provide separate evidence.")
