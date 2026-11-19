"""Build the live temperature and mass trend for the reactor operator view."""

from math import ceil

import altair as alt
import pandas as pd


TREND_VIEW_MIN = 60
TREND_LEAD_MIN = 5


def trend_bounds(elapsed_min, *, full_run=False):
    """Keep the first hour fixed, then extend the right edge in five-minute steps."""
    end = max(TREND_VIEW_MIN, TREND_LEAD_MIN * ceil((elapsed_min + TREND_LEAD_MIN) / TREND_LEAD_MIN))
    return (0 if full_run else end - TREND_VIEW_MIN), end


def _visible_history(history, start_min):
    """Crop to the recent view, carrying measurements and commands to its left edge."""
    first = history["minutes"].searchsorted(start_min)
    visible = history.iloc[first:]
    if not first or visible.iloc[0]["minutes"] == start_min:
        return visible

    prior = history.iloc[first - 1]
    following = visible.iloc[0]
    weight = (start_min - prior["minutes"]) / (following["minutes"] - prior["minutes"])
    boundary = prior.to_dict()
    boundary.update(time_s=start_min * 60, minutes=start_min)
    for field in ("water_c", "outlet_c"):
        if field in history:
            boundary[field] = prior[field] + weight * (following[field] - prior[field])
    return pd.concat([pd.DataFrame([boundary]), visible], ignore_index=True)


def build_temperature_trend(data, *, show_outlet=False, full_run=False, show_mass=False):
    """Return a Vega-Lite spec with fixed dataset names for in-place live updates."""
    history = data.assign(minutes=data["time_s"] / 60)
    start, end = trend_bounds(history["minutes"].iloc[-1], full_run=full_run)
    show_target = history["reactor_target_c"].notna().any()
    history = _visible_history(history, start)
    target_active = history["reactor_target_c"].notna()

    labels = {
        "water_c": "TT-201 Water",
        "inlet_c": "TIC-201 Setpoint",
    }
    colors = ["#427cdb", "#bc7900"]
    dashes = [[1, 0], [8, 4]]
    if show_target:
        labels["reactor_target_c"] = "Reactor target"
        colors.append("#858d9f")
        dashes.append([2, 4])
    if show_outlet:
        labels["outlet_c"] = "Jacket outlet"
        colors.append("#138c7d")
        dashes.append([8, 3, 2, 3])

    legend = alt.Legend(
        orient="top", columns=2, title=None, labelLimit=180,
        labelFontSize=21, padding=2, offset=7, columnPadding=12,
    )
    domain = list(labels.values())
    x = alt.X(
        "minutes:Q", title="Simulated time (min)",
        scale=alt.Scale(domain=[start, end], zero=False, nice=False),
        axis=alt.Axis(
            tickCount=6, labelOverlap="greedy", labelFontSize=22,
            titleFontSize=23, titlePadding=7,
        ),
    )
    y = alt.Y(
        "temperature_c:Q", title="Temperature (°C)", scale=alt.Scale(zero=False),
        axis=alt.Axis(
            tickCount=4, labelFontSize=22, titleFontSize=23, titlePadding=7,
        ),
    )

    traces = []
    datasets = {"trend_samples": history}
    for field, label in labels.items():
        rows = history[["minutes", field]].rename(columns={field: "temperature_c"})
        rows = rows.assign(series=label, segment=0)
        if field == "reactor_target_c":
            # A segment ends at the command that switched Thermostat off.
            # Pad the segment to that instant before removing rows in Manual.
            was_active = target_active.shift(fill_value=False)
            segment = (target_active & ~was_active).cumsum()
            rows["segment"] = segment
            rows["temperature_c"] = rows["temperature_c"].where(
                target_active, rows["temperature_c"].shift()
            )
            rows = rows[target_active | was_active]

        rows["single_point"] = ~rows["segment"].duplicated(keep=False)
        dataset_name = f"trend_{field}"
        datasets[dataset_name] = rows
        trace = (
            alt.Chart(alt.NamedData(name=dataset_name))
            .encode(
                x=x,
                y=y,
                color=alt.Color(
                    "series:N", scale=alt.Scale(domain=domain, range=colors), legend=legend
                ),
                strokeDash=alt.StrokeDash(
                    "series:N", scale=alt.Scale(domain=domain, range=dashes), legend=legend
                ),
                detail="segment:N",
            )
        )
        traces.append(trace.mark_line(
            interpolate="step-after" if field in {"inlet_c", "reactor_target_c"} else "linear",
            strokeWidth=2 if field == "reactor_target_c" else 2.8,
        ))
        # Show a lone point at time zero or in a new thermostat segment without changing the spec.
        traces.append(
            trace.mark_point(filled=True, size=42).transform_filter(alt.datum.single_point)
        )

    # The invisible points select the nearest logged sample along the time axis.
    hover = alt.selection_point(
        name="trend_hover", fields=["minutes"], nearest=True,
        on="pointerover", clear="pointerout", empty=False,
    )
    samples = alt.Chart(alt.NamedData(name="trend_samples"))
    selectors = samples.properties(name="trend_hover_points").mark_point(opacity=0).encode(x=x).add_params(hover)
    tooltips = [
        alt.Tooltip("minutes:Q", title="Simulated time (min)", format=".2f"),
        *[
            alt.Tooltip(field, type="quantitative", title=f"{label} (°C)", format=".1f")
            for field, label in labels.items()
        ],
    ]
    if show_mass:
        tooltips.append(alt.Tooltip("batch_mass_kg:Q", title="WT-201 · Net batch mass (kg)", format=".1f"))
        if "gross_mass_kg" in history:
            tooltips.append(alt.Tooltip("gross_mass_kg:Q", title="WT-201 · Gross mass (kg)", format=".1f"))
    hover_rule = (
        samples
        .mark_rule(color="#858d9f", opacity=0.65)
        .encode(
            x=x,
            tooltip=tooltips,
        )
        .transform_filter(hover)
    )
    chart = alt.layer(*traces, selectors, hover_rule)
    if show_mass:
        mass_color = "#a673d2"
        datasets["trend_mass"] = history[["minutes", "batch_mass_kg"]].assign(
            single_point=history["batch_mass_kg"].count() == 1,
        )
        mass = alt.Chart(alt.NamedData(name="trend_mass")).encode(
            x=x,
            y=alt.Y(
                "batch_mass_kg:Q", title="Mass (kg)",
                scale=alt.Scale(domainMin=0, zero=True),
                axis=alt.Axis(
                    orient="right", grid=False, tickCount=4,
                    labelFontSize=22, titleFontSize=23, titlePadding=7,
                    labelColor=mass_color, titleColor=mass_color,
                ),
            ),
        )
        mass_trace = alt.layer(
            mass.mark_line(
                color=mass_color, strokeWidth=2.6, strokeDash=[6, 3, 2, 3], interpolate="step-after",
            ),
            mass.mark_point(color=mass_color, filled=True, size=42).transform_filter(
                alt.datum.single_point,
            ),
        )
        chart = alt.layer(chart, mass_trace).resolve_scale(y="independent")
    spec = chart.properties(
        height=240, padding={"left": 3, "right": 6, "top": 4, "bottom": 3},
    ).to_dict()
    # Streamlit updates these named tables in place while the chart window is unchanged.
    # Only a window advance or a change to the display controls needs a new spec.
    spec["datasets"] = datasets
    return spec
